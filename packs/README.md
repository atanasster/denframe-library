# Reference pack review candidates

These three self-contained sources contain 20 Bulgarian/English vocabulary items,
12 real animal-recording items, and 12 short thinking puzzles. They are **review
candidates, not approved teaching material**. `reviews.json` pins each source hash;
fluent, content and listening reviews are pending. Never promote them as reviewed
language learning packs or remove this distinction from the public catalog.

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

Build from this repository with the standalone toolchain:

```sh
mantel-author validate packs/first-words/source.json
mantel-author build packs/first-words/source.json first-words.mantelpack
```

Repeat for `animal-sounds` and `tiny-puzzles`. Output archives must not already
exist. Host preview tooling generates synthetic, silent author fixtures; it is separate
from this standalone build tool. Use local Library import to review audio
on a nominated test target; never test on household receivers by default.

Before promotion, reviewers must record name, date, exact source/archive hashes,
corrections, pronunciation/listening results and supported test devices. Changing
content requires a new release version once any archive has been distributed.
