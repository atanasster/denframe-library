"""The owner's merge command: the gate that decides what reaches `main` (D19, D20, D24).

    python3 tools/merge_pr.py 42            # check, then merge pull request 42
    python3 tools/merge_pr.py 42 --dry-run  # check only

A `pull_request` workflow comes from the pull request itself, so its checks are advisory: a
pull request can edit or drop them. This command is the control. Run it from a clean, up-to-date
`main` clone of atanasster/mantel-library; it

1. reads the pull request's author, head commit and base with fixed read-only `gh` calls, and the
   author's numeric account id with `gh api users/<login>` (GitHub's metadata, never the pull
   request's content);
2. fetches `pull/<n>/head` and requires it to be exactly that commit;
3. runs *main's* `tools/pr_gate.py` with `python -I` over the git objects, and refuses outright,
   for anyone but a maintainer, a change under `.github/`, `tools/`, `format/`, `.claude/`, to
   `reviews.json` or to any `distribution`;
4. exports the head commit with `git archive` into a temporary directory -- never checking it
   out, never importing, installing or running anything from it -- and runs main's
   `tools/check.py --root` and `tools/rebuild.py --root` over the export in the pinned release
   image (`format/release-environment.json`, main's format installed from main's tree). A
   maintainer's pull request that changes `tools/` or `format/` itself -- a format release, say,
   whose new fixtures main's validator cannot know -- is checked with its own toolchain instead:
   that code is the maintainer's, and main's gate above has already been applied to it;
5. only then runs `gh pr merge <n> --squash --match-head-commit <sha>`, so a push after the
   checks cannot slip in.
"""

import argparse
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "atanasster/mantel-library"
# Refused outright for anyone but a maintainer, whatever the gate says (defence in depth).
OWNER_ONLY_PREFIXES = (".github/", "tools/", "format/", ".claude/")
OWNER_ONLY_FILES = ("reviews.json",)


class Refused(Exception):
    """The merge refused, with a sentence that says why."""


def run(command, *, cwd=ROOT, data=None):
    result = subprocess.run(command, cwd=cwd, input=data, capture_output=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip().splitlines()[-1:] or ["failed"]
        raise Refused(f"{' '.join(map(str, command[:3]))} failed: {detail[0]}")
    return result.stdout


def text(command, **options):
    return run(command, **options).decode().strip()


def pull_request(number, gh=text):
    """(author login, numeric author id, head sha, base branch) from GitHub's metadata."""
    view = json.loads(
        gh(["gh", "pr", "view", str(number), "--repo", REPOSITORY, "--json",
            "author,headRefOid,baseRefName,state"])
    )  # fmt: skip
    if view.get("state") != "OPEN" or view.get("baseRefName") != "main":
        raise Refused(f"Pull request {number} is not an open pull request into main.")
    login = view["author"]["login"]
    account = gh(["gh", "api", f"users/{login}", "--jq", ".id"])
    if not account.isdigit():
        raise Refused(f"GitHub gave no numeric account id for {login}.")
    return login, int(account), view["headRefOid"], view["baseRefName"]


def up_to_date_main(git=text):
    """This clone is `main`, clean, and at origin's `main`: its tools are main's."""
    if git(["git", "rev-parse", "--abbrev-ref", "HEAD"]) != "main":
        raise Refused("Run the merge from the main branch.")
    if git(["git", "status", "--porcelain", "--untracked-files=no"]):
        raise Refused("The main clone has uncommitted changes.")
    git(["git", "fetch", "--quiet", "origin", "main"])
    head, origin = git(["git", "rev-parse", "HEAD"]), git(["git", "rev-parse", "origin/main"])
    if head != origin:
        raise Refused("This clone is not at origin/main; pull first.")
    return head


def maintainers(root=ROOT):
    """main's `mantel` handle accounts: the only authors whose pull requests carry policy."""
    registry = json.loads((root / "publishers.json").read_text(encoding="utf-8"))
    for entry in registry["publishers"]:
        if entry["handle"] == "mantel":
            return set(entry["github_account_ids"])
    return set()


def owner_only(base, head, repo=ROOT):
    """Paths and distribution changes only a maintainer's pull request may carry."""
    fork = text(["git", "merge-base", base, head], cwd=repo)
    names = text(["git", "diff", "--name-only", "--no-renames", fork, head], cwd=repo).splitlines()
    found = [
        name for name in names if name.startswith(OWNER_ONLY_PREFIXES) or name in OWNER_ONLY_FILES
    ]

    def distributions(sha, path, key):
        shown = subprocess.run(
            ["git", "-C", str(repo), "show", f"{sha}:{path}"], capture_output=True, check=False
        )
        entries = json.loads(shown.stdout) if shown.returncode == 0 else []
        return {entry[key]: entry.get("distribution") for entry in entries}

    for path, key in (("definitions/catalog.json", "id"), ("packs/catalog.json", "slug")):
        before, after = distributions(fork, path, key), distributions(head, path, key)
        found += [
            f"{path} ({name} distribution)"
            for name, value in after.items()
            if before.get(name, "library") != value
        ]
    return found


def export(head, destination, repo=ROOT):
    """The head commit's files as data: `git archive`, extracted with tarfile's `data` filter
    (no links out, no devices, no permissions beyond files). Nothing is run."""
    archive = run(["git", "archive", "--format=tar", head], cwd=repo)
    with tempfile.TemporaryFile() as stream:
        stream.write(archive)
        stream.seek(0)
        with tarfile.open(fileobj=stream) as tar:
            tar.extractall(destination, filter="data")
    return destination


def checks_in_image(exported, runner=run, root=ROOT, *, toolchain="/main"):
    """check.py and rebuild.py over the exported head, in the pinned release image. The tools and
    format come from `toolchain`: main's tree, or `/head` for a maintainer's own toolchain change.
    The head is mounted read-only as data."""
    if toolchain not in ("/main", "/head"):
        raise ValueError("The toolchain is main's or the head's")
    environment = json.loads((root / "format/release-environment.json").read_text())
    script = (
        "set -e; python -m pip install -q --root-user-action=ignore --require-hashes "
        f"-r {toolchain}/format/requirements.lock; cp -r {toolchain}/format /tmp/format; "
        "python -m pip install -q --root-user-action=ignore --no-deps /tmp/format; "
        f"python -I {toolchain}/tools/check.py --root /head; "
        f"python -I {toolchain}/tools/rebuild.py --root /head"
    )
    return runner(
        ["docker", "run", "--rm", "--platform", environment["platform"],
         "--mount", f"type=bind,source={root},target=/main,readonly",
         "--mount", f"type=bind,source={exported},target=/head,readonly",
         environment["image"], "sh", "-c", script]
    )  # fmt: skip


def merge(number, *, dry_run=False, root=ROOT, gh=text, git=None, runner=run):
    """Check pull request `number` with main's tools and merge exactly its head, or refuse."""
    git = git or (lambda command: text(command, cwd=root))
    base = up_to_date_main(git)
    login, author, head, _ = pull_request(number, gh)
    git(["git", "fetch", "--quiet", "origin", f"pull/{number}/head"])
    if git(["git", "rev-parse", "FETCH_HEAD"]) != head:
        raise Refused("The fetched head is not the commit GitHub reports; try again.")
    found = owner_only(base, head, repo=root)
    if author not in maintainers(root) and found:
        raise Refused(f"{login} may not change: " + ", ".join(found[:10]))
    # Only a maintainer reaches here with a toolchain change; theirs checks the head.
    toolchain = "/head" if any(path.startswith(("tools/", "format/")) for path in found) else "/main"
    gate = subprocess.run(
        [sys.executable, "-I", str(root / "tools/pr_gate.py"), "--repo", str(root),
         "--base-sha", base, "--head-sha", head, "--author-id", str(author)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    if gate.returncode != 0:
        raise Refused(gate.stderr.strip().removeprefix("Refused: "))
    lines = [gate.stdout.strip()]
    with tempfile.TemporaryDirectory(prefix="mantel-merge-") as temporary:
        exported = export(head, Path(temporary) / "head", repo=root)
        lines.append(runner_output(checks_in_image(exported, runner, root, toolchain=toolchain)))
    if toolchain == "/head":
        lines.insert(1, "Checked with the pull request's own toolchain (a maintainer's change).")
    if dry_run:
        lines.append(f"Dry run: pull request {number} at {head[:12]} would merge.")
        return lines
    gh(["gh", "pr", "merge", str(number), "--repo", REPOSITORY, "--squash",
        "--match-head-commit", head])  # fmt: skip
    lines.append(f"Merged pull request {number} at {head[:12]} (author {login}, {author}).")
    return lines


def runner_output(result):
    return result.decode().strip() if isinstance(result, bytes) else str(result).strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("number", type=int)
    parser.add_argument("--dry-run", action="store_true", help="check only; never merge")
    args = parser.parse_args(argv)
    try:
        print("\n".join(merge(args.number, dry_run=args.dry_run)))
    except Refused as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
