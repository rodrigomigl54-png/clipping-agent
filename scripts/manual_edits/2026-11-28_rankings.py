"""Ranking clips 2026-11-28 (format: scripts/manual_edits/ranking.py, no SFX). Moments found and cut by us from the
creators' own uploads (free vidIQ import, 360p).
  agent   Agent 00 "How Fast You'd Die Throughout Earth's History" (smRUDCmsx-k) — whole 21 min reaction analysed;
          only Agent's own commentary is used                                                              [AMP]
  stable  Stable Ronaldo "We Tried Black Friday Shopping!" (ytYjQCV2vqQ)                                    [CORE]
  lacy    Lacy "I Tried Cooking Thanksgiving For My Girlfriend.." (xuYhR9Bzl9Q)                             [CORE]
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location("ranking", ROOT / "scripts/manual_edits/ranking.py")
ranking = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ranking)
SRC = str(ROOT / "assets/streams/2026-11-28")
AMP = str(ROOT / "outputs/_PRIVATE_TEST/AMP/2026-11-28")
CORE = str(ROOT / "outputs/_PRIVATE_TEST/CORE/2026-11-28")

SPECS = {
    "agent": dict(
        id="amp_ranking_agent_history", src_dir=SRC, src="agent_die", out_dir=AMP,
        title=["Ranking {Agent 00}'s", "Prehistoric Survival Takes"], sub=("(last one ", "💀"),
        moments=[
            dict(slot=4, label="\"What is that?!\"", emoji="👽", parts=[(169.5, 176.5)]),
            dict(slot=5, label="Too scary to have a cool name", emoji="🦂", parts=[(505.0, 515.6)]),
            dict(slot=3, label="One infection = game over", emoji="🩸", parts=[(366.8, 374.4), (388.3, 392.6)]),
            dict(slot=2, label="Usain Bolt from the dinos", emoji="🏃", parts=[(746.4, 756.3)]),
            dict(slot=1, label="\"I could survive, trust me\"", emoji="💀", parts=[(1256.3, 1264.2)]),
        ],
        fix={},
    ),
}

if __name__ == "__main__":
    for k in sys.argv[1:] or list(SPECS):
        print(k, ranking.render(SPECS[k]), flush=True)
