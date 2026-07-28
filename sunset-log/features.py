"""Turn stored hourly readings into one feature vector per evening.

The features are chosen to describe the two things that physically have to
happen for a vivid sunset here, plus the obvious confounders so they can be
ruled out rather than assumed away:

  a canvas   cloud aloft to catch the light. Mid and high cloud overhead.
  a slot     a gap at the western horizon, 25-150 km out, for the light to get
             through on its way to that canvas. The station cannot see this -
             it is below the horizon from the beach - which is why the archive
             samples a fan of offshore points and picks the bearing nearest the
             evening's actual sunset azimuth.

Everything is computed from the archive, so the same code runs on history and on
a forecast. That is deliberate: a feature that cannot be computed from a
forecast is useless for predicting tomorrow.
"""

import os
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import store  # noqa: E402

# hours relative to the sunset hour that features may reference
PRE = [-3, -2, -1]
TRACE = [-3, -2, -1, 0, 1, 2, 3]
SWING = [-2, -1, 0, 1, 2, 3]

FEATURE_NAMES = [
    "cc_low", "cc_mid", "cc_high",
    "canvas", "canvas_any", "canvas_high_frac",
    "vis", "rh", "dew", "mslp",
    "rh_pre_min", "vis_pre_max", "dew_pre_min",
    "dryness", "swing",
    "slot_50", "slot_100", "slot_best",
    "canvas_x_slot", "canvas_any_x_slot",
    "low_drop_after", "clearing_trend",
]

# There is more than one way to get a good sunset here, and a feature set that
# only knows about one of them will keep scoring the others at zero:
#
#   canvas aloft   mid/high cloud overhead, lit from below      (12 Jul, 27 Mar)
#   lit deck       the marine layer itself, lit from underneath (27 Jul)
#   clean air      no cloud at all, colour from path length     (21 Jul)
#
# `canvas` covers only the first. `canvas_any` also counts a low deck as
# something to light, and `dryness` covers the third case, where the sky is
# empty and what matters is how clean the air is.


def _round_hour(hhmm):
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    return h + (1 if m >= 30 else 0)


def load_day(con, day, point_ids):
    """{point_id: {ts: row}} for the day and the one after (for post-sunset hours)."""
    nxt = (datetime.fromisoformat(day) + timedelta(days=1)).strftime("%Y-%m-%d")
    out = {p: {} for p in point_ids}
    q = ("SELECT * FROM hourly WHERE (substr(ts,1,10)=? OR substr(ts,1,10)=?) "
         "AND point_id IN (%s)" % ",".join("?" * len(point_ids)))
    for r in con.execute(q, (day, nxt, *point_ids)):
        out[r["point_id"]][r["ts"]] = r
    return out


def _series(rows, base_dt, offsets, col):
    vals = []
    for k in offsets:
        ts = (base_dt + timedelta(hours=k)).strftime("%Y-%m-%dT%H:%M")
        r = rows.get(ts)
        vals.append(None if r is None or r[col] is None else r[col])
    return vals


def evening_features(con, day, pts=None, evening=None):
    """Feature dict for one date, or None if the archive lacks the hours."""
    pts = pts or store.points(con)
    by_label = {p["label"]: p for p in pts}
    evening = evening or con.execute(
        "SELECT * FROM evenings WHERE date=?", (day,)).fetchone()
    if evening is None:
        return None

    hour = _round_hour(evening["sunset_local"])
    base = datetime.fromisoformat(day).replace(hour=0) + timedelta(hours=hour)
    data = load_day(con, day, [p["id"] for p in pts])

    st = data[by_label["station"]["id"]]
    at = st.get(base.strftime("%Y-%m-%dT%H:%M"))
    if at is None or at["cc_low"] is None:
        return None

    trace = _series(st, base, TRACE, "cc_low")
    if any(v is None for v in trace):
        return None
    pre_rh = [v for v in _series(st, base, PRE, "rh") if v is not None]
    pre_vis = [v for v in _series(st, base, PRE, "vis") if v is not None]
    pre_dew = [v for v in _series(st, base, PRE, "dew") if v is not None]
    if not (pre_rh and pre_vis and pre_dew):
        return None

    swing_vals = [trace[TRACE.index(k)] for k in SWING]
    post = [trace[TRACE.index(k)] for k in (1, 2, 3)]

    # Offshore: use the two fan bearings nearest this evening's sunset azimuth.
    az = evening["sunset_azimuth"]
    fan = [p for p in pts if p["bearing"] is not None]
    slots = {}
    for km in store.FAN_KM:
        at_km = [p for p in fan if p["km"] == km]
        near = sorted(at_km, key=lambda p: abs(p["bearing"] - az))[:2]
        vals = []
        for p in near:
            r = data[p["id"]].get(base.strftime("%Y-%m-%dT%H:%M"))
            if r is not None and r["cc_low"] is not None:
                vals.append(r["cc_low"])
        slots[km] = (sum(vals) / len(vals)) if vals else None
    if any(v is None for v in slots.values()):
        return None

    # "slot" is openness, so invert cloud cover: 100 = wide open horizon.
    slot_50 = 100 - slots[50]
    slot_100 = 100 - slots[100]
    slot_best = max(slot_50, slot_100)

    canvas = min(100.0, at["cc_mid"] + at["cc_high"])
    denom = at["cc_mid"] + at["cc_high"]
    # a low deck overhead is also something to light, provided the slot is open
    canvas_any = max(canvas, float(at["cc_low"]))

    return {
        "cc_low": at["cc_low"],
        "cc_mid": at["cc_mid"],
        "cc_high": at["cc_high"],
        "canvas": canvas,
        "canvas_any": canvas_any,
        "canvas_high_frac": (at["cc_high"] / denom * 100) if denom else 0.0,
        "vis": at["vis"] / 1000,
        "rh": at["rh"],
        "dew": at["dew"],
        "mslp": at["mslp"],
        "rh_pre_min": min(pre_rh),
        "vis_pre_max": max(pre_vis) / 1000,
        "dew_pre_min": min(pre_dew),
        "dryness": 100 - min(pre_rh),
        "swing": max(swing_vals) - min(swing_vals),
        "slot_50": slot_50,
        "slot_100": slot_100,
        "slot_best": slot_best,
        # the mechanism, as one number: light needs a way in AND something to hit
        "canvas_x_slot": canvas * slot_best / 100,
        "canvas_any_x_slot": canvas_any * slot_best / 100,
        "low_drop_after": trace[TRACE.index(0)] - min(post),
        "clearing_trend": trace[0] - trace[TRACE.index(0)],
    }


def all_features(con, dates=None):
    """{date: features} for every date that has enough data."""
    pts = store.points(con)
    evenings = {r["date"]: r for r in con.execute("SELECT * FROM evenings")}
    dates = dates or sorted(evenings)
    out = {}
    for d in dates:
        if d not in evenings:
            continue
        f = evening_features(con, d, pts, evenings[d])
        if f:
            out[d] = f
    return out


if __name__ == "__main__":
    con = store.connect()
    feats = all_features(con)
    print(f"{len(feats)} evenings have a complete feature vector")
    for d in sorted(feats)[:3]:
        print(f"\n{d}")
        for k, v in feats[d].items():
            print(f"   {k:<18} {v:.1f}")
