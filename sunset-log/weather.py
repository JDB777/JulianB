"""Pull Open-Meteo data and compute the sunset-window statistics for this project.

Definitions follow CLAUDE_CODE_HANDOFF.md section 4 exactly:

  low_trace  seven low-cloud values, sunset-3h .. sunset+3h
  swing      max - min of low cloud over sunset-2h .. sunset+3h  (SIX values,
             i.e. low_trace[1:], deliberately a different window from the trace)
  swing_rank rank of swing among every evening in the pulled window, 1 = highest

Usage:
    python weather.py station          backfill the three blank evenings
    python weather.py july             re-pull July from this endpoint as a check
    python weather.py offshore         sample along the sunset bearing
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

OUT = os.environ.get("SUNSET_OUT", ".")  # where intermediate JSON lands

HIST = "https://historical-forecast-api.open-meteo.com/v1/forecast"
LAT, LON = 37.7594, -122.5107
HOURLY = [
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "visibility",
    "relative_humidity_2m",
    "dew_point_2m",
    "pressure_msl",
]


def fetch(lat, lon, start, end, host=HIST, models=None):
    q = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY),
        "daily": "sunset",
        "timezone": "America/Los_Angeles",
        "start_date": start,
        "end_date": end,
    }
    if models:
        q["models"] = models
    url = host + "?" + urllib.parse.urlencode(q)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if attempt == 3:
                raise
            print(f"    retry {attempt + 1} after {e}")
            time.sleep(3 * (attempt + 1))


def index_hourly(d):
    """Map 'YYYY-MM-DDTHH:MM' -> dict of the seven variables."""
    h = d["hourly"]
    out = {}
    for i, t in enumerate(h["time"]):
        out[t] = {k: h[k][i] for k in HOURLY}
    return out


def true_offset_hours(day):
    """Real UTC offset for America/Los_Angeles on a given date, in hours."""
    d = datetime.fromisoformat(day + "T12:00").replace(tzinfo=ZoneInfo("America/Los_Angeles"))
    return d.utcoffset().total_seconds() / 3600


def sunset_hours(d):
    """Map date -> (label datetime of the sunset hour, true local 'HH:MM').

    CAUTION: Open-Meteo applies ONE utc offset to the whole response, taken from
    the request's *current* season. A window of February dates therefore comes
    back stamped PDT (-7) rather than PST (-8), and every sunset reads an hour
    late. The hourly timestamps are shifted by the same amount, so matching an
    hour against the API's own labels still selects the correct physical hour —
    but any label shown to a human must be corrected first.
    """
    api_off = d["utc_offset_seconds"] / 3600
    out = {}
    for day, s in zip(d["daily"]["time"], d["daily"]["sunset"]):
        dt = datetime.fromisoformat(s)
        rounded = dt.replace(minute=0, second=0) + timedelta(hours=1 if dt.minute >= 30 else 0)
        skew = api_off - true_offset_hours(day)  # +1 when Feb is stamped as PDT
        out[day] = (rounded, (dt - timedelta(hours=skew)).strftime("%H:%M"), skew)
    return out


def key(dt):
    return dt.strftime("%Y-%m-%dT%H:%M")


def evening_stats(hourly, sun_dt):
    """Everything the schema needs for one evening, or None if hours are missing."""
    trace_dts = [sun_dt + timedelta(hours=k) for k in range(-3, 4)]  # -3 .. +3
    pre_dts = [sun_dt + timedelta(hours=k) for k in (-3, -2, -1)]

    if any(key(t) not in hourly for t in trace_dts + pre_dts):
        return None
    at = hourly[key(sun_dt)]
    if at["cloud_cover_low"] is None:
        return None

    trace = [hourly[key(t)]["cloud_cover_low"] for t in trace_dts]
    if any(v is None for v in trace):
        return None

    swing_vals = trace[1:]  # sunset-2h .. +3h, six values
    pre = [hourly[key(t)] for t in pre_dts]

    def g(row, k):
        return row[k]

    return {
        "cc_low": at["cloud_cover_low"],
        "cc_mid": at["cloud_cover_mid"],
        "cc_high": at["cloud_cover_high"],
        "visibility_km": round(at["visibility"] / 1000, 1),
        "rh": at["relative_humidity_2m"],
        "dew_c": at["dew_point_2m"],
        "mslp": at["pressure_msl"],
        "rh_pre_min": min(g(r, "relative_humidity_2m") for r in pre),
        "vis_pre_max_km": round(max(g(r, "visibility") for r in pre) / 1000, 1),
        "dew_pre_min_c": min(g(r, "dew_point_2m") for r in pre),
        "low_trace": trace,
        "swing": max(swing_vals) - min(swing_vals),
    }


def window(lat, lon, start, end, label, models=None):
    """Pull a window and return {date: stats} plus the coordinates actually used."""
    d = fetch(lat, lon, start, end, models=models)
    coords = (round(d["latitude"], 6), round(d["longitude"], 6))
    print(f"  {label}: requested {lat}, {lon}  ->  returned {coords[0]}, {coords[1]}"
          f"  (elev {d.get('elevation')})")
    hourly = index_hourly(d)
    suns = sunset_hours(d)
    skews = {sk for _, _, sk in suns.values()}
    if skews != {0.0}:
        print(f"    NOTE: API offset differs from true local time by {sorted(skews)} h "
              f"on these dates; sunset labels corrected, hour matching unaffected.")
    stats = {}
    for day, (sun_dt, true_local, _) in suns.items():
        s = evening_stats(hourly, sun_dt)
        if s:
            s["sunset_local"] = true_local
            stats[day] = s
    return stats, coords


def rank_within(stats, target):
    """Rank of target's swing among all evenings in the window, 1 = highest."""
    swings = sorted((s["swing"] for s in stats.values()), reverse=True)
    return swings.index(stats[target]["swing"]) + 1, len(swings)


def show(stats, dates, title):
    print(f"\n{title}")
    print(f"{'date':<12}{'sun':>6}{'low':>5}{'mid':>5}{'high':>6}{'vis':>7}"
          f"{'rh':>5}{'dew':>7}{'mslp':>8}{'swing':>7}{'rank':>10}")
    for dt in dates:
        if dt not in stats:
            print(f"{dt:<12}  -- no data --")
            continue
        s = stats[dt]
        r, n = rank_within(stats, dt)
        print(f"{dt:<12}{s['sunset_local']:>6}{s['cc_low']:>5}{s['cc_mid']:>5}"
              f"{s['cc_high']:>6}{s['visibility_km']:>7}{s['rh']:>5}{s['dew_c']:>7}"
              f"{s['mslp']:>8}{s['swing']:>7}{f'{r} of {n}':>10}")
        print(f"{'':<12}trace {s['low_trace']}  pre: rh_min {s['rh_pre_min']}"
              f"  vis_max {s['vis_pre_max_km']}  dew_min {s['dew_pre_min_c']}")


TARGETS = {
    "2026-02-20": ("2026-02-10", "2026-03-02"),
    "2026-03-18": ("2026-03-08", "2026-03-28"),
    "2026-03-27": ("2026-03-17", "2026-04-06"),
}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "station"

    if mode == "station":
        print("Backfilling the three blank evenings (Historical Forecast API)\n")
        result = {}
        for target, (a, b) in TARGETS.items():
            stats, _ = window(LAT, LON, a, b, f"{target} window {a}..{b}")
            show(stats, [target], f"-- {target} (window {a} .. {b}, n={len(stats)}) --")
            r, n = rank_within(stats, target)
            result[target] = {**stats[target], "swing_rank": r, "window_n": n}
        json.dump(result, open(os.path.join(OUT, "backfill_result.json"), "w"), indent=2)
        print("\nwrote backfill_result.json to", OUT)

    elif mode == "offshore":
        import math

        def offshore_point(bearing_deg, km):
            b = math.radians(bearing_deg)
            dlat = km * math.cos(b) / 111.32
            mid = LAT + dlat / 2
            dlon = km * math.sin(b) / (111.32 * math.cos(math.radians(mid)))
            return round(LAT + dlat, 3), round(LON + dlon, 3)

        BEARING = 296.0  # July sunset azimuth
        models = sys.argv[2] if len(sys.argv) > 2 else None
        print(f"Offshore sampling along bearing {BEARING}°"
              + (f", models={models}" if models else ", default model")
              + "\n")

        pts = [("station", LAT, LON)]
        for km in (25, 50, 100, 150):
            la, lo = offshore_point(BEARING, km)
            pts.append((f"{km} km", la, lo))

        series, coords = {}, {}
        for label, la, lo in pts:
            stats, c = window(la, lo, "2026-07-07", "2026-07-27", label, models=models)
            series[label] = stats
            coords[label] = c

        # ---- grid snapping check: did the points actually resolve differently? ----
        print("\nGrid-snapping check — coordinates the API actually used:")
        seen = {}
        for label, c in coords.items():
            dup = seen.get(c)
            print(f"  {label:<9} -> {c[0]}, {c[1]}"
                  + (f"   *** SAME CELL AS {dup} ***" if dup else ""))
            seen.setdefault(c, label)
        distinct = len(set(coords.values()))
        print(f"  {distinct} distinct grid cells out of {len(coords)} points requested.")
        if distinct < len(coords):
            print("  WARNING: some points collapsed onto one cell. Values from those"
                  "\n  points are the same data and must not be compared.")

        # ---- low cloud at each evening's sunset hour, per point ----
        days = sorted(series["station"])
        print(f"\nLow cloud at the sunset hour\n{'date':<12}"
              + "".join(f"{lab:>10}" for lab, _, _ in pts))
        for d in days:
            row = f"{d:<12}"
            for lab, _, _ in pts:
                v = series[lab].get(d)
                row += f"{(v['cc_low'] if v else '--'):>10}"
            mark = {"2026-07-12": " <- shot", "2026-07-21": " <- shot",
                    "2026-07-27": " <- shot", "2026-07-13": " <- SKIPPED twin",
                    "2026-07-17": " <- SKIPPED twin"}.get(d, "")
            print(row + mark)

        # ---- the falsifiable prediction ----
        print("\nThe prediction: 07-21 (shot) and 07-13 (skipped) are identical at the"
              "\nstation but should SEPARATE offshore.")
        for lab, _, _ in pts:
            a = series[lab].get("2026-07-21")
            b = series[lab].get("2026-07-13")
            if not (a and b):
                continue
            gap = a["cc_low"] - b["cc_low"]
            print(f"  {lab:<9} 07-21 low {a['cc_low']:>3}   07-13 low {b['cc_low']:>3}"
                  f"   difference {gap:+4d}"
                  + ("   identical" if gap == 0 else ""))

        json.dump({"coords": {k: list(v) for k, v in coords.items()},
                   "series": series},
                  open(os.path.join(OUT, f"offshore_{models or 'default'}.json"), "w"), indent=2)
        print("\nwrote offshore result to", OUT)

    elif mode == "july":
        print("Re-pulling July 7-27 from the Historical Forecast endpoint\n")
        stats, _ = window(LAT, LON, "2026-07-07", "2026-07-27", "july")
        show(stats, sorted(stats), f"-- July (n={len(stats)}) --")
        json.dump(stats, open(os.path.join(OUT, "july_recheck.json"), "w"), indent=2)
        print("\nwrote july_recheck.json to", OUT)
