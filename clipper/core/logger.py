"""Structured JSON-lines logging with secret redaction."""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),                       # Google API keys
    re.compile(r"(?i)(api[_-]?key|token|secret|password)(['\"]?\s*[:=]\s*['\"]?)([^\s'\"&]+)"),
]


def redact(text: str) -> str:
    out = str(text)
    for env in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        val = os.environ.get(env)
        if val and len(val) > 6:
            out = out.replace(val, "[REDACTED]")
    out = _SECRET_PATTERNS[0].sub("[REDACTED]", out)
    out = _SECRET_PATTERNS[1].sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", out)
    return out


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        for key in ("profile", "source_id", "clip_id", "stage"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(f"[{record.levelname[0]}] {record.name}: {record.getMessage()}")


_configured = False


def setup_logging(logs_dir: str | Path, level: str = "INFO", console: bool = True) -> None:
    global _configured
    if _configured:
        return
    Path(logs_dir).mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("clipper")
    root.setLevel(level)
    fh = RotatingFileHandler(Path(logs_dir) / "clipper.jsonl", maxBytes=10_000_000, backupCount=5,
                             encoding="utf-8")
    fh.setFormatter(JsonFormatter())
    root.addHandler(fh)
    if console:
        ch = logging.StreamHandler(sys.stderr)
        ch.setFormatter(ConsoleFormatter())
        ch.setLevel(os.environ.get("CLIPPER_CONSOLE_LOG", "WARNING"))
        root.addHandler(ch)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"clipper.{name}")
