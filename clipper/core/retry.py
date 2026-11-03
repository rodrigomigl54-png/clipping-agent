"""Retry with exponential backoff for transient failures (network, API)."""
from __future__ import annotations

import time
from typing import Callable, TypeVar

from .logger import get_logger

T = TypeVar("T")
log = get_logger("retry")


class TransientError(Exception):
    """Raise for failures worth retrying."""


def retry_call(fn: Callable[[], T], *, attempts: int = 3, backoff: float = 2.0,
               retry_on: tuple[type[BaseException], ...] = (TransientError,),
               what: str = "operation", sleep: Callable[[float], None] = time.sleep) -> T:
    last: BaseException | None = None
    for i in range(1, max(1, attempts) + 1):
        try:
            return fn()
        except retry_on as e:  # type: ignore[misc]
            last = e
            if i >= attempts:
                break
            delay = backoff * (2 ** (i - 1))
            log.warning("%s failed (attempt %d/%d): %s; retrying in %.1fs", what, i, attempts, e, delay)
            sleep(delay)
    assert last is not None
    raise last
