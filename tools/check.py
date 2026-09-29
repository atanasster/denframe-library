"""Validate public sources, mirror integrity, the publisher registry and the shared standalone
conformance corpus."""
import hashlib
import json
import re
import argparse
import runpy
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from library_sources import (  # noqa: E402
    DISTRIBUTIONS,
    check_entry,
    definition_archive,
    handle_of,
    maintainer_logins,
    plain_text,
    publishers_by_handle,
    read_registry,
    registry_problems,
    reviewed_source,
    sha256,
)
from denframe_format.authoring import read_source  # noqa: E402
from denframe_format.elements import Definition  # noqa: E402
from denframe_format.reviews import read_ledger, require_review  # noqa: E402
from denframe_format.validation import inspect_archive  # noqa: E402

TOOLS = Path(__file__).resolve().parent
# The tree checked: this checkout, or `--root` (the owner's merge command checks an exported
# pull-request head with main's own tools; nothing in that tree is imported or run).
ROOT = TOOLS.parent
# Never committed, from anyone: compiled Python and path hooks run without their source.
FORBIDDEN_NAMES = re.compile(r"(^|/)(__pycache__/|\.review/)|\.(pyc|pyo|pth)$")
# Source kinds whose sources need an account or a key. A market block is a watchlist, and its
# quotes come from the Stocks source, which needs a provider key: nothing included reads one.
ACCOUNT_BOUND_KINDS = frozenset({"market"})


def distribution(entry, where):
    value = entry.get("distribution")
    if value not in DISTRIBUTIONS:
        raise ValueError(f"{where}: distribution must be one of {', '.join(DISTRIBUTIONS)}")
    return value


def account_bound(definition):
    """The account- or key-bound source kinds a definition reads, sorted."""
    kinds = {block.kind for block in definition.blocks} | {
        slot.kind for slot in definition.source_slots
    }
    return sorted(kinds & ACCOUNT_BOUND_KINDS)


def check_included(item, definition):
    """What a new household gets without an account (D5): account-free sources only. The
    approved review is `require_review`'s, and the preview budget is the host build's, since
    the definition previews are rendered there."""
    bound = account_bound(definition)
    if bound:
        raise ValueError(f"{item['id']}: included items must not need an account ({', '.join(bound)})")


# Collections (`definitions/collections.json`): curated groups the online library lists in order.
COLLECTION_ID = re.compile(r"[a-z][a-z0-9-]{0,39}")
COLLECTION_FIELDS = {"id", "title", "description", "items"}
MAX_COLLECTIONS = 32
COLLECTION_ITEMS = (2, 24)


def check_collections(known):
    """Each collection: a unique id, a title, one sentence, and 2-24 distinct catalogued ids
    (`known`: every id `definitions/catalog.json` and `packs/catalog.json` list), in order."""
    document = json.loads((ROOT / "definitions/collections.json").read_text())
    if set(document) != {"schema_version", "collections"} or document["schema_version"] != 1:
        raise ValueError("definitions/collections.json must be {schema_version: 1, collections: [...]}")
    collections = document["collections"]
    if not isinstance(collections, list) or not 0 < len(collections) <= MAX_COLLECTIONS:
        raise ValueError(f"definitions/collections.json: 1 to {MAX_COLLECTIONS} collections")
    seen = set()
    for collection in collections:
        if not isinstance(collection, dict) or set(collection) != COLLECTION_FIELDS:
            raise ValueError(f"definitions/collections.json: each collection has exactly {sorted(COLLECTION_FIELDS)}")
        ident = collection["id"]
        if not isinstance(ident, str) or not COLLECTION_ID.fullmatch(ident) or ident in seen:
            raise ValueError(f"definitions/collections.json: invalid or repeated id {ident!r}")
        seen.add(ident)
        plain_text(collection["title"], 60, f"collection {ident} title")
        plain_text(collection["description"], 200, f"collection {ident} description")
        items = collection["items"]
        low, high = COLLECTION_ITEMS
        if not isinstance(items, list) or not low <= len(items) <= high or len(set(items)) != len(items):
            raise ValueError(f"collection {ident}: {low} to {high} distinct items")
        unknown = sorted(item for item in items if item not in known)
        if unknown:
            raise ValueError(f"collection {ident} names items the catalogs don't list: {', '.join(map(str, unknown))}")
    return len(collections)


def pack_catalog():
    """`packs/catalog.json`: each listed activity source's slug and distribution, once."""
    entries = json.loads((ROOT / "packs/catalog.json").read_text())
    listed = {}
    for entry in entries:
        slug = entry.get("slug")
        if not isinstance(slug, str) or not slug.replace("-", "").isalnum() or slug in listed:
            raise ValueError(f"packs/catalog.json: invalid or repeated slug {slug!r}")
        if set(entry) != {"slug", "distribution"}:
            raise ValueError(f"packs/catalog.json: {slug} has unknown fields")
        listed[slug] = distribution(entry, f"packs/catalog.json {slug}")
    return listed


def check_registry():
    """`publishers.json` (D19): valid and unique, and the handles every source and record use."""
    registry = read_registry(ROOT / "publishers.json")
    problems = registry_problems(registry)
    if problems:
        raise ValueError("publishers.json: " + "; ".join(problems))
    return registry


def check_identities(registry, ledger, sources):
    """Each source's handle is registered; each record's submitter is its id's handle, and its
    reviewer, when named, a maintainer (the denframe handle's accounts): tools never invent one."""
    handles = publishers_by_handle(registry)
    for package_id, _ in sources:
        if handle_of(package_id) not in handles:
            raise ValueError(f"{package_id}: the handle {handle_of(package_id)} is not in publishers.json")
    reviewers = maintainer_logins(registry)
    for record in ledger.records:
        if record.submitter_handle != handle_of(record.id):
            raise ValueError(f"{record.id} {record.version}: submitter_handle must be {handle_of(record.id)}")
        if record.submitter_handle not in handles:
            raise ValueError(f"{record.id} {record.version}: {record.submitter_handle} is not in publishers.json")
        if record.reviewer is not None and record.reviewer.casefold() not in reviewers:
            raise ValueError(f"{record.id} {record.version}: reviewer {record.reviewer} is not a maintainer")


def check_tracked():
    """In a git checkout: no tracked file is one `.gitignore` excludes, or compiled Python or a
    path hook (both run without their source). An exported tree has no git; the merge command
    and the pull-request gate check the same over the commit's objects."""
    if not (ROOT / ".git").exists() or shutil.which("git") is None:
        return
    def git(*args):
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout
    ignored = git("ls-files", "-ci", "--exclude-standard").split()
    if ignored:
        raise ValueError("Tracked files that .gitignore excludes: " + ", ".join(ignored[:10]))
    hidden = [name for name in git("ls-files").splitlines() if FORBIDDEN_NAMES.search(name)]
    if hidden:
        raise ValueError("Compiled, path or review files are never committed: " + ", ".join(hidden[:10]))


def check():
    check_tracked()
    hits = runpy.run_path(str(TOOLS / "privacy-check.py"))["findings"](ROOT)
    if hits:
        raise ValueError("Privacy check failed: " + json.dumps(hits))
    manifest = json.loads((ROOT / "MIRROR.json").read_text())
    for name, expected in manifest["files"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    corpus = ROOT / "contracts/format-fixtures"
    index = json.loads((corpus / "index.json").read_text())
    for case in index["archives"]:
        path = corpus / case["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == case["sha256"], case["id"]
        assert inspect_archive(path).layers == case["expected"]["cli"], case["id"]
    registry = check_registry()
    ledger = read_ledger((ROOT / "reviews.json").read_bytes())
    count = reviewed = included = 0
    catalogued = set()
    # Every release (id, version) and slug, across both catalogs, once.
    releases, slugs = set(), set()

    def once(package_id, version, slug, where):
        if (package_id, version) in releases or slug in slugs:
            raise ValueError(f"{where}: {package_id} {version} or its slug {slug} is listed twice")
        releases.add((package_id, version))
        slugs.add(slug)

    with tempfile.TemporaryDirectory() as temp:
        target = Path(temp) / "asset.denframepack"
        for catalog in ("catalog.json", "starters.json"):
            for item in json.loads((ROOT / "definitions" / catalog).read_text()):
                definition = Definition.model_validate(item["definition"])
                data = definition_archive(item)
                target.write_bytes(data)
                assert "fail" not in inspect_archive(target).layers.values(), item["id"]
                # Starters are development releases until promoted; promotion needs a record.
                if catalog == "catalog.json":
                    check_entry(item)
                    once(item["id"], item["version"], item["slug"], "definitions/catalog.json")
                    catalogued.add(item["id"])
                    placed = distribution(item, f"definitions/catalog.json {item['id']}")
                    if placed == "included":
                        check_included(item, definition)
                        included += 1
                    require_review(
                        ledger,
                        item["id"],
                        item["version"],
                        archive_sha256=sha256(data),
                        source_sha256=reviewed_source(item),
                        distribution=placed,
                    )
                    reviewed += 1
                count += 1
        listed = pack_catalog()
        sources = {path.parent.name: path for path in (ROOT / "packs").glob("*/source.json")}
        missing = sorted(set(listed) - set(sources))
        if missing:
            raise ValueError("packs/catalog.json lists packs without a source: " + ", ".join(missing))
        for slug, source in sorted(sources.items()):
            item, _, archive = read_source(source)
            if slug in listed:
                once(item["id"], item["version"], slug, "packs/catalog.json")
                catalogued.add(item["id"])
                require_review(
                    ledger,
                    item["id"],
                    item["version"],
                    archive_sha256=sha256(archive),
                    source_sha256=sha256(source.read_bytes()),
                    distribution=listed[slug],
                )
                reviewed += 1
                included += listed[slug] == "included"
            count += 1
    check_identities(registry, ledger, releases)
    collections = check_collections(catalogued)
    print(
        f"Validated {count} sources ({reviewed} with exact review records, {included} included), "
        f"{collections} collections, {len(registry['publishers'])} publishers, "
        f"{len(index['archives'])} conformance archives and mirror hashes."
    )


def main(argv=None):
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="check another tree (an exported head)")
    args = parser.parse_args(argv)
    if args.root is not None:
        ROOT = args.root.resolve()
    check()


if __name__ == "__main__":
    main()
