"""Mirror only committed format tooling and contracts; never copy asset or host data."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

MAPPINGS = {
    "packages/mantel-format": "format",
    "contracts/composition": "contracts/composition",
    "contracts/packs": "contracts/packs",
    "contracts/format": "contracts/format",
    "contracts/format-fixtures": "contracts/format-fixtures",
    "contracts/vocabulary.json": "contracts/vocabulary.json",
}


def projection(name, data):
    if name == "format/pyproject.toml":
        return data.replace(b'extend = "../../backend/pyproject.toml"', b'line-length = 100\ntarget-version = "py311"').replace(b'name = "mantel-format"', b'name = "mantel-format"\nlicense = "MIT"\nlicense-files = ["LICENSE"]')
    if name == "format/tools/ruff.toml":
        return b'[lint]\nignore = ["T201"]\n'
    if name == "format/README.md":
        text = data.decode().replace("packages/mantel-format", "format")
        text = text.replace("From this repository, `make install` installs both packages. For standalone use:", "From the public repository root:")
        text = text.replace("`library/definitions/themes.json`", "the host's generated theme projection")
        return text.encode()
    return data


def mirror(host, destination, revision=None, check=False):
    """Mirror `revision`; a check defaults to the host commit the mirror records, so unrelated
    later host commits do not make an unchanged mirror look stale."""
    previous = destination / "MIRROR.json"
    if revision is None:
        revision = json.loads(previous.read_text())["host_commit"] if check and previous.exists() else "HEAD"

    def git(*args):
        return subprocess.check_output(["git", "-C", str(host), *args])
    commit = git("rev-parse", "--verify", revision + "^{commit}").decode().strip()
    expected = {}
    for source, target in MAPPINGS.items():
        paths = git("ls-tree", "-r", "--name-only", commit, "--", source).decode().splitlines()
        if not paths:
            raise ValueError("Missing committed mirror input: " + source)
        for path in paths:
            name = target + path[len(source):]
            expected[name] = projection(name, git("show", commit + ":" + path))
    expected["format/LICENSE"] = (destination / "LICENSE").read_bytes()
    manifest = {"schema_version": 1, "host_commit": commit, "files": {
        name: hashlib.sha256(data).hexdigest() for name, data in sorted(expected.items())
    }}
    expected["MIRROR.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    stale = set(json.loads(previous.read_text())["files"]) - expected.keys() if previous.exists() else set()
    # A prior manifest cannot authorize deletion outside the mirrored roots.
    if any(not any(name == target or name.startswith(target + "/") for target in MAPPINGS.values())
           or ".." in Path(name).parts for name in stale):
        raise ValueError("Invalid mirror manifest path")
    for name in set(expected) | stale:
        path = destination / name
        if any(parent.is_symlink() for parent in [path, *path.parents]):
            raise ValueError("Mirror destination contains a symlink")
    if check:
        changed = sorted(name for name, data in expected.items()
                         if not (destination / name).is_file() or (destination / name).read_bytes() != data)
        if changed or any((destination / name).exists() for name in stale):
            raise ValueError("Mirror differs: " + ", ".join(changed + sorted(stale)))
    else:
        for name in stale:
            (destination / name).unlink(missing_ok=True)
        for name, data in expected.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--revision", help="host commit (default: HEAD; the recorded commit with --check)")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    mirror(args.host, args.destination, args.revision, args.check)
