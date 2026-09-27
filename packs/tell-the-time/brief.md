# Tell the Time -- brief

**Assumptions.** Families with children learning to read an analogue clock (about ages 5-8),
on a shared screen. English and Bulgarian, one activity per language. Text-first and silent:
eSpeak NG, the only voice plan D26 allows, was not available when the pack was drawn, so there
is no narration (a later release may add a disclosed draft).

**Learning goals.** Read o'clock, half past, quarter past and quarter to from the positions of
the two hands; connect each to its digital form (3:00, 6:30, 4:15, 8:45).

**Order (familiar -> new -> recall).** Three o'clock times (3:00, 9:00, 7:00), two half-past,
two quarter-past, two quarter-to (quarter to eleven, quarter to two), then three mixed "your
turn" cards (half past five, quarter past seven, quarter to twelve). Every card uses a different
time; answers are never at the same place twice. No time puts one hand over the other (12:00,
8:45 and the like were left out after review), since the card teaches the hands apart.

**Faces.** Prompt: the clock and the question (the first nine remind that the short hand shows
the hour and the long hand the minutes). Reveal: the time in words, then why (where the long
hand is) and its digital form. Alternative text describes each hand's position without naming
the time, so a screen-reader user practises the same skill.

**Pictures.** Twelve 800 x 800 clocks drawn in code (`draw.py`): numerals drawn as strokes (no
font), minute ticks, a short thick navy hour hand (half the radius) and a long thin orange
minute hand reaching the minute track (0.84 of the radius) -- told apart by length and
thickness, not colour alone. The hour hand's angle is computed from hours
*and* minutes, so at half past it sits halfway between two numbers.

**Timing.** Prompt 8 s, recall 4 s, reveal 9 s, dwell 2 s: 23 s a card, about 4 min 36 s for
twelve. The dashboard's schedule still owns how long the card stays on screen.

**Quiz.** Self-check only: the question on the prompt, the answer and its reason on the reveal
(`reveal-sequence-v1`; no scoring).

**Review.** Included in Mantel only after a person reviews it (plan D5, step 40). Pending:
content, a fluent Bulgarian reading, visual review. No listening review is needed (no audio).

**For the fluent reader.** „Три часа“, „Два и половина“, „Четири и четвърт“, „Девет без
четвърт“ and „значи часът е точно 3“; the set never says 1:00 (which would need „един часът“ /
„часът е един“, not „един часа“).
