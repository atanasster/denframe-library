# Activity pack review candidates

Seven self-contained sources. The first three: 20 Bulgarian/English vocabulary items,
12 real animal-recording items and 12 short thinking puzzles. Four more, drawn in code (plan
step 39): **Tell the Time** (12 clock faces), **Moon & Sky** (12 Moon phases and star
patterns), **Shapes & Colours** (12 shape cards) -- English and Bulgarian -- and **Breathe**
(six breathing cycles, English, ending after the sixth). `catalog.json` places all seven in the `library`
distribution: they are offered online and do not ship inside Mantel. Tell the Time is planned
to become `included` only after a person reviews it (plan D5, step 40).
They are **review candidates, not approved teaching material**. The root `reviews.json` ledger pins each
source and archive hash with a `preview` verdict; fluent, content and listening reviews
are pending. Never promote them as reviewed language learning packs or remove this
distinction from the public catalog.

Text selection and puzzles were drafted for Mantel with AI assistance and are
provided under CC0-1.0. Vocabulary words and mathematical facts remain ordinary
words/facts. No Armodini text, illustrations, recordings, trademark or teaching
claims were copied.

Vocabulary speech was generated with eSpeak NG 1.52.0, native `bg` and `en`
procedural voices, 145 words/minute. No MBROLA voices or engine binaries are
redistributed. The engine author's [output permission](https://sourceforge.net/p/espeak/discussion/538920/thread/c6944a60/)
permits reuse of generated WAV speech; our original generated resources are
provided under CC0-1.0. This is synthetic reference speech, not a pronunciation
quality endorsement.

Animal recordings came from BigSoundBank. Every resource records its specific
source page and credited creator, where CC0 redistribution was stated when checked
on 2026-09-12. See the [site's license terms](https://bigsoundbank.com/licenses.html)
and each asset's `credit.source`. Source credits are retained even where optional.
Recordings were limited to their first six seconds, converted to mono 44.1 kHz
96 kbps MP3, normalized with FFmpeg `loudnorm=I=-20:TP=-3:LRA=7`, and stripped of
container metadata. The manifest marks modifications. Reviewers must confirm
that each excerpt actually contains the intended call and is comfortable to hear.
Two items distinguish cat meowing/purring; two distinguish hen calls. All have
visible text clues and answers when sound is unavailable.

The same MP3 conversion was applied to narration. Pack rebuilds copy these exact
checked-in bytes; they do not rerun a version-dependent synthesizer or encoder.
There are no remote asset fetches during build, install or playback. Nothing in
this folder is automatically installed or played.

## The drawn packs (step 39)

`tell-the-time/`, `moon-and-sky/`, `shapes-and-colours/` and `breathe/` each hold `source.json`,
`assets/`, a `brief.md` (audience, goals, order, timing, sources, simplifications) and a
`provenance.json` (every picture, the cards that show it, the toolchain, sources and review
status). Their `draw.py`, with the shared `drawing.py`, is the source of the pictures and the
card text: SVG drawn in Python, rasterised by librsvg (`rsvg-convert`), re-encoded by Pillow
as an 8-bit palette PNG with **no metadata chunks** (no text, time, colour profile or EXIF);
`provenance.json` records librsvg, cairo, Pillow and zlib, the versions that decide the bytes.
No font is used; clock numerals are drawn strokes. Run `python3 packs/<slug>/draw.py` from
the repository root to redraw; the committed bytes are what builds use.

- **Credits.** Every picture is original work by Mantel, **CC0-1.0**, with a per-resource
  credit (creator, licence, a one-line attribution and its source). Moon & Sky's star charts
  credit the positions and brightnesses they are drawn from in their attribution: *SIMBAD J2000
  values, SIMBAD database, operated at CDS, Strasbourg, France* (queried 27 September 2026); every
  credit's source is the pack's folder here. Its facts cite NASA Science pages,
  listed in its `brief.md`. The Library's item page and the website print these credits as
  text (D33); a card on the wall prints them under the card.
- **Alternative text** on every picture describes what it teaches (where the hands point, which
  side is lit, the outline and pattern of each shape). On a prompt face it never gives the
  answer: no side count on a counting card, the colours listed apart from the shapes on a colour
  card; the reveal face's alternative text tells everything.
- **Not by colour alone.** The clock hands differ by length and thickness; each colour in
  Shapes & Colours has its own pattern (solid, stripes, dots, slanted stripes, checks, grid).
- **Motion.** Nothing animates: the pictures are still PNGs, so reduced-motion viewers see
  exactly what everyone sees. Breathe's pace is the card's own 4/4/4/4 timing (approximate:
  the player pauses briefly between cards); its first card says to stop and breathe normally if
  dizzy.
- **AI assistance.** The card text, briefs and drawing code were drafted with AI assistance
  (Claude) and are review candidates. No image-generation model was used; the pictures are
  geometry. The disclosure travels with each archive: every picture's credit says "made in code
  with AI assistance".
- **Narration: none.** eSpeak NG, the only voice the plan allows for drafts (D26), was not
  available where these packs were drawn, so they carry no speech and no sound; every card is
  complete as text. A later release may add a disclosed synthetic draft.
- **Review.** Each release has a `preview` record in `reviews.json` (reviewer none; content,
  design, identity, licence and -- for Bulgarian -- fluent reading pending; listening not
  applicable). The review sandbox recommended approve with only its source-link notes.

## Preview pictures

`previews/<slug>-{landscape,portrait,square}.png` are captures of each pack's first card from
the real Mantel renderer (silent author fixture), **without the credits line**: the credits
are printed as text beside a preview instead (D33). Each `.json` beside them pins the source
it was captured from. The host's legacy signed pack release keeps the pictures it was signed
with (credits drawn in) until the owner re-signs it.

## Building

Build from this repository with the standalone toolchain:

```sh
mantel-author validate packs/first-words/source.json
mantel-author build packs/first-words/source.json first-words.mantelpack
```

Repeat for every other folder. Output archives must not already
exist. Host preview tooling generates synthetic, silent author fixtures; it is separate
from this standalone build tool. Use local Library import to review audio
on a nominated test target; never test on household receivers by default.

Before promotion, reviewers must record name, date, exact source/archive hashes,
corrections, pronunciation/listening results and supported test devices. Changing
content requires a new release version once any archive has been distributed.
