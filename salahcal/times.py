"""Prayer times from first principles: the sun's position, no API.

Uses the standard astronomical method (solar declination and equation of time),
the calculation conventions used by the major authorities, and a high-latitude
rule for places like the UK, where in summer the sky never gets dark enough
for the usual Fajr and Isha angles.

Times are rounded to the minute. Always follow your local masjid's timetable
where it differs: this is a planning tool, not a fatwa.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# name: (fajr angle, isha angle or None, isha minutes after maghrib or None)
METHODS: dict[str, tuple[float, float | None, int | None]] = {
    "MWL": (18.0, 17.0, None),        # Muslim World League
    "ISNA": (15.0, 15.0, None),       # Islamic Society of North America
    "Egypt": (19.5, 17.5, None),      # Egyptian General Authority of Survey
    "Makkah": (18.5, None, 90),       # Umm al-Qura (Isha 120 min in Ramadan)
    "Karachi": (18.0, 18.0, None),    # University of Islamic Sciences, Karachi
    "Dubai": (18.2, 18.2, None),      # UAE General Authority of Islamic Affairs
    "Moonsighting": (18.0, 18.0, None),
}
METHOD_NAMES = {
    "MWL": "Muslim World League", "ISNA": "Islamic Society of North America",
    "Egypt": "Egyptian General Authority of Survey", "Makkah": "Umm al-Qura, Makkah",
    "Karachi": "University of Islamic Sciences, Karachi", "Dubai": "UAE (GAIAE)",
    "Moonsighting": "Moonsighting Committee (angles only)",
}
PRAYERS = ["fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha"]


def _d(x): return math.radians(x)
def _r(x): return math.degrees(x)
def _sin(x): return math.sin(_d(x))
def _cos(x): return math.cos(_d(x))
def _tan(x): return math.tan(_d(x))
def _asin(x): return _r(math.asin(x))
def _acos(x): return _r(math.acos(x))
def _atan2(y, x): return _r(math.atan2(y, x))
def _acot(x): return _r(math.atan(1 / x))
def _fix(a, b): return a - b * math.floor(a / b)


def julian(y: int, m: int, d: int) -> float:
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + d + b - 1524.5


def sun_position(jd: float) -> tuple[float, float]:
    """(declination in degrees, equation of time in hours)."""
    D = jd - 2451545.0
    g = _fix(357.529 + 0.98560028 * D, 360)
    q = _fix(280.459 + 0.98564736 * D, 360)
    L = _fix(q + 1.915 * _sin(g) + 0.020 * _sin(2 * g), 360)
    e = 23.439 - 0.00000036 * D
    ra = _fix(_atan2(_cos(e) * _sin(L), _cos(L)) / 15, 24)
    eqt = q / 15 - ra
    decl = _asin(_sin(e) * _sin(L))
    return decl, eqt


@dataclass
class Settings:
    lat: float
    lon: float
    tz: str
    method: str = "MWL"
    asr: str = "shafii"          # "shafii" (shadow = 1x) or "hanafi" (2x)
    high_lat: str = "angle"      # "angle", "seventh", "middle" or "none"
    adjust: dict[str, int] | None = None  # minutes to add per prayer, e.g. {"dhuhr": 2}

    def __post_init__(self):
        if self.method not in METHODS:
            raise ValueError(f"unknown method {self.method!r}: choose from {', '.join(METHODS)}")
        if self.asr not in ("shafii", "hanafi"):
            raise ValueError("asr must be 'shafii' or 'hanafi'")
        if self.high_lat not in ("angle", "seventh", "middle", "none"):
            raise ValueError("high_lat must be angle, seventh, middle or none")


def _utc_offset_hours(tz: str, day: date) -> float:
    local_noon = datetime.combine(day, time(12), ZoneInfo(tz))
    return local_noon.utcoffset().total_seconds() / 3600


def compute(day: date, s: Settings) -> dict[str, datetime]:
    """Prayer times for one day as timezone-aware datetimes (Jumu'ah is Dhuhr on Fridays)."""
    fajr_angle, isha_angle, isha_minutes = METHODS[s.method]
    jd = julian(day.year, day.month, day.day) - s.lon / (15 * 24)
    lat = s.lat

    def mid_day(t):
        _, eqt = sun_position(jd + t)
        return _fix(12 - eqt, 24)

    def angle_time(angle, t, ccw=False):
        decl, _ = sun_position(jd + t)
        noon = mid_day(t)
        cos_h = (-_sin(angle) - _sin(decl) * _sin(lat)) / (_cos(decl) * _cos(lat))
        if cos_h > 1 or cos_h < -1:
            return float("nan")  # the sun never reaches this angle today
        h = _acos(cos_h) / 15
        return noon - h if ccw else noon + h

    def asr_time(factor, t):
        decl, _ = sun_position(jd + t)
        angle = -_acot(factor + _tan(abs(lat - decl)))
        return angle_time(angle, t)

    # first guesses (hours), then two refinement passes
    times = {"fajr": 5.0, "sunrise": 6.0, "dhuhr": 12.0, "asr": 13.0, "sunset": 18.0, "maghrib": 18.0, "isha": 18.0}
    factor = 1 if s.asr == "shafii" else 2
    for _ in range(2):
        f = {k: v / 24 for k, v in times.items()}
        times = {
            "fajr": angle_time(fajr_angle, f["fajr"], ccw=True),
            "sunrise": angle_time(0.833, f["sunrise"], ccw=True),
            "dhuhr": mid_day(f["dhuhr"]),
            "asr": asr_time(factor, f["asr"]),
            "sunset": angle_time(0.833, f["sunset"]),
            "maghrib": angle_time(0.833, f["maghrib"]),
            "isha": angle_time(isha_angle, f["isha"]) if isha_angle is not None else float("nan"),
        }
        times = {k: (v if not math.isnan(v) else {"fajr": 5.0, "isha": 18.0}.get(k, v)) for k, v in times.items()}

    # recompute Fajr/Isha honestly: NaN means the angle isn't reached (high latitude summer)
    f = {k: v / 24 for k, v in times.items()}
    fajr = angle_time(fajr_angle, f["fajr"], ccw=True)
    isha = angle_time(isha_angle, f["isha"]) if isha_angle is not None else times["maghrib"] + isha_minutes / 60
    night = 24 - (times["sunset"] - times["sunrise"])
    if s.high_lat != "none":
        portion = {"angle": lambda a: a / 60, "seventh": lambda a: 1 / 7, "middle": lambda a: 1 / 2}[s.high_lat]
        fajr_limit = portion(fajr_angle) * night
        if math.isnan(fajr) or times["sunrise"] - fajr > fajr_limit:
            fajr = times["sunrise"] - fajr_limit
        if isha_angle is not None:
            isha_limit = portion(isha_angle) * night
            if math.isnan(isha) or isha - times["sunset"] > isha_limit:
                isha = times["sunset"] + isha_limit
    if math.isnan(fajr) or math.isnan(isha):
        raise ValueError("Fajr or Isha can't be found at this latitude today: choose a high-latitude rule")
    times["fajr"], times["isha"] = fajr, isha

    offset = _utc_offset_hours(s.tz, day) - s.lon / 15
    adjust = s.adjust or {}
    zone = ZoneInfo(s.tz)
    out = {}
    for name in PRAYERS:
        hours = times[name] + offset + adjust.get(name, 0) / 60
        minutes = int(math.floor(hours * 60 + 0.5))
        out[name] = datetime.combine(day, time(0), zone) + timedelta(minutes=minutes)
    return out


def label(name: str, day: date) -> str:
    if name == "dhuhr" and day.weekday() == 4:
        return "Jumu'ah"
    return {"fajr": "Fajr", "sunrise": "Sunrise", "dhuhr": "Dhuhr", "asr": "Asr", "maghrib": "Maghrib", "isha": "Isha"}[name]
