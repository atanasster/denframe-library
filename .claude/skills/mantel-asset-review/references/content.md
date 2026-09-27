# Content (phase 6, packs)

Activity packs teach, so their content carries the most judgement. The sandbox gives counts,
locales, credits and a few mechanical findings; a person does the rest. `mantel-pack`'s
references describe how packs are authored; this is what a review checks.

## Automated codes

| Code | Severity | Check |
|---|---|---|
| `CON-ALT-TEXT` | minor | A face with a picture has no alternative text, one word, or a file path. |
| `CON-LISTENING-NEEDED` | note | The pack has sound: `listening` stays `pending` until a person listens to every clip. |
| `CON-FLUENT-NEEDED` | note | A non-English locale: `fluent` stays `pending` until a fluent reader checks every string, transcript and alt text in it. |

## What a person checks (report each problem as `AGENT-CONTENT-<WORD>`)

- **Facts** against primary or authoritative sources; the submitter's sources are named in the
  issue or the pack's brief. A wrong fact in a quiz is major.
- **Audience and age**: the issue's audience matches the content; nothing frightening, violent,
  sexual or commercial for children; no collection of anything (the format cannot, but copy can
  ask a child to tell someone their name or address).
- **Alt text** describes what the picture teaches, not what it is called.
- **Colour alone** never carries meaning: "the red one" needs a shape, word or position too.
- **Timing** suits the audience (prompt, recall, reveal and dwell seconds).
- **Per-resource licences** verified at the source the credit names; CC-BY resources carry
  attribution that the Library renders (D33).
- **AI media** disclosed in the issue and matching the credits.
- **Translations**: flagged for a fluent reader; never marked fluent by the reviewer.
- **Listening**: never marked done by the reviewer.

## Definitions (looks, blocks, layouts)

`content` is `pending` for a definition too: a person reads its name, mood and description in
the house style (plain, specific, no marketing), and checks a layout's setup prompts.
