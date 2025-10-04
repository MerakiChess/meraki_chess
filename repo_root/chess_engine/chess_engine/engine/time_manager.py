from __future__ import annotations
from typing import Optional
import time


class TimeManager:
    """Wall-clock based stop condition."""

    def __init__(self) -> None:
        self._start_ns: int = 0
        self._budget_ms: Optional[int] = None

    def start(self, budget_ms: Optional[int]) -> None:
        self._start_ns = time.time_ns()
        self._budget_ms = budget_ms

    def time_up(self) -> bool:
        if self._budget_ms is None:
            return False
        return (time.time_ns() - self._start_ns) / 1e6 >= self._budget_ms
