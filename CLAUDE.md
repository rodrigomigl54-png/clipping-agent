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
