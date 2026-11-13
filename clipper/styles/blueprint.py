"""Deep "blueprint" analysis of an example short with Gemini video understanding.

The model watches the whole clip (frames + audio) and returns a structured, reproducible description:
hook, beat-by-beat structure, layout, every on-screen text, captions, effects (zooms, freeze frames,
circles/arrows), audio (music, voice, SFX), pacing, ending, retention tactics and a recipe. Combined with
local measurements (exact cut times, tempo) and the post's public engagement numbers, it is stored in the
style library and used to pick formats, lengths and tools for new clips.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

BLUEPRINT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "content_type": {"type": "string", "description": "streamer_clip, meme_skit, hype_edit, fun_fact, news, tips, comparison, countdown, reaction, gameplay_moment, other"},
        "category": {"type": "string"},
        "summary": {"type": "string"},
        "hook": {"type": "object", "properties": {
            "first_2s": {"type": "string"}, "hook_text": {"type": "string"},
            "hook_type": {"type": "string"}, "why_it_hooks": {"type": "string"}}},
        "structure": {"type": "array", "items": {"type": "object", "properties": {
            "start": {"type": "number"}, "end": {"type": "number"},
            "beat": {"type": "string", "description": "hook, setup, escalation, reveal, payoff, twist, loop, cta"},
            "what_happens": {"type": "string"}}}},
        "layout": {"type": "object", "properties": {
            "type": {"type": "string", "enum": ["full_frame", "split_top_bottom", "blurred_bands", "black_bars", "picture_in_picture", "other"]},
            "picture_top": {"type": "number"}, "picture_bottom": {"type": "number"},
            "facecam_position": {"type": "string", "enum": ["top", "bottom", "overlay", "none"]},
            "split_ratio": {"type": "number"}, "background": {"type": "string"}}},
        "on_screen_text": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"}, "start": {"type": "number"}, "end": {"type": "number"},
            "position_y": {"type": "number"}, "purpose": {"type": "string"},
            "case": {"type": "string"}, "color": {"type": "string"}, "box_color": {"type": "string"},
            "box_shape": {"type": "string"}, "outline": {"type": "boolean"}, "emoji": {"type": "boolean"},
            "animation": {"type": "string"}}}},
        "captions": {"type": "object", "properties": {
            "present": {"type": "boolean"}, "position_y": {"type": "number"}, "uppercase": {"type": "boolean"},
            "words_per_line": {"type": "integer"}, "color": {"type": "string"}, "highlight_color": {"type": "string"},
            "animation": {"type": "string"}}},
        "visual_effects": {"type": "array", "items": {"type": "object", "properties": {
            "effect": {"type": "string"}, "at": {"type": "number"}, "purpose": {"type": "string"}}}},
        "detail_tools": {"type": "object", "properties": {
            "zoom_to_detail": {"type": "boolean"}, "freeze_frame": {"type": "boolean"},
            "circle": {"type": "boolean"}, "arrow": {"type": "boolean"}, "text_label": {"type": "boolean"},
            "slow_motion": {"type": "boolean"}, "replay": {"type": "boolean"}}},
        "audio": {"type": "object", "properties": {
            "music_present": {"type": "boolean"}, "music_genre": {"type": "string"}, "music_energy": {"type": "string"},
            "beat_synced_cuts": {"type": "boolean"}, "voice": {"type": "string"},
            "sfx": {"type": "array", "items": {"type": "string"}}, "audio_notes": {"type": "string"}}},
        "pacing": {"type": "object", "properties": {
            "cuts_per_minute": {"type": "number"}, "typical_shot_seconds": {"type": "number"},
            "energy_curve": {"type": "string"}}},
        "ending": {"type": "object", "properties": {
            "type": {"type": "string", "description": "loop, punchline, cta, cut_to_black, cliffhanger"},
            "description": {"type": "string"}}},
        "duration_reason": {"type": "string"},
        "retention_tactics": {"type": "array", "items": {"type": "string"}},
        "why_it_works": {"type": "string"},
        "reproduction_recipe": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["content_type", "summary", "hook", "structure", "layout", "on_screen_text", "captions",
                 "audio", "pacing", "ending", "why_it_works", "reproduction_recipe"],
}

PROMPT = """You are a senior short-form video editor studying a reference clip for a GTA 6 content channel
(streamer clips, memes, fun facts, hype edits). Watch the WHOLE video with sound and describe its format so
precisely that another editor could rebuild it shot for shot.

Rules: timestamps in seconds from the start; vertical positions as fractions of the frame height (0 = top);
colours as #RRGGBB; quote every on-screen text exactly (keep emojis); only describe what is really in the
video. category must be one of: {categories}.
Context from local measurements: duration {duration}s, detected hard cuts at {cuts}, estimated tempo {bpm} BPM.
Public post stats: {stats}. Caption: {desc}"""


def map_to_vision(bp: dict) -> dict:
    """Map a blueprint onto the fields derive_preset() understands."""
    lay = bp.get("layout") or {}
    texts = bp.get("on_screen_text") or []
    title = next((t for t in texts if (t.get("purpose") or "").lower() in ("title", "hook", "headline")), texts[0] if texts else None)
    cap = bp.get("captions") or {}
    return {
        "layout": lay.get("type"), "facecam_position": lay.get("facecam_position"), "split_ratio": lay.get("split_ratio"),
        "captions_present": bool(cap.get("present")), "caption_position": cap.get("position_y"),
        "caption_uppercase": cap.get("uppercase"), "caption_words_per_line": cap.get("words_per_line"),
        "caption_primary_color": cap.get("color"), "caption_highlight_color": cap.get("highlight_color"),
        "title_banner_present": title is not None, "title_position": (title or {}).get("position_y"),
        "title_box_color": (title or {}).get("box_color") or "none", "title_text_color": (title or {}).get("color"),
        "title_text": (title or {}).get("text"), "effects": [e.get("effect") for e in bp.get("visual_effects") or []],
        "category": bp.get("category"),
    }


def analyze_video_blueprint(path: Path, gemini, *, categories: list[str], local: dict, stats: dict | None,
                            desc: str | None) -> dict:
    from google.genai import types
    data = Path(path).read_bytes()
    if len(data) > 19_000_000:
        raise ValueError("video too large for inline analysis; downscale first")
    prompt = PROMPT.format(categories=", ".join(categories), duration=local.get("duration"),
                           cuts=local.get("cuts_at"), bpm=local.get("bpm_est"), stats=stats or "unknown",
                           desc=(desc or "")[:300])
    part = types.Part.from_bytes(data=data, mime_type="video/mp4")
    return gemini.generate_json([part, prompt], BLUEPRINT_SCHEMA, temperature=0.1)
