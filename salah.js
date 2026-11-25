/*! salah.js v1.0.0 · MIT · github.com/kal-eficia/salah-calendar
 * Browser twin of salahcal/times.py and salahcal/ics.py. Same maths, same results
 * (checked against each other in the test suite).
 */
(function (root) {
  "use strict";
  const METHODS = {
    MWL: [18.0, 17.0, null], ISNA: [15.0, 15.0, null], Egypt: [19.5, 17.5, null],
    Makkah: [18.5, null, 90], Karachi: [18.0, 18.0, null], Dubai: [18.2, 18.2, null], Moonsighting: [18.0, 18.0, null],
  };
  const PRAYERS = ["fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha"];
  const rad = (x) => (x * Math.PI) / 180, deg = (x) => (x * 180) / Math.PI;
  const sin = (x) => Math.sin(rad(x)), cos = (x) => Math.cos(rad(x)), tan = (x) => Math.tan(rad(x));
  const asin = (x) => deg(Math.asin(x)), acos = (x) => deg(Math.acos(x)), atan2 = (y, x) => deg(Math.atan2(y, x));
  const acot = (x) => deg(Math.atan(1 / x));
  const fix = (a, b) => a - b * Math.floor(a / b);

  function julian(y, m, d) {
    if (m <= 2) { y -= 1; m += 12; }
    const a = Math.floor(y / 100), b = 2 - a + Math.floor(a / 4);
    return Math.floor(365.25 * (y + 4716)) + Math.floor(30.6001 * (m + 1)) + d + b - 1524.5;
  }
  function sunPosition(jd) {
    const D = jd - 2451545.0;
    const g = fix(357.529 + 0.98560028 * D, 360), q = fix(280.459 + 0.98564736 * D, 360);
    const L = fix(q + 1.915 * sin(g) + 0.020 * sin(2 * g), 360);
    const e = 23.439 - 0.00000036 * D;
    const ra = fix(atan2(cos(e) * sin(L), cos(L)) / 15, 24);
    return [asin(sin(e) * sin(L)), q / 15 - ra];
  }
  // UTC offset (hours) of an IANA zone at local noon of y-m-d
  function utcOffset(tz, y, m, d) {
    const probe = new Date(Date.UTC(y, m - 1, d, 12));
    const parts = Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })
      .formatToParts(probe).map((p) => [p.type, p.value]));
    const asUTC = Date.UTC(+parts.year, +parts.month - 1, +parts.day, +parts.hour, +parts.minute);
    return (asUTC - probe.getTime()) / 3600000;
  }

  // Returns { fajr: {h, m, utc: Date}, ... } for local calendar date y-m-d
  function compute(y, m, d, s) {
    const [fajrAngle, ishaAngle, ishaMinutes] = METHODS[s.method || "MWL"];
    const lat = s.lat, jd = julian(y, m, d) - s.lon / (15 * 24);
    const midDay = (t) => fix(12 - sunPosition(jd + t)[1], 24);
    const angleTime = (angle, t, ccw) => {
      const decl = sunPosition(jd + t)[0];
      const c = (-sin(angle) - sin(decl) * sin(lat)) / (cos(decl) * cos(lat));
      if (c > 1 || c < -1) return NaN;
      const h = acos(c) / 15, noon = midDay(t);
      return ccw ? noon - h : noon + h;
    };
    const asrTime = (factor, t) => {
      const decl = sunPosition(jd + t)[0];
      return angleTime(-acot(factor + tan(Math.abs(lat - decl))), t);
    };
    const factor = s.asr === "hanafi" ? 2 : 1;
    let T = { fajr: 5, sunrise: 6, dhuhr: 12, asr: 13, sunset: 18, maghrib: 18, isha: 18 };
    for (let i = 0; i < 2; i++) {
      const f = Object.fromEntries(Object.entries(T).map(([k, v]) => [k, v / 24]));
      T = {
        fajr: angleTime(fajrAngle, f.fajr, true), sunrise: angleTime(0.833, f.sunrise, true), dhuhr: midDay(f.dhuhr),
        asr: asrTime(factor, f.asr), sunset: angleTime(0.833, f.sunset), maghrib: angleTime(0.833, f.maghrib),
        isha: ishaAngle !== null ? angleTime(ishaAngle, f.isha) : NaN,
      };
      for (const [k, dflt] of [["fajr", 5], ["isha", 18]]) if (Number.isNaN(T[k])) T[k] = dflt;
    }
    let fajr = angleTime(fajrAngle, T.fajr / 24, true);
    let isha = ishaAngle !== null ? angleTime(ishaAngle, T.isha / 24) : T.maghrib + ishaMinutes / 60;
    const night = 24 - (T.sunset - T.sunrise);
    const rule = s.highLat || "angle";
    if (rule !== "none") {
      const portion = (a) => (rule === "angle" ? a / 60 : rule === "seventh" ? 1 / 7 : 1 / 2);
      const fl = portion(fajrAngle) * night;
      if (Number.isNaN(fajr) || T.sunrise - fajr > fl) fajr = T.sunrise - fl;
      if (ishaAngle !== null) {
        const il = portion(ishaAngle) * night;
        if (Number.isNaN(isha) || isha - T.sunset > il) isha = T.sunset + il;
      }
    }
    T.fajr = fajr; T.isha = isha;
    const tzOff = utcOffset(s.tz, y, m, d), offset = tzOff - s.lon / 15, adjust = s.adjust || {};
    const out = {};
    for (const name of PRAYERS) {
      const hours = T[name] + offset + (adjust[name] || 0) / 60;
      const minutes = Math.floor(hours * 60 + 0.5);
      const utc = new Date(Date.UTC(y, m - 1, d) + (minutes - tzOff * 60) * 60000);
      out[name] = { minutes, h: Math.floor(minutes / 60), m: ((minutes % 60) + 60) % 60, utc };
    }
    return out;
  }

  const label = (name, weekday) => (name === "dhuhr" && weekday === 5 ? "Jumu'ah" : { fajr: "Fajr", sunrise: "Sunrise", dhuhr: "Dhuhr", asr: "Asr", maghrib: "Maghrib", isha: "Isha" }[name]);
  const pad = (n) => String(n).padStart(2, "0");
  const icsTime = (d) => `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`;
  const esc = (s) => s.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,");

  function toICS(startY, startM, startD, days, s, opts = {}) {
    const minutes = opts.minutes ?? 20, jm = opts.jumuahMinutes ?? 60, reminder = opts.reminder ?? 10, place = opts.place || "";
    const L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//kal-eficia//salah-calendar 1.0//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
      `X-WR-CALNAME:${esc("Salah" + (place ? " · " + place : ""))}`, `X-WR-TIMEZONE:${s.tz}`];
    const stamp = icsTime(new Date());
    for (let i = 0; i < days; i++) {
      const day = new Date(Date.UTC(startY, startM - 1, startD + i));
      const y = day.getUTCFullYear(), m = day.getUTCMonth() + 1, d = day.getUTCDate(), wd = day.getUTCDay();
      const t = compute(y, m, d, s);
      for (const name of PRAYERS) {
        if (name === "sunrise") continue;
        const title = label(name, wd), len = title === "Jumu'ah" ? jm : minutes;
        const st = t[name].utc, en = new Date(st.getTime() + len * 60000);
        L.push("BEGIN:VEVENT", `UID:${y}${pad(m)}${pad(d)}-${title.toLowerCase().replace("'", "")}-${s.lat.toFixed(2)}_${s.lon.toFixed(2)}@salah-calendar`,
          `DTSTAMP:${stamp}`, `DTSTART:${icsTime(st)}`, `DTEND:${icsTime(en)}`, `SUMMARY:${esc(title)}`,
          `DESCRIPTION:${esc(`${title} at ${pad(t[name].h)}:${pad(t[name].m)}. Calculated with the ${s.method} method; follow your local masjid where it differs.`)}`,
          "TRANSP:OPAQUE", "CATEGORIES:Salah");
        if (reminder) L.push("BEGIN:VALARM", "ACTION:DISPLAY", `DESCRIPTION:${esc(title)}`, `TRIGGER:-PT${reminder}M`, "END:VALARM");
        L.push("END:VEVENT");
      }
    }
    L.push("END:VCALENDAR");
    // fold lines longer than 75 octets, as the iCalendar standard requires
    const fold = (line) => {
      const out = []; const enc = new TextEncoder();
      while (enc.encode(line).length > 74) {
        let cut = 74;
        while (enc.encode(line.slice(0, cut)).length > 74) cut--;
        out.push(line.slice(0, cut)); line = " " + line.slice(cut);
      }
      out.push(line); return out.join("\r\n");
    };
    return L.map(fold).join("\r\n") + "\r\n";
  }

  const api = { compute, toICS, label, METHODS, PRAYERS, utcOffset, version: "1.0.0" };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Salah = api;
})(typeof window !== "undefined" ? window : globalThis);
