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
| Submitted file | SHA-256 `72c1a904f5ae271b4552326e4ec04d0ae61877aee2115b6e82b2d909c003fa3f`, 953 bytes |
| Archive | SHA-256 `72c1a904f5ae271b4552326e4ec04d0ae61877aee2115b6e82b2d909c003fa3f`, 953 bytes |
| Release (what would be signed) | SHA-256 `72c1a904f5ae271b4552326e4ec04d0ae61877aee2115b6e82b2d909c003fa3f` (rebuild: identical) |
| Source | SHA-256 `4883477d61998e3c30d221cf5f3ef054405171aca3072ee8080719a50cdc170b` of the unpacked `source.json` |
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

- `denframe/theme-salon`: ΔE 2.49 (background 3.36, surface 4.29, text 0.75, mutedText 3.09, accent 6.73, accentText 0.96)
- `denframe/theme-moss`: ΔE 2.63 (background 2.05, surface 2.61, text 1.09, mutedText 3.06, accent 12.44, accentText 4.37)
- `denframe/theme-dusk`: ΔE 3.82 (background 7.27, surface 9.08, text 2.35, mutedText 7.8, accent 0.0, accentText 1.67)

Motion: no motion declared; the format carries no animation code.

## Content evidence

Not a pack.

## Still for a person

- [ ] a person looks at our rendered previews and the shelf
- [ ] a person reads the copy (and, for packs, checks facts and audience)
- [ ] a person verifies every licence at its source
- [ ] Rendered previews at 1920x1080, 1080x1920 and 1024x768, at the panel's distance
- [ ] `min_host` (a catalog entry's, set by `tools/intake.py unpack --min-host`) is at least the host version that introduced every capability the manifest declares

## Recommendation

**Recommend reject**, because of critical findings: `ID-HANDLE-UNREGISTERED-USE`. The draft record below leaves the decision to a person.

## Draft `reviews.json` record

```json
{
  "id": "aurora/dawn",
  "version": "1.0.0",
  "kind": "definition",
  "archive_sha256": "72c1a904f5ae271b4552326e4ec04d0ae61877aee2115b6e82b2d909c003fa3f",
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

Recommended verdict: `rejected`. The record goes into `reviews.json` as it stands once a person fills `reviewer`, `reviewed_at` and `verdict`; `source_sha256` is pending: A definition's source hash is its catalog entry's (tools/check.py `reviewed_source`: the entry without `distribution`); the entry gains its slug, mood and description when `tools/intake.py unpack` adds it, and `tools/intake.py approve` computes `source_sha256` from the tree when the owner records their decision.

## How this was checked

Image `python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285` (linux/amd64), `denframe_format` 0.3.0, Python 3.13.15; release runtime matches. Network: none (docker --network none). Limits: 512m memory, 1 CPU, 64 pids, 64m no-exec tmpfs, read-only root, uid 65534, no capabilities, no-new-privileges. Nothing from the submission ran; the household host was never used.

```json review-summary
{"id": "aurora/dawn", "version": "1.0.0", "recommendation": "recommend reject", "layers": {"archive": "pass", "json": "pass", "schema": "pass", "capabilities": "pass", "contrast": "pass", "media": "not applicable", "trust": "not checked"}, "statuses": {"identity": "fail", "structure": "pass", "security": "pass", "design": "pending", "content": "pending", "licence": "pending", "listening": "not-applicable", "fluent": "not-applicable"}, "findings": [{"code": "ID-HANDLE-UNREGISTERED-USE", "severity": "critical", "area": "identity"}, {"code": "DES-PREVIEWS-PENDING", "severity": "note", "area": "design"}]}
```
