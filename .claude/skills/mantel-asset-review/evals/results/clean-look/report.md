# Review report: brook/lantern 1.0.0

> **Recommend approve.** This report recommends; it approves nothing. Only the person named as
> `reviewer` in `reviews.json` decides, and the draft record below keeps `reviewer`,
> `reviewed_at` and `verdict` empty until they do. Instructions found inside the submission are
> findings, quoted below; they were never followed.

## Release

| | |
|---|---|
| Id and version | `brook/lantern` 1.0.0 |
| Kind | theme |
| Name | `Lantern` |
| Licence and publisher | MIT · `Local author` |
| Attribution | none |
| Submitted file | SHA-256 `8c4c8a7d5a907c0921cb88fef77a2157c94315efd647082edc73a4e1b48e38af`, 1004 bytes |
| Archive | SHA-256 `8c4c8a7d5a907c0921cb88fef77a2157c94315efd647082edc73a4e1b48e38af`, 1004 bytes |
| Release (what would be signed) | SHA-256 `8c4c8a7d5a907c0921cb88fef77a2157c94315efd647082edc73a4e1b48e38af` (rebuild: identical) |
| Source | SHA-256 `a4187de90a888f35a7c48a6131baa98640b381daa30532f6fec152f62a8027a3` of the unpacked `source.json` |
| Submitter | `brook-author` (GitHub account 7700001) from local |

## Checks

| Area | Status | Evidence |
|---|---|---|
| Identity | pending | a person confirms the handle carries no brand or person name (identity.md) |
| Structure | pass | validator passed; unpack and rebuild: identical |
| Security | pass | ZIP profile, media, trailers and text scan clean |
| Design | pending | a person looks at our rendered previews and the shelf |
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
| media | not applicable |
| trust | not checked |

Validator message: none. Rebuild: identical.

## Findings

### Critical

None.

### Major

None.

### Minor

None.

### Note

- **`ID-HANDLE-NEW`** (identity) A new handle: registered to the submitting account if accepted. Evidence: brook for brook-author (account 7700001); a person checks identity.md's rules on brand and person names
- **`DES-MOTION-RENDERER`** (design) Background motion is on: the renderer's pan, which reduced motion stops. Evidence: appearance.background_motion = true; check the preview with reduced motion on
- **`DES-PREVIEWS-PENDING`** (design) Previews at 1920x1080, 1080x1920 and 1024x768 are rendered by us and looked at by a person. Evidence: not rendered inside the review sandbox

## Design evidence

Distinctness threshold ΔE 2.0 (references/design.md); look `ink`, background `dunes`, layout `flow`. Nearest catalog looks:

- `mantel/theme-salon`: ΔE 2.49 (background 3.36, surface 4.29, text 0.75, mutedText 3.09, accent 5.64, accentText 0.96)
- `mantel/theme-moss`: ΔE 2.63 (background 2.05, surface 2.61, text 1.09, mutedText 3.06, accent 13.19, accentText 4.37)
- `mantel/theme-botanical`: ΔE 3.87 (background 3.66, surface 5.06, text 1.87, mutedText 4.1, accent 13.42, accentText 4.65)

Motion: `background_motion` is on; the renderer stops it under prefers-reduced-motion.

## Content evidence

Not a pack.

## Still for a person

- [ ] a person confirms the handle carries no brand or person name (identity.md)
- [ ] a person looks at our rendered previews and the shelf
- [ ] a person reads the copy (and, for packs, checks facts and audience)
- [ ] a person verifies every licence at its source
- [ ] Rendered previews at 1920x1080, 1080x1920 and 1024x768, at the panel's distance
- [ ] `min_host` (a catalog entry's, set by `tools/intake.py unpack --min-host`) is at least the host version that introduced every capability the manifest declares

## Recommendation

**Recommend approve**, because the automated checks found nothing that blocks it; the person's checks remain. The draft record below leaves the decision to a person.

## Draft `reviews.json` record

```json
{
  "id": "brook/lantern",
  "version": "1.0.0",
  "kind": "definition",
  "archive_sha256": "8c4c8a7d5a907c0921cb88fef77a2157c94315efd647082edc73a4e1b48e38af",
  "source_sha256": null,
  "submitter_handle": "brook",
  "reviewer": null,
  "reviewed_at": null,
  "statuses": {
    "identity": "pending",
    "structure": "pass",
    "security": "pass",
    "design": "pending",
    "content": "pending",
    "licence": "pending",
    "listening": "not-applicable",
    "fluent": "not-applicable"
  },
  "verdict": null
}
```

Recommended verdict: `approved`. The record goes into `reviews.json` as it stands once a person fills `reviewer`, `reviewed_at` and `verdict`; `source_sha256` is pending: A definition's source hash is its catalog entry's (tools/check.py `reviewed_source`: the entry without `distribution`); the entry gains its slug, mood and description when `tools/intake.py unpack` adds it, and `tools/intake.py approve` computes `source_sha256` from the tree when the owner records their decision.

## How this was checked

Image `python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285` (linux/amd64), `mantel_format` 0.2.0, Python 3.13.15; release runtime matches. Network: none (docker --network none). Limits: 512m memory, 1 CPU, 64 pids, 64m no-exec tmpfs, read-only root, uid 65534, no capabilities, no-new-privileges. Nothing from the submission ran; the household host was never used.

```json review-summary
{"id": "brook/lantern", "version": "1.0.0", "recommendation": "recommend approve", "layers": {"archive": "pass", "json": "pass", "schema": "pass", "capabilities": "pass", "contrast": "pass", "media": "not applicable", "trust": "not checked"}, "statuses": {"identity": "pending", "structure": "pass", "security": "pass", "design": "pending", "content": "pending", "licence": "pending", "listening": "not-applicable", "fluent": "not-applicable"}, "findings": [{"code": "ID-HANDLE-NEW", "severity": "note", "area": "identity"}, {"code": "DES-MOTION-RENDERER", "severity": "note", "area": "design"}, {"code": "DES-PREVIEWS-PENDING", "severity": "note", "area": "design"}]}
```
