"""The archive: a single SQLite file holding every evening we have ever fetched.

Design intent
-------------
This is meant to run for years. Weather is fetched once and kept. Nothing here
re-downloads data it already has, and the raw hourly readings are stored rather
than derived summaries, so a better feature idea later can be applied to the
whole history without touching the network.

Three things are stored:

  points   the station plus a fan of offshore sample points. The sun sets 60
           degrees further north in June than in December, so a single "due
           west" point is wrong most of the year; the fan covers the range and
           features pick the bearing nearest each date's actual sunset azimuth.
  hourly   raw readings per point per hour, in TRUE local time (see below).
  labels   which evenings were keepers. This is the signal being learned.

Time
----
Open-Meteo stamps an entire response with one UTC offset taken from the
request's current season, so a February window comes back labelled PDT and every
timestamp reads an hour late. Hourly and daily fields shift together, so the data
is internally consistent, but storing those labels would corrupt the archive the
moment it is queried across a DST boundary. Everything here is normalised to true
America/Los_Angeles local time on the way in.
"""

import json
import math
import os
import sqlite3
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "data", "sunsets.db")

STATION_LAT, STATION_LON = 37.7594, -122.5107

# Sunset azimuth at this latitude runs about 240 deg at the December solstice to
# 301 deg at the June solstice. Five bearings keeps the worst-case error under
# 8 deg, which at 100 km is a lateral miss of ~13 km - inside a grid cell.
FAN_BEARINGS = [240, 255, 270, 285, 300]
FAN_KM = [50, 100]

VARS = ["cloud_cover_low", "cloud_cover_mid", "cloud_cover_high",
        "visibility", "relative_humidity_2m", "dew_point_2m", "pressure_msl"]
COLS = ["cc_low", "cc_mid", "cc_high", "vis", "rh", "dew", "mslp"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS points (
    id INTEGER PRIMARY KEY,
    label TEXT UNIQUE NOT NULL,
    bearing REAL,
    km REAL,
    req_lat REAL, req_lon REAL,
    grid_lat REAL, grid_lon REAL
);
CREATE TABLE IF NOT EXISTS hourly (
    ts TEXT NOT NULL,            -- true local 'YYYY-MM-DDTHH:MM'
    point_id INTEGER NOT NULL,
    cc_low REAL, cc_mid REAL, cc_high REAL,
    vis REAL, rh REAL, dew REAL, mslp REAL,
    source TEXT,                 -- 'historical' or 'forecast'
    PRIMARY KEY (ts, point_id)
);
CREATE INDEX IF NOT EXISTS hourly_day ON hourly (substr(ts, 1, 10));
CREATE TABLE IF NOT EXISTS evenings (
    date TEXT PRIMARY KEY,       -- local date
    sunset_local TEXT,           -- 'HH:MM'
    sunset_azimuth REAL
);
CREATE TABLE IF NOT EXISTS labels (
    date TEXT PRIMARY KEY,
    status TEXT NOT NULL,        -- 'favorite' | 'not_favorite'
    photos TEXT,                 -- JSON array of filenames
    shot_time TEXT,
    note TEXT,
    added_at TEXT
);
"""


def offshore_point(bearing_deg, km, lat=STATION_LAT, lon=STATION_LON):
    b = math.radians(bearing_deg)
    dlat = km * math.cos(b) / 111.32
    mid = lat + dlat / 2
    dlon = km * math.sin(b) / (111.32 * math.cos(math.radians(mid)))
    return round(lat + dlat, 4), round(lon + dlon, 4)


def connect(path=DB_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    _seed_points(con)
    # a rebuilt database still knows which evenings mattered
    if not con.execute("SELECT 1 FROM labels LIMIT 1").fetchone():
        restored = import_labels(con)
        if restored:
            print(f"  (restored {restored} labels from data/favorites.json)")
    con.commit()
    return con


def _seed_points(con):
    have = {r["label"] for r in con.execute("SELECT label FROM points")}
    rows = [("station", None, 0.0, STATION_LAT, STATION_LON)]
    for b in FAN_BEARINGS:
        for km in FAN_KM:
            la, lo = offshore_point(b, km)
            rows.append((f"b{b}_{km}km", float(b), float(km), la, lo))
    for label, bearing, km, la, lo in rows:
        if label not in have:
            con.execute(
                "INSERT INTO points (label, bearing, km, req_lat, req_lon) "
                "VALUES (?,?,?,?,?)", (label, bearing, km, la, lo))


def points(con):
    return list(con.execute("SELECT * FROM points ORDER BY id"))


def get_meta(con, key, default=None):
    r = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def set_meta(con, key, value):
    con.execute("INSERT INTO meta (key,value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)))


def store_hourly(con, rows):
    """rows: (ts, point_id, cc_low, cc_mid, cc_high, vis, rh, dew, mslp, source).

    A forecast row may later be replaced by a historical one; historical is
    never downgraded back to forecast.
    """
    con.executemany(
        "INSERT INTO hourly (ts, point_id, cc_low, cc_mid, cc_high, vis, rh, dew,"
        " mslp, source) VALUES (?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(ts, point_id) DO UPDATE SET "
        " cc_low=excluded.cc_low, cc_mid=excluded.cc_mid, cc_high=excluded.cc_high,"
        " vis=excluded.vis, rh=excluded.rh, dew=excluded.dew, mslp=excluded.mslp,"
        " source=excluded.source "
        "WHERE hourly.source != 'historical' OR excluded.source = 'historical'",
        rows)


def store_evening(con, d, sunset_local, azimuth):
    con.execute("INSERT INTO evenings (date, sunset_local, sunset_azimuth) "
                "VALUES (?,?,?) ON CONFLICT(date) DO UPDATE SET "
                "sunset_local=excluded.sunset_local, "
                "sunset_azimuth=excluded.sunset_azimuth",
                (d, sunset_local, azimuth))


def set_label(con, d, status, photos=None, shot_time=None, note=None):
    con.execute(
        "INSERT INTO labels (date, status, photos, shot_time, note, added_at) "
        "VALUES (?,?,?,?,?,?) ON CONFLICT(date) DO UPDATE SET "
        "status=excluded.status, photos=excluded.photos, "
        "shot_time=excluded.shot_time, note=excluded.note",
        (d, status, json.dumps(photos or []), shot_time, note,
         datetime.now().isoformat(timespec="seconds")))


def favorites(con):
    return [r["date"] for r in
            con.execute("SELECT date FROM labels WHERE status='favorite' ORDER BY date")]


LABELS_JSON = os.path.join(HERE, "data", "favorites.json")


def export_labels(con, path=LABELS_JSON):
    """Mirror the labels to a small committed JSON file.

    The weather in this archive can always be fetched again. Which evenings you
    liked cannot - it exists nowhere else. So the database is disposable and
    gitignored, and this file is the thing that actually matters.
    """
    rows = [dict(r) for r in con.execute("SELECT * FROM labels ORDER BY date")]
    for r in rows:
        r["photos"] = json.loads(r["photos"] or "[]")
    payload = {
        "watch_start": get_meta(con, "watch_start"),
        "watch_end": get_meta(con, "watch_end"),
        "labels": rows,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(payload, open(path, "w", encoding="utf-8"), indent=2)
    return len(rows)


def import_labels(con, path=LABELS_JSON):
    """Restore labels from the committed mirror, for a rebuilt database."""
    if not os.path.exists(path):
        return 0
    payload = json.load(open(path, encoding="utf-8"))
    have = {r["date"] for r in con.execute("SELECT date FROM labels")}
    n = 0
    for r in payload.get("labels", []):
        if r["date"] in have:
            continue
        con.execute(
            "INSERT INTO labels (date, status, photos, shot_time, note, added_at) "
            "VALUES (?,?,?,?,?,?)",
            (r["date"], r["status"], json.dumps(r.get("photos") or []),
             r.get("shot_time"), r.get("note"), r.get("added_at")))
        n += 1
    for k in ("watch_start", "watch_end"):
        if payload.get(k) and not get_meta(con, k):
            set_meta(con, k, payload[k])
    return n


def covered_dates(con, point_label="station"):
    """Dates with at least 12 hours stored at the given point."""
    return [r["d"] for r in con.execute(
        "SELECT substr(h.ts,1,10) AS d, COUNT(*) c FROM hourly h "
        "JOIN points p ON p.id = h.point_id WHERE p.label = ? "
        "GROUP BY d HAVING c >= 12 ORDER BY d", (point_label,))]


def watch_window(con):
    """The span over which a missing favorite label genuinely means 'not a keeper'.

    Before the user started sending photographs, an unlabelled evening carries no
    information; treating it as a negative would invent data. Stored explicitly
    rather than assumed.
    """
    start = get_meta(con, "watch_start")
    end = get_meta(con, "watch_end") or date.today().isoformat()
    return start, end


def summary(con):
    n_hours = con.execute("SELECT COUNT(*) c FROM hourly").fetchone()["c"]
    n_days = len(covered_dates(con))
    favs = favorites(con)
    start, end = watch_window(con)
    span = con.execute("SELECT MIN(substr(ts,1,10)) a, MAX(substr(ts,1,10)) b "
                       "FROM hourly").fetchone()
    return {
        "hourly_rows": n_hours,
        "days_covered": n_days,
        "span": (span["a"], span["b"]),
        "points": len(points(con)),
        "favorites": len(favs),
        "watch_start": start,
        "watch_end": end,
        "db_mb": round(os.path.getsize(DB_PATH) / 1e6, 2) if os.path.exists(DB_PATH) else 0,
    }


if __name__ == "__main__":
    con = connect()
    s = summary(con)
    print(f"archive: {DB_PATH}")
    for k, v in s.items():
        print(f"  {k:<14} {v}")
    print("\npoints:")
    for p in points(con):
        grid = (f"  grid {p['grid_lat']}, {p['grid_lon']}"
                if p["grid_lat"] is not None else "  (not yet fetched)")
        print(f"  {p['label']:<12} req {p['req_lat']}, {p['req_lon']}{grid}")
