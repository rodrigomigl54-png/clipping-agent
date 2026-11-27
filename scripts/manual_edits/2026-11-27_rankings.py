"""Ranking clips 2026-11-27 (format: scripts/manual_edits/ranking.py, no SFX). Moments found and cut by us from the
creators' own uploads (free vidIQ import, 360p).
  agent  Agent 00 "The iPhone Battery Conspiracy Was Real.." (YvSGQtTdKLo) — whole 42 min reaction analysed; only
         Agent's own commentary while he is full screen is used                                         [AMP]
  silky  Silky "Lucia Goes On A Robbery Spree! (GTA 6 Playthrough #7)" (cjlKOW_nzng)                     [CORE]
Skipped: Stable "Clips That Made Cuffem Famous!" (other people's Kick/TikTok clips, little own commentary),
Adapt "The FUNNIEST Duo in Warzone!" (318 MB, over the free 299 MB import limit).
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location("ranking", ROOT / "scripts/manual_edits/ranking.py")
ranking = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ranking)
SRC = str(ROOT / "assets/streams/2026-11-27")
AMP = str(ROOT / "outputs/_PRIVATE_TEST/AMP/2026-11-27")
CORE = str(ROOT / "outputs/_PRIVATE_TEST/CORE/2026-11-27")

SPECS = {
    "agent": dict(
        id="amp_ranking_agent_apple", src_dir=SRC, src="agent_iphone", out_dir=AMP,
        title=["Ranking {Agent 00}'s", "Apple Rants"], sub=("(last one ", "😭"),
        moments=[
            dict(slot=4, label="\"Beating of a lifetime\"", emoji="😭", parts=[(94.6, 105.8)]),
            dict(slot=5, label="\"Be a little bored, bro\"", emoji="📱", parts=[(191.5, 203.6)]),
            dict(slot=3, label="Only a $500M fine?", emoji="💸", parts=[(493.0, 504.3)]),
            dict(slot=2, label="Two SIMs = dead phone", emoji="🔋", parts=[(574.1, 586.7)]),
            dict(slot=1, label="\"How much more do you need?\"", emoji="🍎", parts=[(2394.0, 2405.0)]),
        ],
        fix={},
    ),
    "silky": dict(
        id="core_ranking_silky_lucia", src_dir=SRC, src="silky_gta7", out_dir=CORE,
        title=["Ranking {Silky}'s", "Lucia Robbery Spree"], sub=("(last one ", "🧠"),
        moments=[
            dict(slot=4, label="\"This car's hard\"", emoji="🏎", parts=[(438.2, 452.2)]),
            dict(slot=5, label="\"Am I dumb?\"", emoji="🤦", parts=[(814.3, 824.6)]),
            dict(slot=3, label="Robbed a store for $7", emoji="💵", parts=[(1312.9, 1317.0), (1331.8, 1335.7)]),
            dict(slot=2, label="\"Now what?!\"", emoji="😳", parts=[(1074.4, 1087.0)]),
            dict(slot=1, label="The $200 jail glitch", emoji="🧠", parts=[(1845.7, 1857.0), (1872.6, 1875.7)]),
        ],
        fix={},
    ),
}

if __name__ == "__main__":
    for k in sys.argv[1:] or list(SPECS):
        print(k, ranking.render(SPECS[k]), flush=True)
