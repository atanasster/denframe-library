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

- `definitions/catalog.json`: the 16 design definitions and editorial text. Each entry's
  `distribution` says where it goes: `included` ships inside Mantel, `library` is offered
  online only.
- `definitions/starters.json`: nine included layout sources, currently development releases.
- `definitions/collections.json`: the collections the online library shows on *Get more*: an
  id, a title, one sentence and, in order, 2 to 24 ids the two catalogs list (definitions and
  activities alike). Host builds sign it as a target of its own; see *Collections* below.
- `packs/`: activity sources, exact media and credits. `packs/catalog.json` lists each
  catalogued activity by slug with its `distribution`.
- `contracts/`: schemas, vocabulary and the valid/invalid conformance corpus.
- `publishers.json`: registered handles and their numeric GitHub account IDs.
- `reviews.json`: the review ledger (schema v2), one record per exact release; see below.

Every catalogued definition and activity has a `reviews.json` record naming the exact
archive and source SHA-256, the submitter, the reviewer and date, eight review statuses and a
verdict (`approved`, `preview`, `changes-requested` or `rejected`). A definition's source hash
covers its catalog entry without `distribution`, so moving a release between distributions
needs no new review of its bytes, only a verdict that admits the new one. Included items need
`approved`; library items need `approved` or `preview`. `tools/check.py` refuses any
catalogued release without a record for its exact bytes, and host builds refuse to sign one.
Only a person approves: a `preview` may rest on automated checks, but never names a reviewer
who did not review. Reports follow [reviews/report-template.md](reviews/report-template.md).

What Mantel includes is what a new household needs on day one without an account. So
`tools/check.py` also refuses an included definition that reads an account- or key-bound
source (a market watchlist needs the Stocks key). The host build adds the last rule: the
included previews total at most 3 MB.

The activity sources are **preview material**, awaiting human content, language and
listening review. A build or a signature is not a content endorsement. The source seed
and tool release do not publish a new catalog to household hosts.

### Collections

A collection is a short, editorial group: *Calm and quiet*, *For the kitchen*. Keep a title
under 60 characters and the sentence under 200, in plain words about what the group is for,
not a list of what it holds. Order matters: the first four are what a household sees before
*See all*. `tools/check.py` refuses an unknown or repeated id, an item no catalog lists, and
control or bidirectional formatting characters. A collection may name included items as well as
library ones; hosts mark what a household already has.

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
and run `python tools/check.py`. `python tools/rebuild.py` is the rebuild gate: in the pinned
release environment (`format/release-environment.json`) it rebuilds every reviewed asset from
source, and again from its unpacked archive, and requires the exact bytes its review record
names. CI runs both in that image; locally, run them in the same image:

```sh
docker run --rm --platform linux/amd64 \
  --mount type=bind,source="$PWD",target=/repo,readonly -w /repo \
  python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285 \
  sh -c 'pip install -q --require-hashes -r format/requirements.lock && cp -r format /tmp/f &&
    pip install -q --no-deps /tmp/f && python tools/check.py && python tools/rebuild.py'
```

The host pins a tagged source subtree at `library/src`; its signed runtime catalogs are
generated from those sources.

`python tools/mirror-from-host.py --host /path/to/host --destination . --check`
checks the one-way toolchain/contract mirror against the host commit `MIRROR.json` records;
pass `--revision <host-commit>` to check or mirror another commit. Omit `--check` only while
preparing a reviewed format release. The script never replaces asset sources or copies host data.
Run `python tools/privacy-check.py .` on the concrete tree before any first push.

`tools/tuf_repository.py` (mirrored from the host) operates the online library's TUF
repository: `init`, `publish`, `revoke`, `renew`, `rotate-root` and `status`. The
`Renew library metadata` workflow runs `renew` and `status` daily against the staging
repository on the `metadata-staging` branch, with only the online key from the protected
`release` environment, and opens or comments on an issue labelled `metadata-renewal` when it
fails. It stays off until the repository variable `LIBRARY_RENEWAL` is `on`, which the owner
sets at the pre-launch gate. Its runtime is `tools/requirements-release.lock`. The host's
`docs/operations/LIBRARY_TUF_OPERATIONS.md` is the runbook: roles, keys, rotation, key loss,
lapse and takedown.
