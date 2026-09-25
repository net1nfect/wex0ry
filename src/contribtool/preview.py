from __future__ import annotations

import sys

SYMBOLS = "·░▒▓█"
ASCII_SYMBOLS = ".:+#@"


def render(schedule, ascii_only: bool = False) -> str:
    symbols = ASCII_SYMBOLS if ascii_only or (sys.stdout.encoding or "").lower() in {"ascii", "cp437"} else SYMBOLS
    by_date = {day.date: day for day in schedule.days}
    lines = [f"{schedule.pattern} {schedule.start} -> {schedule.end}", "    Mon Tue Wed Thu Fri Sat Sun"]
    cursor = schedule.start
    while cursor.weekday():
        cursor = cursor.fromordinal(cursor.toordinal() - 1)
    last = schedule.end
    while cursor <= last:
        cells = []
        for offset in range(7):
            current = cursor.fromordinal(cursor.toordinal() + offset)
            day = by_date.get(current)
            cells.append(symbols[int(day.intensity)] if day else " ")
        lines.append("    " + "  ".join(cells))
        cursor = cursor.fromordinal(cursor.toordinal() + 7)
    legend = " . none  : low  + medium  # high  @ very high" if symbols is ASCII_SYMBOLS else " · none  ░ low  ▒ medium  ▓ high  █ very high"
    lines.append("Legend:" + legend)
    return "\n".join(lines)
