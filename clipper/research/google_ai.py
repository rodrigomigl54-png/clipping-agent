"""Google Gemini API client (google-genai SDK).

Used for: grounded web research (Google Search tool), semantic scoring of transcript windows,
and truthful metadata drafting. It is never a substitute for inspecting the actual media, and
every output is treated as unverified until checked against the transcript/source.

Verified against the installed ``google-genai`` SDK: ``genai.Client(api_key=...)``,
``client.models.generate_content(model, contents, config=GenerateContentConfig(...))``,
``types.Tool(google_search=types.GoogleSearch())`` and
``response.candidates[0].grounding_metadata.grounding_chunks[i].web.{uri,title}``.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from ..config import GoogleAICfg
from ..core.logger import get_logger, redact
from ..core.retry import TransientError, retry_call

log = get_logger("google_ai")


_EXHAUSTED: set[str] = set()   # models whose quota ran out in this process


class ModelNotFound(RuntimeError):
    """The requested model is retired or not available to this key."""


class GeminiUnavailable(RuntimeError):
    """Raised when no API key / SDK is configured. Callers must degrade gracefully."""


@dataclass
class GroundedResult:
    text: str
    data: Any
    citations: list[dict[str, str]] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    model: str = ""


def extract_json(text: str) -> Any:
    """Parse JSON from model text, tolerating ```json fences and surrounding prose."""
    if text is None:
        raise ValueError("empty model response")
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except ValueError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        s, e = t.find(open_c), t.rfind(close_c)
        if s != -1 and e > s:
            try:
                return json.loads(t[s:e + 1])
            except ValueError:
                continue
    raise ValueError("model response did not contain valid JSON")


class GeminiClient:
    def __init__(self, cfg: GoogleAICfg, client: Any = None):
        self.cfg = cfg
        self._client = client
        self.last_model: str | None = None

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.cfg.api_key_env) or None

    def available(self) -> bool:
        if self._client is not None:
            return True
        if not self.api_key:
            return False
        try:
            import google.genai  # noqa: F401
        except ImportError:
            return False
        return True

    def client(self):
        if self._client is not None:
            return self._client
        if not self.available():
            raise GeminiUnavailable(f"Gemini disabled: set {self.cfg.api_key_env} in .env")
        from google import genai
        from google.genai import types
        self._client = genai.Client(api_key=self.api_key,
                                    http_options=types.HttpOptions(timeout=self.cfg.timeout_seconds * 1000))
        return self._client

    # ------------------------------------------------------------------ core call
    def _generate(self, contents: str, config: Any) -> Any:
        """Call the configured model; on overload/unavailability fall back to the next model."""
        models = [self.cfg.model] + [m for m in self.cfg.fallback_models if m != self.cfg.model]
        last: Exception | None = None
        for model in [m for m in models if m not in _EXHAUSTED] or models[-1:]:
            def call(model=model):
                try:
                    resp = self.client().models.generate_content(model=model, contents=contents, config=config)
                    self.last_model = model
                    return resp
                except GeminiUnavailable:
                    raise
                except Exception as e:  # classify transient vs permanent
                    name = type(e).__name__
                    code = getattr(e, "code", None) or getattr(e, "status_code", None)
                    msg = redact(str(e))
                    if code == 429 and ("quota" in msg.lower() or "RESOURCE_EXHAUSTED" in msg):
                        _EXHAUSTED.add(model)          # daily free-tier quota: don't retry this model today
                        raise ModelNotFound(f"{model}: quota exhausted") from e
                    if name in ("ServerError", "TimeoutException", "ConnectError", "ReadTimeout") or code in (429, 500, 502, 503, 504):
                        raise TransientError(f"{name}: {msg}") from e
                    if code == 404:
                        raise ModelNotFound(f"{model}: {msg}") from e
                    raise RuntimeError(f"Gemini request failed ({name}): {msg}") from e
            try:
                return retry_call(call, attempts=self.cfg.max_retries, backoff=self.cfg.retry_backoff_seconds,
                                  what=f"gemini.generate_content[{model}]")
            except (TransientError, ModelNotFound) as e:
                log.warning("model %s unavailable (%s); trying fallback", model, str(e)[:120])
                last = e
        assert last is not None
        raise last

    def generate_json(self, prompt: str, schema: dict | None = None, temperature: float = 0.2) -> Any:
        from google.genai import types
        cfg_kwargs: dict[str, Any] = {"temperature": temperature, "response_mime_type": "application/json"}
        if schema:
            cfg_kwargs["response_json_schema"] = schema
        resp = self._generate(prompt, types.GenerateContentConfig(**cfg_kwargs))
        return extract_json(resp.text)

    def grounded_research(self, prompt: str, temperature: float = 0.2) -> GroundedResult:
        """Run a Google-Search-grounded query. JSON is requested in the prompt (not via schema,
        since structured output and the search tool are not combinable on every model)."""
        from google.genai import types
        tools = [types.Tool(google_search=types.GoogleSearch())] if self.cfg.use_search_grounding else None
        resp = self._generate(prompt, types.GenerateContentConfig(temperature=temperature, tools=tools))
        text = resp.text or ""
        citations: list[dict[str, str]] = []
        queries: list[str] = []
        try:
            gm = resp.candidates[0].grounding_metadata
            for ch in (gm.grounding_chunks or []) if gm else []:
                if ch.web and ch.web.uri:
                    citations.append({"uri": ch.web.uri, "title": ch.web.title or "",
                                      "domain": getattr(ch.web, "domain", None) or ""})
            queries = list(gm.web_search_queries or []) if gm else []
        except (AttributeError, IndexError, TypeError):
            pass
        try:
            data = extract_json(text)
        except ValueError:
            data = None
        return GroundedResult(text=text, data=data, citations=citations, queries=queries,
                              model=self.last_model or self.cfg.model)
