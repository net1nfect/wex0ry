from __future__ import annotations

from pathlib import Path
import json
import os
import time

from .models import Schedule


def dirs(root: Path) -> None:
    for name in ("plans", "state", "journals", "locks"):
        (root / name).mkdir(parents=True, exist_ok=True)


def append_activity(repo: Path, schedule: Schedule, day, sequence: int, timestamp) -> Path:
    path = repo / ".contribution-history" / "activity.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schedule_id": schedule.schedule_id,
        "sequence": sequence,
        "date": day.isoformat(),
        "timestamp": timestamp.isoformat(),
        "pattern": schedule.pattern,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def state_path(root: Path, schedule_id: str) -> Path:
    return root / "state" / f"{schedule_id}.json"


def journal_path(root: Path, schedule_id: str) -> Path:
    return root / "journals" / f"{schedule_id}.jsonl"


def load_state(root: Path, schedule_id: str) -> dict | None:
    path = state_path(root, schedule_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid checkpoint: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"invalid checkpoint: {path}")
    return data


def completed_sequences(root: Path, schedule_id: str) -> set[int]:
    path = journal_path(root, schedule_id)
    if not path.exists():
        return set()
    result: set[int] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("status") == "success":
                result.add(int(item["sequence"]))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid journal: {path}") from exc
    return result


def save_state(root: Path, schedule_id: str, data: dict) -> None:
    path = state_path(root, schedule_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def journal(root: Path, schedule_id: str, entry: dict) -> None:
    path = journal_path(root, schedule_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, sort_keys=True) + "\n")


class Lock:
    def __init__(self, path: Path, schedule_id: str, repository: str = "", stale_after: int = 3600):
        self.path = path
        self.schedule_id = schedule_id
        self.repository = repository
        self.stale_after = stale_after
        self.acquired = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {"pid": os.getpid(), "timestamp": time.time(), "schedule_id": self.schedule_id, "repository": self.repository}
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(metadata, stream)
        except FileExistsError as exc:
            try:
                existing = json.loads(self.path.read_text(encoding="utf-8"))
                pid = int(existing.get("pid", -1))
                timestamp = float(existing.get("timestamp", 0))
                stale = time.time() - timestamp > self.stale_after and (pid <= 0 or not _pid_alive(pid))
            except (OSError, ValueError, json.JSONDecodeError):
                stale = False
            if stale:
                self.path.unlink(missing_ok=True)
                return self.__enter__()
            raise RuntimeError(f"execution lock exists: {self.path}") from exc
        self.acquired = True
        return self

    def __exit__(self, *_args):
        if self.acquired:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass


def _pid_alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
