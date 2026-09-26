# Mantel format

`mantel_format` owns the data-only models, ZIP profile, canonical JSON encoding, capability
triggers, palette contrast checks and bounded media inspection used by the host. Its runtime
dependencies are Pydantic and Pillow. It imports no host modules and reads no household state.
Authentication, identity trust, installation, upload quotas and worker isolation remain in the host.

From the public repository root:

```sh
python -m pip install ./format
```

```python
from mantel_format import read_package, validate_archive

manifest, definition = read_package(design_bytes)
pack = validate_archive(pack_path, fresh_private_directory)
```

`read_package` validates v1 designs; `validate_archive` validates and extracts v2 media packs.
Neither function authorizes an identity or makes a publisher claim trustworthy. Run media
validation in a disposable, resource-limited process when accepting untrusted files. The host's
upload worker supplies those limits. Scene exports and household privacy filtering stay in the
backend adapters.

The backend adapters re-export these same model classes and validators. `make check` covers
both packages, checks the dependency direction, builds an isolated wheel, and proves every
signed release validates and rebuilds with identical bytes. The themes resource is a packaged
snapshot of the host's generated theme projection; the suite refuses drift between them. Update that
snapshot whenever the canonical theme data changes.

## Authoring commands

Installing the wheel adds `mantel-author`; `python -m mantel_format` runs the same CLI.

```sh
mantel-author new block friend/clock source.json --name "My clock" --publisher "My studio"
mantel-author validate source.json
mantel-author build source.json clock.mantelpack
mantel-author validate clock.mantelpack --json
mantel-author inspect clock.mantelpack
mantel-author unpack clock.mantelpack editable
mantel-author build editable/source.json rebuilt.mantelpack
mantel-author build editable/source.json rebuilt.mantelpack --check
```

`new` supports themes, blocks, content collections and text-only draft packs. Author sources contain
`id`, `version` and `definition`, plus an optional explicit `manifest`. Pack media lives beside the
source under `assets/`. `unpack` preserves resource bytes, attribution, publisher and exact manifest
locks. Editing the definition recalculates its digest; authors must choose a new version before
publishing changed bytes. Builds use the deterministic ZIP profile. Arbitrary imported ZIP timestamps,
compression and v1 JSON whitespace are normalized; the rebuild parity promise applies to releases
produced by the canonical builders in the pinned release environment.

Commands refuse existing outputs. `build --check` compares without writing. `validate` and `inspect`
report layer verdicts and return a nonzero exit code on refusal. Source files and command output
use UTF-8, independent of the system locale. Publisher trust remains `not checked`;
a valid file does not establish ownership of its namespace. The host decides admission with its trusted
catalog and receipts. The shared `inspect_archive(path)` API returns the same report without installing
anything. CLI media inspection runs locally; services accepting uploads must still isolate their worker.

`scripts/library-author.py` delegates these commands to the package and retains the repository-only
`preview` command. Its `--check` builds every design through the standalone CLI and compares with
`build-library.py`; it runs in `make check` without accessing signing keys.

## Reproducible release environment

`release-environment.json` records the measured Linux amd64 release runtime, including the
native libraries used by Python and Pillow. `requirements.lock` retains the host lock's exact
runtime versions and wheel hashes. Developer platforms may differ; release artifacts use the
recorded image and decoder runtime. Verify it with:

```sh
docker run --rm --platform linux/amd64 \
  --mount type=bind,source="$PWD/format",target=/format,readonly \
  python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285 \
  sh -c 'python -m pip install --require-hashes -r /format/requirements.lock && python /format/tools/release_environment.py --check'
```

Setuptools 84.0.0 is the wheel build backend. `pip wheel --no-deps --no-build-isolation` builds
with that version after installing the `dev` extra; runtime validation needs neither pip nor
Setuptools. Tagged public mirrors and publication belong to the release workflow.
