# GTA 6 content playbook (learned from 22 reference clips)

Source: 22 TikTok reference clips sent by the owner (≈42 M total views), each analysed with Gemini video
understanding (frames + audio), local measurements (exact cuts, tempo, layout, black/blurred bands) and the
post's public engagement. Machine-readable copy: `config/style_examples/gta6.json` (loaded automatically).

Engagement = (likes + comments + shares + saves) / views.

## 1. Hype edit — highest engagement (median ≈ 0.16, up to 0.31)
Examples: @norage_ae 14.9 M views · @stackz_jm8 2.3 M · @moribontaru 1.2 M · @havoceeditz 1.1 M · @mfx.3dits · @tanartfact
- **Length** 13–33 s (median ≈ 17 s). **Shots 0.7–1.4 s** (40–80 cuts/min); slower "cinematic" variant: 3 s shots.
- **Cuts land on the beat** (phonk / Latin club / synthwave / trap); bass drop = biggest action shot.
- **Full-screen 9:16** trailer/gameplay, no captions, no boxes.
- **One short centred white line** (y ≈ 0.45–0.5), viewer's voice: "I can't wait to play as Lucia",
  "Literally next week btw...", "I need this game right now", countdown "844 DAYS → 127 DAYS → ARE YOU READY".
- **Ending**: hard cut to black on the last beat, or seamless loop back to the first shot.
- Produced by `python main.py hype make <trailer/gameplay files>` (beat-sync engine, see the recipe below).

## 2. Meme / "fake feature" skit — biggest reach (up to 4.1 M), lower engagement (0.03–0.18)
Examples: @gta_memes_sol ×6 (period system 4.1 M, shower scene 2.6 M, "not woke" 1.7 M …)
- **Black bars** above/below (30–50 % of height), 16:9 gameplay/machinima centred, **one take, 0 cuts**.
- **Headline in the top bar** (y ≈ 0.12–0.25), white, no box, often ending in 💀/☠:
  "GTA 6 reportedly features a realistic ___ system where ___" · "34 hours into GTA 6, you finally ___ and THIS happens".
- Optional **word-by-word captions** low (y ≈ 0.85–0.9), 3 words, UPPERCASE, red highlight (#FF0000/#FF204E).
- AI-voiced or in-game dialogue; SFX for the joke (punch, gunshot, baby cry, gasp).
- **Structure**: absurd premise → escalation → absurd payoff; ends on the punchline.
- Safer framing to keep the format without presenting it as real news: "POV: GTA 6 if ___", "What if GTA 6 had ___".

## 3. Streamer clip — steady performer (0.07–0.14, 0.3–1.4 M views)
Examples: @overtime (Agent 00 + "Lucia") 1.4 M · @onlyclipinn (Kai Cenat) 1.3 M · @gtbgringo.clips · @lacy · @therealmnent
- **Length** 8–37 s (median ≈ 29 s), **one take**, original stream audio, **no captions**.
- **Headline at the top** (y ≈ 0.10–0.20) — white box + black text or black box + white text, emojis 🔥😳👀💀:
  "[Streamer] [VERB] [GTA 6 thing] 🔥" — "Agent does a stream with Lucia from GTA 6 🔥",
  "Kai Cenat is OFFICIALLY the first streamer to PLAY GTA6 😨👀", "Braeden LEAKS the method on how to get RICH during GTA 6 💀👀🔥".
- Layout varies: black bars, blurred bands, split cam, full face — the text never sits on the streamer.
- **Ending**: punchline, cliffhanger or abrupt cut right after the payoff (drives rewatch).
- Extra seen once: a GTA-style "Mission Passed" payoff card + jingle (use our own look-alike, not Rockstar's asset).

## 4. News / info — weakest in the set (0.05)
@gtavlviralclips: AI voice-over, green bouncing captions, 57 s, subscribe CTA. Keep these shorter and lead with the payoff.

## Cross-cutting rules the machine applies
1. **Text never covers a face or the picture** (text safety), headline style per type from these examples.
2. **No captions on streamer clips by default**; captions only where the type uses them (memes, news).
3. **Length is per moment**: scored against the engagement-weighted length of the same type (no fixed limits);
   silent pauses inside a clip are cut (dead-air jump cuts).
4. **Endings**: cut right after the payoff or loop; never trail off.
5. **Detail tools** (zoom + circle/arrow + label, optional freeze) only when a visual detail is key —
   easter eggs, fun facts, comparisons, or when the speaker says "look at / did you see…". Seen in the
   reference set in the Leonida map edit (zoom-to-detail + arrow + label).

## Hype edit — frame-accurate recipe (second pass, 9 edits measured at 30 fps)
Raw numbers: `config/style_examples/gta6_hype_measurements.json`.

| Edit | Views | Len | BPM | Cuts | Median shot | Shot = beats | Cuts on beat | Opener |
|---|---|---|---|---|---|---|---|---|
| @norage_ae | 14.9 M | 14 s | 83 | 16 | 0.73 s | 1.0 | 94 % | 2.97 s |
| @stackz_jm8 | 2.3 M | 34 s | 94 | 31 | 0.67 s | 1.0 | 61 % (half-beat) | 2.73 s |
| @moribontaru | 1.2 M | 22 s | 143 | 10 | 1.6 s | 4 | 70 % (half-beat) | 2.3 s |
| @havoceeditz | 1.1 M | 14 s | ~136 | 16 | 0.77 s | ~2 | - | 0.7 s |
| @mfx.3dits | 0.5 M | 17 s | 176 | 21 | 0.70 s | 2.0 | 100 % (half-beat) | 0.7 s |
| @mt.editz.mt | 0.7 M | 11 s | 107 | 14 | 0.56 s | 1.0 | 93 % | 1.13 s |

1. **Structure: opener → drop → metronome → button.** One longer opening shot (2.3–3 s: car on a road, logo,
   aerial) while the music builds; the first cut lands on the drop; then every shot is exactly 1 beat
   (≈0.55–0.75 s) or 2 beats; the last shot is held ~1 beat longer or cut to black / looped to shot 1.
2. **Cut rate doubles or more after the drop** (norage 0.33 → 1.35 cuts/s; mt.editz 0.8 → 1.8).
3. **Shot order alternates**: wide/aerial → character close-up → action (drift, explosion, gunfire) → wide…,
   and day ↔ night / warm ↔ neon so every cut is a visible change. Never two similar shots in a row.
4. **Each shot starts on its motion peak** (car already sliding, gun already raised) — no dead frames.
5. **Text**: one line, centre, white, small; either a viewer thought ("I can't wait to play as Lucia") or a
   countdown that changes on the beat (879 → 617 → 342 → 91 DAYS → "ARE YOU READYYYYY"). Small creator
   watermark in the lower third on every shot.
6. **Look**: boosted contrast/saturation, flashes on kicks (8–11 flash frames in the fastest edits), motion-blur
   whip between some shots. The longer edit (@stackz_jm8) is a *narrative* montage: Rockstar-logo opener, a
   robbery told in order, trailer dialogue kept as the "vocals" over the beat, lines of dialogue as captions.
7. **Framing variants**: full-screen 9:16 crop; 16:9 with black bars; and footage rotated 90° to fill the
   screen (@norage_ae, the 14.9 M one).
8. **Length**: 11–17 s for pure beat edits (loop-friendly), 22–34 s only when there is a story or dialogue.

## Release-week memes (9 more references, 2026-11-14) — biggest reach in the niche
@gta_6.2026 5.6 M (7 % share rate) · @mr_lumbago1899 2.8 M (25 % engagement) · @morisofficial_ 1.9 M · @frostysheeps 1.6 M ·
@ryanpostvids 1.3 M · @el_rumano504 1.2 M · @jobagakes 0.7 M · @gaming.memeology 0.4 M
- **Formula: one relatable line + one famous reaction clip.** The line is the joke's setup, the clip is the payoff;
  no GTA footage needed at all in most of them.
- **The line** (white, top black bar or centred, no box): a date/time stamp ("19.11 - 00:01", "POV: 19 NOVEMBER 00:01",
  "Pov: it's November 19th 12:00 and you finally open gta6…"), "How it feels having GTA 6 downloaded rn",
  "how ALL of us will be waking up on november 19", "POV: Day before GTA VI", a fake system message
  ("This location is only accessible with the Ultimate Edition bundle." / "Me:").
- **The clip**: universally known reaction footage — someone driving like a maniac, a dog going for food, a crying
  athlete, Walter White kicking a door, Fast & Furious driving, a green-screen meme character composited in front of a
  GTA location (strip club, map with a pin circled).
- **Layouts**: black bars with the line in the top bar (most), split top/bottom (GTA map/image over the reaction),
  full frame with centred caption.
- **Length** 5–31 s; the 5-6 s one-joke loops have the highest share rates. **Sound** = the clip's own audio or one
  trending song; no captions besides the line.
- **Themes that work this week**: release-night rush (strip club / map pin), download/preload waiting, crying from the
  soundtrack, morning-of-release routine, paywall/edition jokes, the goth bartender character.
