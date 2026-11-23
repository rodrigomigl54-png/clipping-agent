"""AMP ranking clips 2026-11-23 (format: scripts/manual_edits/ranking.py, no SFX). All moments found and cut by us
from the creators' own uploads.
  kai_irl      Kai Cenat Live "Kai Cenat Plays GTA 6 In Real Life!" (ETWvry6twFA)
  agent        Agent 00 "The Most Unfaithful Couple Ever.." (CacOn66iU2E)
Usage: python scripts/manual_edits/2026-11-23_amp_rankings.py [ids...]
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location("ranking", ROOT / "scripts/manual_edits/ranking.py")
ranking = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ranking)
OUT = str(ROOT / "outputs/_PRIVATE_TEST/AMP/2026-11-23")

SPECS = {
    "kai_irl": dict(
        id="amp_ranking_kai_irl", src_dir=str(ROOT / "assets/streams/2026-11-22"), src="kai_irl", out_dir=OUT,
        title=["Ranking {Kai Cenat}", "GTA 6 In Real Life"], sub=("(last one ", "💀"),
        moments=[
            dict(slot=4, label="Not from Miami", emoji="😭", parts=[(78.5, 86.0)]),
            dict(slot=5, label="Paid? Not today", emoji="💸", parts=[(316.0, 326.4)]),
            dict(slot=3, label="He got SET UP", emoji="😳", parts=[(326.4, 340.0)]),
            dict(slot=2, label="Seatbelt on!!", emoji="🚗", parts=[(502.7, 515.0)]),
            dict(slot=1, label="\"Not my fault\"", emoji="🤷", parts=[(569.2, 584.0)]),
        ],
        fix={"field": "FAILED", "sent": "SET", "chase": "CHAT,"},
    ),
}

if __name__ == "__main__":
    for k in sys.argv[1:] or list(SPECS):
        print(k, ranking.render(SPECS[k]), flush=True)
