from __future__ import annotations

import math
import random
from datetime import date
from typing import Protocol, Callable

from .calendar import build_schedule, date_range

PATTERNS = ("full", "random", "natural", "gradient", "wave", "checkerboard", "weekdays", "weekends", "custom", "text")


class ContributionPattern(Protocol):
    name: str

    def __call__(self, *args, **kwargs): ...


class PatternRegistry:
    """Small registry boundary so new generators can be added without Git knowledge."""
    def __init__(self) -> None:
        self._handlers: dict[str, Callable] = {}

    def register(self, name: str, handler: Callable) -> None:
        self._handlers[name] = handler

    def names(self) -> tuple[str, ...]:
        return tuple(self._handlers)


registry = PatternRegistry()

_GLYPHS = {
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
}


def generate(start, end, name, timezone="Asia/Jakarta", branch="main", min_commits=0, max_commits=4, seed=None, options=None, work_start=9, work_end=20, intensity_mapping=None):
    if name not in PATTERNS:
        raise ValueError(f"unknown pattern: {name}")
    if min_commits < 0 or max_commits < min_commits:
        raise ValueError("invalid commit bounds")
    options = options or {}
    rng = random.Random(seed)
    days = list(date_range(start, end))
    counts = {}
    if name == "full":
        counts = {day: max_commits for day in days}
    elif name in ("weekdays", "weekends"):
        wanted = range(5) if name == "weekdays" else range(5, 7)
        counts = {day: (rng.randint(min_commits, max_commits) if day.weekday() in wanted else 0) for day in days}
    elif name == "random":
        counts = {day: rng.randint(min_commits, max_commits) for day in days}
    elif name == "natural":
        for day in days:
            if rng.random() < (0.25 if day.weekday() >= 5 else 0.12):
                counts[day] = 0
            else:
                skewed = int((rng.random() ** 2) * max_commits) + (1 if max_commits else 0)
                counts[day] = max(min_commits, min(max_commits, skewed))
    elif name == "gradient":
        denominator = max(1, len(days) - 1)
        counts = {day: round(min_commits + (max_commits - min_commits) * index / denominator) for index, day in enumerate(days)}
    elif name == "wave":
        period = float(options.get("period", max(1, len(days) / 2)))
        if period <= 0:
            raise ValueError("wave period must be positive")
        counts = {day: round(min_commits + (max_commits - min_commits) * (math.sin(2 * math.pi * index / period) + 1) / 2) for index, day in enumerate(days)}
    elif name == "checkerboard":
        counts = {day: (max_commits if ((day.weekday() + ((day - date(1970, 1, 1)).days // 7)) % 2 == 0) else min_commits) for day in days}
    elif name == "custom":
        custom = options.get("dates", {})
        if not isinstance(custom, dict):
            raise ValueError("custom dates must be an object")
        counts = {day: int(custom.get(day.isoformat(), 0)) for day in days}
        if any(value < 0 for value in counts.values()):
            raise ValueError("custom commit counts must be non-negative")
    elif name == "text":
        text = str(options.get("text", ""))
        if not text:
            raise ValueError("text pattern requires non-empty text")
        counts = {day: 0 for day in days}
        position = 0
        for character in text.upper():
            glyph = _GLYPHS.get(character)
            if glyph is None:
                raise ValueError(f"unsupported text glyph: {character}")
            for row, bits in enumerate(glyph):
                for column, bit in enumerate(bits):
                    index = position + column * 7 + row
                    if bit == "1" and index < len(days):
                        counts[days[index]] = max_commits
            position += 6 * 7
        if position - 42 + 34 >= len(days):
            raise ValueError("text does not fit in the selected date range")
    return build_schedule(start, end, name, timezone, branch, counts, seed, options, work_start, work_end, intensity_mapping)
