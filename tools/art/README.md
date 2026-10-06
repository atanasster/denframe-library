# Art collections: curation

An art collection (a `gallery` pack, art backgrounds plan D2) is curated with this tool, at
authoring time. The host never asks a museum for these works (D3): what is committed under the
public library's `packs/<slug>/` (the curation beside its `source.json`) is what a build packs
(D12).

The tool lives in the host repository, beside the other library tooling it mirrors to the public
repository; `library/src` is the public repository's pinned tree and changes only through a
public source release.

```sh
python scripts/art/curate.py library/src/packs/<slug>/brief.json
```

`brief.json` names the collection (`slug`, `name`, `description`, and for a pack source its
`id`, `version` and optional `publisher`), its `shape` (`landscape` or `portrait`) and, in order,
each work as `{"provider": …, "object_id": …}`, with an `alt_text` for screen readers. The run writes, beside
the brief:

- `assets/<sha256>.jpg`: each admitted work's receiver derivative;
- `assets/<sha256>.webp`: its thumbnail, and the strip of the collection's first three works;
- `source.json`: when the brief names a pack `id` and `version`, the gallery pack source the
  library builds (a `gallery` definition, validated by the format);
- `curation.json`: every admitted work (file, size, orientation, mean colour, placard, rights
  evidence) and every refused one with its reasons;
- `contact-sheet.html`: the admitted works at screen size, for the review.

## The rules

A work is admitted only when its provider's own rights signal says public domain / CC0 (D6.1,
D7) and it passes every rule below. Works outside a rule are refused, never cropped or repaired.

| Rule | Check |
| --- | --- |
| D6.2 Never upscaled | The source covers its fitted size in the shape's box: 1920x1080 for landscape, 1080x1920 for portrait. |
| D6.3 Shape | Width over height between 1.25 and 2.1 (landscape) or 0.5 and 0.8 (portrait). |
| D6.4 Tone | Mean luminance between 0.12 and 0.85, and at most 25% of the picture blown out (above 0.98) or crushed (below 0.02). |
| D6.7 Placard | A title, a creator and a date. The creator is put on one line: a museum's extra lines (nationality, dates) go in brackets. |

Two rules are a person's, on the contact sheet: **subject** (no violence, death, nudity,
devotional scenes or distress: a screen is on all day in a family room) and **variety** (at most
two works by one creator, which `curation.json`'s `review_notes` flags, and a spread of colour).

## The files (D5)

- Derivative: fitted to the shape's box, sRGB, every piece of metadata stripped, progressive
  JPEG at quality 82.
- Thumbnail and strip: WebP, at most 60 KB each (library assets plan D32).

The same source makes the same bytes, so a re-run reproduces what `curation.json` names.

## Providers

| Name in a brief | Museum | Rights signal | Image |
| --- | --- | --- | --- |
| `met` | The Metropolitan Museum of Art | `isPublicDomain` is true | `primaryImage`, full size |
| `aic` | Art Institute of Chicago | `is_public_domain` is true | IIIF at 1686 px wide (the museum prefers 843 unless there is a clear need; a wall screen is one) |
| `cleveland` | The Cleveland Museum of Art | `share_license_status` is `CC0` | the `print` image, else `web` |
| `nga` | National Gallery of Art, Washington | `openaccess` is `1` on the primary published image | IIIF, at most 2400 px on the long side |

The NGA publishes CSV files, not an API: point `NGA_OPENDATA` at a checkout of
<https://github.com/NationalGalleryOfArt/opendata> before curating from it.

## Asking museums

Works are fetched one at a time, with a pause of a second between two from the same provider,
as museums ask of their open APIs. A provider (`art_providers.py`) admits a work only on its own
rights signal. `art_fetch.py` holds every request to the host's remote-fetch policy as far as a
curator's machine needs it: HTTPS on port 443 to the provider's own hosts, no credentials in a
URL, every redirect hop checked, no private or loopback address, one overall deadline and a
size limit. It does not pin the connection to the address it checked, as the host does. A
fetch that fails refuses that work; the rest of the run goes on.
