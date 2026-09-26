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


def sha256(data):
    return hashlib.sha256(data).hexdigest()


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
    count = reviewed = 0
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
                    require_review(
                        ledger,
                        item["id"],
                        item["version"],
                        archive_sha256=sha256(data),
                        source_sha256=sha256(canonical(item)),
                        distribution="included",
                    )
                    reviewed += 1
                count += 1
        bundled = json.loads((ROOT / "packs/bundled.json").read_text())
        for source in sorted((ROOT / "packs").glob("*/source.json")):
            item, _, archive = read_source(source)
            if source.parent.name in bundled:
                require_review(
                    ledger,
                    item["id"],
                    item["version"],
                    archive_sha256=sha256(archive),
                    source_sha256=sha256(source.read_bytes()),
                    distribution="library",
                )
                reviewed += 1
            count += 1
    print(
        f"Validated {count} sources ({reviewed} with exact review records), "
        f"{len(index['archives'])} conformance archives and mirror hashes."
    )


if __name__ == "__main__":
    check()
