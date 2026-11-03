"""Transcription engine.

Primary engine: faster-whisper (local, Whisper-compatible, word-level timestamps, VAD).
Alternative: sidecar transcripts (.json / .srt / .vtt next to the media) — used when present and
``prefer_sidecar`` is on, or when engine is ``sidecar_only``. Sidecar JSON may carry speaker labels,
which is how speaker separation is supported (e.g. output from a diarization tool you run).

Transcripts are stored in SQLite and indexed in an FTS5 table for searching.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Protocol

from ..config import Settings
from ..core.database import Database, dumps, loads, now_iso
from ..core.logger import get_logger
from ..models import Segment, Transcript, Word

log = get_logger("transcription")


class TranscriptionError(RuntimeError):
    pass


class Transcriber(Protocol):
    name: str

    def transcribe(self, audio_path: Path, source_id: str) -> Transcript: ...


# --------------------------------------------------------------------------- sidecars
_TS = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")


def _ts(s: str) -> float:
    m = _TS.search(s)
    if not m:
        raise ValueError(f"bad timestamp {s!r}")
    h, mi, se, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(se) + int(ms.ljust(3, "0")) / 1000


def _estimate_words(text: str, start: float, end: float, speaker: str | None) -> list[Word]:
    toks = text.split()
    if not toks:
        return []
    weights = [max(1, len(t)) for t in toks]
    total = sum(weights)
    out, t = [], start
    for tok, w in zip(toks, weights):
        d = (end - start) * w / total
        out.append(Word(round(t, 3), round(t + d, 3), tok, 1.0, speaker))
        t += d
    return out


def parse_srt_vtt(text: str) -> list[Segment]:
    segs: list[Segment] = []
    blocks = re.split(r"\n\s*\n", text.replace("\r", ""))
    for b in blocks:
        lines = [l for l in b.strip().split("\n") if l.strip()]
        tl = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if tl is None:
            continue
        a, _, c = lines[tl].partition("-->")
        try:
            st, en = _ts(a), _ts(c)
        except ValueError:
            continue
        body = " ".join(lines[tl + 1:])
        speaker = None
        m = re.match(r"^\s*(?:<v\s+([^>]+)>|\[?([A-Za-z0-9 _]{1,30})\]?:)\s*(.*)$", body)
        if m and (m.group(1) or m.group(2)):
            speaker = (m.group(1) or m.group(2)).strip()
            body = m.group(3)
        body = re.sub(r"<[^>]+>", "", body).strip()
        if body:
            segs.append(Segment(st, en, body, _estimate_words(body, st, en, speaker), speaker))
    return segs


def parse_json_transcript(data: dict | list) -> tuple[list[Segment], str]:
    raw = data.get("segments", data) if isinstance(data, dict) else data
    segs, timing = [], "native"
    for s in raw:
        words = [Word(float(w["start"]), float(w["end"]), str(w.get("text", w.get("word", ""))).strip(),
                      float(w.get("probability", w.get("confidence", 1.0))), w.get("speaker", s.get("speaker")))
                 for w in s.get("words", [])]
        if not words:
            timing = "estimated"
            words = _estimate_words(s["text"], float(s["start"]), float(s["end"]), s.get("speaker"))
        segs.append(Segment(float(s["start"]), float(s["end"]), str(s["text"]).strip(), words, s.get("speaker")))
    return segs, timing


def find_sidecar(media: Path) -> Path | None:
    for ext in (".transcript.json", ".json", ".srt", ".vtt"):
        cand = media.with_suffix(ext)
        if cand.exists() and not cand.name.endswith(".source.json"):
            return cand
    return None


def load_sidecar(path: Path, source_id: str) -> Transcript:
    if path.suffix == ".json":
        segs, timing = parse_json_transcript(json.loads(path.read_text(encoding="utf-8")))
    else:
        segs, timing = parse_srt_vtt(path.read_text(encoding="utf-8")), "estimated"
    if not segs:
        raise TranscriptionError(f"sidecar transcript {path} contained no segments")
    return Transcript(source_id, f"sidecar:{path.suffix.lstrip('.')}", "en", segs, timing)


# --------------------------------------------------------------------------- whisper
class FasterWhisperTranscriber:
    name = "faster_whisper"

    def __init__(self, settings: Settings):
        self.cfg = settings.global_.transcription
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                raise TranscriptionError("faster-whisper not installed: pip install faster-whisper") from e
            model_ref = os.environ.get(self.cfg.model_path_env) or self.cfg.model_size
            try:
                self._model = WhisperModel(model_ref, device=self.cfg.device, compute_type=self.cfg.compute_type)
            except Exception as e:
                raise TranscriptionError(
                    f"could not load Whisper model '{model_ref}': {e}. The first run downloads the model "
                    f"from Hugging Face; offline, set {self.cfg.model_path_env} to a local model folder.") from e
        return self._model

    def transcribe(self, audio_path: Path, source_id: str) -> Transcript:
        model = self._load()
        seg_iter, _info = model.transcribe(str(audio_path), language=self.cfg.language, word_timestamps=True,
                                           vad_filter=self.cfg.vad_filter, condition_on_previous_text=False)
        segs = []
        for s in seg_iter:
            words = [Word(round(w.start, 3), round(w.end, 3), w.word.strip(), float(w.probability))
                     for w in (s.words or []) if w.word.strip()]
            segs.append(Segment(round(s.start, 3), round(s.end, 3), s.text.strip(), words,
                                avg_logprob=s.avg_logprob, no_speech_prob=s.no_speech_prob))
        return Transcript(source_id, f"faster_whisper:{self.cfg.model_size}", self.cfg.language, segs, "native")


# --------------------------------------------------------------------------- gemini
class GeminiTranscriber:
    """Transcription with Gemini audio understanding (works on the free tier, needs network).

    Gemini returns sentence-level segments with timestamps; word timings inside a segment are
    estimated, and segment boundaries are snapped to detected speech so captions stay in sync."""
    name = "gemini"
    SCHEMA = {"type": "object", "properties": {"segments": {"type": "array", "items": {
        "type": "object", "properties": {"start": {"type": "number"}, "end": {"type": "number"},
                                         "speaker": {"type": "string"}, "text": {"type": "string"}},
        "required": ["start", "end", "text"]}}}, "required": ["segments"]}
    PROMPT = ("Transcribe this English audio verbatim. Split it into short segments of one sentence or "
              "phrase (at most ~8 seconds each). For each segment give start and end in seconds from the "
              "beginning of the audio, the speaker label (S1, S2, ...) and the exact words spoken. Do not "
              "summarise, fix, or invent words; mark unclear words as [inaudible]. Return JSON.")

    def __init__(self, settings: Settings, gemini=None):
        from ..research.google_ai import GeminiClient
        self.gemini = gemini or GeminiClient(settings.global_.google_ai)
        self.chunk = 600.0

    def transcribe(self, audio_path: Path, source_id: str) -> Transcript:
        from google.genai import types
        from ..core.media import extract_audio_wav, media_info, read_wav_mono, run
        from ..detection.audio_analyzer import analyze_samples
        if not self.gemini.available():
            raise TranscriptionError("Gemini transcription needs GEMINI_API_KEY")
        dur = media_info(audio_path)["duration"]
        data, sr = read_wav_mono(audio_path)
        feat = analyze_samples(data, sr)
        segs: list[Segment] = []
        t = 0.0
        while t < dur - 0.5:
            length = min(self.chunk, dur - t)
            mp3 = audio_path.with_suffix(f".{int(t)}.mp3")
            run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-t", f"{length:.2f}", "-i", str(audio_path),
                 "-ac", "1", "-b:a", "64k", str(mp3)], timeout=600)
            part = types.Part.from_bytes(data=mp3.read_bytes(), mime_type="audio/mp3")
            mp3.unlink(missing_ok=True)
            res = self.gemini.generate_json([part, self.PROMPT], self.SCHEMA, temperature=0.0)
            for r in (res or {}).get("segments", []):
                try:
                    st, en, text = float(r["start"]) + t, float(r["end"]) + t, str(r["text"]).strip()
                except (KeyError, TypeError, ValueError):
                    continue
                if not text or en <= st or st >= t + length + 1:
                    continue
                st, en = self._snap(feat, st, min(en, t + length))
                spk = r.get("speaker") or None
                words = _estimate_words(text, st, en, spk)
                for w in words:
                    if "[inaudible]" in w.text:
                        w.probability = 0.0
                    else:
                        w.probability = 0.8   # model-estimated timing, not acoustic confidence
                segs.append(Segment(st, en, text, words, spk))
            t += length
        segs.sort(key=lambda s: s.start)
        for a, b in zip(segs, segs[1:]):   # remove overlaps
            if b.start < a.end:
                a.end = max(a.start + 0.2, b.start - 0.02)
                a.words = _estimate_words(a.text, a.start, a.end, a.speaker)
        return Transcript(source_id, f"gemini:{self.gemini.last_model or self.gemini.cfg.model}", "en", segs, "estimated")

    @staticmethod
    def _snap(feat, st: float, en: float) -> tuple[float, float]:
        """Move boundaries inward/outward (max 0.6 s) to the nearest voiced audio."""
        def voiced(x):
            return not feat.silence[feat.idx(x)]
        for d in [i * 0.1 for i in range(7)]:
            if voiced(st + d):
                st = st + d; break
            if st - d >= 0 and voiced(st - d):
                st = st - d; break
        for d in [i * 0.1 for i in range(7)]:
            if voiced(en - d):
                en = en - d + 0.1; break
        return round(st, 2), round(max(en, st + 0.3), 2)


# --------------------------------------------------------------------------- engine
class TranscriptionEngine:
    def __init__(self, db: Database, settings: Settings, transcriber: Transcriber | None = None):
        self.db, self.settings = db, settings
        self.cfg = settings.global_.transcription
        self._transcriber = transcriber

    @property
    def transcriber(self) -> Transcriber:
        if self._transcriber is None:
            if self.cfg.engine == "gemini":
                self._transcriber = GeminiTranscriber(self.settings)
            else:
                self._transcriber = FasterWhisperTranscriber(self.settings)
        return self._transcriber

    def _transcribe(self, audio_path: Path, source_id: str) -> Transcript:
        """faster-whisper first; if its model cannot be loaded (e.g. offline), fall back to Gemini."""
        try:
            return self.transcriber.transcribe(audio_path, source_id)
        except TranscriptionError as e:
            if self.cfg.engine != "faster_whisper" or not getattr(self.cfg, "fallback_to_gemini", True):
                raise
            g = GeminiTranscriber(self.settings)
            if not g.gemini.available():
                raise
            from ..core.logger import get_logger as _gl
            _gl("transcription").warning("whisper unavailable (%s); using Gemini transcription", str(e)[:200])
            self._transcriber = g
            return g.transcribe(audio_path, source_id)

    def get(self, source_id: str) -> Transcript | None:
        r = self.db.one("SELECT data FROM transcripts WHERE source_id=?", (source_id,))
        return Transcript.from_dict(loads(r["data"])) if r else None

    def transcribe_source(self, source: dict, audio_path: Path) -> Transcript:
        existing = self.get(source["id"])
        if existing:
            return existing  # checkpoint: never re-transcribe
        media = Path(source["local_path"])
        sidecar = find_sidecar(media)
        if sidecar and (self.cfg.prefer_sidecar or self.cfg.engine == "sidecar_only"):
            tr = load_sidecar(sidecar, source["id"])
        elif self.cfg.engine == "sidecar_only":
            raise TranscriptionError("engine is sidecar_only but no .json/.srt/.vtt transcript found")
        else:
            tr = self._transcribe(audio_path, source["id"])
        if not tr.segments:
            raise TranscriptionError("no speech detected")
        self.save(source, tr)
        return tr

    def save(self, source: dict, tr: Transcript) -> None:
        words = tr.words
        avg = sum(w.probability for w in words) / len(words) if words else None
        with self.db.transaction() as c:
            c.execute("INSERT OR REPLACE INTO transcripts(source_id,engine,language,word_timing,data,avg_confidence,created_at) "
                      "VALUES(?,?,?,?,?,?,?)", (tr.source_id, tr.engine, tr.language, tr.word_timing,
                                                dumps(tr.to_dict()), avg, now_iso()))
            c.execute("DELETE FROM transcript_fts WHERE source_id=?", (tr.source_id,))
            for s in tr.segments:
                c.execute("INSERT INTO transcript_fts(source_id,profile,t_start,t_end,text) VALUES(?,?,?,?,?)",
                          (tr.source_id, source["profile"], s.start, s.end, s.text))

    def search(self, query: str, profile: str | None = None, limit: int = 20) -> list[dict]:
        q = " ".join(f'"{t}"' for t in re.findall(r"\w+", query))
        if not q:
            return []
        sql = "SELECT source_id, profile, t_start, t_end, text FROM transcript_fts WHERE transcript_fts MATCH ?"
        params: list = [q]
        if profile:
            sql += " AND profile=?"; params.append(profile)
        return self.db.query(sql + " LIMIT ?", (*params, limit))
