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
}

if __name__ == "__main__":
    for k in sys.argv[1:] or list(SPECS):
        print(k, ranking.render(SPECS[k]), flush=True)
