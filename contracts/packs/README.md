# Multimedia pack contracts

These contracts describe the first data-only multimedia format. They do not enable imports,
card rendering or advertised receiver capabilities by themselves. Generate schemas with
`PYTHONPATH=backend .venv/bin/python scripts/export-pack-contracts.py`; use `--check` in CI.
Python models in `backend/app/pack_contracts.py` are authoritative. Shared fixtures run through
Pydantic and frontend JSON Schema 2020-12 validation. Reference-graph invariants are additional
host validation, not assertions that JSON Schema can compare arbitrary resource references.

## Identity and archive dispatch

V1 retains its current two-file theme/block/content format. V2 contains `manifest.json`,
`definition.json` and exactly the asset paths inventoried by the definition. Items and activities
are embedded in the bounded definition document in the first version; there are no nested content
documents or cross-pack dependencies. The definition's canonical JSON hashes all content plus the
asset inventory. Each resource path contains the exact SHA-256 of its bytes. The manifest contains
the definition hash; the catalog contains the complete original archive hash. `DefinitionRef.digest`
continues to mean the definition hash, never the archive hash. Local content references name both.

Unknown format versions are rejected before decoding content. Same ID/version with different bytes
is a conflict. V2 is intended for the version-dispatching reader implemented in step 2; the existing
v1 reader is deliberately unchanged at this contract milestone.

## Closed limits

| Resource | Maximum |
| --- | --- |
| Compressed archive / expanded bytes | 128 MiB / 256 MiB |
| Files / structured document bytes | 2,048 / 4 MiB |
| Installed packs / staging reservations | 2 GiB / 512 MiB |
| Aggregate installed files | 16,384 (keeps full backup inventory bounded) |
| Concurrent validation jobs | 2 |
| Image / MP3 bytes | 8 MiB / 2 MiB |
| Audio duration per cue / cues per item | 30 seconds / 4 |
| ZIP compression ratio | 100:1 |
| Items / activities / locales | 1,000 / 32 / 8 |
| Name / visible text / credit text | 100 / 240 / 500 characters |
| Prompt / recall / reveal / dwell seconds | 1–30 / 0–30 / 1–30 / 1–30 |
| Unprotected projection / protected window | 12 KiB / 16 KiB |
| Scene / complete envelope / checkpoint | 60 KiB / 64 KiB / 2 KiB |

Resource paths are lower-case ASCII `assets/<sha256>.<png|jpg|webp|mp3>` and exactly one level
deep. Each byte is streamed and checked against the inventory in the archive reader; image decode
limits use the existing bounded image validator. Declared MP3 duration must be checked against
decoded/probed media in step 2. A filename, declared duration or MIME string alone is not evidence.
No video, HTML, scripts, SVG, fonts, remote asset URLs or executable install hooks are accepted.
Credit source is inert text, never a playable URL or fetch instruction. Credit notices are required
for MIT and CC BY resources; CC0 fixture assets require no attribution but retain provenance.

Every item has all declared translations; each activity chooses a supported locale and a unique
ordered subset. Every resource and item is used. Images require alternative text. Cue references
must resolve to audio; image references must resolve to image resources. Graph validation is host
owned. Card subsets are separately checked against their installed activity at application time.

## Capability and platform evidence

`capabilities.json` lists known format/activity/renderer contracts, not currently enabled features.
Actual advertisement is added only when each subsystem exists. Audio availability and actual touch
input are runtime results and must never be inferred from the registry alone.

| Surface | Source-inspected condition | Verification status |
| --- | --- | --- |
| Cast | Current `NativeCastReceiver` calls `context.start()` without custom touch UI options | Existing fake adapter tests; new pack playback/hardware pending |
| Native panel | WebView sets `mediaPlaybackRequiresUserGesture = false` | Existing shell behavior; actual pack audio/hardware pending |
| Browser panel | Browser may reject audio playback | Future coordinator must handle rejected play promises |
| Preview | No-output policy required regardless of element muting | Contract established; runtime tests in step 7 |
| Bulgarian text | Display fonts are supplied as Latin subsets | Cyrillic glyph/layout proof pending step 8; no current support claim |

The synthetic fixture is a green circle made with Pillow and a 440 Hz test tone encoded as MP3.
Both are original CC0 test assets. The tone is **not** speech, animal audio or a publishable learning
recording. Its inventory length/hash are tested; hardware playback and fluent content review are
not claimed. Both Bulgarian and English strings exercise schema and UTF-8 transport behavior.

## State and errors

The player will use prepare, prompt, recall, reveal, dwell, paused, ended and unavailable states.
Cue completion has a watchdog; stale-generation callbacks have no effect. Default final-item
behavior is ended. Looping is explicit; shuffle is unsupported. Timers and audio are local; the
host accepts only authorized, ordered item checkpoints, not phase state or inferred learning.

Public error codes are `invalid-format`, `invalid-content`, `unsupported-capability`,
`integrity-failed`, `quota-exceeded`, `cancelled`, `expired`, `conflict`, `unauthorized` and
`unavailable`. Errors contain no credentials or file contents. Later API implementations map
these to bounded user-facing explanations while retaining HTTP authorization semantics.
