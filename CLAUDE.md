# Operating the AI Clipping Machine from Claude Code

This repo is a local clipping system. Operate it with `python main.py <command>` (see README for
the full table). Rules for the operator:

* Never claim a clip is exported unless `python main.py clips --decision approved` shows a `file`
  path that exists. When reporting a finished clip, give: profile, title, duration, quality score,
  viral potential score, rights status, and the exact local file path.
* Never add or approve a permission record without evidence the user provided. Do not mark
  third-party content as `none` unless the user confirmed it. Public ≠ licensed.
* Never invent performance numbers. Analytics come only from CSVs the user imports.
* Do not change production settings silently: use `set-threshold`, `set-duration` or
  `learning apply`, which log to `learning history`.
* **Every video is posted to BOTH TikTok and YouTube Shorts** (same file, channel Most Wanted: TikTok
  @mostwanted.vi, YouTube @mostwantedgtavi). So every output is vertical 1080x1920 (landscape/square edits are
  centred on a blurred copy), carries no channel tag, and ships with a post kit for both platforms. Target
  10–20 videos per day (memes + edits).
* **Daily workflow (owner's rule, 2026-11-15):** the morning run only researches and sends a detailed trend
  report + content plan (every video: type, viral reference, style, exact on-screen text, footage, song, hook,
  caption/title, why). Nothing is rendered until the owner approves or edits the plan. Every day uses NEW viral
  references; templates, meme clips and trailer shots used on earlier days are not reused unless the owner asks —
  except proven performers (good numbers on our channel), which may come back after a few days with a completely
  new joke/text. Footage: 2–3 edits/day from unused trailer parts + new official sources proposed in the plan
  first; the rest are memes. The report is a phone-friendly HTML page (outputs/reports/IZVESTAJ_<date>.html)
  sent with SendUserFile, plus a short chat summary.
* **Music on YouTube Shorts (owner's rule, 2026-11-16):** never upload a file with the song baked in — the
  owner uploads the silent version and adds the song from YouTube's own sound library in the app (licensed,
  no Content ID claims). Post kits say which song to search for; memes get a silent version for YouTube too.
* **Long-form (owner's rule, 2026-11-17):** YouTube gets a 16:9 faceless long-form video every ~2 days (English,
  AI narration voice `am_fenrir` via local Kokoro, speed 1.1). Flow: ideas report -> owner picks topic -> script
  (fact-checked, sources listed; unconfirmed things are said to be unconfirmed) -> owner approves -> render with
  `content/longform/<id>/make.py` (clipper/editing/longform.py). No music baked in: post kit proposes Audio Library
  tracks and where. Text never covers faces. Each long-form is later cut into Shorts.
* **Recreating the owner's references (owner's rule, 2026-11-21 — this overrides the "official footage /
  unused trailer parts" plan rule above):** when the owner sends a reference and asks for it, recreate THAT
  video: same subject/character (a Niko Bellic edit = Niko Bellic), same format, same joke. Only change what
  the owner asked to change (e.g. "another background that makes sense"). Never swap the character, scene or
  joke for something from the official footage. If the needed footage is not on disk, get it (in-game
  cutscene/gameplay uploads via the vidIQ import, render to `outputs/_PRIVATE_TEST/`, say where it came from);
  if it truly can't be found, ask before substituting anything.
* **Streamer clips only from the VOD (owner's rule, 2026-11-22 — overrides the "uploads via vidIQ" part above
  for anything posted to YouTube):** every moment is cut by us from the streamer's own VOD/upload. Never use
  footage from other people's Shorts, TikToks, clip-channel uploads or re-cuts of them (that is what YouTube's
  1 Oct 2026 Shorts update stops recommending). Viral moments are fine. The cut, structure, headline and title
  are our own. Preferred YouTube format: transformed clips (Top 3/5/10 rankings, comparisons, story with context)
  with our scripted AI narrator (Kokoro `am_fenrir`) around the streamer's original audio. The narrator says our
  own context/ranking/verdict and never just reads what happens on screen.
  Finding the moments is our own work too: we do NOT look at other clippers' clips to pick moments. We search the
  VOD ourselves (scripts/tools/find_moments.py + watching), cut, edit and render, then send the post kit.
* **Channels (owner's decision, 2026-11-22):** the long-form channel goes back to its old name **Groundwork** and
  its old niche ("Your Life as Every Level/Rank of …" faceless explainers). The owner teaches the format and we make
  a test video first, which is published only if it is good. The GTA long-form there goes private. GTA long-form /
  "Leonida Files" plans are paused. Most Wanted = AMP clips, CORE clipper = CORE/Lacy clips.
  **Groundwork runs in its own conversation (owner, 2026-11-24)**: everything about it is in docs/GROUNDWORK.md.
  A clipping session does not do Groundwork work, and a Groundwork session does not do clipping.
* Do not add publishing/upload integrations, cloud services, dashboards, or scraping/downloader
  tools (e.g. yt-dlp) — out of scope by design.

Common requests → commands:

| User says | Run |
|---|---|
| start the machine | `python main.py start` (blocks; use `--once` for one cycle) |
| pause / resume research | `python main.py pause` / `python main.py resume` |
| research AMP / CORE / LosPollosTV | `python main.py research amp` (`core`, `lospollostv`) |
| process sources | `python main.py process` |
| new candidates | `python main.py candidates --status new` |
| approved / rejected clips | `python main.py clips --decision approved` / `rejected` |
| rights status | `python main.py rights list` |
| errors | `python main.py errors` |
| analytics / import CSV | `python main.py analytics` / `python main.py analytics import <csv>` |
| compare LosPollosTV formats | `python main.py compare-formats` |
| change threshold / durations | `python main.py set-threshold <p> <v>` / `set-duration <p> --min --max` |
| system status | `python main.py status` |
| learn a format from an example clip | `python main.py examples add <file> --profile gta6 --category <cat>` |
| hype / countdown edit from trailer files | `python main.py hype make <video> [<video>...] --profile gta6` |
| learn viral edit templates / make the day's edits | `python main.py hype learn-trending` / `python main.py hype daily` |
| reaction memes (caption + clip) | `python main.py meme daily --n 8` (`meme add <url>` to learn a clip) |
| private quality test on a recording | `python main.py private-test <file> --profile gta6 --creators "<name>"` |

Development: code lives in `clipper/`; run `python -m pytest -q` before committing; keep
`PROJECT_STATUS.md` up to date after major changes.
