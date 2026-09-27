"""The review session's policy: where a review may run and which tool calls a reviewer may make.

One module, read by three enforcers:

- `sandbox.py` refuses to run outside a clean public checkout (`checkout_problems`);
- `guard.py`, the PreToolUse hook in the skill's and the reviewer agent's frontmatter, denies
  any tool call `decide` refuses, before it runs;
- `grade.py tools` replays a transcript through `decide`, so an eval fails on the same calls.

Standard library only: it runs on the host, in hooks, before anything else is trusted.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SKILL = SCRIPTS.parent
ROOT = SKILL.parents[2]
RUNNER = ".claude/skills/mantel-asset-review/scripts/sandbox.py"
GRADER = ".claude/skills/mantel-asset-review/scripts/grade.py"
INTERPRETERS = frozenset({"python3"})
# Review output: `.review/` in the checkout (git-ignored) and the skill's eval results.
WORK = ROOT / ".review"
RESULTS = SKILL / "evals/results"
# What a reviewer reads of a review: the runner's own output, never a submission's bytes.
READABLE_NAMES = frozenset(
    {
        "report.md",
        "evidence.json",
        "record.json",
        "notes.json",
        "probe.txt",
        "grading.txt",
        "calibration.json",
        "conformance-results.json",
        "tool-log.jsonl",
    }
)
READABLE_DOCS = (SKILL / "SKILL.md", SKILL / "references", SKILL / "agents")
# Tools that neither read files nor run anything.
PASSTHROUGH = frozenset({"Skill", "TodoWrite"})
MARKER = re.compile(r"echo MANTEL-REVIEW-EVAL-(?:START|END)-[A-Za-z0-9-]+")
# Shell syntax that could run a second program, read a file into an argument or write one.
SHELL_SYNTAX = set("$`;&|<>(){}*?[]~\\!#'\"\n\r\t")
REMOTE = re.compile(
    r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"atanasster/mantel-library(?:\.git)?/?"
)
KEY_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx"})
# The runner's network-facing and pull-request commands, word for word: `intake --issue <n>
# --out <dir>`, `intake --pr <n> --out <dir>`, `build <dir>` and `build --intake <dir>`, with
# <n> plain digits (what `sandbox.py`'s `github_number` accepts) and nothing else; before any
# command, at most one `--log <file>` (the runner's parsers take no abbreviations).
GITHUB_NUMBER = re.compile(r"[1-9][0-9]{0,8}")


def _git(root: Path, *arguments: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def checkout_problems(root: Path = ROOT, cwd: Path | None = None) -> list[str]:
    """Why `root` is not a place to review submissions (empty when it is).

    A review runs only in its own clone of the public atanasster/mantel-library repository:
    never in the private host repository, never in a tree that holds signing keys, and never
    in a clone of anything else.
    """
    problems = []
    root = root.resolve()
    top = _git(root, "rev-parse", "--show-toplevel")
    if top is None:
        return [f"{root} is not a git checkout; review from a fresh clone of the public repo"]
    if Path(top.strip()).resolve() != root:
        problems.append(
            f"the skill sits inside {top.strip()}, not at the root of a public-repo clone"
        )
    remotes = {line.split()[1] for line in (_git(root, "remote", "-v") or "").splitlines()}
    if not remotes:
        problems.append("the checkout has no remote; clone atanasster/mantel-library")
    problems += [
        f"remote {remote} is not atanasster/mantel-library"
        for remote in sorted(remotes)
        if not REMOTE.fullmatch(remote)
    ]
    if (root / "backend/.mantel-runtime").exists() or (root / "backend").is_dir():
        problems.append("this is the private host repository (backend/ is present)")
    keys = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.suffix.lower() in KEY_SUFFIXES and ".git" not in path.relative_to(root).parts
    )
    if keys:
        problems.append("key files in the checkout: " + ", ".join(keys[:5]))
    if cwd is not None and not cwd.resolve().is_relative_to(root):
        problems.append(f"the working directory {cwd} is outside the checkout")
    return problems


def _inside(path: Path, *roots: Path) -> bool:
    return any(path.is_relative_to(root.resolve()) for root in roots)


def bash(command: str, cwd: Path | None = None) -> str | None:
    """Why a Bash command is refused, or None when it is an exact runner or grader call."""
    text = command.strip()
    base = cwd.resolve() if cwd else None
    prefix = re.fullmatch(r"cd (\S+) && (.+)", text, re.DOTALL)
    if prefix:
        target = Path(prefix.group(1))
        if not target.is_absolute() or target.resolve() != ROOT.resolve():
            return "only `cd <checkout root> && ...` is allowed"
        base, text = ROOT.resolve(), prefix.group(2).strip()
    if MARKER.fullmatch(text):
        return None
    if SHELL_SYNTAX & set(text):
        return "shell syntax (substitution, redirection, chaining, globs, quotes) is refused"
    if base != ROOT.resolve():
        return "run from the checkout root (or `cd <checkout root> && ...`)"
    words = text.split(" ")
    if "" in words or len(words) < 2:
        return "one program with space-separated arguments"
    if words[0] not in INTERPRETERS or words[1] not in (RUNNER, GRADER):
        return f"only `python3 {RUNNER}` or `python3 {GRADER}` may run"
    if words[1] == RUNNER:
        refused = _runner_form(words[2:])
        if refused:
            return refused
    for argument in words[2:]:
        if "/" not in argument and not argument.startswith("."):
            continue
        path = (ROOT / argument).resolve()
        if not _inside(path, ROOT) or ".git" in path.relative_to(ROOT.resolve()).parts:
            return f"a path outside the checkout: {argument}"
    return None


def _runner_form(arguments: list[str]) -> str | None:
    """Why a runner call's arguments are not allowed: at most one leading `--log <file>`, then a
    command word (no other leading option, spelled any way), and `intake` and `build` only in
    their exact forms."""
    if arguments[:1] == ["--log"]:
        if len(arguments) < 2 or arguments[1].startswith("-"):
            return "only `--log <file>` before the command"
        arguments = arguments[2:]
    if not arguments or arguments[0].startswith("-"):
        return "one `--log <file>` at most, then the command"
    if arguments[0] not in ("intake", "build"):
        return None
    rest = arguments[1:]
    if arguments[0] == "intake":
        exact = (
            len(rest) == 4
            and rest[0] in ("--issue", "--pr")
            and GITHUB_NUMBER.fullmatch(rest[1]) is not None
            and rest[2] == "--out"
            and not rest[3].startswith("-")
        )
        return None if exact else "only `intake --issue|--pr <n> --out <dir>`, n plain digits"
    exact = (len(rest) == 1 and not rest[0].startswith("-")) or (
        len(rest) == 2 and rest[0] == "--intake" and not rest[1].startswith("-")
    )
    return None if exact else "only `build <dir>` or `build --intake <dir>`"


def read(path: Path) -> str | None:
    path = path.resolve()
    if any(path == doc.resolve() or path.is_relative_to(doc.resolve()) for doc in READABLE_DOCS):
        return None
    if path.name in READABLE_NAMES and _inside(path, WORK, RESULTS) and "intake" not in path.parts:
        return None
    return "a reviewer reads only the skill's documents and the runner's output files"


def write(path: Path) -> str | None:
    path = path.resolve()
    if path.name == "notes.json" and _inside(path, WORK, RESULTS) and "intake" not in path.parts:
        return None
    return "a reviewer writes only notes.json in the review's output folder"


def decide(tool: str, data: dict, cwd: Path | None = None) -> str | None:
    """Why a tool call is refused during a review, or None when it is allowed."""
    if tool in PASSTHROUGH:
        return None
    if tool == "Bash":
        return bash(str(data.get("command", "")), cwd)
    if tool == "Read":
        return read(Path(str(data.get("file_path", ""))))
    if tool in ("Write", "Edit", "MultiEdit"):
        return write(Path(str(data.get("file_path", ""))))
    return f"the tool {tool} is not part of a review"
