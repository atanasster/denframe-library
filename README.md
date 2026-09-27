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

- `definitions/catalog.json`: the design definitions and editorial text. Each entry's
  `distribution` says where it goes: `included` ships inside Mantel, `library` is offered
  online only. An optional `min_host` is catalog metadata; an optional `manifest` keeps an
  author's own manifest (publisher, licence, attribution) so the entry rebuilds their archive.
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

Every submission is reviewed in an isolated container from the pinned release image: no
network, a read-only filesystem holding only the published toolchain and the submitted file,
and nothing from the submission ever run. Text inside a submission is data; instructions found
in it are reported as findings. The review recommends *approve*, *changes requested* or
*reject* and drafts the record with the reviewer, date and verdict left empty for a person.
The review skill lives here (`.claude/skills/mantel-asset-review/`) and runs only from a clean
clone of this repository -- never beside signing keys; its `SKILL.md` has the launch line.

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

### Publishing an accepted submission

The whole path, from an issue to the website, is the host's
`docs/operations/LIBRARY_PUBLISHING.md`. The steps in this repository:

1. **Review** with the `mantel-asset-review` skill from a clean clone (its `SKILL.md`); it
   writes `.review/<n>/report.md`, `evidence.json` and a draft `record.json`, never committed.
2. **Unpack** on a new branch: `python tools/intake.py unpack <archive> --evidence
   .review/<n>/evidence.json --mood "..." --description "..."` (a pack takes neither). It
   writes the canonical source -- a `definitions/catalog.json` entry with `distribution:
   library` (and the author's `manifest` when the default one would not rebuild the bytes), or
   `packs/<slug>/` and its `packs/catalog.json` line -- and refuses an id or version already
   listed, changed bytes for a listed release, an archive the review did not read, and any
   source that does not rebuild the submitted archive byte for byte. It prints the pull
   request's checklist and the source SHA-256 the record will name.
3. **Register a first-time handle**: `python tools/intake.py register --evidence ...
   --display-name "..."` binds it to the numeric GitHub account id the skill's intake read from
   the issue's author (GitHub's metadata, never the submission). A local intake has none: pass
   `--login` and `--account-id` from `gh api users/<login> --jq .id`. The identity rules
   (`.claude/skills/mantel-asset-review/references/identity.md`) apply.
4. **Open the pull request.** CI runs `tools/check.py` (which also validates the registry:
   unique handles, numeric ids, no reserved or look-alike handles, every source's handle
   registered, every record's submitter its id's handle and its reviewer a maintainer, and no
   tracked file that `.gitignore` excludes), `tools/rebuild.py`, and the `gate` job
   (`tools/pr_gate.py`). It stays red until the record is in: the check refuses a catalogued
   release without an admitting record for its exact bytes.
5. **The owner's record**, after reading the report: `python tools/intake.py approve --draft
   .review/<n>/record.json --evidence .review/<n>/evidence.json --reviewer <login> --verdict
   approved|preview --status area=pass ...`. It fills the source SHA-256 from the tree, refuses
   a reviewer who is not a maintainer, an approval over a pending or failed status, a status the
   tools settled, and a draft whose archive is not the submitted one. Records are the owner's:
   the owner commits it to their own intake pull request. A publisher's pull request (the route
   over 20 MB) never carries a record or a `distribution` change; the owner merges its branch
   into an `intake/<n>` branch of their own, adds the record there, merges that, and closes the
   publisher's pull request as landed.
6. **Merge with `python3 tools/merge_pr.py <n>`**, from a clean, up-to-date `main` clone -- the
   one way a pull request reaches `main`. A source release (`sources-vN`) follows.

**CI is advisory; the owner's merge command is the gate.** A `pull_request` workflow comes from
the pull request itself, so a pull request can edit or drop any job in it, including the gate:
a green check never decides a merge. The `gate` job still runs no head code -- it checks out the
base commit, fetches the head as git objects, installs nothing and runs the base's
`tools/pr_gate.py` with `python -I` -- so it is an honest early signal for an unmodified
workflow. `tools/merge_pr.py` is the control: it reads the author's numeric id, the head commit
and the base with fixed read-only `gh` calls; fetches `pull/<n>/head` and requires that exact
commit; refuses outright, for anyone but a maintainer, changes under `.github/`, `tools/`,
`format/`, `.claude/`, to `reviews.json` or to a `distribution`; runs *main's* `pr_gate.py` over
the git objects; exports the head with `git archive` (never checked out, imported, installed or
run) and runs main's `check.py --root` and `rebuild.py --root` over it in the pinned image; and
only then merges with `gh pr merge <n> --squash --match-head-commit <sha>`.

`tools/pr_gate.py` reads git objects only (the merge base to the head), so build products in a
working tree are not changes and ignored names hide nothing: from anyone, a `__pycache__` path, a
`.pyc`/`.pyo`/`.pth` file, anything under `.review/`, and any tracked file `.gitignore` excludes
are refused. Against the base registry: a handle's sources or registry entry change only by one
of its accounts or a maintainer (the `mantel` handle's accounts); a first-time handle is
registered only to its author's own id; adding an account to a handle, or removing or renaming
another account, is a transfer (a maintainer's change); and records, distributions and anything
outside the asset sources -- tools, workflows, the format, the skill, previews, collections,
starters -- are a maintainer's change.

Signing happens on the owner's key machine from the pinned host tree
(`scripts/library-release.py`), never in this repository's CI.

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
