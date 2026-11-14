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


def _hook(lines: list[str], days: int) -> str:
    """One readable sentence from the on-screen lines (what the viewer reads in the video)."""
    ls = [_clean(l) for l in lines if _clean(l)]
    if not ls:
        return f"GTA 6 in {days} days." if days > 0 else "GTA 6 is here."
    if len(ls) == 1:
        return ls[0]
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
          release: str = "November 19, 2026", orientation: str = "vertical") -> dict:
    hook = _hook(lines, days)
    tags = list(BASE_TAGS)
    if days > 0:
        tags.append("#gta6countdown")
    for t in topics or []:
        tag = TOPIC_TAGS.get(t.lower())
        if tag and tag not in tags:
            tags.append(tag)
    if "#leonida" not in tags and "leonida" in hook.lower():
        tags.append("#leonida")
    tags = tags[:6]
    emoji = "🌴" if "leonida" in hook.lower() or "vice" in hook.lower() else "🔥"
    when = f"{days} days left" if days > 1 else ("1 day left" if days == 1 else "out now")

    tiktok = f"{hook} {emoji} {' '.join(tags)}"
    yt_title = f"{hook} {emoji}"
    if days > 0 and str(days) not in yt_title:
        yt_title = f"{yt_title} | GTA 6 in {days} days"
    yt_title = (yt_title[:90].rstrip() + " #Shorts") if len(yt_title) > 90 else yt_title + " #Shorts"
    yt_desc = "\n".join([
        f"{hook} {emoji}",
        f"GTA 6 release: {release} ({when}).",
        "New GTA 6 edit, meme or clip every day — subscribe so you don't miss one.",
        "",
        "Footage: official Rockstar Games trailers. Fan edit, not affiliated with Rockstar Games.",
        "",
        "#GTA6 #GTAVI #Shorts",
    ])
    x_text = f"{hook} {emoji}\n\n#GTA6 #GTAVI" + (" #GTA6Countdown" if days > 0 else "")
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
        "platforms": ["tiktok", "youtube_shorts", "x"] if orientation == "vertical" else ["tiktok", "x"],
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
