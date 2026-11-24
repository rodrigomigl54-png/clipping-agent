# Groundwork — handoff (separate project from clipping)

Owner's decision 2026-11-24: Groundwork is handled in its OWN conversation so it never gets mixed up with the
clipping work (AMP / CORE). This file has everything decided so far. Reply to the owner in Serbian.

## The channel
* YouTube **@ground-workz** (name **Groundwork**, ~70 subscribers). Before the GTA detour it was briefly renamed
  "Leonida Files" (@LeonidaFilesUncut). The owner is putting the old name, logo, banner and niche back.
* Niche: faceless long-form **"Your Life as Every Level/Rank of …"** explainers.
* Public videos (views from the owner's screen recording, 2026-11-22):

  | Title | Length | Views |
  |---|---|---|
  | Your Life as a Gambling Addict: Every Level Explained | 16:43 | 721 |
  | Your Life as Every Level of a Profitable Memecoin Trader | 18:53 | 200 |
  | Your Life as Every Rank in the Secret Service | 18:33 | 438 |
  | Your Life as Every Rank of a Casino Card Counter | 15:39 | 346 |
  | Your Life as Every Rank of a Getaway Driver | 17:09 | ? |
  | POV: You Recruited Spies for the CIA for 28 Years | 10:04 | ? |
  | Your Life as Every Level of a Unprofitable Memecoin Trader | 13:38 | ? |
  | Your Life as Every Level of a Pyramid Scheme | 8:15 | ? |
  | Your Life as Every Rank in a Wall Street Investment Bank | 9:14 | ? |
  | Your Life as Every Rank in a Cartel | 8:57 | ? |
* The GTA long-form "50 Things You NEED to Know About GTA 6" goes **private**, and the GTA Shorts go private
  (or get deleted, the owner's choice). The owner restores the old videos to public. GTA long-form plans are paused.

## Style analysis (from "Gambling Addict" and "Secret Service", transcribed + frame-by-frame)
* **No intro.** The video opens directly on "Level one, the …". 10 levels, each 60–200 s.
* **Level title card**: black screen, white bold condensed font, about 2 s, e.g. "LEVEL THREE:\nTHE CHASER".
* **Images**: one recurring character (large round plain white head, two small black dot eyes, small flat mouth,
  no hair/nose, grey hoodie) in detailed, muted, cinematic, semi-realistic painted interiors. A new image every
  ~3–5 s, hard cuts, almost no motion. Mix of wide shots, close-ups of the face, and object close-ups (phone
  screens, papers, calendars).
* **Narration**: second person, present tense ("You're 26 years old…"), concrete numbers and small details
  ($140, $310, "Tuesday's game starts in 11 minutes"), slow emotional descent across levels, ~170 wpm.
* **My opinion of the channel** (sent to the owner): the character and writing are strong. Weak points:
  1. Low views and a ~1 month upload gap.
  2. Inconsistent title formats, plus the "a Unprofitable" grammar error.
  3. Two memecoin topics back to back.
  4. No 10–15 s hook promising where the story ends. The retention graph is needed to confirm.
  5. Very static visuals.

## Test level made (2026-11-24)
* "Your Life as Every Level of a Dropshipper", **LEVEL ONE: THE DREAM**, 85.5 s.
* Files: `content/groundwork/dropshipper_test/`
  * `script.json`: 16 lines, 261 words.
  * `vo.wav`: Kokoro `am_fenrir`, speed 1.05.
  * `timing.json`
  * `shotlist.json` / `SHOTLIST.md`: 23 shots, each with a full image prompt in the channel style.
  * `make_level.py`: renders 1920x1080. It puts `images/shot_XX.png` in place automatically, and uses
    PLACEHOLDER frames from the old Gambling video until those images exist.
* Output: `outputs/_PRIVATE_TEST/GROUNDWORK/level1_dropshipper_test.mp4`. The owner has it and will give feedback.
* Reference videos for analysis: `assets/groundwork/refs/gambling.mp4` and `secret_service.mp4`, imported
  free via vidIQ at 360p, plus their `.words.json` transcripts. This folder is gitignored, so re-import if missing.

## Open blocker: images
Images cannot be generated for free from here:
* there is no GPU;
* vidIQ / Higgsfield cost credits, and the owner's rule is FREE ONLY;
* the environment network now allows `image.pollinations.ai` (owner approved), but the Claude Code permission
  classifier denied the call, so it was not worked around.

Options given to the owner:
1. The owner generates the images with the tool he used before, from `SHOTLIST.md`.
2. The owner adds a Claude Code permission for calls to image.pollinations.ai.
3. Paid credits, only if the owner decides.

## Standing rules that also apply here (see CLAUDE.md)
* Free only. Never ask for keys or passwords in chat. Don't invent numbers.
* AI voice Kokoro `am_fenrir` (model files at /root/.cache/kokoro, re-download from the kokoro-onnx GitHub
  release `model-files-v1.0` if missing).
* No music baked in: the post kit proposes YouTube Audio Library tracks.
* Long-form flow: ideas -> owner picks the topic -> script (fact-checked where it states facts, sources
  listed) -> owner approves -> render.
* Commit and push to branch `claude/kind-mayer-1k2jgc`.
* YouTube (Oct 2026 / Jul 2025): avoid mass-produced, templated content. Every video needs a genuinely
  researched topic and its own script.

## Owner's decisions (2026-11-24, after the "Video Creation Master" prompt review)
* FULL AUTOMATION: Claude writes ideas, script, image prompts, generates the images, edits, renders and sends the
  post kit. The owner only (1) picks the topic and (2) approves the script. Everything must work from his PHONE
  (no desktop app, no computer).
* Script: fact-checked with sources, but still storytelling, gripping, never boring.
* Images must match exactly what the narration says at that moment (no random images) and must never be
  stretched/distorted. One character reference (character sheet) is sent with every image for consistency.
* NO text inside generated images at all.
* Title + thumbnail concept are decided together with the idea (stage 2), before the script.
* Small fixes accepted: chapters in the description, little time on tags, no music baked in.
* The owner has more video ideas for later; first build this system.
* Niche question still OPEN: switch to hand-drawn stick-figure explainers, or adapt the prompt to the
  "Every Level" format.

## Image generation status (2026-11-24)
* Google Flow (owner's previous tool): web app, no public API; automating it needs a logged-in desktop browser,
  which the phone-only setup can't provide.
* Pollinations free (no key): works now but 1 image / 45 s, 1024x576, watermark, weak model (sana). The two
  test images (`outputs/_PRIVATE_TEST/GROUNDWORK/img_test/`) got the character wrong: NOT usable.
* Gemini API: per sources from Oct 2026 there is no free tier for image models (paid only).
* Best free candidate: Cloudflare Workers AI free plan (10,000 Neurons/day, FLUX models). Needs a free
  Cloudflare account + API token from the owner (through the secure credential form, never chat). Quality to be
  tested first.

## Next (waiting on the owner)
The owner will send extra information, his own prompts, ideas and more example videos/styles to analyse, and
feedback on the test level. Give him an honest opinion, then continue.
