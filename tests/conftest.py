"""Shared fixtures: an isolated project root and synthetic media with sidecar transcripts."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clipper.config import load_settings  # noqa: E402
from clipper.core.database import Database  # noqa: E402

# A conversation with a setup, a surprising reveal, a loud reaction and a payoff.
SCRIPT = [
    (2.0, 5.5, "A", "Alright chat we are back, let me tell you what happened yesterday."),
    (6.0, 10.0, "A", "So basically I was at the store with my boy and we see this guy."),
    (10.5, 14.5, "B", "Bro I remember that, he was wearing the craziest outfit ever."),
    (15.0, 19.0, "A", "And then he walks up to us and asks if we want to race him."),
    (19.5, 23.0, "B", "A race? In the store? Are you serious right now?"),
    (23.5, 27.5, "A", "I swear on everything, he puts his bag down and says ready set go."),
    (28.0, 31.0, "B", "No way! No way bro! What did you do?"),
    (31.5, 35.0, "A", "I ran! I actually ran down the cereal aisle!"),
    (35.5, 39.0, "B", "Hahaha I'm dead, I'm crying, that's hilarious!"),
    (39.5, 43.0, "A", "And the worst part, he won. He beat me by a mile."),
    (43.5, 47.0, "B", "You lost to a random guy in the store? You're trash bro."),
    (47.5, 51.0, "A", "Shut up, he was fast, I'm telling you he was fast."),
    (55.0, 58.5, "A", "Okay okay, anyway let's get back to the game now."),
    (59.0, 63.0, "A", "We need to finish this level before the stream ends tonight."),
    (63.5, 67.0, "A", "Let me check the map real quick and see where we are going."),
    (67.5, 71.0, "A", "Alright this looks good, we go left here and then straight."),
    (71.5, 75.0, "A", "Chat tell me if you see anything, I can't find the exit."),
    (75.5, 79.0, "A", "There it is, finally, we found it, let's go."),
]
LOUD = [(28.0, 31.5), (35.5, 39.0), (43.5, 47.0)]


def make_video(path: Path, duration: float = 82, loud=LOUD, size="1280x720", color_src="testsrc2") -> Path:
    vol = "+".join(f"between(t,{a},{b})*7" for a, b in loud) or "0"
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "lavfi", "-i", f"{color_src}=size={size}:rate=30:duration={duration}",
           "-f", "lavfi", "-i", f"anoisesrc=d={duration}:c=pink:a=0.04:r=48000",
           "-filter_complex", f"[1:a]volume='1+{vol}':eval=frame,aformat=channel_layouts=stereo[a]",
           "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-shortest", str(path)]
    subprocess.run(cmd, check=True)
    return path


def write_transcript(media: Path, script=SCRIPT) -> Path:
    segs = []
    for st, en, spk, text in script:
        toks = text.split()
        step = (en - st) / len(toks)
        words = [{"start": round(st + i * step, 3), "end": round(st + (i + 1) * step - 0.02, 3), "text": t,
                  "probability": 0.95, "speaker": spk} for i, t in enumerate(toks)]
        segs.append({"start": st, "end": en, "text": text, "speaker": spk, "words": words})
    out = media.with_suffix(".json")
    out.write_text(json.dumps({"segments": segs}), encoding="utf-8")
    return out


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Tests never touch the network: no Gemini key, no live YouTube."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    import clipper.research.source_discovery as sd
    def no_net(url):
        raise OSError("network disabled in tests")
    monkeypatch.setattr(sd.YouTubeRSSDiscovery, "_fetch", staticmethod(no_net))


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """A throw-away project root with a copy of the real config."""
    shutil.copytree(ROOT / "config", tmp_path / "config")
    for d in ("sources/inbox/amp", "sources/inbox/core", "sources/inbox/lospollostv", "outputs", "work", "logs",
              "assets/approved_gameplay", "assets/fonts", "database"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture()
def settings(project: Path):
    return load_settings(project)


@pytest.fixture()
def db(settings):
    d = Database(settings.db_path)
    yield d
    d.close()


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("media")
    return make_video(d / "stream.mp4")


@pytest.fixture(scope="session")
def gameplay_video(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("gameplay")
    return make_video(d / "gta_gameplay.mp4", duration=20, loud=[], size="1920x1080", color_src="smptehdbars")
