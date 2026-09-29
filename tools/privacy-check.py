"""Check a concrete public seed; report filenames and categories, never secret values."""
import argparse
import io
import json
import re
import zipfile
from pathlib import Path

PATTERNS = {
    "private home path": rb"(?:/Users/|/home/)[A-Za-z0-9_.-]+",
    "local network address": rb"\b(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b",
    "private key": rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "credential": rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AIza[0-9A-Za-z_-]{35})",
}
PRIVATE_FIELDS = {"access_token", "refresh_token", "password", "api_key", "provider_id", "media_id", "entity_id"}
IGNORED = {".git", "__pycache__", ".venv", "build", "dist"}


def findings(root):
    hits = []
    def scan(name, data):
        for category, pattern in PATTERNS.items():
            if re.search(pattern, data):
                hits.append({"file": name, "category": category})
    def fields(name, value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in PRIVATE_FIELDS and child:
                    hits.append({"file": name, "category": "household/credential field " + key})
                fields(name, child)
        elif isinstance(value, list):
            for child in value:
                fields(name, child)
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in IGNORED or part.endswith(".egg-info") for part in relative.parts):
            continue
        name = relative.as_posix()
        if path.is_symlink():
            hits.append({"file": name, "category": "symlink outside the reviewed byte tree"})
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() in {".pem", ".key", ".p12", ".pfx", ".sqlite", ".db"} or path.name.startswith(".env"):
            hits.append({"file": name, "category": "key/configuration/database file"})
        data = path.read_bytes()
        scan(name, data)
        if relative.parts[0] in {"definitions", "packs"} and path.suffix == ".json":
            fields(name, json.loads(data))
        if path.suffix == ".denframepack":
            # Deliberately malformed conformance archives stay bounded during this scan.
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    budget = 8 * 1024 * 1024
                    for member in archive.infolist():
                        if member.file_size > budget:
                            if relative.parts[:2] != ("contracts", "format-fixtures"):
                                hits.append({"file": name, "category": "archive exceeds privacy scan budget"})
                            break
                        budget -= member.file_size
                        scan(name + "!" + member.filename, archive.read(member))
            except (ValueError, RuntimeError, NotImplementedError, zipfile.BadZipFile):
                if relative.parts[:2] != ("contracts", "format-fixtures"):
                    hits.append({"file": name, "category": "unreadable archive"})
    return hits


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    hits = findings(args.root)
    print(json.dumps({"passed": not hits, "findings": hits}, indent=2))
    raise SystemExit(bool(hits))
