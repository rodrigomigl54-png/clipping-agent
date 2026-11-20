"""Narration for LF2 with Chatterbox (MIT, local) conditioned on our own synthetic voice #2 (Kokoro Onyx70+Fenrir30).
Sentence by sentence, with emotion per sentence type, then Whisper word timings -> <vo>/<section>.wav(.json).
Usage: python content/longform/2026-11-20_gta6_50_things/voice.py [vo_dir] [section ids...]
Skips sections whose wav already exists, so it can be resumed.
"""
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
VO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/claude-0/lf2vo")
ONLY = sys.argv[2:]
REF = "/tmp/claude-0/voice/mix_on70_fe30.wav"           # our own Kokoro blend (no third-party voice)


def split_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“])", text.strip())
    out = []
    for p in parts:                                     # very short fragments ride along with the next sentence
        if out and len(out[-1].split()) < 3:
            out[-1] = out[-1] + " " + p
        else:
            out.append(p)
    return out


def style(sid, sent, i):
    """(exaggeration, cfg_weight, pause_after) by context."""
    s = sent.lower()
    if sid == "hook":
        return (0.7, 0.35, 0.45) if len(sent.split()) <= 5 else (0.6, 0.4, 0.35)
    if sid.startswith("ch"):
        return 0.7, 0.35, 0.3
    if s.startswith("number") or s.startswith("and number"):
        return 0.6, 0.4, 0.25                            # "Number twenty-three." punchy
    if any(w in s for w in ("gone", "mistake", "don't", "won't", "never", "careful", "stupid", "heavier", "fight back")):
        return 0.65, 0.38, 0.3
    if sid == "outro":
        return 0.5, 0.45, 0.35
    return 0.55, 0.42, 0.28


def main():
    import torch
    import torchaudio as ta
    from chatterbox.tts import ChatterboxTTS
    from faster_whisper import WhisperModel
    torch.set_num_threads(8)
    VO.mkdir(parents=True, exist_ok=True)
    script = json.loads((HERE / "script.json").read_text())
    tts = ChatterboxTTS.from_pretrained(device="cpu")
    asr = WhisperModel("small.en", compute_type="int8")
    t0 = time.time()
    for sec in script["sections"]:
        sid = sec["id"]
        if ONLY and sid not in ONLY:
            continue
        wav_p = VO / f"{sid}.wav"
        if wav_p.exists() and (VO / f"{sid}.wav.json").exists():
            continue
        pieces = []
        for i, sent in enumerate(split_sentences(sec["text"])):
            ex, cfg, pause = style(sid, sent, i)
            torch.manual_seed(1000 + i)
            w = tts.generate(sent, audio_prompt_path=REF, exaggeration=ex, cfg_weight=cfg)
            pieces += [w, torch.zeros(1, int(tts.sr * pause))]
        audio = torch.cat(pieces[:-1], dim=1)
        ta.save(str(wav_p), audio, tts.sr)
        a16 = ta.functional.resample(audio, tts.sr, 16000).numpy()[0].astype(np.float32)
        segs, _ = asr.transcribe(a16, word_timestamps=True, condition_on_previous_text=False)
        words = [{"w": x.word.strip(), "s": round(x.start, 3), "e": round(x.end, 3)} for s in segs for x in s.words]
        meta = {"dur": round(audio.shape[1] / tts.sr, 3), "sr": tts.sr, "words": words,
                "heard": " ".join(x["w"] for x in words)}
        (VO / f"{sid}.wav.json").write_text(json.dumps(meta))
        print(f"{time.time() - t0:6.0f}s {sid:6s} {meta['dur']:5.1f}s", flush=True)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
