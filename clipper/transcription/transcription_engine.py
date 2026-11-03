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


# --------------------------------------------------------------------------- engine
class TranscriptionEngine:
    def __init__(self, db: Database, settings: Settings, transcriber: Transcriber | None = None):
        self.db, self.settings = db, settings
        self.cfg = settings.global_.transcription
        self._transcriber = transcriber

    @property
    def transcriber(self) -> Transcriber:
        if self._transcriber is None:
            self._transcriber = FasterWhisperTranscriber(self.settings)
        return self._transcriber

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
            tr = self.transcriber.transcribe(audio_path, source["id"])
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
