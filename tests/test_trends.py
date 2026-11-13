"""Trend research + daily plan (offline, with recorded page snippets)."""
import json
import time
from datetime import date

from clipper.research.planner import make_plan
from clipper.research.trends import TikTokPublic, TrendResearch, YouTubePublic, classify, on_topic


def _tt_fetch(url):
    if "/embed/@" in url:
        state = {"source": {"data": {"/embed/@x": {"videoList": [
            {"id": "7700000000000000002", "desc": "GTA 6 edit #gta6", "playCount": 900000, "authorUniqueId": "x"},
            {"id": "7700000000000000001", "desc": "old", "playCount": 100000, "authorUniqueId": "x"}]}}}}
        return f'<script id="__FRONTITY_CONNECT_STATE__" type="application/json">{json.dumps(state)}</script>'
    vid = url.rsplit("/", 1)[-1]
    item = {"id": vid, "desc": "GTA 6 edit 🔥 #gta6 #edit" if vid.endswith("2") else "old video", "createTime": int(time.time()) - 10 * 3600,
            "author": {"uniqueId": "x"}, "video": {"duration": 15, "width": 1080, "height": 1920},
            "stats": {"playCount": 900000, "diggCount": 90000, "commentCount": 1000, "shareCount": 9000, "collectCount": "5000"},
            "music": {"id": "1", "title": "Phonk Song", "authorName": "DJ", "original": False}}
    data = {"__DEFAULT_SCOPE__": {"webapp.video-detail": {"itemInfo": {"itemStruct": item}}}}
    return f'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">{json.dumps(data)}</script>'


def _yt_fetch(url):
    data = {"contents": [{"videoRenderer": {"videoId": "abc", "title": {"runs": [{"text": "Grand Theft Auto VI: Pre-Load Now"}]},
                                            "ownerText": {"runs": [{"text": "Rockstar Games"}]},
                                            "viewCountText": {"simpleText": "11,550,352 views"},
                                            "publishedTimeText": {"simpleText": "2 days ago"}}}]}
    return f"<script>var ytInitialData = {json.dumps(data)};</script>"


def test_research_and_plan(tmp_path):
    tr = TrendResearch(tmp_path, TikTokPublic(delay=0, fetch=_tt_fetch), YouTubePublic(fetch=_yt_fetch),
                       known_types={"x": "hype_edit"})
    snap = tr.run(["x"], ["gta 6"], max_pages_per_creator=2)
    v = next(x for x in snap.tiktok if x["id"].endswith("2"))
    assert v["velocity"] == 90000 and v["type"] == "hype_edit" and abs(v["engagement"] - 0.1167) < 1e-3
    s = tr.summarize(snap)
    assert s["events"][0]["title"].startswith("Grand Theft Auto VI") and s["sounds"][0]["title"] == "Phonk Song"
    plan = make_plan(s, n=10, release=date(2026, 11, 19), today=date(2026, 11, 13))
    assert plan["videos"] == 10 and plan["phase"] == "pre_release" and plan["days_to_release"] == 6
    assert plan["allocation"]["hype_edit"] >= 2 and all(x["variants"] for x in plan["slots"])
    assert (tmp_path / f"snapshot_{snap.taken_at[:10]}.json").exists()


def test_helpers():
    assert YouTubePublic._age_hours("2d ago") == 48 and YouTubePublic._views("1.2M views") == 1200000
    assert classify("Kai Cenat reacts to GTA 6") == "streamer_clip" and on_topic("vice city looks crazy")
