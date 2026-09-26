"""Print or check the native decoder runtime used for reproducible format releases."""

import argparse
import hashlib
import json
import platform
import zlib
from pathlib import Path

from PIL import __version__, features

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    runtime = {
        "python": platform.python_version(),
        "platform": platform.machine(),
        "zlib_build": zlib.ZLIB_VERSION,
        "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
        "pillow": __version__,
        "native": {
            name: features.version(name) for name in ("zlib", "jpg", "libjpeg_turbo", "webp")
        },
    }
    if not args.check:
        print(json.dumps(runtime, indent=2))
        return 0
    recorded = json.loads((ROOT / "release-environment.json").read_text())
    lock = hashlib.sha256((ROOT / "requirements.lock").read_bytes()).hexdigest()
    if runtime != recorded["runtime"] or lock != recorded["requirements_sha256"]:
        print("Format release environment differs from its recorded runtime or dependency lock.")
        print(json.dumps(runtime, indent=2))
        return 1
    print("Format release environment matches its recorded runtime and dependency lock.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
