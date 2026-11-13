"""Keep on-screen text (title card, captions) off the streamer and off the content.

Before rendering we compute *protected* vertical spans of the output frame — the streamer's face
(with head room and chin), the real picture in blurred/black-band layouts, the middle of gameplay
panels — and place text only in free space: blurred or black bands, the seam between panels, or above
/ below the face. If nothing fits, the title is shrunk, and if it still does not fit it is dropped:
covering the content is never the fallback.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .layout_engine import LayoutPlan

Span = tuple[int, int]


@dataclass
class TextPlacement:
    title_y: int | None                 # top of the title card (px) or None = title dropped
    title_scale: float                  # 1.0 = configured size
    caption_center: float | None        # fraction of height; None = captions off (no free space)
    protected: list[Span] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    ok: bool = True                     # False only if captions could not avoid protected areas


def picture_span(plan: LayoutPlan, src_w: int, src_h: int) -> Span:
    """Vertical span of the real picture in fit_blur / letterbox layouts (largest zoom included)."""
    W, H = plan.out_w, plan.out_h
    zmax = max([1.0] + ([float(plan.zoom_cfg.get("emphasis", 1.12))] if plan.zoom_times else []))
    nh = int(src_h * W * min(1.25, zmax) / src_w)
    yc = H * 0.42 if plan.layout == "fit_blur" else H / 2
    if plan.layout == "fit_blur":
        top = max(0, int(yc - src_h * W / src_w / 2))           # fit_blur anchors the unzoomed top
        return top, min(H, top + nh)
    return max(0, int(yc - nh / 2)), min(H, int(yc + nh / 2))


def protected_spans(plan: LayoutPlan, src_w: int, src_h: int) -> list[Span]:
    W, H = plan.out_w, plan.out_h
    cam = plan.camera
    face_h = float(np.median([h for h in cam.face_h if h > 0])) if cam is not None and cam.face_h.size and \
        (cam.face_h > 0).any() else 0.0
    if plan.layout in ("fit_blur", "letterbox"):
        return [picture_span(plan, src_w, src_h)]
    if plan.layout == "focus":
        if face_h > 0:
            zmax = float(plan.zoom_cfg.get("emphasis", 1.12)) if plan.zoom_times else 1.0
            fh = face_h * H * zmax                           # crop height == source height for 16:9 sources
            yc = H * 0.42 + fh * 0.08
            return [(max(0, int(yc - fh * 0.95)), min(H, int(yc + fh * 1.25)))]
        return [(int(H * 0.25), int(H * 0.72))]              # no face: keep the middle of the action clear
    if plan.layout == "stack_regions" and plan.stack:
        spans, y = [], 0
        for i, (region, frac) in enumerate(plan.stack):
            ph = H - y if i == len(plan.stack) - 1 else int(round(H * frac / 2) * 2)
            if tuple(region) == (0.0, 0.0, 1.0, 1.0):      # gameplay / full picture panel: protect its centre
                spans.append((y + int(ph * 0.30), y + int(ph * 0.80)))
            else:                                          # camera panel: face sits ~45% down the panel
                spans.append((y + int(ph * 0.15), y + int(ph * 0.78)))
            y += ph
        return spans
    if plan.layout in ("split_gta", "hybrid"):
        sh = plan.streamer_h
        return [(int(sh * 0.12), int(sh * 0.82)), (sh + int((H - sh) * 0.22), sh + int((H - sh) * 0.85))]
    return []


def _free(y0: int, y1: int, blocked: list[Span], margin: int) -> bool:
    return all(y1 + margin <= a or y0 - margin >= b for a, b in blocked)


def faces_in_output(frames: list[np.ndarray]) -> list[Span]:
    """Vertical spans of every face visible in composed output frames (head room + chin added)."""
    from ..detection.visual_analyzer import detect_faces
    import cv2
    spans: list[Span] = []
    for fr in frames:
        H, W = fr.shape[:2]
        small = cv2.resize(fr, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
        for x, y, w, h in detect_faces(small, 0.025):
            y, h = y * 2, h * 2
            spans.append((max(0, int(y - h * 0.45)), min(H, int(y + h * 1.35))))
    return spans


def place_text(plan: LayoutPlan, src_w: int, src_h: int, *, title_h: int | None, title_pref: float,
               caption_h: int, caption_pref: float, safe: dict, margin: int = 18,
               extra_protected: list[Span] | None = None) -> TextPlacement:
    W, H = plan.out_w, plan.out_h
    top_safe = int(H * safe.get("top", 0.08))
    bot_safe = H - int(H * safe.get("bottom", 0.20))
    prot = protected_spans(plan, src_w, src_h)
    layout_prot = list(prot)
    prot = prot + list(extra_protected or [])
    notes: list[str] = []

    def title_slot(scale: float) -> int | None:
        h = int(title_h * scale)
        pref = (layout_prot[0][0] - h - 24) if plan.layout in ("fit_blur", "letterbox") else int(H * title_pref)
        cands = [pref] + sorted(range(top_safe, bot_safe - h, 8), key=lambda y: abs(y - pref))
        return next((y for y in cands if top_safe <= y <= bot_safe - h and _free(y, y + h, prot, margin)), None)

    def caption_slot(blocked: list[Span]) -> tuple[int, int | None]:
        if plan.layout in ("fit_blur", "letterbox"):
            pref_c = layout_prot[0][1] + 30 + caption_h // 2
        else:
            pref_c = int(H * caption_pref)
        cands = [pref_c] + sorted(range(top_safe + caption_h // 2, bot_safe - caption_h // 2, 8),
                                  key=lambda y: abs(y - pref_c))
        return pref_c, next((y for y in cands if _free(y - caption_h // 2, y + caption_h // 2, blocked, margin)), None)

    scales = (1.0, 0.85, 0.72, 0.6) if title_h else (1.0,)
    first_fit: tuple[float, int] | None = None
    for scale in scales:
        ty = title_slot(scale) if title_h else None
        if title_h and ty is None:
            continue
        if title_h and first_fit is None:
            first_fit = (scale, ty)
        blocked = prot + ([(ty, ty + int(title_h * scale))] if ty is not None else [])
        pref_c, cy = caption_slot(blocked)
        if cy is not None:
            if scale < 1.0:
                notes.append(f"title shrunk to {scale:.0%} so title and captions both stay off the content")
            if cy != pref_c:
                notes.append(f"captions moved to {cy / H:.2f} of height to stay off the content")
            return TextPlacement(ty, scale, round(cy / H, 4), prot, notes, True)
    # captions cannot fit anywhere without covering something: keep the title, drop the captions
    if first_fit is None and title_h:
        notes.append("title dropped: no free space that would not cover the streamer/content")
    if first_fit is None:
        pref_c, cy = caption_slot(prot)
        if cy is not None:
            return TextPlacement(None, 1.0, round(cy / H, 4), prot, notes, True)
    notes.append("captions turned off for this clip: no free space that would not cover the streamer/content")
    return TextPlacement(first_fit[1] if first_fit else None, first_fit[0] if first_fit else 1.0, None, prot, notes, True)



def upscale_factor(plan: LayoutPlan, src_w: int, src_h: int) -> float:
    """How much the source picture is enlarged in the output (1.0 = native). >~1.8 looks soft, >2.2 blurry."""
    W, H = plan.out_w, plan.out_h
    if plan.layout in ("fit_blur", "letterbox"):
        z = max([1.0] + ([float(plan.zoom_cfg.get("emphasis", 1.12))] if plan.zoom_times else []))
        return W * z / src_w
    if plan.layout == "focus":
        if src_w / src_h > W / H:                         # landscape source: crop keeps full height
            return H / src_h
        return W / src_w
    if plan.layout == "stack_regions" and plan.stack:
        worst, y = 1.0, 0
        for i, (region, frac) in enumerate(plan.stack):
            ph = H - y if i == len(plan.stack) - 1 else int(round(H * frac / 2) * 2)
            rw, rh = region[2] * src_w, region[3] * src_h
            worst = max(worst, max(W / rw, ph / rh) if rw and rh else 1.0)
            y += ph
        return worst
    if plan.layout in ("split_gta", "hybrid"):
        sh = plan.streamer_h                               # streamer panel: W x sh cropped from the source
        if plan.region:
            rw, rh = plan.region[2] * src_w, plan.region[3] * src_h
            return max(W / rw, sh / rh)
        return sh / src_h if src_w / src_h > W / sh else W / src_w
    return H / src_h
