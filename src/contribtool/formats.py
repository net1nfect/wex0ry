from __future__ import annotations

from pathlib import Path
import json
import tomllib

from .models import Schedule


def load_mapping(path: Path) -> dict:
    """Load a custom pattern mapping from JSON, TOML, or optional YAML."""
    suffix = path.suffix.lower()
    if suffix == ".toml":
        with path.open("rb") as stream:
            data = tomllib.load(stream)
    elif suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("YAML support requires pip install 'contribtool[yaml]'") from exc
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("custom pattern input must be an object")
    return data


def dump_schedule(schedule: Schedule, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("YAML support requires pip install 'contribtool[yaml]'") from exc
        content = yaml.safe_dump(schedule.to_dict(), sort_keys=False)
    elif suffix == ".toml":
        raise ValueError("TOML is supported for config/custom input; export schedules as JSON or YAML")
    else:
        content = json.dumps(schedule.to_dict(), indent=2, ensure_ascii=False) + "\n"
    path.write_text(content, encoding="utf-8")


def load_schedule(path: Path) -> Schedule:
    suffix = path.suffix.lower()
    try:
        if suffix in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError as exc:
                raise RuntimeError("YAML support requires pip install 'contribtool[yaml]'") from exc
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        elif suffix == ".toml":
            with path.open("rb") as stream:
                data = tomllib.load(stream)
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"cannot parse schedule: {path}") from exc
    return Schedule.from_dict(data)
