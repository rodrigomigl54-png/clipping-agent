"""Test of the new clipping system: Top 3 with our AI narrator, all cut from Kai's own upload.

Source: Kai Cenat Live "Robbing Every Bank In GTA 6 Free Roam!" (youtube.com/watch?v=q1jR850CE_o), free vidIQ
import (360p), transcript + find_moments (scores 52 / 78 / the ending picked by eye: car jump -> WASTED).
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location("topn", ROOT / "scripts/manual_edits/topn.py")
topn = importlib.util.module_from_spec(_s)
_s.loader.exec_module(topn)

SPEC = dict(
    id="amp_kai_banks_top3",
    src_dir=str(ROOT / "assets/streams/2026-11-23"), src="kai_banks",
    out_dir=str(ROOT / "outputs/_PRIVATE_TEST/AMP/2026-11-23"),
    headline=["{KAI CENAT}'S GTA 6 BANK SPREE", "TOP 3 MOMENTS"],
    hook=(3780.6, 1.8),
    items=[
        dict(rank=3, parts=[(1421.5, 1433.0)],
             vo="Number three. Kai's first job goes so smooth, he can't believe the money."),
        dict(rank=2, parts=[(3424.6, 3437.0)],
             vo="Number two. Over a hundred K in one night, and Kai loses it."),
        dict(rank=1, parts=[(3776.0, 3788.0), (3807.0, 3819.5)],
             vo="Number one. Rich, wanted, and feeling untouchable, Kai tries one last jump."),
    ],
    outro="Would you have taken that jump? Tell me in the comments.",
    crop=None, fix={},
)

if __name__ == "__main__":
    print(topn.render(SPEC))
