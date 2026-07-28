"""Regenerate the site's data file from the archive.

    python publish.py

Numbers come from the archive, which is authoritative. Prose - type, read,
revision, note - is preserved from the existing data/evenings.json, because it
is written by a person and cannot be regenerated. Anything new gets TODO
markers so it is obvious what still needs writing.
"""

import json
import math
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import features as F  # noqa: E402
import solar  # noqa: E402
import store  # noqa: E402

DATA = os.path.join(HERE, "data", "evenings.json")

PROSE_FIELDS = ["type", "read", "revision", "note"]


def low_trace(con, day, evening, station_id):
    hour = F._round_hour(evening["sunset_local"])
    base = datetime.fromisoformat(day).replace(hour=0) + timedelta(hours=hour)
    rows = F.load_day(con, day, [station_id])[station_id]
    out = []
    for k in F.TRACE:
        ts = (base + timedelta(hours=k)).strftime("%Y-%m-%dT%H:%M")
        r = rows.get(ts)
        out.append(None if r is None else r["cc_low"])
    return out


def swing_rank(feats, day, window=10):
    o = date.fromisoformat(day).toordinal()
    lo = date.fromordinal(o - window).isoformat()
    hi = date.fromordinal(o + window).isoformat()
    vals = sorted((f["swing"] for d, f in feats.items() if lo <= d <= hi),
                  reverse=True)
    if not vals or day not in feats:
        return None, 0
    return vals.index(feats[day]["swing"]) + 1, len(vals)


def main():
    con = store.connect()
    feats = F.all_features(con)
    pts = {p["label"]: p for p in store.points(con)}
    station_id = pts["station"]["id"]

    old = {}
    doc = {}
    if os.path.exists(DATA):
        doc = json.load(open(DATA, encoding="utf-8"))
        old = {e["date"]: e for e in doc.get("evenings", [])}

    favs = store.favorites(con)
    if not favs:
        print("No favorites recorded yet; leaving the data file alone.")
        return

    evenings = []
    for day in favs:
        lab = con.execute("SELECT * FROM labels WHERE date=?", (day,)).fetchone()
        ev = con.execute("SELECT * FROM evenings WHERE date=?", (day,)).fetchone()
        if ev is None:
            print(f"  {day}: no solar record, skipping")
            continue
        prev = old.get(day, {})
        f = feats.get(day)

        photos = json.loads(lab["photos"] or "[]") or prev.get("photos", [])
        shot = lab["shot_time"] or prev.get("shot_time") or ev["sunset_local"]
        geo = solar.describe(date.fromisoformat(day), shot)

        weather = None
        if f:
            rank, n = swing_rank(feats, day)
            weather = {
                "cc_low": round(f["cc_low"]), "cc_mid": round(f["cc_mid"]),
                "cc_high": round(f["cc_high"]),
                "visibility_km": round(f["vis"], 1), "rh": round(f["rh"]),
                "dew_c": round(f["dew"], 1), "mslp": round(f["mslp"], 1),
                "rh_pre_min": round(f["rh_pre_min"]),
                "vis_pre_max_km": round(f["vis_pre_max"], 1),
                "dew_pre_min_c": round(f["dew_pre_min"], 1),
                "low_trace": [None if v is None else round(v)
                              for v in low_trace(con, day, ev, station_id)],
                "swing": round(f["swing"]), "swing_rank": rank,
            }

        b = math.radians(geo["sunset_azimuth"])
        dlat = 50 * math.cos(b) / 111.32
        mid = store.STATION_LAT + dlat / 2
        dlon = 50 * math.sin(b) / (111.32 * math.cos(math.radians(mid)))

        entry = {
            "date": day,
            "photos": photos,
            **geo,
            "offshore_50km": [round(store.STATION_LAT + dlat, 3),
                              round(store.STATION_LON + dlon, 3)],
            "timestamp_confidence": prev.get("timestamp_confidence")
            or (lab["note"] or "recorded"),
            "weather": weather,
            "offshore": ({"slot_50": round(f["slot_50"]),
                          "slot_100": round(f["slot_100"]),
                          "bearing": ev["sunset_azimuth"]} if f else None),
            "type": prev.get("type", "TODO: short label"),
            "read": prev.get("read", "TODO: what the photograph shows."),
            "revision": prev.get("revision"),
            "note": prev.get("note", "TODO: what the day around it was doing."),
        }
        evennew = entry
        evenings.append(evennew)

    doc.setdefault("station", {
        "name": "Ocean Beach, San Francisco",
        "lat": store.STATION_LAT, "lon": store.STATION_LON,
    })
    doc["station"]["weather_source"] = (
        "Open-Meteo, archived locally. Station plus a fan of offshore points "
        "sampled along each evening's sunset bearing.")
    doc.setdefault("notes_on_method", {})
    doc["notes_on_method"].setdefault("swing", "")
    doc["notes_on_method"].setdefault("caution", "")
    doc["notes_on_method"].setdefault("visual_reads", "")
    doc["evenings"] = evenings

    json.dump(doc, open(DATA, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    json.load(open(DATA, encoding="utf-8"))
    todo = sum(1 for e in evenings
               if any(str(e.get(k, "")).startswith("TODO") for k in PROSE_FIELDS))
    print(f"      wrote {len(evenings)} evenings to data/evenings.json"
          + (f"; {todo} still need prose" if todo else ""))


if __name__ == "__main__":
    main()
