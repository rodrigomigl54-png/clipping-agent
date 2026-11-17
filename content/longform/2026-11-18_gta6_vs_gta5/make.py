"""Render long-form #1. Usage: python content/longform/2026-11-18_gta6_vs_gta5/make.py [vo_dir] [out] [section ids...]"""
import importlib.util, json, sys
from pathlib import Path
HERE = Path(__file__).parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from clipper.editing import longform as L  # noqa: E402

vo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/claude-0/lfvo")
out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "outputs/longform/LF1_GTA6_vs_GTA5.mp4"
only = sys.argv[3:]
script = json.loads((HERE / "script.json").read_text())
if only:
    script["sections"] = [s for s in script["sections"] if s["id"] in only]
spec = importlib.util.spec_from_file_location("plan", HERE / "plan.py")
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)
labels = {s["id"]: s.get("label", "") for s in script["sections"]}
tl = L.build_timeline(script, vo, plan.PLAN, tail=10.0 if not only or "outro" in only else 0.0)
res = L.render(tl, out, labels)
(out.with_suffix(".srt")).write_text(L.srt(tl))
(out.with_name(out.stem + "_chapters.txt")).write_text("\n".join(L.chapters(tl, labels)))
print(json.dumps(res), "\n".join(L.chapters(tl, labels)))
