"""Complete Top 5 example (owner's request 2026-11-23): intro, 5 ranked moments, #1 payoff, outro.

Everything cut by us from Kai Cenat Live "Robbing Every Bank In GTA 6 Free Roam!" (youtube.com/watch?v=q1jR850CE_o).
Moments found with find_moments + watched by eye; ranked from weakest (#5) to strongest (#1).
Format learned from ranked streamer compilations: cold-open hook -> "TOP 5" title card with narrator intro ->
for each rank a card (big number + moment title + one narrator line) -> the moment (streamer audio, captions,
rank badge, moment title on screen) -> #1 gets the longest moment -> outro card "comment your number".
Kept under 60 s (YouTube: Shorts over 1 min with a Content ID claim get blocked).
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location("topn", ROOT / "scripts/manual_edits/topn.py")
topn = importlib.util.module_from_spec(_s)
_s.loader.exec_module(topn)

SPEC = dict(
    id="amp_kai_banks_top5",
    src_dir=str(ROOT / "assets/streams/2026-11-23"), src="kai_banks",
    out_dir=str(ROOT / "outputs/_PRIVATE_TEST/AMP/2026-11-23"),
    headline=["{KAI CENAT} ROBBED EVERY BANK", "IN GTA 6 — RANKED"],
    hook=(3780.8, 1.3),
    intro=dict(vo="Here are Kai Cenat's top five craziest bank spree moments.",
               lines=["{KAI CENAT}'S CRAZIEST", "GTA 6 BANK SPREE MOMENTS"]),
    items=[
        dict(rank=5, title="THE \"REAL CRIMINAL\" TUTORIAL", parts=[(1538.2, 1545.6)],
             vo="Five. The real criminal tutorial."),
        dict(rank=4, title="HE PICKED THE WRONG DAY", parts=[(748.5, 756.2)],
             vo="Four. This guy picked the wrong day."),
        dict(rank=3, title="OFF-ROAD? NOT TODAY", parts=[(792.5, 800.5)],
             vo="Three. Kai versus one hill."),
        dict(rank=2, title="100K IN ONE NIGHT", parts=[(3425.0, 3432.2)],
             vo="Two. A hundred K in one night."),
        dict(rank=1, title="ONE JUMP TOO FAR", parts=[(3778.6, 3787.2), (3810.2, 3816.8)],
             vo="Number one. Rich, wanted, and one jump too far."),
    ],
    outro="Which was craziest? Comment your number.",
    outro_lines=[("WHICH ONE WAS", 96, -120), ("THE {CRAZIEST}?", 120, -20), ("COMMENT YOUR NUMBER", 80, 100)],
    speed=1.18, crop=None, fix={},
)

if __name__ == "__main__":
    print(topn.render(SPEC))
