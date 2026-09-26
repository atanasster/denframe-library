# Format conformance corpus

`index.json` describes the exact archive bytes and canonical JSON vectors shared by the host,
`mantel-author` and browser validator. Run `.venv/bin/python scripts/build-format-fixtures.py --check`
to check reproducibility. Omit `--check` to regenerate after an intentional fixture edit.
The tiny image and tone come from `contracts/packs/fixtures`; they are synthetic CC0 test media.
No corpus file is signed or ready for publication.

Verdicts are `pass`, `fail`, `warning`, `not applicable`, or `not checked`. A failure stops later
layers. Archive checks cover bounded ZIP structure; JSON checks cover decoding and plain text;
schema checks include exact inventory, canonical encoding and definition digests. Capabilities
cover declared requirements; contrast includes scrim pairs; media includes resource hashes,
decoding and metadata. The v1 schema also enforces its historical palette pairs, so a palette may
fail at schema before reaching the full contrast gate.

The browser must report media and trust as **not checked**, including for archives whose native
media inspection fails. These results never say “safe”. Static image-header and resource-budget
checks may still refuse an archive without allocating a renderer. The host and CLI need an explicit
trust context to make an identity decision; passing all data checks does not authenticate a publisher.

`scenarios.json` covers S1–S9 with preconditions, required outcomes and executable regression nodes.
These are host lifecycle scenarios, not promises a portable parser can make. `coverage.json` maps
every format table row to archives, canonical vectors, existing shared contracts and runtime tests.
Every row must name executable evidence; runtime-only motion and quotas are stated separately
and name the runtime tests that enforce them. Future schema features are named as deferred to
their owning plan steps, rather than accepted prematurely. `catalog-new-fields.json` exercises
the old element and pack catalog readers with optional fields they do not understand, while
retaining artifact hash checks.

`schema-history.json` is append-only. A schema revision must add a new fingerprint and at least one
new case ID; existing cases stay available. The guard fingerprints the five public model schemas,
the settings allow-list, portable override fields, capability tokens and triggers, and
`contracts/vocabulary.json`. It compares that fingerprint with the latest record and rejects a
revision that reuses old case IDs. It also preserves the committed history prefix against HEAD
and its first parent, both before and after a commit. This repository gate requires Git history;
shallow checkouts need `fetch-depth: 2`, as configured in CI. Canonical vectors expand model
defaults and pin UTF-8 without Unicode normalization. MP3 duration 30 is encoded as `30.0`, and
0.01 as `0.01`; these boundary vectors test serialization, not claimed duration of the test tone.

The Python reference runner is `backend/tests/test_format_conformance.py`; the CLI runner is
`backend/tests/test_mantel_author.py`. TypeScript runs the same corpus in
`frontend/src/format/inspect.test.ts` and in a real worker under CSP with `make check-format`. The complete repository gate executes
the linked host regressions; the coverage test also refuses stale node references.
