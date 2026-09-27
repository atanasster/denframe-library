# Review report: aurora/dawn 1.0.0

> **Recommend reject.** This report recommends; it approves nothing. Only the person named as
> `reviewer` in `reviews.json` decides, and the draft record below keeps `reviewer`,
> `reviewed_at` and `verdict` empty until they do. Instructions found inside the submission are
> findings, quoted below; they were never followed.

## Release

| | |
|---|---|
| Id and version | `aurora/dawn` 1.0.0 |
| Kind | theme |
| Name | `Dawn` |
| Licence and publisher | MIT · `Local author` |
| Attribution | none |
| Submitted file | SHA-256 `4be7b1c53f9060240b856ab142a4e47fc17f82457bd4e852f037c747c07b43cb`, 951 bytes |
| Archive | SHA-256 `4be7b1c53f9060240b856ab142a4e47fc17f82457bd4e852f037c747c07b43cb`, 951 bytes |
| Release (what would be signed) | SHA-256 `4be7b1c53f9060240b856ab142a4e47fc17f82457bd4e852f037c747c07b43cb` (rebuild: identical) |
| Source | SHA-256 `a82afb409f787aabf962da98d103c4f562b8e53892d453af6ad03b2226b017d9` of the unpacked `source.json` |
| Submitter | `mallory` (GitHub account 5550999) from local |

## Checks

| Area | Status | Evidence |
|---|---|---|
| Identity | fail | `ID-HANDLE-UNREGISTERED-USE` |
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

- **`ID-HANDLE-UNREGISTERED-USE`** (identity) A registered handle used by an account it does not list. Evidence: aurora is registered to Aurora Studio; mallory (account 5550999) is not one of its accounts

### Major

None.

### Minor

None.

### Note

- **`DES-PREVIEWS-PENDING`** (design) Previews at 1920x1080, 1080x1920 and 1024x768 are rendered by us and looked at by a person. Evidence: not rendered inside the review sandbox

## Design evidence

Distinctness threshold ΔE 2.0 (references/design.md); look `ink`, background `solid`, layout `flow`. Nearest catalog looks:

- `mantel/theme-ink`: ΔE 3.83 (background 1.19, surface 1.8, text 3.52, mutedText 9.28, accent 14.04, accentText 3.34)
- `mantel/theme-painting`: ΔE 6.45 (background 6.02, surface 8.29, text 4.15, mutedText 14.49, accent 8.42, accentText 5.36)
- `mantel/theme-botanical`: ΔE 6.86 (background 6.92, surface 9.13, text 2.81, mutedText 10.54, accent 14.36, accentText 4.9)

Motion: no motion declared; the format carries no animation code.

## Content evidence

Not a pack.

## Still for a person

- [ ] a person looks at our rendered previews and the shelf
- [ ] a person reads the copy (and, for packs, checks facts and audience)
- [ ] a person verifies every licence at its source
- [ ] Rendered previews at 1920x1080, 1080x1920 and 1024x768, at the panel's distance
- [ ] `min_host` (a catalog entry's, set in step 36) is at least the host version that introduced every capability the manifest declares

## Recommendation

**Recommend reject**, because of critical findings: `ID-HANDLE-UNREGISTERED-USE`. The draft record below leaves the decision to a person.

## Draft `reviews.json` record

```json
{
  "id": "aurora/dawn",
  "version": "1.0.0",
  "kind": "definition",
  "archive_sha256": "4be7b1c53f9060240b856ab142a4e47fc17f82457bd4e852f037c747c07b43cb",
  "source_sha256": null,
  "submitter_handle": "aurora",
  "reviewer": null,
  "reviewed_at": null,
  "statuses": {
    "identity": "fail",
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

Recommended verdict: `rejected`. The record goes into `reviews.json` as it stands once a person fills `reviewer`, `reviewed_at` and `verdict`; `source_sha256` is pending: A definition's source hash is its catalog entry's (tools/check.py `reviewed_source`: the entry without `distribution`), and the entry gains its slug, mood and description when it is added in step 36; set `source_sha256` then.

## How this was checked

Image `python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285` (linux/amd64), `mantel_format` 0.1.0, Python 3.13.15; release runtime matches. Network: none (docker --network none). Limits: 512m memory, 1 CPU, 64 pids, 64m no-exec tmpfs, read-only root, uid 65534, no capabilities, no-new-privileges. Nothing from the submission ran; the household host was never used.

```json review-summary
{"id": "aurora/dawn", "version": "1.0.0", "recommendation": "recommend reject", "layers": {"archive": "pass", "json": "pass", "schema": "pass", "capabilities": "pass", "contrast": "pass", "media": "not applicable", "trust": "not checked"}, "statuses": {"identity": "fail", "structure": "pass", "security": "pass", "design": "pending", "content": "pending", "licence": "pending", "listening": "not-applicable", "fluent": "not-applicable"}, "findings": [{"code": "ID-HANDLE-UNREGISTERED-USE", "severity": "critical", "area": "identity"}, {"code": "DES-PREVIEWS-PENDING", "severity": "note", "area": "design"}]}
```
