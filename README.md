# Mantel library

Portable, data-only themes, block presets, layouts and activity sources for Mantel.
This repository is the canonical home of the asset sources. The host maintains the
format implementation; tagged snapshots are mirrored here in one direction.

## Install the tools

```sh
pip install "mantel-format @ git+https://github.com/atanasster/mantel-library@format-v0.1.0#subdirectory=format"
mantel-author --help
```

Each `format-v*` release attaches the wheel. No PyPI publication is required.
`format/requirements.lock` and `format/release-environment.json` pin the reproducible
runtime. See [format/README.md](format/README.md) and the
[format specification](https://smart.meggy.com/docs/format).

## Sources and contributions

- `definitions/catalog.json`: the 16 shipped design definitions and editorial text.
- `definitions/starters.json`: nine included layout sources, currently development releases.
- `packs/`: activity sources, exact media, credits and review-candidate records.
- `contracts/`: schemas, vocabulary and the valid/invalid conformance corpus.
- `publishers.json`: registered handles and their numeric GitHub account IDs.

The activity sources are **preview material**, awaiting human content, language and
listening review. A build or a signature is not a content endorsement. The source seed
and tool release do not publish a new catalog to household hosts.

Use [Submit an asset](https://github.com/atanasster/mantel-library/issues/new?template=submit-asset.yml).
Issues and pull requests are public: remove household data, private paths, credentials,
locations and unlicensed material before submitting. Later source changes use pull
requests. Handle ownership and all checks are reviewed before acceptance.

Tools are [MIT](LICENSE); [asset licences and credits](ASSET-LICENSES.md) apply separately.
Read the [website terms](https://smart.meggy.com/terms),
[privacy note](https://smart.meggy.com/privacy), [security policy](SECURITY.md) and
[code of conduct](CODE_OF_CONDUCT.md).

## Maintainers

Install `format/requirements.lock` with `--require-hashes`, then install `./format`
and run `python tools/check.py`. The host pins a tagged source subtree at `library/src`;
its signed runtime catalogs are generated from those sources.

`python tools/mirror-from-host.py --host /path/to/host --destination . --check`
checks the one-way toolchain/contract mirror. Omit `--check` only while preparing a
reviewed format release. The script never replaces asset sources or copies host data.
Run `python tools/privacy-check.py .` on the concrete tree before any first push.
