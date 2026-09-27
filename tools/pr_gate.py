"""The pull-request gate (D19, D20): who may change what, read from git objects only.

    python -I tools/pr_gate.py --repo . --base-sha BASE --head-sha HEAD --author-id N

It never checks the head out and never runs anything from it: the changed paths come from
`git diff` between the merge base and the head commit, and every file it reads is a blob
(`git show`, `git ls-tree`). So it sees exactly what the pull request commits -- including files
under names `.gitignore` hides -- and nothing a build left in a working tree.

**Where it is authoritative.** `tools/merge_pr.py`, which the owner runs from an up-to-date
`main` to merge, runs *main's* copy of this gate (and of `check.py` and `rebuild.py`) over the
exported head, then merges only that exact head commit. That is the gate. The `gate` job in
`.github/workflows/check.yml` runs the base commit's copy too, installs nothing and runs no head
code, but a `pull_request` workflow comes from the pull request itself, which can edit or drop
the job: its result is an early, advisory signal, never a reason to merge.

Rules, against the **base** registry (a pull request cannot grant itself authority):

- From anyone: no path with a `__pycache__` segment, a `.pyc`/`.pyo`/`.pth` suffix, or under
  `.review/`, and no tracked file the base's `.gitignore` excludes.
- A maintainer (an account of the `mantel` handle) may change anything else.
- Everyone else changes only asset sources -- a `definitions/catalog.json` entry, a pack's own
  `packs/<slug>/` folder and its `packs/catalog.json` line, `publishers.json` -- and only under a
  handle registered to their account, or a first-time handle they register to their own id.
- Never from a non-maintainer: `reviews.json` (decisions are the owner's), a `distribution`
  (what Mantel ships is the owner's), adding an account to a handle (a transfer), removing or
  renaming another account of a handle, or anything outside the asset sources (tools, workflows,
  the format, the skill, pack previews, collections, starters, policies).
"""

import argparse
import json
import subprocess
import sys

SEMANTIC_PATHS = ("definitions/catalog.json", "packs/catalog.json", "publishers.json", "reviews.json")
FORBIDDEN_PARTS = ("__pycache__",)
FORBIDDEN_SUFFIXES = (".pyc", ".pyo", ".pth")
FORBIDDEN_PREFIXES = (".review/",)
MAINTAINERS = "mantel"


class Refused(Exception):
    """The gate refused, with a sentence that says why."""


class Git:
    """Read-only access to one repository's objects."""

    def __init__(self, repo):
        self.repo = str(repo)

    def run(self, *args, data=None):
        result = subprocess.run(
            ["git", "-C", self.repo, *args], input=data, capture_output=True, check=False
        )
        if result.returncode != 0:
            raise Refused(f"git {args[0]} failed: {result.stderr.decode(errors='replace').strip()}")
        return result.stdout

    def show(self, sha, path, default):
        exists = subprocess.run(
            ["git", "-C", self.repo, "cat-file", "-e", f"{sha}:{path}"], capture_output=True, check=False
        )
        if exists.returncode != 0:
            return default
        return json.loads(self.run("show", f"{sha}:{path}"))

    def tree(self, sha, prefix):
        """{path: blob id} for every file under `prefix` at `sha`."""
        found = {}
        for line in self.run("ls-tree", "-r", "-z", sha, "--", prefix).split(b"\0"):
            if line:
                meta, path = line.split(b"\t", 1)
                found[path.decode()] = meta.split()[2].decode()
        return found


def handle_of(package_id):
    return str(package_id).split("/", 1)[0]


def definitions(git, sha):
    """(id, version) -> the entry without its distribution; and (id, version) -> distribution."""
    entries = git.show(sha, "definitions/catalog.json", [])
    releases = {
        (e["id"], e["version"]): json.dumps({k: v for k, v in e.items() if k != "distribution"}, sort_keys=True)
        for e in entries
    }
    return releases, {(e["id"], e["version"]): e.get("distribution") for e in entries}


def packs(git, sha):
    """slug -> (id, version, the folder's blob ids)."""
    found = {}
    folders = {}
    for path, blob in git.tree(sha, "packs").items():
        parts = path.split("/")
        if len(parts) > 2:
            folders.setdefault(parts[1], {})[path] = blob
    for slug, files in folders.items():
        source = f"packs/{slug}/source.json"
        if source in files:
            item = git.show(sha, source, {})
            found[slug] = (item.get("id"), item.get("version"), json.dumps(files, sort_keys=True))
    return found


def placed(git, sha):
    return {e["slug"]: e.get("distribution") for e in git.show(sha, "packs/catalog.json", [])}


def records(git, sha):
    return {
        (r["id"], r["version"]): json.dumps(r, sort_keys=True)
        for r in git.show(sha, "reviews.json", {"records": []})["records"]
    }


def registry(git, sha):
    return {e["handle"]: e for e in git.show(sha, "publishers.json", {"publishers": []})["publishers"]}


def changed(before, after):
    return {key for key in set(before) | set(after) if before.get(key) != after.get(key)}


def forbidden(path):
    parts = path.split("/")
    return (
        any(part in FORBIDDEN_PARTS for part in parts)
        or path.endswith(FORBIDDEN_SUFFIXES)
        or path.startswith(FORBIDDEN_PREFIXES)
    )


def ignored(git, paths):
    """Paths the checked-out base's `.gitignore` rules exclude: a tracked file never may match
    one (git would hide it from every status and diff a person reads)."""
    if not paths:
        return []
    result = subprocess.run(
        ["git", "-C", git.repo, "-c", "core.excludesFile=/dev/null", "check-ignore", "--no-index",
         "--stdin", "-z"],
        input="\0".join(paths).encode(), capture_output=True, check=False,
    )  # fmt: skip
    return sorted(filter(None, result.stdout.decode().split("\0")))


def owner_changes(registry_base, registry_head, author_id):
    """Refused edits to handles the author holds: transfers, and other accounts' removal."""
    for handle, before in registry_base.items():
        after = registry_head.get(handle)
        if after is None or after == before or author_id not in before["github_account_ids"]:
            continue
        added = set(after["github_account_ids"]) - set(before["github_account_ids"])
        if added:
            raise Refused(f"Adding accounts to {handle} is a transfer: a maintainer's change.")
        removed = set(before["github_account_ids"]) - set(after["github_account_ids"]) - {author_id}
        if removed:
            raise Refused(f"Removing another account from {handle} is a transfer: a maintainer's change.")
        logins_before = dict(zip(before["github_account_ids"], before["github_logins"], strict=False))
        logins_after = dict(zip(after["github_account_ids"], after["github_logins"], strict=False))
        if any(logins_before.get(i) != login for i, login in logins_after.items() if i != author_id):
            raise Refused(f"Only an account's own pull request changes its login under {handle}.")


def gate(repo, base_sha, head_sha, author_id):
    """The handles and paths this pull request changes, or Refused. Returns a summary line."""
    if type(author_id) is not int or author_id <= 0:
        raise Refused("The pull request author's numeric account id is missing.")
    git = Git(repo)
    base = git.run("rev-parse", "--verify", f"{base_sha}^{{commit}}").decode().strip()
    head = git.run("rev-parse", "--verify", f"{head_sha}^{{commit}}").decode().strip()
    fork = git.run("merge-base", base, head).decode().strip()
    paths = [p for p in git.run("diff", "--name-only", "--no-renames", "-z", fork, head).decode().split("\0") if p]
    hidden = sorted(p for p in paths if forbidden(p))
    if hidden:
        raise Refused("Compiled, path or review files are never committed: " + ", ".join(hidden[:10]))
    excluded = ignored(git, [p for p in git.run("ls-tree", "-r", "--name-only", "-z", head).decode().split("\0") if p])
    if excluded:
        raise Refused("Tracked files that .gitignore excludes: " + ", ".join(excluded[:10]))
    authority = registry(git, base)
    maintainers = set(authority.get(MAINTAINERS, {}).get("github_account_ids", []))
    if author_id in maintainers:
        return f"Author {author_id} (maintainer) may change {len(paths)} files."
    # Everyone else: only asset sources, under handles they hold.
    before_packs, after_packs = packs(git, fork), packs(git, head)
    owners = {slug: handle_of(value[0]) for slug, value in {**before_packs, **after_packs}.items()}
    privileged = []
    for path in paths:
        parts = path.split("/")
        if path in SEMANTIC_PATHS:
            continue
        if not (len(parts) > 2 and parts[0] == "packs" and parts[1] in owners):
            privileged.append(path)
    if "reviews.json" in paths and changed(records(git, fork), records(git, head)):
        privileged.append("reviews.json (review records are the owner's)")
    before_definitions, before_placed = definitions(git, fork)
    after_definitions, after_placed = definitions(git, head)
    for key in set(before_placed) & set(after_placed):
        if before_placed[key] != after_placed[key]:
            privileged.append(f"definitions/catalog.json ({key[0]} {key[1]} distribution)")
    for key in set(after_placed) - set(before_placed):
        if after_placed[key] != "library":
            privileged.append(f"definitions/catalog.json ({key[0]} {key[1]} distribution)")
    placed_before, placed_after = placed(git, fork), placed(git, head)
    for slug in changed(placed_before, placed_after):
        if placed_before.get(slug) is not None and placed_after.get(slug) is not None:
            privileged.append(f"packs/catalog.json ({slug} distribution)")
        elif placed_after.get(slug, "library") != "library":
            privileged.append(f"packs/catalog.json ({slug} distribution)")
        elif slug not in owners:
            privileged.append(f"packs/catalog.json ({slug})")
    if privileged:
        raise Refused(
            "Only a maintainer changes these: " + ", ".join(sorted(privileged)[:10])
            + (" ..." if len(privileged) > 10 else "")
        )
    handles = {handle_of(key[0]) for key in changed(before_definitions, after_definitions)}
    handles |= {owners[slug] for slug in changed(before_packs, after_packs)}
    handles |= {owners[slug] for slug in changed(placed_before, placed_after) if slug in owners}
    head_registry = registry(git, head)
    handles |= changed(
        {h: json.dumps(e, sort_keys=True) for h, e in authority.items()},
        {h: json.dumps(e, sort_keys=True) for h, e in head_registry.items()},
    )
    owner_changes(authority, head_registry, author_id)
    for handle in sorted(handles):
        if handle in authority:
            if author_id not in authority[handle]["github_account_ids"]:
                raise Refused(
                    f"The author (account {author_id}) is not registered to {handle}; only its "
                    "accounts or a maintainer change its assets or registry entry."
                )
            continue
        entry = head_registry.get(handle)
        if entry is None:
            raise Refused(f"{handle} is not registered; register it in the same pull request.")
        if entry["github_account_ids"] != [author_id]:
            raise Refused(
                f"A first-time handle ({handle}) is registered to its author's own account id "
                f"({author_id}) only."
            )
    return (
        f"Author {author_id} (publisher) may change {len(paths)} files"
        + (f" under the handles {', '.join(sorted(handles))}." if handles else ".")
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--author-id", required=True)
    args = parser.parse_args(argv)
    try:
        author = int(args.author_id) if args.author_id.isdigit() else None
        print(gate(args.repo, args.base_sha, args.head_sha, author))
    except Refused as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
