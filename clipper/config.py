"""Configuration loading and validation.

All tunable behaviour lives in YAML under ``config/``. User changes made through the CLI are
written to ``config/local_overrides.yaml`` (merged on top of the base files) and every change is
recorded in the ``config_changes`` table, so the original files keep their comments and the full
history of changes stays inspectable.
"""
from __future__ import annotations

import copy
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

PROJECT_ROOT = Path(os.environ.get("CLIPPER_ROOT", Path(__file__).resolve().parent.parent))
CONFIG_DIR = Path(os.environ.get("CLIPPER_CONFIG_DIR", PROJECT_ROOT / "config"))
OVERRIDES_FILE = "local_overrides.yaml"
PROFILE_IDS = ("amp", "core", "lospollostv")

PRIORITY_WEIGHTS = {
    "very_high": 1.6,
    "high": 1.3,
    "medium_high": 1.1,
    "medium": 1.0,
    "equal": 1.0,
    "low": 0.7,
}


# --------------------------------------------------------------------------- models
class ResearchCfg(BaseModel):
    window_days: int = 7
    interval_minutes: int = 60
    gemini_research_interval_minutes: int = 360
    max_sources_per_cycle: int = 10
    enable_gemini_research: bool = True
    enable_youtube_rss: bool = True


class GoogleAICfg(BaseModel):
    model: str = "gemini-3.8-flash"
    fallback_models: list[str] = ["gemini-3.5-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-flash-latest", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-lite-latest"]
    api_key_env: str = "GEMINI_API_KEY"
    timeout_seconds: int = 90
    max_retries: int = 3
    retry_backoff_seconds: float = 5
    use_search_grounding: bool = True
    semantic_scoring: bool = True
    semantic_weight: float = Field(0.35, ge=0, le=1)
    max_candidates_for_semantic: int = 12


class TranscriptionCfg(BaseModel):
    engine: str = "faster_whisper"
    model_size: str = "small.en"
    model_path_env: str = "WHISPER_MODEL_PATH"
    device: str = "auto"
    compute_type: str = "int8"
    language: str = "en"
    vad_filter: bool = True
    low_confidence_threshold: float = 0.55
    prefer_sidecar: bool = True
    fallback_to_gemini: bool = True


class PipelineCfg(BaseModel):
    max_candidates_per_source: int = 25
    max_render_attempts: int = 2
    stage_timeout_seconds: int = 3600
    keep_rejected_renders: bool = False


class GlobalCfg(BaseModel):
    timezone: str = "UTC"
    database_path: str = "database/clipping_machine.db"
    work_dir: str = "work"
    outputs_dir: str = "outputs"
    logs_dir: str = "logs"
    sources_dir: str = "sources"
    research: ResearchCfg = ResearchCfg()
    google_ai: GoogleAICfg = GoogleAICfg()
    transcription: TranscriptionCfg = TranscriptionCfg()
    pipeline: PipelineCfg = PipelineCfg()
    export: dict[str, Any] = {"date_format": "%Y-%m-%d"}


class DurationCfg(BaseModel):
    min_seconds: float = 15
    max_seconds: float = 180
    ideal_ranges: dict[str, list[float]] = {}

    @field_validator("max_seconds")
    @classmethod
    def _check(cls, v, info):
        mn = info.data.get("min_seconds", 0)
        if v <= mn:
            raise ValueError("max_seconds must be greater than min_seconds")
        return v


class CreatorCfg(BaseModel):
    name: str
    priority: str = "medium"
    aliases: list[str] = []
    hashtags: list[str] = []
    youtube_channel_ids: list[str] = []
    youtube_handles: list[str] = []        # e.g. "@KaiCenatLive"; resolved to channel IDs at discovery time
    twitch: list[str] = []
    kick: list[str] = []

    @property
    def initial_weight(self) -> float:
        return PRIORITY_WEIGHTS.get(self.priority, 1.0)


class AttentionCfg(BaseModel):
    dynamic: bool = True
    min_multiplier: float = 0.5
    max_multiplier: float = 2.0
    learning_rate: float = 0.2


class CaptionCfg(BaseModel):
    font: str = "DejaVu Sans"
    font_file: str | None = None
    size: int = 72
    primary_color: str = "#FFFFFF"
    highlight_color: str = "#FFD400"
    outline_color: str = "#000000"
    outline: int = 5
    shadow: int = 2
    bold: bool = True
    uppercase: bool = False
    max_words: int = 3
    max_chars: int = 22
    position: float = 0.66


class ProfileEditingCfg(BaseModel):
    style: str = "default"
    layout_policy: str = "auto"
    caption: CaptionCfg = CaptionCfg()
    zoom_emphasis: bool = True


class FormatExperimentCfg(BaseModel):
    formats: dict[str, dict[str, Any]] = {}
    caption_position: dict[str, float] = {}
    min_samples_per_format: int = 20
    target_samples_per_format: int = 30
    primary_metric: str = "avg_pct_viewed"
    gameplay_dir: str = "assets/approved_gameplay"


class ProfileCfg(BaseModel):
    id: str
    display_name: str
    output_folder: str
    min_quality_threshold: float = Field(60, ge=0, le=100)
    duration: DurationCfg = DurationCfg()
    creators: list[CreatorCfg] = []
    group_name: str | None = None
    group_youtube_handles: list[str] = []  # official group channels (e.g. AMP, CORE)
    content_categories: list[str] = []
    affiliates_are_members: bool = False
    attention: AttentionCfg = AttentionCfg()
    scoring_weights: dict[str, float] = {}
    features: dict[str, bool] = {}
    editing: ProfileEditingCfg = ProfileEditingCfg()
    format_experiment: FormatExperimentCfg | None = None
    monetization: dict[str, Any] = {}
    metadata: dict[str, Any] = {}

    def creator(self, name: str) -> CreatorCfg | None:
        low = name.strip().lower()
        for c in self.creators:
            if c.name.lower() == low or low in (a.lower() for a in c.aliases):
                return c
        return None

    def feature(self, key: str) -> bool:
        return bool(self.features.get(key, False))


class EditingCfg(BaseModel):
    output: dict[str, Any]
    audio: dict[str, Any]
    face_tracking: dict[str, Any]
    zoom: dict[str, Any]
    safe_zones: dict[str, float]
    trim: dict[str, float]
    title_overlay: dict[str, Any] = {"enabled": True}


class Settings(BaseModel):
    root: Path
    global_: GlobalCfg
    profiles: dict[str, ProfileCfg]
    editing: EditingCfg
    quality: dict[str, Any]
    rights: dict[str, Any]
    lexicons: dict[str, list[str]] = {}

    model_config = {"arbitrary_types_allowed": True}

    def path(self, rel: str | Path) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else self.root / p

    @property
    def db_path(self) -> Path:
        return self.path(self.global_.database_path)

    @property
    def work_dir(self) -> Path:
        return self.path(self.global_.work_dir)

    def profile(self, pid: str) -> ProfileCfg:
        pid = pid.lower()
        if pid not in self.profiles:
            raise KeyError(f"Unknown profile '{pid}'. Valid: {', '.join(self.profiles)}")
        return self.profiles[pid]


# --------------------------------------------------------------------------- loading
def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    return data


def read_overrides(config_dir: Path | None = None) -> dict:
    return _read_yaml((config_dir or CONFIG_DIR) / OVERRIDES_FILE)


def write_overrides(data: dict, config_dir: Path | None = None) -> None:
    path = (config_dir or CONFIG_DIR) / OVERRIDES_FILE
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write("# Machine-managed overrides written by the CLI. Every change is logged in the\n")
        fh.write("# config_changes table. Delete a key to fall back to the base YAML value.\n")
        yaml.safe_dump(data, fh, sort_keys=True)
    tmp.replace(path)


def load_settings(root: Path | None = None, config_dir: Path | None = None) -> Settings:
    root = Path(root or PROJECT_ROOT)
    cdir = Path(config_dir or (root / "config"))
    overrides = read_overrides(cdir)

    g = deep_merge(_read_yaml(cdir / "global.yaml"), overrides.get("global", {}))
    profiles = {}
    for pid in PROFILE_IDS:
        raw = deep_merge(_read_yaml(cdir / f"{pid}.yaml"), overrides.get("profiles", {}).get(pid, {}))
        if raw:
            profiles[pid] = ProfileCfg(**raw)
    editing = deep_merge(_read_yaml(cdir / "editing.yaml"), overrides.get("editing", {}))
    quality = deep_merge(_read_yaml(cdir / "quality.yaml"), overrides.get("quality", {}))
    rights = deep_merge(_read_yaml(cdir / "rights.yaml"), overrides.get("rights", {}))
    lex_file = rights.get("monetization", {}).get("lexicon_file", "config/content_lexicons.yaml")
    lex_path = Path(lex_file) if Path(lex_file).is_absolute() else root / lex_file
    lexicons = {k: [str(x).lower() for x in (v or [])] for k, v in _read_yaml(lex_path).items()}

    return Settings(
        root=root,
        global_=GlobalCfg(**g),
        profiles=profiles,
        editing=EditingCfg(**editing),
        quality=quality,
        rights=rights,
        lexicons=lexicons,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()


def set_override(path: list[str], value: Any, config_dir: Path | None = None) -> Any:
    """Set an override value at a nested key path; returns the previous override value."""
    data = read_overrides(config_dir)
    node = data
    for k in path[:-1]:
        node = node.setdefault(k, {})
    old = node.get(path[-1])
    node[path[-1]] = value
    write_overrides(data, config_dir)
    return old
