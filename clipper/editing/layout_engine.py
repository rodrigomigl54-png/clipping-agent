"""Vertical layout composition.

Layouts (all 1080x1920 by default):
* ``focus``      — full-screen streamer focus: 9:16 crop following the face, adaptive zoom (Format B)
* ``fit_blur``   — whole frame fitted on a blurred fill; used when cropping would cut people out
* ``split_gta``  — streamer top half, licensed gameplay bottom half (Format A)
* ``hybrid``     — streamer larger top section, gameplay smaller bottom section (Format C)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .face_tracker import CameraPath

LAYOUTS = ("focus", "fit_blur", "split_gta", "hybrid")


@dataclass
class LayoutPlan:
    layout: str
    out_w: int = 1080
    out_h: int = 1920
    streamer_fraction: float = 0.5          # height share of the streamer panel (split/hybrid)
    region: tuple[float, float, float, float] | None = None   # facecam region (normalised)
    camera: CameraPath | None = None
    zoom_times: list[float] = field(default_factory=list)
    zoom_cfg: dict = field(default_factory=dict)
    needs_gameplay: bool = False
    reason: str = ""

    @property
    def streamer_h(self) -> int:
        return int(round(self.out_h * self.streamer_fraction / 2) * 2)

    @property
    def gameplay_h(self) -> int:
        return self.out_h - self.streamer_h

    def caption_y(self, configured: float) -> float:
        """Caption centre (fraction of height). Split layouts sit on the seam so neither the
        streamer's face nor the gameplay action is covered."""
        if self.layout in ("split_gta", "hybrid"):
            return self.streamer_fraction
        return configured


def choose_auto_layout(camera: CameraPath, region) -> tuple[str, str]:
    if region is not None:
        return "focus", "facecam region configured"
    if camera.face_found < 0.2:
        return "fit_blur", f"faces visible in only {camera.face_found:.0%} of samples"
    if camera.multi_face >= 0.4 and camera.spread >= 0.3:
        return "fit_blur", f"multiple people spread across frame (spread {camera.spread:.2f})"
    return "focus", f"single primary face tracked ({camera.face_found:.0%})"


def zoom_at(plan: LayoutPlan, t: float) -> float:
    z = plan.zoom_cfg
    if not z.get("enabled", True) or not plan.zoom_times:
        return float(z.get("base", 1.0))
    base, peak = float(z.get("base", 1.0)), float(z.get("emphasis", 1.12))
    ramp, hold = float(z.get("ramp_seconds", 0.35)), float(z.get("hold_seconds", 1.2))
    best = base
    for zt in plan.zoom_times:
        d = t - (zt - ramp)
        if 0 <= d < ramp:
            f = d / ramp
        elif ramp <= d < ramp + hold:
            f = 1.0
        elif ramp + hold <= d < 2 * ramp + hold:
            f = 1 - (d - ramp - hold) / ramp
        else:
            continue
        f = f * f * (3 - 2 * f)  # smoothstep easing
        best = max(best, base + (peak - base) * f)
    return best


def _crop_rect(W: int, H: int, aspect: float, cx: float, cy: float, zoom: float,
               bounds: tuple[float, float, float, float] | None = None) -> tuple[int, int, int, int]:
    """Largest rect of ``aspect`` (w/h) within bounds, scaled by 1/zoom, centred near (cx, cy)."""
    bx, by, bw, bh = bounds or (0, 0, 1, 1)
    BX, BY, BW, BH = bx * W, by * H, bw * W, bh * H
    if BW / BH > aspect:
        ch = BH; cw = ch * aspect
    else:
        cw = BW; ch = cw / aspect
    cw, ch = cw / zoom, ch / zoom
    x = cx * W - cw / 2
    y = cy * H - ch * 0.42          # keep the face slightly above centre
    x = min(max(x, BX), BX + BW - cw)
    y = min(max(y, BY), BY + BH - ch)
    return int(x), int(y), max(2, int(cw)), max(2, int(ch))


def _cover(frame: np.ndarray, w: int, h: int) -> np.ndarray:
    H, W = frame.shape[:2]
    s = max(w / W, h / H)
    r = cv2.resize(frame, (max(w, int(W * s + 0.5)), max(h, int(H * s + 0.5))), interpolation=cv2.INTER_AREA)
    y0, x0 = (r.shape[0] - h) // 2, (r.shape[1] - w) // 2
    return r[y0:y0 + h, x0:x0 + w]


def _panel(frame: np.ndarray, plan: LayoutPlan, t: float, w: int, h: int) -> np.ndarray:
    H, W = frame.shape[:2]
    cx, cy = plan.camera.at(t) if plan.camera else (0.5, 0.45)
    x, y, cw, ch = _crop_rect(W, H, w / h, cx, cy, zoom_at(plan, t), plan.region)
    crop = frame[y:y + ch, x:x + cw]
    interp = cv2.INTER_AREA if cw >= w else cv2.INTER_CUBIC
    return cv2.resize(crop, (w, h), interpolation=interp)


def compose(frame: np.ndarray, plan: LayoutPlan, t: float, gameplay: np.ndarray | None = None) -> np.ndarray:
    W, H = plan.out_w, plan.out_h
    if plan.layout == "focus":
        return _panel(frame, plan, t, W, H)
    if plan.layout == "fit_blur":
        # background built at 1/10 resolution (blur + darken are cheap there), then upscaled
        small = _cover(frame, W // 10, H // 10)
        small = cv2.convertScaleAbs(cv2.GaussianBlur(small, (0, 0), 6), alpha=0.55)
        bg = cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)
        fh, fw = frame.shape[:2]
        z = zoom_at(plan, t)
        nw = int(W * min(1.25, z)); nh = int(fh * nw / fw)
        fg = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
        if nw > W:
            x0 = (nw - W) // 2
            fg = fg[:, x0:x0 + W]; nw = W
        y = max(0, int(H * 0.42 - nh / 2))
        bg[y:y + nh, (W - nw) // 2:(W - nw) // 2 + nw] = fg[: H - y]
        return bg
    if plan.layout in ("split_gta", "hybrid"):
        out = np.zeros((H, W, 3), np.uint8)
        sh = plan.streamer_h
        out[:sh] = _panel(frame, plan, t, W, sh)
        gh = H - sh
        if gameplay is not None:
            out[sh:] = _cover(gameplay, W, gh)
        else:  # should never happen: rendering requires licensed gameplay for these layouts
            raise RuntimeError("split/hybrid layout requires a licensed gameplay asset")
        out[sh - 2:sh + 2] = 0    # subtle seam
        return out
    raise ValueError(f"unknown layout {plan.layout}")
