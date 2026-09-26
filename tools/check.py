"""Validate public sources, mirror integrity and the shared standalone conformance corpus."""
import hashlib
import json
import runpy
import tempfile
from pathlib import Path

from mantel_format.authoring import read_source
from mantel_format.elements import Definition, build_package
from mantel_format.encoding import canonical
from mantel_format.reviews import read_ledger, require_review
from mantel_format.validation import inspect_archive

ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTIONS = ("included", "library")
# Source kinds whose sources need an account or a key. A market block is a watchlist, and its
# quotes come from the Stocks source, which needs a provider key: nothing included reads one.
ACCOUNT_BOUND_KINDS = frozenset({"market"})


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def reviewed_source(item):
    """The SHA-256 a review record names for a catalog entry: the entry without its
    `distribution`, so moving a release between distributions needs no new review of its
    bytes -- only a verdict that admits the new one."""
    return sha256(canonical({key: value for key, value in item.items() if key != "distribution"}))


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


def check():
    hits = runpy.run_path(str(ROOT / "tools/privacy-check.py"))["findings"](ROOT)
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
    ledger = read_ledger((ROOT / "reviews.json").read_bytes())
    count = reviewed = included = 0
    with tempfile.TemporaryDirectory() as temp:
        target = Path(temp) / "asset.mantelpack"
        for catalog in ("catalog.json", "starters.json"):
            for item in json.loads((ROOT / "definitions" / catalog).read_text()):
                definition = Definition.model_validate(item["definition"])
                data = build_package(item["id"], item["version"], definition)
                target.write_bytes(data)
                assert "fail" not in inspect_archive(target).layers.values(), item["id"]
                # Starters are development releases until promoted; promotion needs a record.
                if catalog == "catalog.json":
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
    print(
        f"Validated {count} sources ({reviewed} with exact review records, {included} included), "
        f"{len(index['archives'])} conformance archives and mirror hashes."
    )


if __name__ == "__main__":
    check()
