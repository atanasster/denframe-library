# Identity (phase 2)

Who may publish an id (D19), and the handle rules the registry follows. The registry is
`publishers.json` in the public repository: each handle maps to GitHub account ids (numbers --
logins change) and a display name. Only those accounts submit under it.

## Checks and codes

| Code | Severity | Rule |
|---|---|---|
| `ID-RESERVED` | critical | `mantel/` is the signed catalog's. Only an account registered to the `mantel` handle submits under it. |
| `ID-IMPOSTOR` | critical | The id is a catalog item's, claimed by an account the registry does not list for its handle. An unsigned claim on a signed id is refused (S1–S3). |
| `ID-LOCAL` | major | `local/` marks a household's own export. Rebuild under the submitter's handle. |
| `ID-HANDLE-UNREGISTERED-USE` | critical | The handle is registered, but not to the submitting account. |
| `ID-HANDLE-NEW` | note | A new handle. If the submission is accepted, `tools/intake.py register` binds it to the submitting account id. |
| `ID-HANDLE-RESERVED-WORD` | major | The handle is a brand, platform, vendor or role (`RESERVED_HANDLES` in `container/review_checks.py`). |
| `ID-HANDLE-LOOKALIKE` | major | Against **registered publishers** (and `mantel`): the handle folds to, is one edit from, or (for a handle of five letters or more) contains theirs -- the website's submit page makes the same comparison, with the same folding (`rn`→`m`, `vv`→`w`, `cl`→`d`, `0`→`o`, `1`/`i`→`l`, `5`→`s`, `3`→`e`, `4`→`a`; separators dropped). Against **reserved words** only folded equality counts (`t3am` is `team`; `beam`, `preview` and `ecosystem` are fine); the website does not check reserved words. |
| `ID-HANDLE-MISMATCH` | major | (Person.) The handle the issue claims differs from the id's namespace. |
| `ID-VERSION-NOT-BUMPED` | major | An update to a catalog id must raise its version. |
| `ID-SAME-NAME` | minor | The id's name part repeats a catalog item's under another handle. |
| `ID-CONFUSABLE-NAME` | major | A name or publisher mixes Latin with Cyrillic or Greek letters in one word. Other scripts mix freely (right-to-left and emoji names are allowed). |
| `ID-UNREADABLE` | major | No id could be read. |
| `LIC-INVALID` | major | The licence is not MIT, CC0-1.0 or CC-BY-4.0, or CC-BY lacks attribution. |

The id's grammar, controls and bidi characters are the validator's (`SEC-TEXT-ENCODING`,
`STRUCT-SCHEMA`).

## Handle rules a person applies

Confirmed by the owner (`atanasster`) on 27 September 2026, as written below.

- **Brand and person names.** No handle names a company, product, platform or public figure the
  submitter does not represent, or a private person other than the submitter. Evidence of
  representation (an official account, a verified domain) goes in the report; without it the
  finding is `AGENT-IDENTITY-BRAND` (major).
- **Squatting.** A new handle must be used: the first submission under it is the reason it is
  registered. Handles are not reserved in advance, and a handle registered with no accepted
  asset for 12 months may be released.
- **Transfer.** A handle moves to another account only by a pull request to `publishers.json`
  approved from an account already listed for it, or -- when every listed account is gone -- by
  the owner after a public issue has stood for 30 days. The old account ids stay in the pull
  request's history.
- **Abandonment.** A handle whose accounts are all deleted keeps its published assets; updates
  stop until a transfer. The handle is never reissued to someone else for the same assets.
- **Display names** follow the same rules as handles and are shown as *By {publisher}*.
- **Accepted items** show *By {publisher} · reviewed by Mantel*. There are no third-party
  signing keys: Mantel signs every release.
