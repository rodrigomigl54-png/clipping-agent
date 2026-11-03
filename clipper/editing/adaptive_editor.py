"""Adaptive editing engine: plans and renders one vertical clip for a candidate moment."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings
from ..core.database import loads
from ..detection.audio_analyzer import AudioFeatures
from ..models import Transcript
from . import face_tracker
from .caption_engine import CaptionReport, build_ass
from .format_experiment import FormatExperiment
from .layout_engine import LayoutPlan, choose_auto_layout
from .renderer import render


@dataclass
class EditResult:
    path: Path
    start: float
    end: float
    layout: str
    format: str | None
    captions: CaptionReport
    gameplay_asset: str | None
    layout_reason: str
    transformative_elements: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start


class AdaptiveEditor:
    def __init__(self, settings: Settings, rights_gate=None, db=None):
        self.settings = settings
        self.gate = rights_gate
        self.db = db

    def trim(self, tr: Transcript, start: float, end: float, audio: AudioFeatures | None) -> tuple[float, float]:
        """Trim dead air at the edges without cutting speech or a live reaction."""
        t = self.settings.editing.trim
        words = tr.words_in(start, end)
        if not words:
            return start, end
        lead = words[0].start - start
        if lead > t.get("max_leading_silence", 0.4):
            if audio is None or audio.silence_fraction(start, words[0].start) > 0.6:
                start = words[0].start - 0.15
        tail = end - words[-1].end
        if tail > t.get("max_trailing_silence", 0.8):
            if audio is None or audio.silence_fraction(words[-1].end, end) > 0.6:
                end = words[-1].end + 0.4
        return round(start, 3), round(end, 3)

    def zoom_times(self, audio: AudioFeatures | None, start: float, end: float, max_n: int) -> list[float]:
        if audio is None or max_n <= 0:
            return []
        times = []
        sl = audio.z[audio.slice(start, end)]
        order = sl.argsort()[::-1]
        for i in order:
            if sl[i] < 2.5 or len(times) >= max_n:
                break
            t = float(i * audio.hop)
            if all(abs(t - x) > 4.0 for x in times) and 1.0 < t < (end - start) - 1.0:
                times.append(t)
        return sorted(times)

    def edit(self, *, source: dict, candidate: dict, transcript: Transcript, audio: AudioFeatures | None,
             clip_id: str, out_dir: Path, title: str | None = None) -> EditResult:
        prof = self.settings.profile(source["profile"])
        ecfg = self.settings.editing
        out_w, out_h = int(ecfg.output["width"]), int(ecfg.output["height"])
        start, end = self.trim(transcript, float(candidate["start"]), float(candidate["end"]), audio)
        region = loads(source.get("facecam_region"))
        region = tuple(region) if region else None
        ft = ecfg.face_tracking
        cam = face_tracker.track(source["local_path"], start, end - start, sample_fps=ft.get("sample_fps", 4),
                                 smoothing=ft.get("smoothing", 0.85), dead_zone=ft.get("dead_zone", 0.06),
                                 min_face=ft.get("min_face_size", 0.06), region=region)
        fmt, gameplay, offset = None, None, 0.0
        fraction = 0.5
        caption_y = prof.editing.caption.position
        if prof.editing.layout_policy == "experiment":
            exp = FormatExperiment(self.db, self.settings, self.gate, prof.id)
            fmt, spec, gameplay = exp.assign(candidate["id"], clip_id)
            layout = spec["layout"]
            fraction = float(spec.get("streamer_fraction", 0.5))
            reason = f"format experiment: Format {fmt}"
            caption_y = prof.format_experiment.caption_position.get(fmt, caption_y)
            if gameplay:
                offset = exp.gameplay_offset(gameplay)
        elif loads(source.get("extra"), {}).get("stack_regions"):
            layout, reason = "stack_regions", "source defines stacked regions (e.g. guest window over streamer cam)"
        elif prof.editing.layout_policy in ("focus", "fit_blur"):
            layout, reason = prof.editing.layout_policy, "profile layout policy"
        else:
            layout, reason = choose_auto_layout(cam, region)
        plan = LayoutPlan(layout=layout, out_w=out_w, out_h=out_h, streamer_fraction=fraction, region=region,
                          camera=cam, zoom_cfg=dict(ecfg.zoom), needs_gameplay=layout in ("split_gta", "hybrid"),
                          reason=reason, stack=[(tuple(r), f) for r, f in loads(source.get("extra"), {}).get("stack_regions", [])])
        if prof.editing.zoom_emphasis and ecfg.zoom.get("enabled", True) and layout in ("focus", "fit_blur"):
            plan.zoom_times = self.zoom_times(audio, start, end, int(ecfg.zoom.get("max_emphasis_per_clip", 3)))
        out_dir.mkdir(parents=True, exist_ok=True)
        ass = out_dir / f"{clip_id}.ass"
        cap = build_ass(transcript.words_in(start, end), start, end, prof.editing.caption, width=out_w,
                        height=out_h, y_fraction=plan.caption_y(caption_y), safe=ecfg.safe_zones,
                        low_conf=self.settings.global_.transcription.low_confidence_threshold, out_path=ass,
                        title=title, title_cfg=ecfg.title_overlay)
        fonts = self.settings.path("assets/fonts")
        out = render(source["local_path"], start, end, plan, out_dir / f"{clip_id}.mp4", output_cfg=ecfg.output,
                     audio_cfg=ecfg.audio, ass_path=ass, gameplay=gameplay, gameplay_offset=offset,
                     fonts_dir=fonts, timeout=self.settings.global_.pipeline.stage_timeout_seconds)
        elements = ["vertical reframing", "synchronized captions", "loudness normalization"]
        if layout == "focus" and cam.face_found > 0.2:
            elements.append("face-tracked crop")
        if plan.zoom_times:
            elements.append("emphasis zoom")
        if layout in ("split_gta", "hybrid", "stack_regions"):
            elements.append("multi-panel composition")
        return EditResult(out, start, end, layout, fmt, cap,
                          str(gameplay) if gameplay else None, reason, elements)
