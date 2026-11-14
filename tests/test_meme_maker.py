import subprocess

from clipper.editing import meme_maker as M


def _meme_like(path):
    """Static caption bar on black on top + moving test pattern below (like a reference meme)."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=black:s=576x1024:d=3:r=30",
                    "-f", "lavfi", "-i", "testsrc2=s=576x324:d=3:r=30", "-f", "lavfi", "-i", "sine=f=440:d=3",
                    "-filter_complex", "[0][1]overlay=0:400,drawbox=x=40:y=250:w=496:h=60:color=white:t=fill[v]",
                    "-map", "[v]", "-map", "2:a", "-shortest", str(path)], check=True)


def test_extract_clip_finds_moving_band(tmp_path):
    src = tmp_path / "m.mp4"
    _meme_like(src)
    x, y, w, h = M.moving_box(str(src))
    assert abs(y - 400) < 30 and abs(h - 324) < 40 and w >= 500
    r = M.extract_clip(str(src), tmp_path / "c.mp4")
    assert r["w"] >= 500 and abs(r["duration"] - 3) < 0.2 and M._probe(r["file"])["audio"]


def test_render_meme_caption_on_top_and_upscale_capped(tmp_path):
    src = tmp_path / "m.mp4"
    _meme_like(src)
    clip = M.extract_clip(str(src), tmp_path / "c.mp4")["file"]
    r = M.render_meme(clip, "Me when the GTA 6 preload finally hits 100%", tmp_path / "o.mp4")
    info = M._probe(r["file"])
    assert (info["w"], info["h"]) == (1080, 1920) and info["audio"] and r["upscale"] <= 2.0


class _G:
    def generate_json(self, prompt, schema, temperature=0.2):
        assert "november 19" in prompt.lower()
        return {"captions": [{"clip": "a", "caption": "Me at 11:59 on November 18"}, {"clip": "b", "caption": "old one"}]}


def test_write_captions_skips_used():
    clips = [{"id": "a", "what": "x", "emotion": ["hype"], "used_captions": []},
             {"id": "b", "what": "y", "used_captions": ["old one"]}]
    caps = M.write_captions(clips, _G(), days=5, topics=["lucia"], examples=["POV: 19.11"], today="2026-11-14")
    assert caps == {"a": "Me at 11:59 on November 18"}
