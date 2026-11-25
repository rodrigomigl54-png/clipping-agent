"""Ranking clips 2026-11-25 (format: scripts/manual_edits/ranking.py, no SFX). All moments found and cut by us from
the creators' own uploads (free vidIQ import, 360p):
  agent   Agent 00 "Testing The Deadliest Animals On Earth..." (Pr3DtMYOJYw) — only Agent's own commentary  [AMP]
  stable  Stable Ronaldo "Reacting To CORE's Old Cringey TikToks.." (4y5xLjKUjV0)                          [CORE]
  lacy    Lacy "We Tried Facebook Marketplace Food For 24 Hours.." (5XuBPRCOac0) — Lacy + Silky             [CORE]
Not importable today (free limit 299 MB): Kai+Speed "Who Can Make The Most Money In GTA 6?" (334 MB),
Jason "We Hosted The Worst Streamer Thanksgiving!" (353 MB).
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location("ranking", ROOT / "scripts/manual_edits/ranking.py")
ranking = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ranking)
SRC = str(ROOT / "assets/streams/2026-11-25")
AMP = str(ROOT / "outputs/_PRIVATE_TEST/AMP/2026-11-25")
CORE = str(ROOT / "outputs/_PRIVATE_TEST/CORE/2026-11-25")

SPECS = {
    "agent": dict(
        id="amp_ranking_agent_animals", src_dir=SRC, src="agent_animals", out_dir=AMP,
        title=["Ranking {Agent 00}'s", "Deadliest Animal Takes"], sub=("(last one ", "😭"),
        moments=[
            dict(slot=4, label="\"Preliminary answer: orcas\"", emoji="🐋", parts=[(27.0, 35.2)]),
            dict(slot=5, label="Croc needs a diet", emoji="🐊", parts=[(682.0, 691.0)]),
            dict(slot=3, label="\"How do they know this?\"", emoji="🤨", parts=[(1551.5, 1562.7)]),
            dict(slot=2, label="\"Most orcas are good\"", emoji="😇", parts=[(1673.6, 1687.5)]),
            dict(slot=1, label="Polar bears sell Coca-Cola", emoji="🥤", parts=[(1733.0, 1745.0)]),
        ],
        fix={},
    ),
    "stable": dict(
        id="core_ranking_stable_cringe", src_dir=SRC, src="stable_tiktoks", out_dir=CORE,
        title=["Ranking {CORE}'s", "Old Cringey TikToks"], sub=("(last one ", "💀"),
        moments=[
            dict(slot=4, label="\"Good morning, pookie\"", emoji="🥴", parts=[(352.4, 365.5)]),
            dict(slot=5, label="\"Why am I in this?\"", emoji="😳", parts=[(161.0, 174.2)]),
            dict(slot=3, label="That hairstyle", emoji="💇", parts=[(272.7, 284.0)]),
            dict(slot=2, label="\"Only 8 minutes in\"", emoji="😩", parts=[(785.7, 794.7)]),
            dict(slot=1, label="Jason's worst one", emoji="💀", parts=[(879.0, 889.4)]),
        ],
        fix={"marlin": "MARLON", "stumble": "STABLE", "robert": "RONALDO"},
    ),
    "lacy": dict(
        id="core_ranking_lacy_marketplace", src_dir=SRC, src="lacy_marketplace", out_dir=CORE,
        title=["Ranking {Lacy} & {Silky}'s", "Facebook Marketplace Food"], sub=("(last one ", "🤢"),
        moments=[
            dict(slot=4, label="Hibachi in someone's yard", emoji="🏠", parts=[(800.5, 812.7)]),
            dict(slot=5, label="\"Be a better role model\"", emoji="🙄", parts=[(704.5, 716.4)]),
            dict(slot=3, label="Sushi burger + sushi hot dog", emoji="🍣", parts=[(1097.0, 1108.0)]),
            dict(slot=2, label="\"You sound like chat\"", emoji="💬", parts=[(2136.5, 2150.0)]),
            dict(slot=1, label="Tastes like tartar sauce", emoji="🤢", parts=[(1492.9, 1503.0)]),
        ],
        fix={"lace.": "LACY.", "lace": "LACY"},
    ),
}

if __name__ == "__main__":
    for k in sys.argv[1:] or list(SPECS):
        print(k, ranking.render(SPECS[k]), flush=True)
