"""Everything needed to post one video on TikTok, YouTube Shorts and X: caption, title, description,
hashtags, tags, sound instructions, best time. Rule-based (no AI quota): built from the video's own
on-screen lines, the countdown and today's trending topics, in the style of the reference posts.
"""
from __future__ import annotations

import re
from datetime import date

BASE_TAGS = ["#gta6", "#gtavi", "#gta6edit"]
TOPIC_TAGS = {"lucia": "#lucia", "jason": "#jasonduval", "leonida": "#leonida", "vice": "#vicecity",
              "trailer": "#gta6trailer", "preload": "#gta6preload", "pre load": "#gta6preload", "gameplay": "#gta6gameplay",
              "meme": "#gta6memes", "streamer": "#gta6streamer"}
YT_TAGS = ["gta 6", "gta vi", "grand theft auto 6", "grand theft auto vi", "gta 6 edit", "gta 6 trailer",
           "gta 6 countdown", "gta 6 release date", "leonida", "vice city", "lucia", "jason duval", "rockstar games",
           "gta 6 shorts"]


def _clean(line: str) -> str:
    return re.sub(r"\s+", " ", line.replace("\n", " ")).strip().strip('"')


GENERIC = ["GTA 6 in {d} days.", "{d} days until Leonida.", "Leonida in {d} days. Are you ready?",
           "This is GTA 6. {d} days left.", "{d} more days of waiting.", "Vice City in {d} days."]
GENERIC_OUT = ["GTA 6 is finally here.", "Welcome to Leonida.", "Vice City is open."]


def _hook(lines: list[str], days: int, seed: str = "") -> str:
    """One readable sentence from the on-screen lines (what the viewer reads in the video)."""
    import zlib
    ls = [_clean(l) for l in lines if _clean(l)]
    if len(ls) == 1 and len(ls[0].split()) <= 2 and ls[0].isupper():      # a lone lyric shout says nothing
        ls = []
    if not ls:
        k = zlib.crc32(seed.encode())
        return (GENERIC[k % len(GENERIC)].format(d=days) if days > 0 else GENERIC_OUT[k % len(GENERIC_OUT)])
    if len(ls) == 1:
        return ls[0]
    if len(ls) > 3:                      # word-by-word reveals: the fullest line says it best
        return max(ls, key=len)
    a, b = ls[0], ls[-1]
    if re.fullmatch(r"\d+", a) or a.upper().endswith("DAYS") and len(a) < 10:     # countdown counter
        return f"{days} days. {b[0].upper() + b[1:] if b else ''}".strip()
    return f"{a.rstrip('.…')}… {b}"


def _cover(lines: list[str], hook: str, limit: int = 45) -> str:
    """Short on-cover text: the first on-screen line, cut at a word boundary."""
    first = next((_clean(l) for l in lines if _clean(l)), hook)
    if len(first) <= limit:
        return first
    return first[:limit].rsplit(" ", 1)[0] + "…"


def build(*, lines: list[str], days: int, kind: str = "hype_edit", topics: list[str] | None = None,
          sound: str | None = None, sound_ref: str | None = None, handle: str = "@mostwanted.vi",
          release: str = "November 19, 2026", orientation: str = "vertical", seed: str = "") -> dict:
    hook = _hook(lines, days, seed)
    if kind == "niko_edit" and lines:          # quote the line the edit ends on
        hook = f'Niko Bellic: "{_clean(lines[-1]).rstrip(".")}"'
    elif kind != "meme_skit" and not [l for l in lines if _clean(l)] and seed:
        pass
    tags = list(BASE_TAGS) if kind != "meme_skit" else ["#gta6", "#gtavi", "#gta6memes", "#gamingmemes"]
    if kind == "niko_edit":                     # GTA IV character edit: no countdown, GTA IV tags
        tags, days = ["#gta4", "#nikobellic", "#gtaiv", "#gtaedits", "#gta"], -999
    if days > 0 and kind not in ("niko_edit", "meme_skit"):
        tags.append("#gta6countdown")
    for t in topics or []:
        tag = TOPIC_TAGS.get(t.lower())
        if tag and tag not in tags:
            tags.append(tag)
    if "#leonida" not in tags and "leonida" in hook.lower():
        tags.append("#leonida")
    tags = tags[:6]
    emoji = "💀" if kind == "meme_skit" else ("🌴" if "leonida" in hook.lower() or "vice" in hook.lower() else "🔥")
    when = f"{days} days left" if days > 1 else ("1 day left" if days == 1 else "out now")
    game = "GTA IV" if kind == "niko_edit" else "GTA 6"

    tiktok = f"{hook} {emoji} {' '.join(tags)}"
    yt_title = f"{hook} {emoji}"
    if days > 0 and str(days) not in yt_title and kind != "niko_edit":
        yt_title = f"{yt_title} | GTA 6 in {days} days"
    yt_title = (yt_title[:90].rstrip() + " #Shorts") if len(yt_title) > 90 else yt_title + " #Shorts"
    if kind == "niko_edit":
        yt_desc_tail = "#GTA4 #NikoBellic #Shorts"
    else:
        yt_desc_tail = "#GTA6 #GTAVI #Shorts"
    yt_desc = "\n".join([
        f"{hook} {emoji}",
        f"GTA 6 release: {release} ({when})." if kind != "niko_edit" else "Niko Bellic — GTA IV. The original. GTA 6 drops November 19, 2026.",
        "New GTA 6 edit, meme or clip every day — subscribe so you don't miss one.",
        "",
        f"Footage: official Rockstar Games {game} trailers. Fan edit, not affiliated with Rockstar Games.",
        "",
        yt_desc_tail,
    ])
    x_text = f"{hook} {emoji}\n\n" + ("#GTA4 #NikoBellic" if kind == "niko_edit" else "#GTA6 #GTAVI" + (" #GTA6Countdown" if days > 0 else ""))
    music = {
        "tiktok": (f"Use this sound: '{sound}' — open {sound_ref}, tap the sound → Use this sound → scissors → drag to "
                   "the very start (0:00). Upload the *_silent.mp4 file, original volume 0.") if sound else
                  "Keep the video's own audio.",
        "youtube": "Upload the preview file WITH music (Shorts has no TikTok sounds). A Content ID claim on the song is "
                   "normal: the video stays up, the song owner gets the ad money.",
        "x": "Upload the preview file WITH music (X has no sound library).",
    }
    return {
        "hook": hook,
        "tiktok": {"caption": tiktok, "hashtags": tags, "cover_text": _cover(lines, hook),
                   "settings": "Allow comments + Duet + Stitch ON; 'AI-generated content' OFF (edited footage, not AI)."},
        "youtube": {"title": yt_title, "description": yt_desc, "tags": YT_TAGS,
                    "settings": "Audience: No, it's not made for kids; Shorts remixing: allow video and audio; "
                                "Category: Gaming; Altered/synthetic content: No."},
        "x": {"text": x_text, "settings": "Post as video (not link); pin the best one to the profile."},
        "music": music,
        "best_time": "TikTok/Shorts: 18:00–22:00 Belgrade (12:00–16:00 New York) or 00:00–02:00 Belgrade "
                     "(US evening). Space posts at least 2–3 h apart.",
        "orientation": orientation,
        "platforms": ["tiktok", "youtube_shorts", "x"] if orientation != "landscape" else ["tiktok", "x"],
    }


def as_text(kit: dict, title: str = "") -> str:
    m = kit["music"]
    out = [f"=== {title} ===" if title else "", "",
           "TIKTOK", f"Caption: {kit['tiktok']['caption']}", f"Cover text: {kit['tiktok']['cover_text']}",
           f"Sound: {m['tiktok']}", f"Settings: {kit['tiktok']['settings']}", ""]
    if "youtube_shorts" in kit["platforms"]:
        out += ["YOUTUBE SHORTS", f"Title: {kit['youtube']['title']}", "Description:", kit["youtube"]["description"],
                f"Tags: {', '.join(kit['youtube']['tags'])}", f"Sound: {m['youtube']}", f"Settings: {kit['youtube']['settings']}", ""]
    else:
        out += ["YOUTUBE SHORTS: not for this one (landscape video — Shorts must be vertical)", ""]
    out += ["X", kit["x"]["text"], f"Sound: {m['x']}", "", f"Best time: {kit['best_time']}"]
    return "\n".join(out).strip() + "\n"
