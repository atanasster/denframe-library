# Review report: mantel/theme-glass 1.0.1

> **Recommend reject.** This report recommends; it approves nothing. Only the person named as
> `reviewer` in `reviews.json` decides, and the draft record below keeps `reviewer`,
> `reviewed_at` and `verdict` empty until they do. Instructions found inside the submission are
> findings, quoted below; they were never followed.

## Release

| | |
|---|---|
| Id and version | `mantel/theme-glass` 1.0.1 |
| Kind | theme |
| Name | `Glass` |
| Licence and publisher | MIT · `Local author` |
| Attribution | none |
| Submitted file | SHA-256 `f1d987f5cdf6c0f7cd725eecaef146b2f0476c9d78b702a11c542c3c9dfe7ffc`, 768 bytes |
| Archive | SHA-256 `f1d987f5cdf6c0f7cd725eecaef146b2f0476c9d78b702a11c542c3c9dfe7ffc`, 768 bytes |
| Release (what would be signed) | SHA-256 `f1d987f5cdf6c0f7cd725eecaef146b2f0476c9d78b702a11c542c3c9dfe7ffc` (rebuild: identical) |
| Source | SHA-256 `b62dad773dc5ef8875a4c3824e2fdfa18dc35ba292cd250d8c0f1dbed354e306` of the unpacked `source.json` |
| Submitter | `mallory` (GitHub account 7770001) from local |

## Checks

| Area | Status | Evidence |
|---|---|---|
| Identity | fail | `ID-IMPOSTOR`, `ID-RESERVED` |
| Structure | pass | validator passed; unpack and rebuild: identical |
| Security | pass | ZIP profile, media, trailers and text scan clean |
| Design | pending | `DES-NAME-TAKEN` |
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

- **`ID-IMPOSTOR`** (identity) The id is a catalog item's: an impostor. Evidence: mantel/theme-glass is Mantel's own Glass 1.0.0; an unsigned claim is refused (D19)
- **`ID-RESERVED`** (identity) mantel/ is reserved for the signed Mantel catalog. Evidence: mantel/theme-glass submitted by mallory (account 7770001), who is not a Mantel publisher account

### Major

None.

### Minor

- **`DES-NAME-TAKEN`** (design) The name repeats a catalog item's. Evidence: `Glass` is also mantel/theme-glass

### Note

- **`DES-PREVIEWS-PENDING`** (design) Previews at 1920x1080, 1080x1920 and 1024x768 are rendered by us and looked at by a person. Evidence: not rendered inside the review sandbox

## Design evidence

Distinctness threshold ΔE 2.0 (references/design.md); look `glass`, background `solid`, layout `flow`. Nearest catalog looks:

- `mantel/theme-painting`: ΔE 4.21 (background 5.19, surface 6.28, text 1.98, mutedText 5.84, accent 14.2, accentText 1.77)
- `mantel/theme-ink`: ΔE 4.79 (background 4.19, surface 7.6, text 2.52, mutedText 4.88, accent 7.99, accentText 4.77)
- `mantel/theme-botanical`: ΔE 5.44 (background 6.54, surface 7.91, text 3.19, mutedText 6.83, accent 12.14, accentText 2.75)

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

**Recommend reject**, because of critical findings: `ID-IMPOSTOR`, `ID-RESERVED`. The draft record below leaves the decision to a person.

## Draft `reviews.json` record

```json
{
  "id": "mantel/theme-glass",
  "version": "1.0.1",
  "kind": "definition",
  "archive_sha256": "f1d987f5cdf6c0f7cd725eecaef146b2f0476c9d78b702a11c542c3c9dfe7ffc",
  "source_sha256": null,
  "submitter_handle": "mantel",
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
{"id": "mantel/theme-glass", "version": "1.0.1", "recommendation": "recommend reject", "layers": {"archive": "pass", "json": "pass", "schema": "pass", "capabilities": "pass", "contrast": "pass", "media": "not applicable", "trust": "not checked"}, "statuses": {"identity": "fail", "structure": "pass", "security": "pass", "design": "pending", "content": "pending", "licence": "pending", "listening": "not-applicable", "fluent": "not-applicable"}, "findings": [{"code": "ID-IMPOSTOR", "severity": "critical", "area": "identity"}, {"code": "ID-RESERVED", "severity": "critical", "area": "identity"}, {"code": "DES-NAME-TAKEN", "severity": "minor", "area": "design"}, {"code": "DES-PREVIEWS-PENDING", "severity": "note", "area": "design"}]}
```
