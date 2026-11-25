import json
import shutil
import subprocess
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from salahcal import PLACES, Settings, clashes, compute, prayer_events, read_meetings, to_ics

ROOT = Path(__file__).resolve().parent.parent
LONDON = Settings(*PLACES["london"])


class Astronomy(unittest.TestCase):
    def test_london_sunrise_sunset_match_almanac(self):
        # Almanac: 21 Jun 2026 sunrise 04:43, sunset 21:21 (BST); 21 Dec sunrise 08:04, sunset 15:54 (GMT)
        for d, rise, sset in [(date(2026, 6, 21), "04:43", "21:21"), (date(2026, 12, 21), "08:04", "15:54")]:
            t = compute(d, LONDON)
            for got, want in ((t["sunrise"], rise), (t["maghrib"], sset)):
                h, m = map(int, want.split(":"))
                diff = abs((got.hour * 60 + got.minute) - (h * 60 + m))
                self.assertLessEqual(diff, 2, f"{d} {got:%H:%M} vs {want}")

    def test_order_every_day_of_the_year_in_many_places(self):
        for key in ("london", "glasgow", "makkah", "hargeisa", "nairobi", "new-york", "kuala-lumpur"):
            s = Settings(*PLACES[key])
            for i in range(0, 366, 3):
                d = date(2026, 1, 1) + timedelta(days=i)
                t = list(compute(d, s).values())
                with self.subTest(place=key, day=d):
                    self.assertEqual(t, sorted(t))

    def test_high_latitude_summer_has_fajr_and_isha(self):
        t = compute(date(2026, 6, 21), Settings(*PLACES["glasgow"]))
        self.assertLess(t["fajr"], t["sunrise"])
        self.assertGreater(t["isha"], t["maghrib"])

    def test_dhuhr_is_solar_noon(self):
        t = compute(date(2026, 3, 20), LONDON)  # near the equinox, noon ~ 12:07 GMT in London
        self.assertEqual((t["dhuhr"].hour, t["dhuhr"].minute // 10), (12, 0))

    def test_hanafi_asr_is_later(self):
        d = date(2026, 11, 25)
        self.assertGreater(compute(d, Settings(*PLACES["london"], asr="hanafi"))["asr"], compute(d, LONDON)["asr"])

    def test_makkah_isha_is_90_minutes_after_maghrib(self):
        t = compute(date(2026, 11, 25), Settings(*PLACES["makkah"], method="Makkah"))
        self.assertEqual(t["isha"] - t["maghrib"], timedelta(minutes=90))

    def test_jumuah_label_and_length(self):
        ev = prayer_events(date(2026, 11, 27), 1, LONDON)
        titles = [e[0] for e in ev]
        self.assertIn("Jumu'ah", titles)
        j = ev[titles.index("Jumu'ah")]
        self.assertEqual(j[2] - j[1], timedelta(minutes=60))


class Calendar(unittest.TestCase):
    def test_ics_is_well_formed(self):
        text = to_ics(prayer_events(date(2026, 11, 25), 3, LONDON), LONDON, "London")
        self.assertTrue(text.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertEqual(text.count("BEGIN:VEVENT"), 15)
        self.assertTrue(all(len(line.encode()) <= 75 for line in text.split("\r\n")))

    def test_clashes(self):
        ics = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Standup\nDTSTART;TZID=Europe/London:20261127T113000\n"
               "DTEND;TZID=Europe/London:20261127T123000\nEND:VEVENT\nBEGIN:VEVENT\nSUMMARY:Deep work\n"
               "DTSTART;TZID=Europe/London:20261126T090000\nDTEND;TZID=Europe/London:20261126T110000\nEND:VEVENT\nEND:VCALENDAR")
        found = clashes(read_meetings(ics, "Europe/London"), LONDON)
        self.assertEqual([(m.summary, title) for m, title, _ in found], [("Standup", "Jumu'ah")])


@unittest.skipUnless(shutil.which("node"), "node not installed")
class JavaScriptTwin(unittest.TestCase):
    def test_same_times_as_python(self):
        cases = [("london", "MWL", "shafii", "2026-06-21"), ("london", "MWL", "hanafi", "2026-11-25"),
                 ("glasgow", "ISNA", "shafii", "2026-06-10"), ("makkah", "Makkah", "shafii", "2026-03-01"),
                 ("hargeisa", "MWL", "shafii", "2026-11-25"), ("new-york", "ISNA", "hanafi", "2026-03-08")]
        script = ("const S=require(process.argv[1]);const C=JSON.parse(process.argv[2]);"
                  "console.log(JSON.stringify(C.map(([lat,lon,tz,method,asr,day])=>{const [y,m,d]=day.split('-').map(Number);"
                  "const t=S.compute(y,m,d,{lat,lon,tz,method,asr});return S.PRAYERS.map(p=>t[p].utc.toISOString())})))")
        payload = [[*PLACES[c][:3], meth, asr, day] for c, meth, asr, day in cases]
        out = json.loads(subprocess.run(["node", "-e", script, str(ROOT / "salah.js"), json.dumps(payload)],
                                        capture_output=True, text=True, check=True).stdout)
        for (c, meth, asr, day), js in zip(cases, out):
            py = compute(date.fromisoformat(day), Settings(*PLACES[c], method=meth, asr=asr))
            py_utc = [v.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:00.000Z") for v in py.values()]
            with self.subTest(place=c, day=day):
                self.assertEqual(js, py_utc)


if __name__ == "__main__":
    unittest.main()
