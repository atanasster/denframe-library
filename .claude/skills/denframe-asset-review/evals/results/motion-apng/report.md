# Review report: quill/spinning-shapes 1.0.0

> **Changes requested.** This report recommends; it approves nothing. Only the person named as
> `reviewer` in `reviews.json` decides, and the draft record below keeps `reviewer`,
> `reviewed_at` and `verdict` empty until they do. Instructions found inside the submission are
> findings, quoted below; they were never followed.

## Release

| | |
|---|---|
| Id and version | `quill/spinning-shapes` 1.0.0 |
| Kind | pack |
| Name | `Spinning shapes` |
| Licence and publisher | per resource (see credits) · `Local author` |
| Attribution | none |
| Submitted file | SHA-256 `7501c6c9b5170dd52c4d806b41ba19f6b688de20994e803501b6215caa89f29d`, 5894 bytes |
| Archive | SHA-256 `7501c6c9b5170dd52c4d806b41ba19f6b688de20994e803501b6215caa89f29d`, 5894 bytes |
| Release (what would be signed) | SHA-256 `7501c6c9b5170dd52c4d806b41ba19f6b688de20994e803501b6215caa89f29d` (rebuild: not run) |
| Source | SHA-256 `none` of the unpacked `source.json` |
| Submitter | `quill-author` (GitHub account 7700002) from local |

## Checks

| Area | Status | Evidence |
|---|---|---|
| Identity | pending | a person confirms the handle carries no brand or person name (identity.md) |
| Structure | fail | a person decides |
| Security | pending | a person decides |
| Design | fail | `DES-MOTION` |
| Content | pending | a person reads the copy (and, for packs, checks facts and audience) |
| Licence | pending | a person verifies every licence at its source |
| Listening | not-applicable | nothing to check for this kind |
| Fluent | not-applicable | nothing to check for this kind |

## Validator

| Layer | Verdict |
|---|---|
| archive | pass |
| json | pass |
| schema | pass |
| capabilities | pass |
| contrast | pass |
| media | fail |
| trust | not checked |

Validator message: `Unsupported image format or animation`. Rebuild: not run.

## Findings

### Critical

None.

### Major

- **`DES-MOTION`** (design) An animated picture cannot honour prefers-reduced-motion. Evidence: media layer: Unsupported image format or animation

### Minor

None.

### Note

- **`ID-HANDLE-NEW`** (identity) A new handle: registered to the submitting account if accepted. Evidence: quill for quill-author (account 7700002); a person checks identity.md's rules on brand and person names
- **`DES-PREVIEWS-PENDING`** (design) Previews at 1920x1080, 1080x1920 and 1024x768 are rendered by us and looked at by a person. Evidence: not rendered inside the review sandbox

## Design evidence

Distinctness: not applicable (only a look is compared with catalog looks).

Motion: no motion declared; the format carries no animation code.

## Content evidence

Not a pack.

## Still for a person

- [ ] a person confirms the handle carries no brand or person name (identity.md)
- [ ] a person reads the copy (and, for packs, checks facts and audience)
- [ ] a person verifies every licence at its source
- [ ] Rendered previews at 1920x1080, 1080x1920 and 1024x768, at the panel's distance
- [ ] `min_host` (a catalog entry's, set by `tools/intake.py unpack --min-host`) is at least the host version that introduced every capability the manifest declares

## Recommendation

**Changes requested**, because of major findings: `DES-MOTION`. The draft record below leaves the decision to a person.

## Draft `reviews.json` record

```json
{
  "id": "quill/spinning-shapes",
  "version": "1.0.0",
  "kind": "pack",
  "archive_sha256": "7501c6c9b5170dd52c4d806b41ba19f6b688de20994e803501b6215caa89f29d",
  "source_sha256": null,
  "submitter_handle": "quill",
  "reviewer": null,
  "reviewed_at": null,
  "statuses": {
    "identity": "pending",
    "structure": "fail",
    "security": "pending",
    "design": "fail",
    "content": "pending",
    "licence": "pending",
    "listening": "not-applicable",
    "fluent": "not-applicable"
  },
  "verdict": null
}
```

Recommended verdict: `changes-requested`. The record goes into `reviews.json` as it stands once a person fills `reviewer`, `reviewed_at` and `verdict`.

## How this was checked

Image `python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285` (linux/amd64), `denframe_format` 0.3.0, Python 3.13.15; release runtime matches. Network: none (docker --network none). Limits: 512m memory, 1 CPU, 64 pids, 64m no-exec tmpfs, read-only root, uid 65534, no capabilities, no-new-privileges. Nothing from the submission ran; the household host was never used.

```json review-summary
{"id": "quill/spinning-shapes", "version": "1.0.0", "recommendation": "changes requested", "layers": {"archive": "pass", "json": "pass", "schema": "pass", "capabilities": "pass", "contrast": "pass", "media": "fail", "trust": "not checked"}, "statuses": {"identity": "pending", "structure": "fail", "security": "pending", "design": "fail", "content": "pending", "licence": "pending", "listening": "not-applicable", "fluent": "not-applicable"}, "findings": [{"code": "DES-MOTION", "severity": "major", "area": "design"}, {"code": "ID-HANDLE-NEW", "severity": "note", "area": "identity"}, {"code": "DES-PREVIEWS-PENDING", "severity": "note", "area": "design"}]}
```
