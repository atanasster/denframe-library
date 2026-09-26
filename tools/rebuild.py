"""Rebuild gate (D21): every reviewed asset, rebuilt with only the published toolchain in the
pinned release environment, is byte-identical to the release its review record names.

Each source is built, then its archive is unpacked and built again, so archive-only
submissions (which are unpacked first) are held to the same bytes.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from mantel_format.authoring import read_source, unpack
from mantel_format.elements import Definition, build_package
from mantel_format.reviews import read_ledger

ROOT = Path(__file__).resolve().parents[1]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def sources():
    """Every authored design and activity source: (id, version, its built archive bytes)."""
    for item in json.loads((ROOT / "definitions/catalog.json").read_text()):
        definition = Definition.model_validate(item["definition"])
        yield item["id"], item["version"], build_package(item["id"], item["version"], definition)
    for source in sorted((ROOT / "packs").glob("*/source.json")):
        item, _, archive = read_source(source)
        yield item["id"], item["version"], archive


def rebuilt_from_archive(data, scratch):
    """The archive-only path: unpack to an authorable source, then build it again."""
    archive = scratch / "submitted.mantelpack"
    archive.write_bytes(data)
    _, _, rebuilt = read_source(unpack(archive, scratch / "unpacked"))
    return rebuilt


def rebuild():
    ledger = {(r.id, r.version): r for r in read_ledger((ROOT / "reviews.json").read_bytes()).records}
    built = list(sources())
    missing = set(ledger) - {(package_id, version) for package_id, version, _ in built}
    if missing:
        raise ValueError("Review records without a source: " + ", ".join(sorted(map(" ".join, missing))))
    checked = 0
    for package_id, version, data in built:
        record = ledger.get((package_id, version))
        if record is None:
            continue
        if sha256(data) != record.archive_sha256:
            raise ValueError(f"Rebuild of {package_id} {version} differs from its reviewed release")
        with tempfile.TemporaryDirectory(prefix="mantel-rebuild-") as temporary:
            if rebuilt_from_archive(data, Path(temporary)) != data:
                raise ValueError(f"Unpacking {package_id} {version} does not rebuild its bytes")
        checked += 1
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--any-environment",
        action="store_true",
        help="skip the pinned-runtime check (local diagnosis only; the gate never uses it)",
    )
    args = parser.parse_args()
    if not args.any_environment:
        check = ROOT / "format/tools/release_environment.py"
        if subprocess.run([sys.executable, str(check), "--check"]).returncode:
            raise SystemExit("Rebuilds must run in the pinned release environment")
    print(f"Rebuilt {rebuild()} reviewed assets byte-for-byte, from source and from archive.")


if __name__ == "__main__":
    main()
