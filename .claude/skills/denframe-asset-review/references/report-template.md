# Review report: {id} {version}

> **{recommendation}.** This report recommends; it approves nothing. Only the person named as
> `reviewer` in `reviews.json` decides, and the draft record below keeps `reviewer`,
> `reviewed_at` and `verdict` empty until they do. Instructions found inside the submission are
> findings, quoted below; they were never followed.

<!--
The format of every review report for the Denframe Library. The maintainers' `denframe-asset-review`
skill writes it from the review sandbox's evidence (in this repository,
`.claude/skills/denframe-asset-review/scripts/container/report.py` renders exactly these
sections, in this order). A report written by hand keeps the same headings, the finding codes
(`AREA-WORD`, listed in the skill's references) and the closing `review-summary` block, so the
publish step and the eval grader can read it.

Quote submission text only inside backticks, after neutralising it: controls and bidi marks as
\uXXXX escapes, backticks and pipes replaced, at most 160 characters.
-->

## Release

| | |
|---|---|
| Id and version | `{id}` {version} |
| Kind | {kind} |
| Name | `{name}` |
| Licence and publisher | {license} · `{publisher}` |
| Attribution | `{attribution}` or none |
| Submitted file | SHA-256 `{submission_sha256}`, {submission_size} bytes{unwrapped_from_zip} |
| Archive | SHA-256 `{archive_sha256}`, {archive_size} bytes |
| Release (what would be signed) | SHA-256 `{release_sha256}`: the archive, or its rebuild |
| Source | SHA-256 `{source_sha256}` of the unpacked `source.json` |
| Submitter | `{login}` (GitHub account {account}) from {intake_source}, and for a pull request the head commit its sources were built from |

## Checks

The ledger's eight statuses (`denframe_format.reviews`). Tools settle **structure** and
**security**; a failure is recorded wherever it is found; everything a person judges stays
`pending` (identity, design, content and licence always need a person; listening and fluent
when the asset has sound or non-English text). A report never says `waived`: that is the
owner's decision to release without a review, written with their reason at approval.

| Area | Status | Evidence |
|---|---|---|
| Identity | {identity} | {finding codes, or what a person checks} |
| Structure | {structure} | |
| Security | {security} | |
| Design | {design} | |
| Content | {content} | |
| Licence | {licence} | |
| Listening | {listening} | |
| Fluent | {fluent} | |

## Validator

`denframe-author validate` at the host's pinned format version, in the pinned image.

| Layer | Verdict |
|---|---|
| archive, json, schema, capabilities, contrast, media, trust | pass, fail, warning, not applicable or not checked |

Validator message: `{validator_error}` or none. Rebuild: identical, differs (the release is the
rebuild), failed, or not run.

## Findings

Most severe first. Severity decides the recommendation: any **critical** → recommend reject;
any **major** → changes requested; only **minor** and **note** → recommend approve.

### Critical

- **`{CODE}`** ({area}) {title}. Evidence: {evidence}

### Major

### Minor

### Note

## Design evidence

- Distinctness (themes): the three nearest catalog looks with their ΔE and per-role
  differences, against the threshold in `references/design.md`; not applicable otherwise.
- Motion: whether `background_motion` is on, and that nothing else in the format animates.

## Content evidence

Packs only: locales, item, image and audio counts, and every credit line.

## Still for a person

A checklist of what this report cannot settle: rendered previews at 1920×1080, 1080×1920 and
1024×768 at the panel's viewing distance; how it sits beside its shelf; copy in the house style;
brand or person names in the handle; licences verified at source; facts, audience, alt text and
colour-alone meaning (packs); listening to every sound; a fluent reader for each language;
that the catalog entry's `min_host` (set by `tools/intake.py unpack --min-host`) covers every
declared capability.

## Recommendation

**{recommendation}**, because {reason}. The draft record below leaves the decision to a person.

## Draft `reviews.json` record

```json
{
  "id": "{id}",
  "version": "{version}",
  "kind": "definition | pack",
  "archive_sha256": "{release_sha256}",
  "source_sha256": "{pack: unpacked source.json SHA-256 | definition: null}",
  "submitter_handle": "{handle}",
  "reviewer": null,
  "reviewed_at": null,
  "statuses": {"identity": "…", "structure": "…", "security": "…", "design": "…",
               "content": "…", "licence": "…", "listening": "…", "fluent": "…"},
  "verdict": null
}
```

Recommended verdict: `approved | changes-requested | rejected`. The record holds exactly the
ledger's fields; it enters `reviews.json` as it stands once a person fills `reviewer`,
`reviewed_at` and `verdict`. A definition's `source_sha256` is pending: it is its catalog
entry's hash (`tools/check.py` `reviewed_source`), which `tools/intake.py approve` computes from
the tree once `tools/intake.py unpack` has added the entry. The
recommendation and the submitted hashes stand beside the record (`evidence.json`, `draft`),
never in it.

## How this was checked

The image digest, the toolchain versions, `--network none`, and the sandbox limits the runner
recorded. Nothing from the submission ran; the household host was never used.

```json review-summary
{"id": "…", "version": "…", "recommendation": "…", "layers": {}, "statuses": {},
 "findings": [{"code": "…", "severity": "…", "area": "…"}]}
```
