from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib
from zoneinfo import ZoneInfo


@dataclass
class ToolConfig:
    timezone: str = "Asia/Jakarta"
    branch: str = "main"
    message_template: str = "chore(contrib): activity {date} #{index}"
    intensity: dict[str, int] = field(default_factory=lambda: {"low": 1, "medium": 3, "high": 6, "very_high": 10})
    seed: int | None = None
    work_start: int = 9
    work_end: int = 20
    allow_dirty: bool = False

    def validate(self) -> "ToolConfig":
        ZoneInfo(self.timezone)
        if not self.branch.strip():
            raise ValueError("branch must not be empty")
        if not (0 <= self.work_start < self.work_end <= 24):
            raise ValueError("working hours must be ordered between 00 and 24")
        if any(int(value) < 0 for value in self.intensity.values()):
            raise ValueError("intensity values must be non-negative")
        return self

    @classmethod
    def load(cls, path: Path | None = None) -> "ToolConfig":
        path = path or Path(".contribution-tool/config.toml")
        if not path.exists():
            return cls()
        with path.open("rb") as stream:
            data = tomllib.load(stream)
        config = cls()
        config.timezone = str(data.get("timezone", config.timezone))
        config.branch = str(data.get("branch", config.branch))
        commit = data.get("commit", {})
        config.message_template = str(commit.get("message_template", config.message_template))
        config.intensity.update({str(k): int(v) for k, v in data.get("intensity", {}).items()})
        config.seed = data.get("random", {}).get("seed", config.seed)
        hours = data.get("working_hours", {})
        config.work_start = int(hours.get("start", config.work_start))
        config.work_end = int(hours.get("end", config.work_end))
        config.allow_dirty = bool(data.get("allow_dirty", config.allow_dirty))
        return config.validate()
