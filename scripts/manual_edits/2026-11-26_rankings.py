"""Ranking clips 2026-11-26 (format: scripts/manual_edits/ranking.py, no SFX). Moments found and cut by us from the
creator's own upload (free vidIQ import, 360p).
  stable  Stable Ronaldo "I Hosted A CORE House Garage Sale!" (ziBKFIEyEz0)                              [CORE]
Skipped today: Silky "Reacts To Adapt & OSCS DRAMA" (drama between members -> campaign rule "no negative
portrayal"), Silky & Riley "Get FRIED At 3AM" (smoking), Silky GTA 6 Playthrough #6 (312 MB, over the free limit).
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location("ranking", ROOT / "scripts/manual_edits/ranking.py")
ranking = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ranking)
SRC = str(ROOT / "assets/streams/2026-11-26")
CORE = str(ROOT / "outputs/_PRIVATE_TEST/CORE/2026-11-26")
AMP = str(ROOT / "outputs/_PRIVATE_TEST/AMP/2026-11-26")

SPECS = {
    "stable": dict(
        id="core_ranking_stable_garage", src_dir=SRC, src="stable_garage", out_dir=CORE,
        title=["Ranking {Stable Ronaldo}'s", "CORE House Garage Sale"], sub=("(last one ", "💸"),
        moments=[
            dict(slot=4, label="\"Maybe zero people show up\"", emoji="😅", parts=[(6.0, 16.5)]),
            dict(slot=5, label="Coin flip for the first sale", emoji="🪙", parts=[(734.0, 746.4)]),
            dict(slot=3, label="$1,000 shoes for $20", emoji="👟", parts=[(801.0, 814.0)]),
            dict(slot=2, label="\"2,000? They offer 50 cents\"", emoji="🤣", parts=[(1282.6, 1294.5)]),
            dict(slot=1, label="\"How much did we make?\"", emoji="💸", parts=[(2187.0, 2198.5)]),
        ],
        fix={"marlin's": "MARLON'S", "ron.": "RON."},
    ),
    "adapt": dict(
        id="core_ranking_adapt_house", src_dir=SRC, src="adapt_house", out_dir=CORE,
        title=["Ranking {Adapt}'s", "CORE House At 3 AM"], sub=("(last one ", "👻"),
        moments=[
            dict(slot=4, label="3 dead crows = bad omen", emoji="💀", parts=[(50.0, 55.8), (62.5, 65.0), (69.6, 73.6), (80.3, 83.0)]),
            dict(slot=5, label="Trick shot vs. his phone", emoji="📱", parts=[(312.5, 317.4), (320.0, 334.4)]),
            dict(slot=3, label="The CORE electric bill", emoji="💡", parts=[(229.5, 237.5), (251.9, 255.4), (266.3, 271.5)]),
            dict(slot=2, label="\"Not pre-recorded\"", emoji="🏀", parts=[(717.4, 722.6), (750.2, 754.2)]),
            dict(slot=1, label="The light turned on by itself", emoji="👻", parts=[(959.7, 963.6), (967.6, 976.3)]),
        ],
        fix={"lay": "LACY", "browse": "BROWN"},
    ),
    "fanum": dict(
        id="amp_ranking_fanum_gta_food", src_dir=SRC, src="fanum_arena", out_dir=AMP, crop_bottom=0.14,
        title=["Ranking {Fanum}'s", "Real Life GTA 6 Food"], sub=("(last one ", "🍔"),
        moments=[
            dict(slot=4, label="\"I'm in Vice City\"", emoji="🌴", parts=[(17.0, 18.95), (21.7, 26.6)]),
            dict(slot=5, label="Big Smoke's order IRL", emoji="🍟", parts=[(75.2, 84.0)]),
            dict(slot=3, label="Cluckin' Bell is tough", emoji="🐔", parts=[(267.0, 273.8), (283.0, 292.7)]),
            dict(slot=2, label="Burger Shot: 2 sauces", emoji="🍔", parts=[(313.9, 319.0), (336.6, 342.8), (344.9, 347.8)]),
            dict(slot=1, label="The final verdict", emoji="🏆", parts=[(363.2, 365.6), (369.3, 370.1), (372.6, 373.6), (376.2, 379.1)]),
        ],
        fix={},
    ),
}

if __name__ == "__main__":
    for k in sys.argv[1:] or list(SPECS):
        print(k, ranking.render(SPECS[k]), flush=True)
