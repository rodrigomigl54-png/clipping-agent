import subprocess

import numpy as np
import pytest

from clipper.editing import template_edit as T
from clipper.editing.hype_editor import Shot, letterbox_bar


def test_text_events_counter_and_lines():
    items = [{"text": f"{v}\nDAYS", "start": i * 0.1, "end": i * 0.1 + 0.1} for i, v in enumerate([993, 963, 927, 891, 7])]
    items += [{"text": "ARE", "start": 2.88, "end": 3.58}, {"text": "ARE YOU READY", "start": 3.6, "end": 5.6},
              {"text": "only 7 days left", "start": 6.0, "end": 7.0}]
    ev = T.text_events(items, cuts=[2.867, 3.6], duration=10)
    c = ev[0]
    assert c["type"] == "counter" and c["from"] == "{days}+986" and c["to"] == "{days}" and c["suffix"] == "DAYS"
    assert ev[1] == {"type": "line", "t0": 2.867, "t1": 3.6, "text": "ARE"}       # snapped to the cuts
    assert ev[3]["text"] == "only {days} days left"
    assert T._counter_value(c, 0.0, {"days": 6}) == 992
    assert T._counter_value(c, c["t1"] - 0.01, {"days": 6}) == 6


def test_counter_expression_is_restricted():
    with pytest.raises(ValueError):
        T._num("__import__('os')", {})


def test_letterbox_bar():
    img = np.full((360, 640, 3), 120, np.uint8)
    img[:36] = 0
    img[-36:] = 0
    assert abs(letterbox_bar(img) - 0.1) < 0.01
    assert letterbox_bar(np.full((360, 640, 3), 120, np.uint8)) == 0.0


def _shot(i, bright, faces=0, length=2.0, src="a.mp4"):
    return Shot(src=src, start=i * 3.0, end=i * 3.0 + length, motion=0.05, peak=i * 3.0 + 0.5, bright=bright, sat=80,
                hue=20, sharp=500, detail=0.1, cx=0.5, faces=faces)


def test_assign_matches_look_and_avoids_recent():
    tpl = {"slots": [{"t0": 0, "t1": 0.7, "bright": 30, "sat": 80, "hue": 20, "motion": 0.05, "faces": 0},
                     {"t0": 0.7, "t1": 1.4, "bright": 200, "sat": 80, "hue": 20, "motion": 0.05, "faces": 1}]}
    shots = [_shot(0, 200, 1), _shot(1, 30), _shot(2, 35), _shot(3, 190, 1)]
    f = T.assign(tpl, shots)
    assert f[0].shot.bright == 30 and f[1].shot.bright == 200
    f2 = T.assign(tpl, shots, exclude={("a.mp4", 3.0), ("a.mp4", 0.0)})
    assert f2[0].shot.bright == 35 and f2[1].shot.bright == 190


def test_learn_and_render_roundtrip(tmp_path):
    ref = tmp_path / "ref.mp4"
    parts = []
    for i, c in enumerate(["red", "blue", "green", "yellow", "white", "purple", "orange"]):
        parts += ["-f", "lavfi", "-i", f"color={c}:s=320x568:d=0.7:r=30"]
    fc = "".join(f"[{i}]" for i in range(7)) + "concat=n=7:v=1[v]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *parts, "-filter_complex", fc, "-map", "[v]", str(ref)], check=True)
    tpl = T.learn_template(ref, "t")
    assert tpl["orientation"] == "vertical" and len(tpl["cuts"]) == 6
    assert all(abs(c - 0.7 * (i + 1)) < 0.05 for i, c in enumerate(tpl["cuts"]))
    src = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:d=8:r=30", str(src)], check=True)
    shots = [Shot(src=str(src), start=i, end=i + 1.0, motion=0.05, peak=i + 0.2, bright=100, sat=100, hue=30, sharp=900,
                  detail=0.2, cx=0.5) for i in range(7)]
    tpl["text"] = [{"type": "counter", "t0": 0, "t1": 0.7, "every": 0.1, "from": "{days}+50", "to": "{days}"},
                   {"type": "line", "t0": 0.7, "t1": 1.4, "text": "ARE YOU READY"},
                   {"type": "scatter", "t0": 1.4, "t1": 1.8, "text": "ARE YOU READY"}]
    fills = T.assign(tpl, shots)
    res = T.render_template(tpl, fills, tmp_path / "o.mp4", {"days": 6}, src_size=(1920, 1080))
    assert res["size"] == "1080x1920" and abs(res["duration"] - tpl["duration"]) < 0.05 and res["upscale"] <= 2.0
