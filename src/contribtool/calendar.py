from __future__ import annotations

from datetime import date, datetime, time, timedelta
import random
from zoneinfo import ZoneInfo

from .models import ActivityDay, CommitSlot, IntensityLevel, Schedule


def date_range(start: date, end: date):
    if start > end:
        raise ValueError("start must be before end")
    for offset in range((end - start).days + 1):
        yield start + timedelta(days=offset)


def slots_for(day: date, count: int, timezone: str, rng: random.Random, start_hour: int = 9, end_hour: int = 20):
    if count <= 0:
        return ()
    if not (0 <= start_hour < 24 and 0 < end_hour <= 24 and start_hour < end_hour):
        raise ValueError("working hours must be within 00:00..24:00 and ordered")
    tz = ZoneInfo(timezone)
    seconds = (end_hour - start_hour) * 3600
    values = sorted(rng.randrange(seconds) for _ in range(count))
    return tuple(
        CommitSlot(datetime.combine(day, time(start_hour), tzinfo=tz) + timedelta(seconds=value), index)
        for index, value in enumerate(values, 1)
    )


def level_for(commits: int, mapping: dict[int, int] | None = None) -> IntensityLevel:
    if commits <= 0:
        return IntensityLevel.NONE
    mapping = mapping or {1: 1, 3: 2, 6: 3, 10: 4}
    for threshold, level in sorted(mapping.items()):
        if commits <= int(threshold):
            return IntensityLevel(max(0, min(4, int(level))))
    return IntensityLevel.VERY_HIGH


def build_schedule(start, end, pattern, timezone, branch, counts, seed=None, options=None, work_start=9, work_end=20, intensity_mapping=None):
    rng = random.Random(seed)
    days = tuple(
        ActivityDay(
            day,
            int(counts.get(day, 0)),
            level_for(int(counts.get(day, 0)), intensity_mapping),
            slots_for(day, int(counts.get(day, 0)), timezone, rng, work_start, work_end),
        )
        for day in date_range(start, end)
    )
    return Schedule(timezone, branch, start, end, pattern, days, seed, options or {})


def stats(schedule: Schedule) -> dict:
    active = [day for day in schedule.days if day.commits > 0]
    weekday_totals = {index: sum(day.commits for day in schedule.days if day.date.weekday() == index) for index in range(7)}
    monthly = {}
    for day in schedule.days:
        key = day.date.strftime("%Y-%m")
        monthly[key] = monthly.get(key, 0) + day.commits

    def streak(predicate):
        best = current = 0
        for day in schedule.days:
            current = current + 1 if predicate(day) else 0
            best = max(best, current)
        return best

    return {
        "date_range": f"{schedule.start} -> {schedule.end}",
        "total_days": len(schedule.days),
        "active_days": len(active),
        "inactive_days": len(schedule.days) - len(active),
        "total_commits": schedule.total_commits,
        "average_active": (schedule.total_commits / len(active) if active else 0.0),
        "max_per_day": max((day.commits for day in schedule.days), default=0),
        "longest_active_streak": streak(lambda day: day.commits > 0),
        "longest_inactive_streak": streak(lambda day: day.commits == 0),
        "busiest_weekday": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")[max(weekday_totals, key=weekday_totals.get)],
        "monthly": monthly,
    }
