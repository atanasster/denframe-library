# Moon & Sky -- brief

**Assumptions.** Curious families (about ages 7 and up) in the Northern Hemisphere, where
Denframe's households are; the Moon cards say "seen from the Northern Hemisphere" wherever the
lit side matters. English and Bulgarian, one activity per language; text-first and silent (no
eSpeak NG where it was drawn; see `provenance.json`).

**Learning goals.** Name the Moon's main phases, tell growing (waxing) from shrinking (waning)
by the lit side, know the cycle is about 29.5 days; recognise five bright-star patterns and use
the Big Dipper to find Polaris.

**Order.** Full moon; first quarter; waxing crescent; waxing gibbous; last quarter; waning
crescent; the whole cycle; then the Big Dipper, Polaris from its pointer stars, Cassiopeia,
Orion, the Summer Triangle.

**Facts and sources** (URLs in `provenance.json`):
- phase names and order, the Moon always half lit, the ~29.5-day cycle: NASA Science, *Moon
  Phases*; NASA names the phase "third quarter", the card says "last quarter (also called third
  quarter)";
- Dubhe and Merak point to Polaris, which stays nearly still while other stars circle the pole:
  NASA Science, *What is the North Star and how do you find it?*;
- Cassiopeia's W or M: NASA Night Sky Network, February 2024 notes;
- the Summer Triangle's stars and constellations: NASA Night Sky Network, *The Summer
  Triangle's Hidden Treasures*;
- every star's position and brightness (SIMBAD J2000 values, whose reference varies by star --
  Hipparcos or Gaia -- and was not recorded per star), Cassiopeia and the Dipper on opposite
  sides of the pole (about 12 h of right ascension apart), Betelgeuse's red and Rigel's
  blue-white spectral types: SIMBAD (CDS, Strasbourg), queried 27 September 2026. The star
  charts are Denframe's own drawings; their credit's source is this folder, and their attribution
  names SIMBAD.

**Simplifications.** Star patterns are drawn north up, east left, as they might look overhead;
in the sky they turn through the night and the year. Cassiopeia is turned until Caph and Segin
stand level, so it reads as the W the card names -- the same stars as at another hour.
The pointer card draws the line from the bottom of the bowl (Merak) through Dubhe and out of
the bowl's open top, as NASA describes it. Every Moon card whose lit side matters says it is
seen from the Northern Hemisphere and that the south sees the other side lit. Star sizes stand for brightness only.
The Moon pictures are diagrams, not photographs.

**Pictures.** Twelve 800 x 800 drawings in code (`draw.py`): six Moon phases with the dark part
still drawn, a ring of eight phases with a clockwise arrow, and five star charts projected
(gnomonic) from the SIMBAD J2000 coordinates. Only Betelgeuse and Rigel are tinted; the text
names their colours.

**Timing.** Prompt 9 s, recall 4 s, reveal 11 s, dwell 2 s: 26 s a card, 5 min 12 s in all.

**Review.** The owner reviewed it on 28 September 2026 -- content (facts above), licence, design
(every picture) and a fluent Bulgarian reading passed (the Bulgarian star and phase names:
Голямата кола, Полярната звезда, Касиопея, Орион, Летният триъгълник, пълнолуние, първа и
последна четвърт, растящ/намаляващ сърп, растяща изпъкнала Луна; „при единия крак“ for Rigel);
no listening review is needed (no audio). 1.0.1 changes only the description, which no longer
calls it a review candidate; the cards and pictures are 1.0.0's.
