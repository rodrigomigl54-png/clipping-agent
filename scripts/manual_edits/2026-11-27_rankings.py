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
}

if __name__ == "__main__":
    for k in sys.argv[1:] or list(SPECS):
        print(k, ranking.render(SPECS[k]), flush=True)
