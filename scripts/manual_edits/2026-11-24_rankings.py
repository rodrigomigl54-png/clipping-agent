"""Ranking clips 2026-11-24 (format: scripts/manual_edits/ranking.py, no SFX). All moments found and cut by us from
the creators' own uploads.
  agent   Agent 00 "He Actually Took Over Bricks and Minifigs.." (FbEq6aQSI_o) — whole 65 min reaction analysed;
          only Agent's own commentary is used (he goes full screen when he talks)
  fanum   Fanum "Fanum Reveals His GTA 6 Streaming Set Up!" (awL5l2gUmkw)                         [AMP]
  jason   JasonTheWeen "We Won..." (B15hv63eYYg)                                                   [CORE]
  adapt   Adapt "Adapt Plays GTA 6 For The FIRST Time" (JHGDUEDpJCY)                                [CORE]
Usage: python scripts/manual_edits/2026-11-24_rankings.py [ids...]
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location("ranking", ROOT / "scripts/manual_edits/ranking.py")
ranking = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ranking)
SRC = str(ROOT / "assets/streams/2026-11-24")
AMP = str(ROOT / "outputs/_PRIVATE_TEST/AMP/2026-11-24")
CORE = str(ROOT / "outputs/_PRIVATE_TEST/CORE/2026-11-24")

SPECS = {
    "agent": dict(
        id="amp_ranking_agent_bricks", src_dir=SRC, src="agent_bricks", out_dir=AMP,
        title=["Ranking {Agent 00}'s", "Bricks & Minifigs Reactions"], sub=("(last one ", "💀"),
        moments=[
            dict(slot=4, label="Police paranoia", emoji="🚓", parts=[(518.0, 531.0)]),
            dict(slot=5, label="\"Elite watch time\"", emoji="🧠", parts=[(3914.5, 3925.0)]),
            dict(slot=3, label="DJI mics hate him", emoji="🎙", parts=[(382.1, 394.0)]),
            dict(slot=2, label="\"What a moron\"", emoji="🤦", parts=[(1117.0, 1125.9)]),
            dict(slot=1, label="$68 in one day", emoji="💀", parts=[(3345.3, 3356.3)]),
        ],
        fix={},
    ),
}

if __name__ == "__main__":
    for k in sys.argv[1:] or list(SPECS):
        print(k, ranking.render(SPECS[k]), flush=True)
