"""Example-clip style learning (local analysis, no network)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from clipper.config import load_settings
from clipper.core.media import media_info
from clipper.styles.style_library import StyleLibrary, derive_preset

from conftest import write_transcript


def _ff(args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


@pytest.fixture(scope="module")
def examples(tmp_path_factory):
    d = tmp_path_factory.mktemp("ex")
    split = d / "split.mp4"
    _ff(["-f", "lavfi", "-i", "testsrc2=size=540x480:rate=30:duration=6", "-f", "lavfi",
         "-t", "6", "-i", "mandelbrot=size=540x480:rate=30",
         "-filter_complex", "[0:v][1:v]vstack=inputs=2,format=yuv420p", "-t", "6", "-c:v", "libx264", "-preset", "ultrafast", str(split)])
    blur = d / "blur.mp4"
    _ff(["-f", "lavfi", "-i", "testsrc2=size=540x304:rate=30:duration=6",
         "-filter_complex", "[0:v]split[a][b];[a]scale=540:960,boxblur=30[bg];[bg][b]overlay=0:328,format=yuv420p",
         "-c:v", "libx264", "-preset", "ultrafast", str(blur)])
    full = d / "full.mp4"
    _ff(["-f", "lavfi", "-t", "6", "-i", "mandelbrot=size=540x960:rate=30", "-t", "6", "-pix_fmt", "yuv420p",
         "-c:v", "libx264", "-preset", "ultrafast", str(full)])
    return {"split": split, "blur": blur, "full": full}


def test_local_analysis_detects_layouts(settings, db, examples):
    lib = StyleLibrary(db, settings)
    s = lib.add(examples["split"], "gta6", category="funny_gameplay")
    b = lib.add(examples["blur"], "gta6", category="news_trailer")
    f = lib.add(examples["full"], "gta6", category="chaos_moment")
    assert s["metrics"]["layout_guess"] == "split_cam" and abs(s["metrics"]["seam_y"] - 0.5) < 0.03
    assert b["metrics"]["layout_guess"] == "fit_blur"
    assert f["metrics"]["layout_guess"] in ("focus", "full_gameplay")
    assert s["preset"]["layout"] == "split_cam" and abs(s["preset"]["split_ratio"] - 0.5) < 0.03


def test_choose_by_category_and_fallback(settings, db, examples):
    lib = StyleLibrary(db, settings)
    lib.add(examples["split"], "gta6", category="funny_gameplay")
    lib.add(examples["blur"], "gta6", category="news_trailer")
    assert lib.choose("gta6", "funny_gameplay").preset["layout"] == "split_cam"
    assert lib.choose("gta6", "news_trailer").preset["layout"] == "fit_blur"
    assert lib.choose("gta6", "glitch_bug") is not None            # falls back to all examples
    assert lib.choose("amp", "anything") is None                    # profiles stay separate


def test_vision_overrides_and_title_style():
    metrics = {"layout_guess": "focus", "seam_y": None, "faces_per_frame": 1.0, "duration": 30, "cuts_per_min": 4}
    vision = {"layout": "split_top_bottom", "facecam_position": "top", "split_ratio": 40, "captions_present": True,
              "caption_position": 0.42, "caption_uppercase": True, "caption_words_per_line": 2,
              "caption_highlight_color": "#ff0000", "title_banner_present": True, "title_position": 0.08,
              "title_box_color": "#FFFFFF", "title_text_color": "#000000"}
    p = derive_preset(metrics, vision)
    assert p["layout"] == "split_cam" and p["split_ratio"] == 0.4 and p["caption"]["highlight_color"] == "#FF0000"
    assert p["caption"]["max_words"] == 2 and p["title_overlay"]["enabled"] is True


def test_gta6_render_uses_learned_style(project, sample_video, examples):
    import yaml
    from clipper.core.orchestrator import Orchestrator
    (project / "config" / "local_overrides.yaml").write_text(yaml.safe_dump({"editing": {"output": {"preset": "ultrafast"}}}))
    orch = Orchestrator(load_settings(project))
    StyleLibrary(orch.db, orch.settings).add(examples["split"], "gta6", category="funny_gameplay")
    v = project / "gta6_stream.mp4"; shutil.copy(sample_video, v); write_transcript(v)
    res = orch.private_test(str(v), "gta6", ["Test Streamer"], max_clips=1)
    clip = orch.db.one("SELECT * FROM clips")
    assert clip and clip["layout"] in ("stack_regions", "fit_blur")      # no face in test media -> documented fallback
    out = [c["private_test"] for c in res["clips"] if c.get("private_test")]
    assert out and "/_PRIVATE_TEST/GTA6/" in out[0]["file"]
    assert media_info(out[0]["file"])["height"] == 1920
