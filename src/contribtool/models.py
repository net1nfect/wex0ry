from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import IntEnum
from hashlib import sha256
import json
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class IntensityLevel(IntEnum):
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    VERY_HIGH = 4


@dataclass(frozen=True)
class CommitSlot:
    timestamp: datetime
    index: int

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError("slot index must be positive")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("commit timestamps must be timezone-aware")


@dataclass(frozen=True)
class ActivityDay:
    date: date
    commits: int = 0
    intensity: IntensityLevel = IntensityLevel.NONE
    slots: tuple[CommitSlot, ...] = ()

    def __post_init__(self) -> None:
        if self.commits < 0:
            raise ValueError("commits must be non-negative")
        if self.commits == 0 and self.slots:
            raise ValueError("inactive day cannot contain commit slots")
        if len(self.slots) != self.commits:
            raise ValueError("slots count must equal commits")
        if self.slots and tuple(s.index for s in self.slots) != tuple(range(1, self.commits + 1)):
            raise ValueError("slot indexes must be contiguous")
        if self.commits == 0 and self.intensity != IntensityLevel.NONE:
            raise ValueError("inactive day must use NONE intensity")


@dataclass(frozen=True)
class Schedule:
    timezone: str
    branch: str
    start: date
    end: date
    pattern: str
    days: tuple[ActivityDay, ...]
    seed: int | None = None
    pattern_options: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1
    schedule_id: str = ""

    def __post_init__(self) -> None:
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone: {self.timezone}") from exc
        if not self.branch.strip():
            raise ValueError("branch must not be empty")
        if self.start > self.end:
            raise ValueError("start must be before end")
        expected = (self.end - self.start).days + 1
        if len(self.days) != expected:
            raise ValueError(f"schedule must contain every date ({expected})")
        for i, day in enumerate(self.days):
            expected_date = self.start.fromordinal(self.start.toordinal() + i)
            if day.date != expected_date:
                raise ValueError("days must be ordered and contiguous")
            for slot in day.slots:
                local_date = slot.timestamp.astimezone(ZoneInfo(self.timezone)).date()
                if local_date != day.date:
                    raise ValueError("commit slot timestamp does not match activity date")
        computed = self.compute_id()
        if self.schedule_id and self.schedule_id != computed:
            raise ValueError("schedule_id does not match canonical schedule content")
        if not self.schedule_id:
            object.__setattr__(self, "schedule_id", computed)

    def canonical(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "timezone": self.timezone,
            "branch": self.branch,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "pattern": self.pattern,
            "seed": self.seed,
            "pattern_options": self.pattern_options,
            "days": [
                {
                    "date": day.date.isoformat(),
                    "commits": day.commits,
                    "intensity": int(day.intensity),
                    "slots": [slot.timestamp.isoformat() for slot in day.slots],
                }
                for day in self.days
            ],
        }

    def compute_id(self) -> str:
        payload = json.dumps(self.canonical(), sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        result = self.canonical()
        result["schedule_id"] = self.schedule_id
        return result

    @property
    def total_commits(self) -> int:
        return sum(day.commits for day in self.days)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Schedule":
        if not isinstance(data, dict):
            raise ValueError("schedule must be an object")
        days: list[ActivityDay] = []
        for item in data.get("days", []):
            slots = tuple(
                CommitSlot(datetime.fromisoformat(value), index)
                for index, value in enumerate(item.get("slots", []), 1)
            )
            days.append(
                ActivityDay(
                    date=date.fromisoformat(item["date"]),
                    commits=int(item.get("commits", 0)),
                    intensity=IntensityLevel(int(item.get("intensity", 0))),
                    slots=slots,
                )
            )
        return cls(
            timezone=str(data["timezone"]),
            branch=str(data["branch"]),
            start=date.fromisoformat(data["start"]),
            end=date.fromisoformat(data["end"]),
            pattern=str(data["pattern"]),
            days=tuple(days),
            seed=data.get("seed"),
            pattern_options=dict(data.get("pattern_options", {})),
            schema_version=int(data.get("schema_version", 1)),
            schedule_id=str(data.get("schedule_id", "")),
        )
