"""Narration for the 21.11 facts Short (Chatterbox, our own Kokoro-blend voice), sentence by sentence + Whisper word timings.
Usage: python content/shorts/2026-11-21_facts/voice.py [out_dir]"""
import json
import os
import sys
from pathlib import Path

import numpy as np

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/claude-0/facts_vo")
REF = "/tmp/claude-0/voice/mix_on70_fe30.wav"
LINES = [
    ("hook", "Here are some insane things you can do in GTA 6.", 0.7, 0.35),
    ("cash", "You can rob a store, but if you die with the cash in your pocket, every dollar is gone. So bank it at an ATM first.", 0.6, 0.4),
    ("rifle", "Walk around with a rifle out, and people actually notice. They back off, or they call the cops.", 0.6, 0.4),
    ("know", "And the cops know exactly what you look like. Your face, your outfit, your car, even if a camera caught you.", 0.6, 0.4),
    ("stars", "Push it too far, and you're up to six stars, with police dogs, spike strips and helicopters.", 0.65, 0.38),
    ("guns", "You can't carry a whole arsenal anymore. Two handguns, two long guns, and the rest stays in your trunk.", 0.6, 0.4),
    ("radio", "You can put on headphones and listen to the radio on foot.", 0.55, 0.42),
    ("animals", "And Leonida has over a hundred and seventy animal species to find.", 0.6, 0.4),
    ("outro", "Which one are you trying first?", 0.65, 0.38),
]


def main():
    import torch
    import torchaudio as ta
    from chatterbox.tts import ChatterboxTTS
    from faster_whisper import WhisperModel
    torch.set_num_threads(8)
    OUT.mkdir(parents=True, exist_ok=True)
    tts = ChatterboxTTS.from_pretrained(device="cpu")
    asr = WhisperModel("small.en", compute_type="int8")
    seed = int(os.environ.get("SEED", "3000"))
    for i, (sid, text, ex, cfg) in enumerate(LINES):
        p = OUT / f"{sid}.wav"
        if p.exists() and (OUT / f"{sid}.json").exists():
            continue
        torch.manual_seed(seed + i)
        w = tts.generate(text, audio_prompt_path=REF, exaggeration=ex, cfg_weight=cfg)
        ta.save(str(p), w, tts.sr)
        a16 = ta.functional.resample(w, tts.sr, 16000).numpy()[0].astype(np.float32)
        # 0.5 s of silence in front, or Whisper drops the first words of a line
        segs, _ = asr.transcribe(np.concatenate([np.zeros(8000, np.float32), a16]), word_timestamps=True,
                                 condition_on_previous_text=False)
        words = [{"w": x.word.strip(), "s": round(max(0, x.start - 0.5), 3), "e": round(max(0, x.end - 0.5), 3)}
                 for s in segs for x in s.words]
        (OUT / f"{sid}.json").write_text(json.dumps({"dur": w.shape[1] / tts.sr, "text": text, "words": words,
                                                     "heard": " ".join(x["w"] for x in words)}))
        print(sid, round(w.shape[1] / tts.sr, 2), "|", " ".join(x["w"] for x in words), flush=True)
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
