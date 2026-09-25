from datetime import date
import json
import os
import subprocess

import pytest

from contribtool.calendar import level_for, slots_for, stats
from contribtool.formats import dump_schedule, load_schedule
from contribtool.models import ActivityDay, CommitSlot, IntensityLevel, Schedule
from contribtool.patterns import PATTERNS, generate
from contribtool.persistence import Lock, completed_sequences, journal, save_state
from contribtool.gitops import GitRepo


def test_deterministic_patterns_and_roundtrip(tmp_path):
    first = generate(date(2026, 1, 1), date(2026, 1, 10), "natural", seed=3)
    second = generate(date(2026, 1, 1), date(2026, 1, 10), "natural", seed=3)
    assert first.schedule_id == second.schedule_id
    assert first.to_dict() == second.to_dict()
    path = tmp_path / "schedule.json"
    dump_schedule(first, path)
    assert load_schedule(path).to_dict() == first.to_dict()


def test_all_patterns_create_complete_schedule():
    for name in PATTERNS:
        options = {"text": "WEX0RY"} if name == "text" else None
        end = date(2026, 12, 31) if name == "text" else date(2026, 1, 14)
        schedule = generate(date(2026, 1, 1), end, name, min_commits=0, max_commits=4, seed=7, options=options)
        assert len(schedule.days) == ((end - date(2026, 1, 1)).days + 1)
        assert schedule.days[0].date == date(2026, 1, 1)


def test_date_timezone_and_intensity_validation():
    schedule = generate(date(2026, 4, 18), date(2026, 4, 18), "full", min_commits=2, max_commits=2)
    assert schedule.days[0].slots[0].timestamp.tzinfo is not None
    assert schedule.days[0].slots[0].timestamp.utcoffset().total_seconds() == 7 * 3600
    assert level_for(0) == IntensityLevel.NONE
    assert level_for(1) == IntensityLevel.LOW
    with pytest.raises(ValueError):
        Schedule("Not/AZone", "main", date(2026, 1, 1), date(2026, 1, 1), "full", (ActivityDay(date(2026, 1, 1)),))


def test_stats_and_weekday_constraints():
    weekdays = generate(date(2026, 1, 5), date(2026, 1, 11), "weekdays", min_commits=1, max_commits=1, seed=1)
    assert all(day.commits == 0 for day in weekdays.days if day.date.weekday() >= 5)
    values = stats(weekdays)
    assert values["total_days"] == 7
    assert values["active_days"] == 5
    assert values["longest_inactive_streak"] == 2


def test_slots_are_ordered_and_within_working_hours():
    slots = slots_for(date(2026, 1, 1), 20, "Asia/Jakarta", __import__("random").Random(1), 9, 10)
    assert list(slots) == sorted(slots, key=lambda item: item.timestamp)
    assert all(9 <= item.timestamp.hour < 10 for item in slots)


def test_state_and_journal_and_lock(tmp_path):
    root = tmp_path / ".contribution-tool"
    save_state(root, "abc", {"status": "running", "completed": 1})
    journal(root, "abc", {"sequence": 1, "status": "success"})
    assert completed_sequences(root, "abc") == {1}
    with Lock(root / "locks" / "abc.lock", "abc"):
        with pytest.raises(RuntimeError):
            with Lock(root / "locks" / "abc.lock", "abc"):
                pass


def test_git_integration_author_and_committer_dates(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True)
    (tmp_path / "README").write_text("x")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "init"], check=True)
    schedule = generate(date(2026, 1, 1), date(2026, 1, 1), "full", min_commits=1, max_commits=1, seed=2)
    path = tmp_path.parent / f"{tmp_path.name}-schedule.json"
    dump_schedule(schedule, path)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(__import__("pathlib").Path(__file__).parents[1] / "src")
    result = subprocess.run(["python", "-m", "contribtool", "apply", str(path), "--repo", str(tmp_path), "--yes"], env=env, capture_output=True, text=True, check=True)
    assert "Execution complete: 1 commits" in result.stdout
    log = subprocess.run(["git", "-C", str(tmp_path), "log", "-1", "--format=fuller"], capture_output=True, text=True, check=True).stdout
    assert "AuthorDate: Thu Jan 1" in log
    assert "CommitDate: Thu Jan 1" in log
    assert "Contrib-Schedule-Id" in log


def test_dirty_worktree_is_rejected_and_duplicate_is_safe(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True)
    (tmp_path / "README").write_text("x")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "init"], check=True)
    schedule = generate(date(2026, 1, 1), date(2026, 1, 1), "full", min_commits=1, max_commits=1)
    path = tmp_path.parent / f"{tmp_path.name}-dirty.json"
    dump_schedule(schedule, path)
    (tmp_path / "user-change.txt").write_text("must survive")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(__import__("pathlib").Path(__file__).parents[1] / "src")
    failed = subprocess.run(["python", "-m", "contribtool", "apply", str(path), "--repo", str(tmp_path), "--yes"], env=env, capture_output=True, text=True)
    assert failed.returncode != 0
    assert (tmp_path / "user-change.txt").read_text() == "must survive"


def test_remote_display_strips_embedded_credentials(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True)
    (tmp_path / "README").write_text("x")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "init"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "remote", "add", "origin", "https://user:secret@example.com/x.git"], check=True)
    assert "secret" not in GitRepo(tmp_path).remote()
