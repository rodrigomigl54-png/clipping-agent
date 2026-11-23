"""Our version of the "Ranking" format: Kai Cenat's GTA 6 bank spree, cut by us from his own upload
(Kai Cenat Live "Robbing Every Bank In GTA 6 Free Roam!", youtube.com/watch?v=q1jR850CE_o).
Slots filled out of order (4, 5, 3, 2, then #1 last), labels are ours. Kept under 60 s for YouTube Shorts.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location("ranking", ROOT / "scripts/manual_edits/ranking.py")
ranking = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ranking)

SPEC = dict(
    id="amp_kai_ranking_banks",
    src_dir=str(ROOT / "assets/streams/2026-11-23"), src="kai_banks",
    out_dir=str(ROOT / "outputs/_PRIVATE_TEST/AMP/2026-11-23"),
    title=["Ranking {Kai Cenat}", "GTA 6 Bank Spree"],
    sub=("(last one ", "💀"),
    moments=[
        dict(slot=4, label="\"Real criminal\" tutorial", emoji="📞", parts=[(1537.6, 1548.0)]),
        dict(slot=5, label="Picked the wrong day", emoji="👊", parts=[(746.0, 757.0)]),
        dict(slot=3, label="Kai vs one hill", emoji="🚙", parts=[(790.5, 802.0)]),
        dict(slot=2, label="100K in one night", emoji="💰", parts=[(3424.6, 3434.0)]),
        dict(slot=1, label="One jump too far", emoji="💀", parts=[(3778.6, 3787.2), (3810.2, 3816.8)]),
    ],
    fix={},
)

if __name__ == "__main__":
    print(ranking.render(SPEC))
