"""2026-11-22 — 3 example AMP clips made the way clipping tools (OpusClip & co.) build them.

What is new compared to the 11-21 AMP clips (see docs/CLIPPING_PLAYBOOK.md):
  * moments picked with scripts/tools/find_moments.py (Hook / Flow / Value / Trend score) + checked by eye
  * COLD OPEN: the loudest 1.5–2.5 s reaction plays first, then a quick rewind, then the story from its setup
    -> the first second is already the payoff (stops the scroll), the viewer stays to see how it got there
  * JUMP CUTS: pauses > 0.45 s without loud sound are cut out (no dead air)
  * bigger subject: 4:5 crop of the frame where the source quality allows it (<= 2x upscale), else full frame
  * curiosity-gap headline (2 lines, name in yellow) + word-by-word captions with the active word yellow
  * thin progress bar at the bottom (people stay to "finish the bar")
  * stream audio only — the post kit names the song to add in the app

Sources (assets/streams/2026-11-22/, free vidIQ import, private test):
  kai_irl.mp4      Kai Cenat Live "Kai Cenat Plays GTA 6 In Real Life!" (ETWvry6twFA), 720p
  agent_cheat.mp4  Agent 00 "Will He Cheat The SECOND His Girlfriend Leaves Town" (iYcHdQ1g0yA), 480p
Usage: python scripts/manual_edits/2026-11-22_amp_examples.py [ids...]
"""
import importlib.util
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("amp", ROOT / "scripts/manual_edits/2026-11-21_amp_clips.py")
amp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(amp)

SRC = ROOT / "assets/streams/2026-11-22"
OUT = ROOT / "outputs/_PRIVATE_TEST/AMP/2026-11-22"
W, H, FPS = 1080, 1920, 30
YEL = (0, 214, 255)          # BGR

CLIPS = {}


def clip(cid, src, parts, headline, cold=None, crop=None, fix=None, jump=True):
    """parts [(a, b)] source seconds; cold (t, dur) cold-open shot; crop (cx 0..1) -> 4:5 crop centred there."""
    CLIPS[cid] = dict(src=src, parts=parts, headline=headline, cold=cold, crop=crop, fix=fix or {}, jump=jump)


def keep_intervals(words, rms, a, b, gap=0.45):
    """Cut silent pauses longer than `gap` between words (unless the pause is loud = action/reaction)."""
    ts = [t for t, _ in words if a <= t < b]
    if not ts:
        return [(a, b)]
    out, cur = [], a
    prev = max(a, ts[0] - 0.25)
    if prev - a > gap:
        cur = prev
    for t in ts[1:]:
        last_end = prev + 0.35                    # a word lasts ~0.35 s
        if t - last_end > gap:
            loud = np.mean(rms[int(last_end):int(t) + 1]) if int(t) + 1 > int(last_end) else 0
            base = np.median(rms) + 1e-4
            if loud < 1.3 * base:                 # quiet pause -> cut it
                out.append((cur, last_end + 0.12))
                cur = t - 0.12
        prev = t
    out.append((cur, min(b, max(prev + 0.6, cur + 0.3))))
    if b - out[-1][1] > 0:
        out[-1] = (out[-1][0], b)
    return [(x, y) for x, y in out if y - x > 0.25]


def words_flat(src, fix):
    d = json.loads((SRC / f"{src}.words.json").read_text())
    ws = []
    for s in d["segs"]:
        for w, t in s["w"]:
            k = re.sub(r"[^\w'*]", "", w).lower()
            w2 = fix.get(k, amp.BAD.get(k))
            txt = (w2 if w2 else re.sub(r"[^\w'?!*.,-]", "", w)).upper()
            if txt:
                ws.append((t, txt))
    return ws, np.array(d["rms"], float)


def probe(path):
    j = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                                   "stream=width,height", "-of", "json", str(path)], capture_output=True,
                                  text=True).stdout)
    return j["streams"][0]["width"], j["streams"][0]["height"]


def grab(path, a, b, w, h):
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(path), "-vf",
                        f"fps={FPS}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
    n = w * h * 3
    return [np.frombuffer(p[i:i + n], np.uint8).reshape(h, w, 3) for i in range(0, len(p) - n + 1, n)]


def render(cid):
    c = CLIPS[cid]
    path = SRC / f"{c['src']}.mp4"
    w, h = probe(path)
    ws, rms = words_flat(c["src"], c["fix"])
    # timeline: list of (source a, source b, kind)
    tl = []
    if c["cold"]:
        t, d = c["cold"]
        tl.append((t, t + d, "cold"))
    for a, b in c["parts"]:
        for x, y in (keep_intervals(ws, rms, a, b) if c["jump"] else [(a, b)]):
            tl.append((x, y, "main"))
    # output-time captions: map each word to where it lands on the timeline
    caps = []
    t_out = 0.0
    for a, b, kind in tl:
        if kind == "main":
            caps += [(t_out + (t - a), txt) for t, txt in ws if a <= t < b]
        t_out += (b - a) + (0.35 if kind == "cold" else 0)
    total = t_out
    subs = amp.sub_chunks(caps)
    head = [amp.fit(line, 1010, 84) for line in c["headline"]]
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / f"_{cid}.mp4"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
                            "-pix_fmt", "yuv420p", str(tmp)], stdin=subprocess.PIPE)
    # picture geometry
    if c["crop"] is not None:
        cw = int(h * 4 / 5)
        x0 = int(np.clip(c["crop"] * w - cw / 2, 0, w - cw))
        PW, PH = 1080, 1350
    else:
        cw, x0 = w, 0
        PW, PH = 1080, int(1080 * h / w)
    PY = 330 + (1350 - PH) // 2 if PH < 1350 else 330
    cache = {}
    audio_parts = []
    k = 0

    def compose(f, to):
        pic = f[:, x0:x0 + cw]
        main = cv2.resize(pic, (PW, PH), interpolation=cv2.INTER_LANCZOS4)
        bg = cv2.GaussianBlur(cv2.resize(f, (192, 108)), (0, 0), 6)
        bg = cv2.resize(bg, (int(H * 192 / 108), H))
        xo = (bg.shape[1] - W) // 2
        fr = (bg[:, xo:xo + W].astype(np.float32) * 0.35).astype(np.uint8)
        fr[PY:PY + PH] = main
        y = 70 if PH >= 1200 else 150
        for im in head:
            amp.paste(fr, im, W / 2, y + im.shape[0] / 2)
            y += im.shape[0] - 10
        for s0, s1, ch in subs:
            if s0 <= to < s1:
                cy = PY + PH - 170 if PH >= 1200 else PY + PH + 150     # on the picture when it's tall
                amp.paste(fr, amp.sub_image(ch, to, cache), W / 2, cy)
                break
        bw = int(W * min(1.0, to / total))
        cv2.rectangle(fr, (0, H - 14), (bw, H), YEL, -1)                # progress bar
        return fr

    t_out = 0.0
    for a, b, kind in tl:
        frames = grab(path, a, b, w, h)
        for j, f in enumerate(frames):
            to = t_out + j / FPS
            fr = compose(f, to)
            if kind == "cold" and j < 4:                                  # punch-in on the cold open
                z = 1.08 - 0.02 * j
                fr = cv2.resize(fr, None, fx=z, fy=z)[int((z - 1) * H / 2):int((z - 1) * H / 2) + H,
                                                      int((z - 1) * W / 2):int((z - 1) * W / 2) + W]
            enc.stdin.write(fr.tobytes())
        audio_parts.append((a, b))
        t_out += len(frames) / FPS
        if kind == "cold":                                                # 0.35 s rewind back to the start
            n = int(0.35 * FPS)
            rew = frames[::-1][::max(1, len(frames) // n)][:n]
            for j, f in enumerate(rew):
                fr = compose(f, t_out + j / FPS)
                fr = cv2.addWeighted(fr, 0.75, np.full_like(fr, 255), 0.25, 0)
                cv2.putText(fr, "<<", (60, 150), cv2.FONT_HERSHEY_SIMPLEX, 3, (255, 255, 255), 8)
                enc.stdin.write(fr.tobytes())
            audio_parts.append(("rew", n / FPS))
            t_out += n / FPS
    enc.stdin.close()
    enc.wait()
    # audio
    chunks = []
    for item in audio_parts:
        if item[0] == "rew":
            chunks.append(np.zeros((int(item[1] * 48000), 2), np.float32))
        else:
            chunks.append(amp.audio(path, [item]))
    a = np.concatenate(chunks)
    wav = OUT / f"_{cid}.wav"
    wf = wave.open(str(wav), "wb")
    wf.setnchannels(2)
    wf.setsampwidth(2)
    wf.setframerate(48000)
    wf.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())
    wf.close()
    out = OUT / f"PRIVATE-TEST_amp_{cid}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-i", str(wav), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-af", "loudnorm=I=-14:TP=-1.5", "-shortest",
                    str(out)], check=True)
    tmp.unlink()
    wav.unlink()
    return out, round(t_out, 1)


# ------------------------------------------------------------------ clip specs (find_moments + checked by eye)
# find_moments top pick (score 60/53/51): the deal at 275–336 and the chase at 465–522 — one story, one clip
clip("kai_irl_setup", "kai_irl", [(313.9, 336.4), (337.0, 343.0), (502.7, 518.0), (569.2, 587.7)],
     ["{KAI CENAT} DID A GTA 6 MISSION", "IN REAL LIFE... IT WENT WRONG"],
     cold=(324.5, 2.2), crop=0.5, fix={"field": "FAILED", "sent": "SET", "chase": "CHAT,"})

if __name__ == "__main__":
    for cid in sys.argv[1:] or list(CLIPS):
        print(cid, render(cid), flush=True)
