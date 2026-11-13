import json
import subprocess
from datetime import date
from pathlib import Path

import pytest

from clipper.editing import hype_editor as H


def _tpl():
    return H.BeatTemplate(id="t", sound="s", sound_author="a", reference="r", bpm=84,
                          cuts=[1.0, 1.7, 2.4, 3.1], duration=3.2, flashes=[1.0])


def test_countdown_text_phases():
    assert H.countdown_text("2026-11-19", date(2026, 11, 13)).main == "6 DAYS"
    assert H.countdown_text("2026-11-19", date(2026, 11, 18)).main == "1 DAY"
    assert H.countdown_text("2026-11-19", date(2026, 11, 19)).main == "IT'S HERE"
    assert H.countdown_text("2026-11-19", date(2026, 11, 22)).main == "DAY 3"


def test_load_templates_only_beat_locked(tmp_path):
    f = tmp_path / "m.json"
    f.write_text(json.dumps({"A": {"dur": 5, "bpm": 90, "cuts": [1, 2], "cuts_on_beat": 0.9, "flashes": [1]},
                             "B": {"dur": 5, "bpm": 90, "cuts": [1, 2], "cuts_on_beat": 0.2, "cuts_on_half_beat": 0.3}}))
    t = H.load_templates(f, {"A": {"sound": "song", "author": "x", "reference": "url"}})
    assert list(t) == ["A"] and t["A"].sound == "song" and t["A"].drop == 1


def _shot(i, length=1.5, bright=100, hue=20, motion=0.05):
    return H.Shot(src="x.mp4", start=i * 2.0, end=i * 2.0 + length, motion=motion, peak=i * 2.0 + 0.5, bright=bright,
                  sat=100, hue=hue, sharp=500, detail=0.12, cx=0.5)


def test_plan_slots_beats_unique_and_alternating():
    shots = [_shot(0, 3.5, motion=0.01)] + [_shot(i, bright=60 + 40 * (i % 2), hue=20 + 60 * (i % 2)) for i in range(1, 8)]
    slots = H.plan_slots(_tpl(), shots)
    assert [s.kind for s in slots] == ["opener", "beat", "beat", "beat", "black"]
    assert slots[1].flash and slots[0].shot.length >= slots[0].dur
    used = [(s.shot.src, s.shot.start) for s in slots if s.shot]
    assert len(used) == len(set(used))
    beats = [s for s in slots if s.kind == "beat"]
    for a, b in zip(beats, beats[1:]):
        assert not H._similar(a.shot, b.shot)
    for s in beats:   # segment fits inside its shot and starts near the motion peak
        assert s.shot.start <= s.src_start and s.src_start + s.dur <= s.shot.end


def test_plan_slots_not_enough_shots():
    with pytest.raises(ValueError):
        H.plan_slots(_tpl(), [_shot(0, 3.5)])


def test_unusable_shots_rejected(tmp_path):
    # black + flat card + textured moving noise: only the textured part is usable
    src = tmp_path / "s.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=black:s=640x360:d=1.5",
                    "-f", "lavfi", "-i", "color=0xd8a0c8:s=640x360:d=1.5",
                    "-f", "lavfi", "-i", "life=s=640x360:mold=10:r=30:ratio=0.5:death_color=#203040:life_color=#e0b070,trim=duration=2", "-filter_complex",
                    "[0]format=yuv420p[a];[1]format=yuv420p[b];[2]format=yuv420p[c];[a][b][c]concat=n=3:v=1[v]", "-map", "[v]", "-r", "30", str(src)], check=True)
    shots = H.analyze_shots(src)
    assert any(not s.usable and s.reason.startswith("black") for s in shots)
    assert any(not s.usable and "card" in s.reason for s in shots)


def test_render_small(tmp_path):
    src = tmp_path / "s.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:d=6", "-r", "30",
                    str(src)], check=True)
    sh = H.Shot(src=str(src), start=0, end=6, motion=0.05, peak=1, bright=120, sat=120, hue=30, sharp=900,
                detail=0.2, cx=0.5)
    slots = [H.Slot(0, 0.5, "opener", sh, 0.1), H.Slot(0.5, 1.0, "beat", sh, 2.0, flash=True), H.Slot(1.0, 1.1, "black")]
    res = H.render_hype(slots, H.HypeText("GTA 6 comes out in 6 days.", "6 DAYS", "ARE YOU READY?"),
                        tmp_path / "o.mp4", src_size=(1920, 1080))
    assert Path(res["file"]).exists() and res["upscale"] <= 2.0 and abs(res["duration"] - 1.1) < 0.05
    m = H.music_instructions(_tpl())
    assert m["drop_at_s"] == 1.0 and m["cut_times_s"] == [1.0, 1.7, 2.4, 3.1]


@pytest.mark.parametrize("vals,expect", [
    ((166, 160, 0.049, 0.002, 2163), "text card"),        # PlayStation features card
    ((145, 140, 0.056, 0.003, 2073), "text card"),        # pre-load logo card
    ((79, 20, 0.089, 0.018, 2981), "logo"),               # GTA VI logo over a shot
    ((40, 15, 0.061, 0.029, 825), "logo"),                # "PRE-LOAD NOW" lettering over a shot
    ((101, 30, 0.171, 0.087, 906), ""),                   # police shootout
    ((95, 30, 0.144, 0.055, 912), ""),                    # skydive over Vice City
    ((16, 5, 0.028, 0.018, 88), "black"),
])
def test_reject_reason_real_trailer_numbers(vals, expect):
    r = H.reject_reason(*vals)
    assert (r == "") if expect == "" else r.startswith(expect)
