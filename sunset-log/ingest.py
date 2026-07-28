"""Fill the archive. Fetch once, keep forever, never re-download.

    python ingest.py backfill 2024-01-01 2026-07-27   # history
    python ingest.py update                           # catch up to yesterday
    python ingest.py forecast                         # next 7 days, for prediction

All eleven sample points come back in a single request per chunk, because
Open-Meteo accepts comma-separated coordinates and returns an array. Chunks are
committed as they land, so an interrupted backfill resumes where it stopped.
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import solar
import store

HIST = "https://historical-forecast-api.open-meteo.com/v1/forecast"
LIVE = "https://api.open-meteo.com/v1/forecast"
TZ = ZoneInfo("America/Los_Angeles")
CHUNK_DAYS = 60


def _true_offset(day_iso):
    d = datetime.fromisoformat(day_iso + "T12:00").replace(tzinfo=TZ)
    return d.utcoffset().total_seconds() / 3600


def fetch(points, start=None, end=None, forecast_days=None):
    q = {
        "latitude": ",".join(str(p["req_lat"]) for p in points),
        "longitude": ",".join(str(p["req_lon"]) for p in points),
        "hourly": ",".join(store.VARS),
        "timezone": "America/Los_Angeles",
    }
    if forecast_days:
        q["forecast_days"] = forecast_days
        host = LIVE
    else:
        q["start_date"], q["end_date"] = start, end
        host = HIST
    url = host + "?" + urllib.parse.urlencode(q)

    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                data = json.loads(r.read().decode())
                return data if isinstance(data, list) else [data]
        except Exception as e:
            if attempt == 4:
                raise
            wait = 4 * (attempt + 1)
            print(f"      retry {attempt + 1} in {wait}s ({e})")
            time.sleep(wait)


def absorb(con, points, payloads, source):
    """Normalise to true local time and store. Returns rows written."""
    rows = []
    for p, d in zip(points, payloads):
        if p["grid_lat"] is None:
            con.execute("UPDATE points SET grid_lat=?, grid_lon=? WHERE id=?",
                        (round(d["latitude"], 5), round(d["longitude"], 5), p["id"]))
        api_off = d["utc_offset_seconds"] / 3600
        h = d["hourly"]
        series = [h[v] for v in store.VARS]
        for i, ts in enumerate(h["time"]):
            day = ts[:10]
            skew = api_off - _true_offset(day)
            if skew:
                t = datetime.fromisoformat(ts) - timedelta(hours=skew)
                ts = t.strftime("%Y-%m-%dT%H:%M")
            vals = [s[i] for s in series]
            if all(v is None for v in vals):
                continue
            rows.append((ts, p["id"], *vals, source))
    store.store_hourly(con, rows)
    return len(rows)


def ensure_evenings(con, d0, d1):
    """Sunset time and azimuth are pure computation - no network needed."""
    n = 0
    day = date.fromisoformat(d0)
    last = date.fromisoformat(d1)
    have = {r["date"] for r in con.execute("SELECT date FROM evenings")}
    while day <= last:
        iso = day.isoformat()
        if iso not in have:
            ss = solar.sunset(day)
            store.store_evening(con, iso, ss.strftime("%H:%M"),
                                round(solar.sunset_azimuth(day), 1))
            n += 1
        day += timedelta(days=1)
    return n


def missing_ranges(con, d0, d1):
    """Contiguous date ranges not yet covered, so we only fetch the gaps."""
    have = set(store.covered_dates(con))
    out, run = [], None
    day, last = date.fromisoformat(d0), date.fromisoformat(d1)
    while day <= last:
        iso = day.isoformat()
        if iso in have:
            if run:
                out.append(run)
                run = None
        else:
            run = (run[0], iso) if run else (iso, iso)
        day += timedelta(days=1)
    if run:
        out.append(run)
    return out


def backfill(con, d0, d1, source="historical"):
    pts = store.points(con)
    gaps = missing_ranges(con, d0, d1)
    if not gaps:
        print(f"  {d0}..{d1} already complete, nothing to fetch.")
        return 0
    total_days = sum((date.fromisoformat(b) - date.fromisoformat(a)).days + 1
                     for a, b in gaps)
    print(f"  {len(gaps)} gap(s), {total_days} days to fetch across "
          f"{len(pts)} points")

    written = 0
    for a, b in gaps:
        start = date.fromisoformat(a)
        end = date.fromisoformat(b)
        while start <= end:
            stop = min(start + timedelta(days=CHUNK_DAYS - 1), end)
            print(f"    {start} .. {stop}", end="", flush=True)
            payloads = fetch(pts, start.isoformat(), stop.isoformat())
            n = absorb(con, pts, payloads, source)
            ensure_evenings(con, start.isoformat(), stop.isoformat())
            con.commit()
            written += n
            print(f"   {n:,} rows")
            start = stop + timedelta(days=1)
            time.sleep(1)  # be polite to a free API
    return written


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "update"
    con = store.connect()
    pts = store.points(con)

    if cmd == "backfill":
        d0, d1 = sys.argv[2], sys.argv[3]
        print(f"Backfilling {d0} .. {d1}")
        n = backfill(con, d0, d1)
        if not store.get_meta(con, "watch_start"):
            favs = store.favorites(con)
            if favs:
                store.set_meta(con, "watch_start", favs[0])
        con.commit()
        print(f"  stored {n:,} hourly rows")

    elif cmd == "update":
        # historical-forecast lags real time slightly; yesterday is safe
        end = (date.today() - timedelta(days=1)).isoformat()
        have = store.covered_dates(con)
        start = (date.fromisoformat(have[-1]) + timedelta(days=1)).isoformat() \
            if have else (date.today() - timedelta(days=30)).isoformat()
        if start > end:
            print("  already up to date.")
        else:
            print(f"Updating {start} .. {end}")
            n = backfill(con, start, end)
            con.commit()
            print(f"  stored {n:,} hourly rows")

    elif cmd == "forecast":
        print("Fetching the next 7 days (forecast, will be overwritten by history)")
        payloads = fetch(pts, forecast_days=8)
        n = absorb(con, pts, payloads, "forecast")
        today = date.today()
        ensure_evenings(con, today.isoformat(),
                        (today + timedelta(days=8)).isoformat())
        con.commit()
        print(f"  stored {n:,} hourly rows")

    else:
        print(__doc__)
        return

    s = store.summary(con)
    print("\narchive now holds "
          f"{s['hourly_rows']:,} hourly rows over {s['days_covered']:,} days "
          f"({s['span'][0]} .. {s['span'][1]}), {s['db_mb']} MB")


if __name__ == "__main__":
    main()
