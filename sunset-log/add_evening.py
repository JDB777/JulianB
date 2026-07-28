"""Add an evening to the log from a folder of new photographs.

    python add_evening.py "C:\\path\\to\\new photos" 2026-08-14
    python add_evening.py "...\\new photos" 2026-08-14 --time 20:03

What it does, in order:

  1. resizes the photographs into photos/ at web size
  2. measures the sun in each frame and derives the time the photograph implies
  3. cross-checks that against --time if you gave one, and stops if they disagree
  4. computes sunset, offset, apparent elevation, sunset azimuth, offshore point
  5. pulls a +/-10 day weather window and computes the trace, swing and swing rank
  6. writes a draft entry into data/evenings.json and validates the file

The prose fields are left as TODO markers. They are written by a person looking
at the photograph, not generated - the project has a documented history of
confident cloud reads that the data later contradicted.

Nothing is deployed. Review the draft, write the prose, then:

    python -c "import json;json.load(open(r'data/evenings.json'));print('ok')"
    vercel deploy --prod --cwd <this folder>
    git -C <repo> add -A && git -C <repo> commit && git -C <repo> push origin master
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import measure_time  # noqa: E402
import solar  # noqa: E402
import weather  # noqa: E402

DATA = os.path.join(HERE, "data", "evenings.json")
PHOTOS = os.path.join(HERE, "photos")
TIME_TOLERANCE_MIN = 6


def resize_into_repo(folder):
    print(f"[1/6] resizing from {folder}")
    r = subprocess.run([sys.executable, os.path.join(HERE, "resize.py"), folder],
                       capture_output=True, text=True)
    print("      " + r.stdout.strip().replace("\n", "\n      "))
    if r.returncode != 0:
        raise SystemExit("resize.py failed:\n" + r.stderr)


def new_photo_names(folder):
    """Filenames as they now exist in photos/, for the files in this folder."""
    out = []
    for f in sorted(os.listdir(folder)):
        stem, ext = os.path.splitext(f)
        if ext.lower() in {".jpg", ".jpeg", ".heic", ".heif", ".png"}:
            if os.path.exists(os.path.join(PHOTOS, stem + ".jpg")):
                out.append(stem + ".jpg")
    return out


def measure_photos(names, on_date):
    print("[2/6] measuring the sun in each frame")
    measured = []
    for n in names:
        el, info = measure_time.measure(os.path.join(PHOTOS, n))
        if el is None:
            print(f"      {n}: {info}")
            continue
        t, resid = measure_time.implied_time(on_date, el)
        print(f"      {n}: elevation {el:+.2f} deg -> implies {t.strftime('%H:%M')}"
              f"  ({info})")
        measured.append((n, el, t))
    return measured


def reconcile(measured, stated, on_date):
    """Decide the shot time. Refuses to guess silently when things disagree.

    Where a disk was measured, the measurement wins. It is a direct observation
    of where the sun actually was, whereas a stated time is a recollection - and
    the recorded times on this project have run several minutes late more often
    than not. Taking the stated time while recording a computed elevation that
    the photograph contradicts is how the original dataset ended up with entries
    whose elevation and clock time disagree by four minutes of solar motion.
    """
    print("[3/6] reconciling the time")
    if not measured:
        if not stated:
            raise SystemExit(
                "      No disk could be measured and no --time was given.\n"
                "      An afterglow frame carries no sun to measure, so the time has\n"
                "      to come from you. Re-run with --time HH:MM.")
        print(f"      no disk to measure; taking your stated {stated} on trust")
        return stated, "stated, no disk available to check"

    times = sorted(t for _, _, t in measured)
    mid = times[len(times) // 2]
    implied = mid.strftime("%H:%M")
    spread = (times[-1] - times[0]).total_seconds() / 60
    print(f"      photographs imply {implied}"
          + (f" (spread {spread:.0f} min across {len(times)} frames)" if len(times) > 1 else ""))

    if not stated:
        print("      no --time given, using the measured time")
        return implied, "measured from the photographs"

    h, m = (int(x) for x in stated.split(":"))
    stated_dt = mid.replace(hour=h, minute=m)
    diff = abs((stated_dt - mid).total_seconds()) / 60
    if diff > TIME_TOLERANCE_MIN:
        raise SystemExit(
            f"      STOP: you said {stated}, the photographs say {implied}"
            f" - {diff:.0f} minutes apart.\n"
            f"      That is past the {TIME_TOLERANCE_MIN} minute tolerance, and this is\n"
            f"      exactly the check that caught the Mar 18 error. Decide which is\n"
            f"      right and re-run with the correct --time, or drop --time to accept\n"
            f"      the measurement.")
    if diff >= 1:
        print(f"      your {stated} is {diff:.0f} min from the measured {implied}; "
              f"using the measurement, which is the direct observation")
        return implied, f"measured from the photographs; stated {stated}, {diff:.0f} min out"
    print(f"      your {stated} agrees with the measurement")
    return implied, "stated and confirmed by measurement"


def gather_weather(on_date):
    print("[5/6] pulling weather (+/-10 day window)")
    d0 = date.fromordinal(on_date.toordinal() - 10).isoformat()
    d1 = date.fromordinal(on_date.toordinal() + 10).isoformat()
    stats, coords = weather.window(weather.LAT, weather.LON, d0, d1, "station")
    key = on_date.isoformat()
    if key not in stats:
        print(f"      no usable data for {key} yet - the endpoint may not cover it.")
        return None
    rank, n = weather.rank_within(stats, key)
    w = {k: stats[key][k] for k in
         ["cc_low", "cc_mid", "cc_high", "visibility_km", "rh", "dew_c", "mslp",
          "rh_pre_min", "vis_pre_max_km", "dew_pre_min_c", "low_trace", "swing"]}
    w["swing_rank"] = rank
    print(f"      low {w['cc_low']}%  mid {w['cc_mid']}%  high {w['cc_high']}%  "
          f"vis {w['visibility_km']} km  swing {w['swing']} (rank {rank} of {n})")
    return w


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="folder holding the new photographs")
    ap.add_argument("date", help="evening date, YYYY-MM-DD")
    ap.add_argument("--time", help="local clock time HH:MM, if you know it")
    ap.add_argument("--type", default="TODO: short label",
                    help="short label, e.g. 'full canvas' or 'clean disk'")
    a = ap.parse_args()

    on_date = date.fromisoformat(a.date)
    doc = json.load(open(DATA, encoding="utf-8"))
    if any(e["date"] == a.date for e in doc["evenings"]):
        raise SystemExit(f"{a.date} is already in the log. Edit it by hand instead.")

    resize_into_repo(a.folder)
    names = new_photo_names(a.folder)
    if not names:
        raise SystemExit("No photographs landed in photos/. Check the folder path.")

    measured = measure_photos(names, on_date)
    shot, confidence = reconcile(measured, a.time, on_date)

    print("[4/6] solar geometry")
    geo = solar.describe(on_date, shot)
    for k, v in geo.items():
        print(f"      {k:<20} {v}")

    w = gather_weather(on_date)

    print("[6/6] writing the draft entry")
    import math
    b = math.radians(geo["sunset_azimuth"])
    dlat = 50 * math.cos(b) / 111.32
    mid = solar.LAT + dlat / 2
    dlon = 50 * math.sin(b) / (111.32 * math.cos(math.radians(mid)))

    entry = {
        "date": a.date,
        "photos": names,
        **geo,
        "offshore_50km": [round(solar.LAT + dlat, 3), round(solar.LON + dlon, 3)],
        "timestamp_confidence": confidence,
        "weather": w,
        "offshore": None,
        "type": a.type,
        "read": "TODO: what the photograph shows.",
        "revision": None,
        "note": "TODO: what the day around it was doing.",
    }
    doc["evenings"].append(entry)
    json.dump(doc, open(DATA, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    json.load(open(DATA, encoding="utf-8"))  # validate
    print(f"      appended {a.date} to data/evenings.json and it still parses.")
    print("\nStill TODO by hand: type, read, note (and revision if the data")
    print("contradicts the read). Then validate, deploy and push.")


if __name__ == "__main__":
    main()
