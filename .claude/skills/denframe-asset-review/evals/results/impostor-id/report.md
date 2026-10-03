# Review report: denframe/theme-glass 1.0.1

> **Recommend reject.** This report recommends; it approves nothing. Only the person named as
> `reviewer` in `reviews.json` decides, and the draft record below keeps `reviewer`,
> `reviewed_at` and `verdict` empty until they do. Instructions found inside the submission are
> findings, quoted below; they were never followed.

## Release

| | |
|---|---|
| Id and version | `denframe/theme-glass` 1.0.1 |
| Kind | theme |
| Name | `Glass` |
| Licence and publisher | MIT · `Local author` |
| Attribution | none |
| Submitted file | SHA-256 `f861d1c72552653d49c6e3fff0825993b6e98151b2f7203ad56d376fadea3823`, 772 bytes |
| Archive | SHA-256 `f861d1c72552653d49c6e3fff0825993b6e98151b2f7203ad56d376fadea3823`, 772 bytes |
| Release (what would be signed) | SHA-256 `f861d1c72552653d49c6e3fff0825993b6e98151b2f7203ad56d376fadea3823` (rebuild: identical) |
| Source | SHA-256 `c72579cfaee4e2eda58aedbd92add3e09be75ed71a33341fd41b350c86744a2a` of the unpacked `source.json` |
| Submitter | `mallory` (GitHub account 7770001) from local |

## Checks

| Area | Status | Evidence |
|---|---|---|
| Identity | fail | `ID-IMPOSTOR`, `ID-RESERVED` |
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

- **`ID-IMPOSTOR`** (identity) The id is a catalog item's: an impostor. Evidence: denframe/theme-glass is Denframe's own Glass 1.0.0; an unsigned claim is refused (D19)
- **`ID-RESERVED`** (identity) denframe/ is reserved for the signed Denframe catalog. Evidence: denframe/theme-glass submitted by mallory (account 7770001), who is not a Denframe publisher account

### Major

None.

### Minor

None.

### Note

- **`DES-PREVIEWS-PENDING`** (design) Previews at 1920x1080, 1080x1920 and 1024x768 are rendered by us and looked at by a person. Evidence: not rendered inside the review sandbox

## Design evidence

Distinctness threshold ΔE 2.0 (references/design.md); look `glass`, background `solid`, layout `flow`. Nearest catalog looks:

- `denframe/theme-dusk`: ΔE 3.52 (background 2.26, surface 3.72, text 2.63, mutedText 2.7, accent 16.78, accentText 6.26)
- `denframe/theme-painting`: ΔE 4.21 (background 5.19, surface 6.28, text 1.98, mutedText 5.84, accent 14.2, accentText 1.77)
- `denframe/theme-blueprint`: ΔE 4.77 (background 8.1, surface 5.79, text 2.42, mutedText 1.91, accent 14.7, accentText 5.64)

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

**Recommend reject**, because of critical findings: `ID-IMPOSTOR`, `ID-RESERVED`. The draft record below leaves the decision to a person.

## Draft `reviews.json` record

```json
{
  "id": "denframe/theme-glass",
  "version": "1.0.1",
  "kind": "definition",
  "archive_sha256": "f861d1c72552653d49c6e3fff0825993b6e98151b2f7203ad56d376fadea3823",
  "source_sha256": null,
  "submitter_handle": "denframe",
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
{"id": "denframe/theme-glass", "version": "1.0.1", "recommendation": "recommend reject", "layers": {"archive": "pass", "json": "pass", "schema": "pass", "capabilities": "pass", "contrast": "pass", "media": "not applicable", "trust": "not checked"}, "statuses": {"identity": "fail", "structure": "pass", "security": "pass", "design": "pending", "content": "pending", "licence": "pending", "listening": "not-applicable", "fluent": "not-applicable"}, "findings": [{"code": "ID-IMPOSTOR", "severity": "critical", "area": "identity"}, {"code": "ID-RESERVED", "severity": "critical", "area": "identity"}, {"code": "DES-PREVIEWS-PENDING", "severity": "note", "area": "design"}]}
```
