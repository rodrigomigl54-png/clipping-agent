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
- Not yet produced by the machine automatically (needs the beat-sync montage engine).

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
