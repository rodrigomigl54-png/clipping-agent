"""CORE ranking clips 2026-11-23 (format: scripts/manual_edits/ranking.py, no SFX). All moments found and cut by us
from the creators' own uploads:
  chains   Lacy "SURPRISING CORE WITH $100,000 CHAINS!" (0bq8vyplJ2U) — Lacy, Marlon, Stable Ronaldo, Silky, Jason
  japan    Lacy "24 HOURS WITH CORE IN JAPAN!" (ehe9nkND3ds)
  dad      Stable Ronaldo "I Let Marlon Be My Dad For 24 Hours!" (nmhXis4FQPs) — Stable + Marlon
Usage: python scripts/manual_edits/2026-11-23_core_rankings.py [ids...]
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location("ranking", ROOT / "scripts/manual_edits/ranking.py")
ranking = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ranking)
SRC = str(ROOT / "assets/streams/2026-11-23")
OUT = str(ROOT / "outputs/_PRIVATE_TEST/CORE/2026-11-23")

SPECS = {
    "chains": dict(
        id="core_ranking_chains", src_dir=SRC, src="lacy_core_chains", out_dir=OUT,
        title=["Ranking {Lacy}'s", "$100K CORE Chains"], sub=("(last one ", "😭"),
        moments=[
            dict(slot=4, label="\"We got the chains\"", emoji="⛓", parts=[(334.0, 344.3)]),
            dict(slot=5, label="\"Guys, no edits\"", emoji="🙅", parts=[(806.0, 815.0)]),
            dict(slot=3, label="Risked the aura", emoji="😬", parts=[(1328.4, 1340.3), (1343.9, 1347.7)]),
            dict(slot=2, label="A chain for everyone", emoji="🎁", parts=[(1409.9, 1421.0)]),
            dict(slot=1, label="\"Are you serious?!\"", emoji="😭", parts=[(1441.0, 1455.5)]),
        ],
        fix={"marlin": "MARLON"},
    ),
    "dad": dict(
        id="core_ranking_marlon_dad", src_dir=SRC, src="stable_marlon_dad", out_dir=OUT,
        title=["Ranking {Stable Ronaldo}'s", "24H With \"Dad\" Marlon"], sub=("(last one ", "😂"),
        moments=[
            dict(slot=4, label="\"Why I play e-sports\"", emoji="🎮", parts=[(1753.0, 1763.6)]),
            dict(slot=5, label="Can't do a seatbelt", emoji="😭", parts=[(1249.0, 1259.0)]),
            dict(slot=3, label="\"Didn't have a dad either\"", emoji="💀", parts=[(64.0, 73.8)]),
            dict(slot=2, label="Red light?! SON", emoji="🚦", parts=[(985.0, 1001.5)]),
            dict(slot=1, label="Kai met his \"dad\"", emoji="😂", parts=[(725.5, 736.2)]),
        ],
        fix={"marlin": "MARLON", "marlin!": "MARLON!", "joes": "YO,"},
    ),
    "japan": dict(
        id="core_ranking_japan", src_dir=SRC, src="lacy_core_japan", out_dir=OUT,
        title=["Ranking {CORE} In Japan", "With Lacy & Jason"], sub=("(last one ", "🔥"),
        moments=[
            dict(slot=4, label="7-Eleven rice ball review", emoji="🍙", parts=[(225.0, 236.6)]),
            dict(slot=5, label="Egg sandwich = 10/10", emoji="🥪", parts=[(408.0, 423.4)]),
            dict(slot=3, label="\"Where you shopping at?\"", emoji="🛍", parts=[(771.0, 782.9)]),
            dict(slot=2, label="\"I want to move here\"", emoji="🇯🇵", parts=[(430.0, 436.2)]),
            dict(slot=1, label="Jason's song in a JP store", emoji="🎶", parts=[(740.0, 753.6)]),
        ],
        fix={},
    ),
}

if __name__ == "__main__":
    for k in sys.argv[1:] or list(SPECS):
        print(k, ranking.render(SPECS[k]), flush=True)
