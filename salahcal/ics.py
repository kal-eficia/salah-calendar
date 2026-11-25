"""Write prayer times as calendar events, and find meetings that clash with them."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .times import PRAYERS, Settings, compute, label


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    out, line = [], line
    while len(line.encode()) > 74:
        cut = 74
        while len(line[:cut].encode()) > 74:
            cut -= 1
        out.append(line[:cut])
        line = " " + line[cut:]
    out.append(line)
    return "\r\n".join(out)


def prayer_events(start: date, days: int, s: Settings, minutes: int = 20, jumuah_minutes: int = 60,
                  include_sunrise: bool = False) -> list[tuple[str, datetime, datetime]]:
    events = []
    for i in range(days):
        day = start + timedelta(days=i)
        for name, at in compute(day, s).items():
            if name == "sunrise" and not include_sunrise:
                continue
            title = label(name, day)
            length = jumuah_minutes if title == "Jumu'ah" else (0 if name == "sunrise" else minutes)
            events.append((title, at, at + timedelta(minutes=length)))
    return events


def to_ics(events, s: Settings, place: str = "", reminder: int | None = 10, busy: bool = True) -> str:
    now = _fmt(datetime.now(timezone.utc))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//kal-eficia//salah-calendar 1.0//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{_escape('Salah' + (' · ' + place if place else ''))}",
             f"X-WR-TIMEZONE:{s.tz}"]
    for title, start, end in events:
        uid = f"{start.strftime('%Y%m%d')}-{title.lower().replace(chr(39), '')}-{round(s.lat, 2)}_{round(s.lon, 2)}@salah-calendar"
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now}", f"DTSTART:{_fmt(start)}", f"DTEND:{_fmt(end)}",
                  f"SUMMARY:{_escape(title)}", f"DESCRIPTION:{_escape(f'{title} at {start:%H:%M}. Calculated with the {s.method} method; follow your local masjid where it differs.')}",
                  f"TRANSP:{'OPAQUE' if busy else 'TRANSPARENT'}", "CATEGORIES:Salah"]
        if reminder and end > start:
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_escape(title)}", f"TRIGGER:-PT{reminder}M", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"


# ---------------------------------------------------------------- clashes

@dataclass
class Meeting:
    summary: str
    start: datetime
    end: datetime


def _parse_dt(value: str, params: str, default_tz: str) -> datetime:
    tzid = re.search(r"TZID=([^;:]+)", params)
    if re.fullmatch(r"\d{8}", value):
        d = datetime.strptime(value, "%Y%m%d")
        return d.replace(tzinfo=ZoneInfo(default_tz))
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    zone = ZoneInfo(tzid.group(1)) if tzid else ZoneInfo(default_tz)
    return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=zone)


def read_meetings(text: str, default_tz: str) -> list[Meeting]:
    """Single events from an .ics export. Repeating events (RRULE) count once, on their first date."""
    text = re.sub(r"\r?\n[ \t]", "", text)  # unfold
    out = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        props = {}
        for line in block.strip().splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            name, _, params = key.partition(";")
            props[name.upper()] = (value.strip(), params)
        if "DTSTART" not in props:
            continue
        start = _parse_dt(*props["DTSTART"], default_tz)
        end = _parse_dt(*props["DTEND"], default_tz) if "DTEND" in props else start + timedelta(hours=1)
        if props.get("TRANSP", ("",))[0] == "TRANSPARENT":
            continue
        out.append(Meeting(props.get("SUMMARY", ("(no title)",))[0].replace("\\,", ","), start, end))
    return out


def clashes(meetings: list[Meeting], s: Settings, minutes: int = 20, jumuah_minutes: int = 60):
    """Meetings that overlap a prayer window, with the prayer they cover."""
    if not meetings:
        return []
    first = min(m.start for m in meetings).astimezone(ZoneInfo(s.tz)).date()
    last = max(m.end for m in meetings).astimezone(ZoneInfo(s.tz)).date()
    prayers = prayer_events(first, (last - first).days + 1, s, minutes, jumuah_minutes)
    found = []
    for m in meetings:
        for title, ps, pe in prayers:
            if pe > ps and m.start < pe and m.end > ps:
                found.append((m, title, ps))
    return sorted(found, key=lambda x: x[2])
