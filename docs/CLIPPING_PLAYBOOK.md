# Clipping playbook (learned 2026-11-22)

How AI clippers (OpusClip, Klap, StreamLadder…) pick and build clips, and how we do the same for free.

## 1. How the tools score a moment
OpusClip's "Virality Score" (0–99) rates every clip on four things
([help.opus.pro](https://help.opus.pro/docs/article/virality-score)):

| | Question | Our signal (scripts/tools/find_moments.py) |
|---|---|---|
| **Hook** | Does the first 1–3 s stop the scroll? | loudness vs. local baseline + hook/surprise words + "!"/"?" in the first 3 s |
| **Flow** | Starts and ends cleanly, complete thought? | starts on a sentence (not "and/so/but…"), ends on a sentence end, little dead air |
| **Value** | Emotion / payoff people share? | peak height, laughs, screams, "oh my god", arguments, emotion words |
| **Trend** | Fits what people care about now? | trend words (GTA 6, Mandy, Lucia, cops, stars, ending…) from the morning research |

Total = 0.35·Hook + 0.2·Flow + 0.3·Value + 0.15·Trend. Use the score to **sort**, then check by eye. The
tools say the same: sort by the score, don't trust it blindly.

Extra free signals:
* **YouTube "Most replayed" heatmap**: the best signal there is, because people rewound to those spots. It only
  shows on videos with roughly 50K views or more. From this cloud machine YouTube blocks watch pages, so check
  the graph on the phone (drag the progress bar) and send the timestamps.
* **"Market heatmap"**: what other clippers already cut from the same stream, and how it did (morning research).
  If a moment already went viral, do the same moment with a better hook and title. If nothing has been clipped
  yet, being first is the advantage.

## 2. How the clip is built
1. **Start on the reaction, not the setup.** If the setup is needed, put the payoff first as a **cold open**:
   the loudest 1.5–2.5 s, a quick rewind, then the story.
2. **0–3 s hook, 3–5 s promise** (headline tells what's coming), then the story, then end right after the payoff.
   No outro.
3. **Jump cuts**: cut every quiet pause over ~0.45 s. Keep loud pauses (gunshots, screams).
4. **Big subject**: fill the frame (4:5 crop) where quality allows (≤2x upscale); else full frame on a blurred
   background.
5. **Captions** of 1–3 words, active word coloured. They are the visual anchor and many people watch muted.
6. **Progress bar** at the bottom.
7. Length 15–60 s; one moment = one clip; one story can join 2–4 parts if every cut moves it forward.

## 3. Titles / on-screen headline (clickbait that keeps people watching)
Clipping tools write 3 variants per clip: **bold claim**, **curiosity gap**, **direct call-out**. The best GTA 6
clip channel right now (Speedy Boykins, 3.6M views on one Short) uses the same formula every time:

`[Streamer] [STRONG VERB IN CAPS] [concrete thing] In GTA 6 [emoji] ([twist])`
* iShowSpeed Finds A HULK-LIKE MONSTER In GTA 6 😱
* iShowSpeed Gets BITTEN By An Alligator In GTA 6 😭🐊 (ALMOST DIES)
* iShowSpeed Helps Animal Activists FREE A Polar Bear In GTA 6 😭💀 (GOES WRONG)

Rules:
* Name the streamer (campaign rule too) and say the concrete thing that happens, never "funny moment".
* Open a gap the clip closes: "…IT WENT WRONG", "WAIT FOR…", "18 SECONDS LATER:". Promise only what is in
  the clip, because a broken promise kills retention and gets reported.
* On-screen headline at most 2 lines, about 6 words each, name in yellow.

## 4. Free open-source alternatives (for reference, not installed)
ClipsAI (Python, WhisperX + clip boundaries), AI-Youtube-Shorts-Generator (Whisper + LLM highlights),
OpenShorts, SupoClip. They do what find_moments + our renderer do; most need an LLM API key, and some use
yt-dlp, which we don't use.

Sources: [OpusClip Virality Score](https://help.opus.pro/docs/article/virality-score),
[OpusClip hook formulas](https://www.opus.pro/blog/youtube-shorts-hook-formulas),
[StreamLadder: first 3 seconds](https://www.streamladder.com/blog/instantly-hook-viewers-first-3-seconds),
[Most-replayed data](https://www.trickster.dev/post/how-to-scrape-youtube-view-intensity-time-series),
[ClipsAI](https://github.com/ClipsAI/clipsai), [AI-Youtube-Shorts-Generator](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator).
