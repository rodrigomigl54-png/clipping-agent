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
    "fanum": dict(
        id="amp_ranking_fanum_setup", src_dir=SRC, src="fanum_setup", out_dir=AMP,
        title=["Ranking {Fanum}'s", "GTA 6 Stream Setup"], sub=("(last one ", "😭"),
        moments=[
            dict(slot=4, label="Real sand + gators", emoji="🐊", parts=[(140.5, 153.6)]),
            dict(slot=5, label="GTA 6 food menu", emoji="🍛", parts=[(160.2, 170.2)]),
            dict(slot=3, label="Not scared of the grease", emoji="🍳", parts=[(1422.0, 1436.8)]),
            dict(slot=2, label="\"Pull up and do it\"", emoji="😤", parts=[(1053.4, 1066.4)]),
            dict(slot=1, label="\"I saved the game already\"", emoji="😡", parts=[(1095.8, 1108.9)]),
        ],
        fix={},
    ),
    "jason": dict(
        id="core_ranking_jason_awards", src_dir=SRC, src="jason_we_won", out_dir=CORE,
        title=["Ranking {Jason}'s", "Streamer Awards Night"], sub=("(last one ", "🏆"),
        moments=[
            dict(slot=4, label="Shoes don't fit", emoji="👞", parts=[(422.5, 433.0)]),
            dict(slot=5, label="First time in a Rolls", emoji="🚗", parts=[(660.0, 670.2)]),
            dict(slot=3, label="Seated in the back", emoji="🪑", parts=[(930.0, 942.1)]),
            dict(slot=2, label="\"And the winner is...\"", emoji="😳", parts=[(1525.0, 1537.7)]),
            dict(slot=1, label="Stable Ronaldo WON", emoji="🏆", parts=[(1470.9, 1483.6)]),
        ],
        fix={"renova": "RONALDO!", "renova!": "RONALDO!"},
    ),
    "adapt": dict(
        id="core_ranking_adapt_gta6", src_dir=SRC, src="adapt_gta6", out_dir=CORE,
        title=["Ranking {Adapt}'s", "First Time In GTA 6"], sub=("(last one ", "⚡"),
        moments=[
            dict(slot=4, label="Starts the game in jail", emoji="🔒", parts=[(28.0, 39.8)]),
            dict(slot=5, label="\"Looks like a movie\"", emoji="🎬", parts=[(55.5, 63.2)]),
            dict(slot=3, label="Two stars already", emoji="⭐", parts=[(404.0, 416.4)]),
            dict(slot=2, label="\"I just killed a cop\"", emoji="🚓", parts=[(375.4, 388.8)]),
            dict(slot=1, label="Got TASED", emoji="⚡", parts=[(614.5, 627.5)]),
        ],
        fix={},
    ),
}

if __name__ == "__main__":
    for k in sys.argv[1:] or list(SPECS):
        print(k, ranking.render(SPECS[k]), flush=True)
