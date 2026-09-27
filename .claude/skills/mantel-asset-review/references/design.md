# Design (phase 5)

The contrast gate and distinctness are automated; fit, legibility, copy and the shelf are a
person's, from previews we render. The dashboard-design skill
(`.claude/skills/dashboard-design/SKILL.md`) is the reference for how a good Mantel look,
layout and block reads on the wall.

## Automated codes

| Code | Severity | Check |
|---|---|---|
| `DES-CONTRAST` | major | The palette fails the one contrast gate (`mantel_format.palette_contrast`, 4.5:1 for every text pair, the picture scrim included). A hand-edited archive can carry a palette `mantel-author` would refuse; the validator's schema or contrast layer catches it. |
| `DES-NOT-DISTINCT` | major | A look sits closer than the threshold below to a catalog look. |
| `DES-MOTION` | major | An animated picture (APNG, animated WebP): it would move regardless of `prefers-reduced-motion`. The validator refuses it at the media layer. |
| `DES-MOTION-RENDERER` | note | `appearance.background_motion` is on: the renderer's slow pan, which `display.css` stops under `prefers-reduced-motion: reduce`. Check the preview both ways. |
| `DES-NAME-TAKEN` | minor | The name repeats a catalog item's. |
| `DES-PREVIEWS-PENDING` | note | Always: previews are rendered by us and looked at by a person (below). |

## Distinctness

A new look must differ from every catalog look *beyond swapping one accent* (plan §5.1).

**Measure** (`scripts/container/palette.py`). Resolve the look's palette (its base look's
tokens with its own over them). For each of the six roles that make a look recognisable --
`background`, `surface`, `text`, `mutedText`, `accent`, `accentText` -- take the OKLab distance
to the catalog look's same role, ×100 (so 1.0 here is 0.01 in OKLab units). **Drop the single
largest** of the six and average the other five. Dropping the largest makes a one-colour swap
score like the original: a catalog look with only a new accent measures 0.0. Border and the two
status colours are left out -- every shipped look uses near-identical positive/negative hues.

**Threshold: 2.0.** A submitted look fails when its distance to any *other* catalog look is
below 2.0. An update is never compared with the release it replaces (same id).

**How it was chosen** (27 September 2026, `sandbox.py calibrate` in the pinned image):

- The six catalogued looks' closest pair is Botanical–Painting at **2.49**, then Linen–Modern
  at 2.63; every other pair is above 4.2. The threshold sits about 20% under the closest pair
  the owner has already accepted as distinct, so every shipped look clears it with margin.
- 2.0 is roughly one OKLab just-noticeable difference (CSS Color 4's gamut mapping uses 0.02,
  i.e. 2.0 here) averaged across five roles: a near-copy with every colour nudged
  imperceptibly fails; a look with its own surface, type and accent passes. The calibration
  above carries the decision; the perceptual reading only says what the number means.
- The measure compares palettes only: a look that swaps its background and surface for the
  opposite family scores high, and a person still judges whether it reads as new.
- Against plan §5.1's ten planned looks: every planned look clears every catalogued look (the
  closest are Riso–Modern 2.01 and Fjord–Modern 2.20), but three planned looks sit under 2.0 of
  *each other*: **Fjord–Riso 1.84** and **Fjord–Harbour 1.87** (Harbour–Riso 2.08 passes).
  Whichever of them is reviewed after another is catalogued fails `DES-NOT-DISTINCT` until its
  palette moves -- a decision for step 37 (move Fjord's surfaces or type, or have the owner accept
  the pair with its different background and layout as the difference).

The report also names the base look, background kind and layout. A person may weigh a
different illustrated background or layout as distinctness the palette measure cannot see, but
records that as their decision; the finding stays.

## What a person checks (report each problem as `AGENT-DESIGN-<WORD>`)

- **Previews rendered by us** at 1920×1080, 1080×1920 and 1024×768, never the submitter's
  images. The sandbox does not render; use the website's own renderer offline -- the local
  build of `/library/submit` checks the file and draws the three shapes in the browser without
  uploading it (`npm --prefix frontend run dev:site`) -- or, for a catalog candidate, the
  preview captures step 36 makes. Never import into the household host to look at it.
- **Fit and geometry**: nothing clipped, overlapping or scrolling at the three shapes; a layout's
  landscape and portrait arrangements both read.
- **Legibility at the panel's default distance** (the dashboard-design skill's type scale).
- **House-style copy**: mood ≤ 60 characters; plain voice, no marketing; names short enough for
  the shelf card.
- **Naming**: unique beside its shelf and the catalog.
- **The shelf**: it sits well beside the looks around it in the Library.
- **Reduced motion**: with `prefers-reduced-motion: reduce`, nothing moves.
- **Localized strings** (`localized`, D33) complete for every locale they name.
