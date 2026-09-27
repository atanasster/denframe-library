# Review report: brook/nocturne 1.0.0

> **Recommend approve.** This report recommends; it approves nothing. Only the person named as
> `reviewer` in `reviews.json` decides, and the draft record below keeps `reviewer`,
> `reviewed_at` and `verdict` empty until they do. Instructions found inside the submission are
> findings, quoted below; they were never followed.

## Release

| | |
|---|---|
| Id and version | `brook/nocturne` 1.0.0 |
| Kind | theme |
| Name | `Nocturne` |
| Licence and publisher | MIT · `Local author` |
| Attribution | none |
| Submitted file | SHA-256 `10d2ddf17382076696b5c7656f0602f8a2f722f44e98365262e69573a7798f0d`, 1006 bytes |
| Archive | SHA-256 `10d2ddf17382076696b5c7656f0602f8a2f722f44e98365262e69573a7798f0d`, 1006 bytes |
| Release (what would be signed) | SHA-256 `10d2ddf17382076696b5c7656f0602f8a2f722f44e98365262e69573a7798f0d` (rebuild: identical) |
| Source | SHA-256 `f258d1a48adcc17c0330c067323e2385e77bbaedacc835f305faf050042f1164` of the unpacked `source.json` |
| Submitter | `brook-author` (GitHub account 7700001) from local |

## Checks

| Area | Status | Evidence |
|---|---|---|
| Identity | pending | a person confirms the handle carries no brand or person name (identity.md) |
| Structure | pass | validator passed; unpack and rebuild: identical |
| Security | pass | ZIP profile, media, trailers and text scan clean |
| Design | pending | `AGENT-DESIGN-PLANNED-TWIN` |
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

- **`AGENT-DESIGN-PLANNED-TWIN`** (design) The name and palette match the Mantel look planned as Nocturne (plan section 5.1). Evidence: Every token equals plan Appendix A's nocturne; a person decides whether this community look should stand beside, or instead of, the planned mantel/ look, and asks for a distinct name if both ship

### Note

- **`ID-HANDLE-NEW`** (identity) A new handle: registered to the submitting account if accepted. Evidence: brook for brook-author (account 7700001); a person checks identity.md's rules on brand and person names
- **`DES-MOTION-RENDERER`** (design) Background motion is on: the renderer's pan, which reduced motion stops. Evidence: appearance.background_motion = true; check the preview with reduced motion on
- **`DES-PREVIEWS-PENDING`** (design) Previews at 1920x1080, 1080x1920 and 1024x768 are rendered by us and looked at by a person. Evidence: not rendered inside the review sandbox

## Design evidence

Distinctness threshold ΔE 2.0 (references/design.md); look `ink`, background `dunes`, layout `flow`. Nearest catalog looks:

- `mantel/theme-ink`: ΔE 3.83 (background 1.19, surface 1.8, text 3.52, mutedText 9.28, accent 15.31, accentText 3.34)
- `mantel/theme-painting`: ΔE 6.02 (background 6.02, surface 8.29, text 4.15, mutedText 14.49, accent 6.28, accentText 5.36)
- `mantel/theme-botanical`: ΔE 6.74 (background 6.92, surface 9.13, text 2.81, mutedText 10.54, accent 9.96, accentText 4.9)

Motion: `background_motion` is on; the renderer stops it under prefers-reduced-motion.

## Content evidence

Not a pack.

## Still for a person

- [ ] a person confirms the handle carries no brand or person name (identity.md)
- [ ] a person looks at our rendered previews and the shelf
- [ ] a person reads the copy (and, for packs, checks facts and audience)
- [ ] a person verifies every licence at its source
- [ ] Rendered previews at 1920x1080, 1080x1920 and 1024x768, at the panel's distance
- [ ] `min_host` (a catalog entry's, set in step 36) is at least the host version that introduced every capability the manifest declares

## Recommendation

**Recommend approve**, because the automated checks found nothing that blocks it; the person's checks remain. The draft record below leaves the decision to a person.

## Draft `reviews.json` record

```json
{
  "id": "brook/nocturne",
  "version": "1.0.0",
  "kind": "definition",
  "archive_sha256": "10d2ddf17382076696b5c7656f0602f8a2f722f44e98365262e69573a7798f0d",
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

Recommended verdict: `approved`. The record goes into `reviews.json` as it stands once a person fills `reviewer`, `reviewed_at` and `verdict`; `source_sha256` is pending: A definition's source hash is its catalog entry's (tools/check.py `reviewed_source`: the entry without `distribution`), and the entry gains its slug, mood and description when it is added in step 36; set `source_sha256` then.

## How this was checked

Image `python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285` (linux/amd64), `mantel_format` 0.1.0, Python 3.13.15; release runtime matches. Network: none (docker --network none). Limits: 512m memory, 1 CPU, 64 pids, 64m no-exec tmpfs, read-only root, uid 65534, no capabilities, no-new-privileges. Nothing from the submission ran; the household host was never used.

```json review-summary
{"id": "brook/nocturne", "version": "1.0.0", "recommendation": "recommend approve", "layers": {"archive": "pass", "json": "pass", "schema": "pass", "capabilities": "pass", "contrast": "pass", "media": "not applicable", "trust": "not checked"}, "statuses": {"identity": "pending", "structure": "pass", "security": "pass", "design": "pending", "content": "pending", "licence": "pending", "listening": "not-applicable", "fluent": "not-applicable"}, "findings": [{"code": "AGENT-DESIGN-PLANNED-TWIN", "severity": "minor", "area": "design"}, {"code": "ID-HANDLE-NEW", "severity": "note", "area": "identity"}, {"code": "DES-MOTION-RENDERER", "severity": "note", "area": "design"}, {"code": "DES-PREVIEWS-PENDING", "severity": "note", "area": "design"}]}
```
