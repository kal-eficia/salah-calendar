"""salah-calendar command line.

  salahcal today --city london
  salahcal ics --city london --days 60 -o salah.ics
  salahcal clashes work-calendar.ics --city london
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import __version__
from .ics import clashes, prayer_events, read_meetings, to_ics
from .places import PLACES
from .times import METHODS, Settings, compute, label


def settings_from(a) -> tuple[Settings, str]:
    if a.city:
        key = a.city.lower().replace(" ", "-")
        if key not in PLACES:
            sys.exit(f"Unknown city {a.city!r}. Use --lat/--lon/--tz, or one of: {', '.join(PLACES)}")
        lat, lon, tz = PLACES[key]
        place = a.city.title()
    elif a.lat is not None and a.lon is not None and a.tz:
        lat, lon, tz, place = a.lat, a.lon, a.tz, f"{a.lat:.2f}, {a.lon:.2f}"
    else:
        sys.exit("Give --city, or --lat, --lon and --tz")
    adjust = {}
    for item in a.adjust or []:
        k, _, v = item.partition("=")
        adjust[k.lower()] = int(v)
    return Settings(lat, lon, tz, a.method, a.asr, a.high_lat, adjust), place


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="salahcal", description="Prayer times as calendar events.")
    ap.add_argument("--version", action="version", version=f"salah-calendar {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--city"); common.add_argument("--lat", type=float); common.add_argument("--lon", type=float)
    common.add_argument("--tz", help="IANA time zone, e.g. Europe/London")
    common.add_argument("--method", default="MWL", choices=list(METHODS))
    common.add_argument("--asr", default="shafii", choices=["shafii", "hanafi"])
    common.add_argument("--high-lat", default="angle", choices=["angle", "seventh", "middle", "none"])
    common.add_argument("--adjust", nargs="*", metavar="PRAYER=MIN", help="e.g. dhuhr=2 maghrib=3")
    common.add_argument("--minutes", type=int, default=20, help="length of each prayer block (default 20)")
    common.add_argument("--jumuah-minutes", type=int, default=60)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("today", parents=[common]); t.add_argument("--date", type=date.fromisoformat)
    i = sub.add_parser("ics", parents=[common])
    i.add_argument("--start", type=date.fromisoformat); i.add_argument("--days", type=int, default=30)
    i.add_argument("--reminder", type=int, default=10, help="minutes before (0 for none)")
    i.add_argument("--free", action="store_true", help="show blocks as free rather than busy")
    i.add_argument("-o", "--output", default="salah.ics")
    c = sub.add_parser("clashes", parents=[common]); c.add_argument("calendar")
    a = ap.parse_args(argv)
    s, place = settings_from(a)
    today = datetime.now(ZoneInfo(s.tz)).date()

    if a.cmd == "today":
        day = a.date or today
        print(f"{place} · {day:%A %d %B %Y} · {s.method}, Asr {s.asr}")
        for name, at in compute(day, s).items():
            print(f"  {label(name, day):<8} {at:%H:%M}")
        return 0
    if a.cmd == "ics":
        events = prayer_events(a.start or today, a.days, s, a.minutes, a.jumuah_minutes)
        Path(a.output).write_text(to_ics(events, s, place, a.reminder or None, busy=not a.free), encoding="utf-8")
        print(f"Wrote {len(events)} prayer blocks for {a.days} days to {a.output}. Import it into Google Calendar, Outlook or Apple Calendar.")
        return 0
    meetings = read_meetings(Path(a.calendar).read_text(encoding="utf-8"), s.tz)
    found = clashes(meetings, s, a.minutes, a.jumuah_minutes)
    if not found:
        print(f"No clashes: {len(meetings)} events checked.")
        return 0
    print(f"{len(found)} clash{'es' if len(found) != 1 else ''} with salah:")
    zone = ZoneInfo(s.tz)
    for m, title, at in found:
        print(f"  {m.start.astimezone(zone):%a %d %b %H:%M}-{m.end.astimezone(zone):%H:%M}  {m.summary}  ->  {title} at {at:%H:%M}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
