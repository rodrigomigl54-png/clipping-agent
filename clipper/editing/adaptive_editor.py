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
    style: dict | None = None
    text_placement: dict | None = None
    captions_enabled: bool = True
    output_duration: float | None = None
    upscale: float | None = None
    details: list | None = None

    @property
    def duration(self) -> float:
        return self.output_duration if self.output_duration else self.end - self.start


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

    # ---------------------------------------------------------------- learned styles
    def _style_layout(self, preset: dict, cam, region, source: dict, out_w: int, out_h: int) -> tuple[str, str]:
        lay = preset.get("layout", "focus")
        if lay == "split_cam":
            if region is not None or cam.face_found >= 0.3:
                return "stack_regions", "streamer camera + gameplay split"
            return "fit_blur", "example uses a camera split but no streamer camera was found in this source"
        if lay == "full_gameplay":
            return "focus", "full-screen gameplay crop"
        return (lay if lay in ("focus", "fit_blur", "letterbox") else "fit_blur"), "example layout"

    def _cam_stack(self, preset: dict, cam, region, source: dict, out_w: int, out_h: int) -> list:
        from ..core.media import media_info
        info = media_info(source["local_path"])
        sw, sh = info["width"], info["height"]
        split = float(preset.get("split_ratio", 0.5))
        top_is_cam = preset.get("cam_position", "top") != "bottom"
        cam_frac = split if top_is_cam else 1 - split
        panel_aspect = out_w / (out_h * cam_frac)
        if region is not None:
            cam_region = tuple(region)
        else:
            import numpy as _np
            fx = float(_np.median(cam.cx)); fy = float(_np.median(cam.cy))
            fh = float(_np.median([h for h in cam.face_h if h > 0]) or 0.2)
            h = min(1.0, fh * 3.2)
            w = min(1.0, h * sh * panel_aspect / sw)
            x = min(max(0.0, fx - w / 2), 1 - w)
            y = min(max(0.0, fy - h * 0.45), 1 - h)
            cam_region = (round(x, 4), round(y, 4), round(w, 4), round(h, 4))
        gameplay = (0.0, 0.0, 1.0, 1.0)
        return [(cam_region, cam_frac), (gameplay, 1 - cam_frac)] if top_is_cam else \
               [(gameplay, 1 - cam_frac), (cam_region, cam_frac)]

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
             clip_id: str, out_dir: Path, title: str | None = None, gemini=None,
             force_layout: str | None = None) -> EditResult:
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
        stack = [(tuple(r), f) for r, f in loads(source.get("extra"), {}).get("stack_regions", [])]
        caption_cfg = prof.editing.caption
        title_cfg = dict(ecfg.title_overlay)
        captions_on = True
        style_used = None
        if prof.editing.layout_policy == "style_examples" and self.db is not None and not stack:
            from ..styles.style_library import StyleLibrary
            choice = StyleLibrary(self.db, self.settings).choose(prof.id, candidate.get("category"))
            if choice:
                p = choice.preset
                style_used = {"examples": choice.example_ids, "reason": choice.reason, "preset": p}
                c = p.get("caption", {})
                captions_on = c.get("enabled", True)
                caption_cfg = caption_cfg.model_copy(update={k: v for k, v in c.items()
                                                             if k in type(caption_cfg).model_fields})
                caption_y = c.get("position", caption_y)
                title_cfg.update(p.get("title_overlay", {}))
                layout, reason = self._style_layout(p, cam, region, source, out_w, out_h)
                if layout == "stack_regions":
                    stack = self._cam_stack(p, cam, region, source, out_w, out_h)
                reason = f"style from examples ({choice.reason}); {reason}"
        if force_layout:
            layout, reason, stack = force_layout, f"A/B variant B layout ({force_layout})", []
        plan = LayoutPlan(layout=layout, out_w=out_w, out_h=out_h, streamer_fraction=fraction, region=region,
                          camera=cam, zoom_cfg=dict(ecfg.zoom), needs_gameplay=layout in ("split_gta", "hybrid"),
                          reason=reason, stack=stack)
        # ---- quality gate: never enlarge the source so much that the clip looks soft
        from ..core.media import media_info as _mi0
        from .text_safety import upscale_factor
        _si = _mi0(source["local_path"])
        max_up = float(self.settings.quality.get("technical", {}).get("max_upscale", 2.0))
        up = upscale_factor(plan, _si["width"], _si["height"])
        if up > max_up and not fmt:          # experiment formats (A/B/C) are never switched silently
            for alt in ("letterbox", "fit_blur"):
                if alt == plan.layout:
                    continue
                trial = LayoutPlan(layout=alt, out_w=out_w, out_h=out_h, camera=cam, zoom_cfg=dict(ecfg.zoom), reason="")
                if upscale_factor(trial, _si["width"], _si["height"]) <= max_up:
                    plan = LayoutPlan(layout=alt, out_w=out_w, out_h=out_h, camera=cam, zoom_cfg=dict(ecfg.zoom),
                                      reason=f"{reason}; switched to {alt}: source {_si['width']}x{_si['height']} would be "
                                             f"enlarged {up:.1f}x in '{layout}' (max {max_up}x)")
                    layout, reason = alt, plan.reason
                    up = upscale_factor(plan, _si["width"], _si["height"])
                    break
        self.last_upscale = round(up, 2)
        if prof.editing.zoom_emphasis and ecfg.zoom.get("enabled", True) and layout in ("focus", "fit_blur", "letterbox"):
            plan.zoom_times = self.zoom_times(audio, start, end, int(ecfg.zoom.get("max_emphasis_per_clip", 3)))
        # ---- retention timeline (dead-air jump cuts) and detail tools (zoom / circle / arrow / freeze)
        from .detail_tools import (Timeline, font_for_labels, needs_detail_tools, plan_details, remove_dead_air)
        timeline = Timeline.whole(end - start)
        if prof.editing.dead_air_removal:
            timeline = remove_dead_air(transcript.words_in(start, end), start, end, audio)
        details = []
        clip_text = " ".join(x.text for x in transcript.window(start, end))
        if prof.editing.detail_tools and gemini is not None and gemini.available() and \
                needs_detail_tools(candidate.get("category"), clip_text):
            details = [d for d in plan_details(source["local_path"], start, end, clip_text, gemini)
                       if timeline.map_time(d.t) is not None]
            for d in details:
                if d.freeze > 0:
                    timeline.insert_hold(d.t, d.freeze)
        plan.zoom_times = [m for m in (timeline.map_time(z) for z in plan.zoom_times) if m is not None]
        out_dir.mkdir(parents=True, exist_ok=True)
        ass = out_dir / f"{clip_id}.ass"
        overlays = []
        image_title = bool(title) and title_cfg.get("enabled", True) and title_cfg.get("renderer", "image") == "image"
        from ..core.media import media_info as _mi
        from .text_safety import place_text
        _info = _mi(source["local_path"])
        card = None
        if image_title:
            from .title_card import make_title_card
            card = make_title_card(title, title_cfg, out_w, self.settings.root)
        cap_pref = (caption_y if style_used and 'position' in style_used['preset'].get('caption', {})
                    else plan.caption_y(caption_y))
        from .text_safety import faces_in_output
        from .layout_engine import compose as _compose
        from ..core.media import read_frames as _rf
        sample_frames = []
        if layout not in ("split_gta", "hybrid"):          # those need the gameplay feed to compose
            dur = max(0.5, end - start)
            for k in range(4):
                tt = dur * (0.1 + 0.8 * k / 3)
                fr = next(iter(_rf(source["local_path"], start + tt, 0.05, 25, min(_info["width"], 1280))), None)
                if fr is not None:
                    sample_frames.append(_compose(fr, plan, tt))
        placement = place_text(plan, _info["width"], _info["height"], extra_protected=faces_in_output(sample_frames),
                               title_h=card.shape[0] if card is not None else None,
                               title_pref=float(title_cfg.get("position", 0.10)),
                               caption_h=int(caption_cfg.size * 1.7), caption_pref=cap_pref, safe=ecfg.safe_zones)
        if card is not None and placement.title_y is not None:
            if placement.title_scale < 1.0:
                card = make_title_card(title, {**title_cfg, "size": int(title_cfg.get("size", 62) * placement.title_scale),
                                               "box_padding": int(title_cfg.get("box_padding", 22) * placement.title_scale)},
                                       out_w, self.settings.root)
            secs = title_cfg.get("seconds")
            overlays.append((card, placement.title_y, float(secs) if secs else None))
        captions_on = captions_on and placement.caption_center is not None
        from ..models import Word as _W
        cap_words = []
        for w in (transcript.words_in(start, end) if captions_on else []):
            a, b = timeline.map_time(w.start - start), timeline.map_time(max(w.start, w.end - 0.01) - start)
            if a is not None:
                cap_words.append(_W(start + a, start + (b if b is not None else a + (w.end - w.start)), w.text, w.probability))
        cap = build_ass(cap_words, start, start + timeline.duration, caption_cfg, width=out_w,
                        height=out_h, y_fraction=placement.caption_center or 0.66, safe=ecfg.safe_zones,
                        low_conf=self.settings.global_.transcription.low_confidence_threshold, out_path=ass,
                        title=None if image_title else title, title_cfg=title_cfg)
        fonts = self.settings.path("assets/fonts")
        out = render(source["local_path"], start, end, plan, out_dir / f"{clip_id}.mp4", output_cfg=ecfg.output,
                     audio_cfg=ecfg.audio, ass_path=ass, gameplay=gameplay, gameplay_offset=offset,
                     fonts_dir=fonts, timeout=self.settings.global_.pipeline.stage_timeout_seconds,
                     overlays=overlays, timeline=timeline, details=details,
                     label_font=font_for_labels(self.settings.root))
        elements = ["vertical reframing", "synchronized captions", "loudness normalization"]
        if not timeline.is_trivial:
            elements.append("pacing edit (dead air removed)")
        if details:
            elements.append("detail callouts (zoom/circle/arrow)")
        if layout == "focus" and cam.face_found > 0.2:
            elements.append("face-tracked crop")
        if plan.zoom_times:
            elements.append("emphasis zoom")
        if layout in ("split_gta", "hybrid", "stack_regions"):
            elements.append("multi-panel composition")
        return EditResult(out, start, end, layout, fmt, cap,
                          str(gameplay) if gameplay else None, reason, elements, style_used,
                          {"title_y": placement.title_y, "title_scale": placement.title_scale,
                           "caption_center": placement.caption_center, "protected": placement.protected,
                           "notes": placement.notes, "ok": placement.ok}, captions_on, timeline.duration,
                          [d.__dict__ for d in details], self.last_upscale)
