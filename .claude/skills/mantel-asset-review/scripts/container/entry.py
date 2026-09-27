"""The one program the review sandbox runs: an allow-listed command over the staged files.

Invoked by `sandbox.py` as `python -I -B /toolchain/review/entry.py <command> [file]` with no
network, a read-only root, and only these read-only mounts:

  /toolchain/site     the hash-locked dependencies of the format (pip --target, prepared once)
  /toolchain/format   the pinned public `mantel_format` source, tools and release environment
  /toolchain/review   this directory
  /reference          the public publisher registry and catalog (trusted reference data)
  /submission         the staged archive, intake and issue text, or a pull request's
                      head tarball and selection (untrusted data)

Output is JSON on stdout; the runner on the host writes files. Nothing here runs, imports or
evaluates anything from /submission.
"""

from __future__ import annotations

import io
import json
import platform
import re
import resource
import runpy
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path[:0] = ["/toolchain/review", "/toolchain/format/src", "/toolchain/site"]

import palette  # noqa: E402
import report  # noqa: E402
import review_checks  # noqa: E402
from mantel_format.authoring import read_source, unpack  # noqa: E402
from mantel_format.cli import main as author  # noqa: E402

COMMANDS = (
    "validate",
    "inspect",
    "unpack",
    "build",
    "rebuild",
    "review",
    "conformance",
    "calibrate",
    "probe",
)
SUBMISSION = Path("/submission")
REFERENCE = Path("/reference")
FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def staged(name: str) -> Path:
    if not FILE_NAME.fullmatch(name):
        raise SystemExit("A staged file name is letters, digits, dots, dashes and underscores")
    return SUBMISSION / name


def trusted_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def environment() -> dict:
    """The runner's facts plus what this interpreter can see of the pinned release runtime."""
    facts = trusted_json(SUBMISSION / "environment.json")
    check = io.StringIO()
    argv = sys.argv
    try:
        sys.argv = ["release_environment.py", "--check"]
        with redirect_stdout(check):
            code = runpy.run_path("/toolchain/format/tools/release_environment.py")["main"]()
    finally:
        sys.argv = argv
    facts["release_environment"] = "matches" if code == 0 else "DIFFERS"
    facts["python"] = platform.python_version()
    version = re.search(
        r'^version = "([^"]+)"',
        Path("/toolchain/format/pyproject.toml").read_text(),
        re.MULTILINE,
    )
    facts["format_version"] = version.group(1) if version else "?"
    return facts


def reference() -> dict:
    override = REFERENCE / "registry.json"
    return review_checks.reference_from(REFERENCE, override if override.is_file() else None)


def review_one(path: Path, intake: dict, facts: dict, issue: str | None, notes: list) -> dict:
    evidence = review_checks.review(path, intake, reference(), issue)
    if notes:
        evidence = report.with_notes(evidence, notes)
    evidence["draft"] = report.draft_evidence(evidence)
    return {
        "evidence": evidence,
        "report": report.render(evidence, facts),
        "record": report.draft_record(evidence),
    }


def inert(value: object, budget: list[int] | None = None) -> object:
    """Submission-derived JSON made safe to show a reviewer: every string neutralised and
    bounded (`review_checks.neutral`), lists capped, at most 400 strings in all."""
    budget = [400] if budget is None else budget
    if isinstance(value, str):
        budget[0] -= 1
        return review_checks.neutral(value) if budget[0] >= 0 else "…"
    if isinstance(value, list):
        return [inert(item, budget) for item in value[:100]]
    if isinstance(value, dict):
        return {
            review_checks.neutral(k, 60): inert(v, budget) for k, v in list(value.items())[:100]
        }
    return value


def main(argv: list[str]) -> int:
    # Belt and braces beside the container's limits: CPU seconds.
    resource.setrlimit(resource.RLIMIT_CPU, (300, 300))
    if not argv or argv[0] not in COMMANDS:
        print(json.dumps({"error": f"not an allowed command; allowed: {', '.join(COMMANDS)}"}))
        return 2
    command, rest = argv[0], argv[1:]
    if command in ("validate", "inspect"):
        output = io.StringIO()
        with redirect_stdout(output):
            code = author(
                [command, "--json", str(staged(rest[0]))]
                if command == "validate"
                else [command, str(staged(rest[0]))]
            )
        print(json.dumps(inert(json.loads(output.getvalue() or "null")), ensure_ascii=False))
        return code
    if command == "unpack":
        with tempfile.TemporaryDirectory(dir="/tmp") as temp:
            source = unpack(staged(rest[0]), Path(temp) / "unpacked")
            files = sorted(
                str(path.relative_to(source.parent))
                for path in source.parent.rglob("*")
                if path.is_file()
            )
            print(
                json.dumps(
                    inert({"files": files, "source": json.loads(source.read_text())}),
                    ensure_ascii=False,
                )
            )
        return 0
    if command == "build":
        if rest:
            # The pull-request route (`intake --pr`): the head tarball's changed asset sources,
            # taken out and built here with the published toolchain, one JSON line per result.
            import pull_request

            selection = json.loads(staged(rest[1]).read_text(encoding="utf-8"))
            try:
                for line in pull_request.build_head(
                    staged(rest[0]),
                    selection,
                    REFERENCE,
                    Path("/tmp/sources"),  # noqa: S108
                ):
                    print(json.dumps(line, ensure_ascii=False), flush=True)
            except pull_request.Refused as error:
                print(json.dumps({"refused": str(error)}, ensure_ascii=False))
                return 1
            return 0
        # One staged source folder: its archive's hash and size.
        _, _, data = read_source(SUBMISSION / "source" / "source.json")
        print(json.dumps({"sha256": review_checks.sha256(data), "size": len(data)}))
        return 0
    if command == "rebuild":
        with tempfile.TemporaryDirectory(dir="/tmp") as temp:
            data = staged(rest[0]).read_bytes()
            result = review_checks.unpack_and_rebuild(staged(rest[0]), Path(temp), data)
        print(json.dumps(result))
        return 0 if result["status"] != "failed" else 1
    if command == "calibrate":
        catalog = review_checks.catalog_looks(reference())
        extra = trusted_json(REFERENCE / "extra-looks.json")
        rows = palette.pairwise({**catalog, **extra})
        shipped = palette.pairwise(catalog)
        print(
            json.dumps(
                {
                    "threshold": palette.THRESHOLD,
                    "catalog_minimum": shipped[0] if shipped else None,
                    "pairs": rows,
                }
            )
        )
        return 0
    if command == "probe":
        import probe

        settings = trusted_json(SUBMISSION / "probe.json")
        print(
            json.dumps(
                probe.probes(
                    settings["host_home"],
                    settings["repo"],
                    settings["canary"],
                    settings.get("connect", []),
                )
            )
        )
        return 0
    facts = environment()
    notes = trusted_json(SUBMISSION / "notes.json").get("findings", [])
    intake = trusted_json(SUBMISSION / "intake.json")
    issue_path = SUBMISSION / "issue.md"
    issue = (
        issue_path.read_text(encoding="utf-8", errors="replace") if issue_path.is_file() else None
    )
    if command == "review":
        print(
            json.dumps(
                review_one(staged(intake["archive"]), intake, facts, issue, notes),
                ensure_ascii=False,
            )
        )
        return 0
    results = []
    for path in sorted((SUBMISSION / "archives").glob("*.mantelpack")):
        results.append({"case": path.stem, **review_one(path, intake, facts, None, [])})
    print(json.dumps(results, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
