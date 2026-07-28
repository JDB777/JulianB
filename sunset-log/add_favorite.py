"""Record an evening you liked.

    python add_favorite.py "C:\\path\\to\\photos" 2026-08-14
    python add_favorite.py "C:\\path\\to\\photos" 2026-08-14 --time 20:03
    python add_favorite.py --not-a-keeper 2026-08-15    # explicit negative

Resizes the photographs in, works out when they were taken by measuring the
sun, makes sure that evening's weather is in the archive, and labels the date as
a favorite. Then regenerates the site's data file.

Unlabelled evenings inside the watch window already count as "seen, not a
keeper", so you only need --not-a-keeper for an evening you want to mark
explicitly - typically one you were away for, which you should instead exclude
with --unseen.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ingest  # noqa: E402
import measure_time  # noqa: E402
import solar  # noqa: E402
import store  # noqa: E402

PHOTOS = os.path.join(HERE, "photos")
TOLERANCE_MIN = 6


def resize_in(folder):
    r = subprocess.run([sys.executable, os.path.join(HERE, "resize.py"), folder],
                       capture_output=True, text=True)
    print("      " + r.stdout.strip().replace("\n", "\n      "))
    if r.returncode != 0:
        raise SystemExit("resize.py failed:\n" + r.stderr)


def landed(folder):
    out = []
    for f in sorted(os.listdir(folder)):
        stem, ext = os.path.splitext(f)
        if ext.lower() in {".jpg", ".jpeg", ".heic", ".heif", ".png"}:
            if os.path.exists(os.path.join(PHOTOS, stem + ".jpg")):
                out.append(stem + ".jpg")
    return out


def decide_time(names, on_date, stated):
    """Measure the sun where possible; the measurement beats a remembered time."""
    measured = []
    for n in names:
        el, info = measure_time.measure(os.path.join(PHOTOS, n))
        if el is None:
            print(f"      {n}: {info}")
            continue
        t, _ = measure_time.implied_time(on_date, el)
        print(f"      {n}: sun at {el:+.2f} deg -> {t.strftime('%H:%M')}")
        measured.append(t)

    if not measured:
        if not stated:
            print("      no disk to measure and no --time given; "
                  "recording without a time")
            return None, "no disk to measure, no time given"
        return stated, "stated, no disk available to check"

    measured.sort()
    mid = measured[len(measured) // 2]
    implied = mid.strftime("%H:%M")
    if not stated:
        return implied, "measured from the photographs"

    h, m = (int(x) for x in stated.split(":"))
    diff = abs((mid.replace(hour=h, minute=m) - mid).total_seconds()) / 60
    if diff > TOLERANCE_MIN:
        raise SystemExit(
            f"      STOP: you said {stated}, the photographs say {implied} - "
            f"{diff:.0f} min apart.\n"
            f"      Re-run with the right --time, or drop --time to accept the "
            f"measurement.")
    if diff >= 1:
        return implied, f"measured; stated {stated} was {diff:.0f} min out"
    return implied, "stated and confirmed by measurement"


def ensure_weather(con, day):
    have = set(store.covered_dates(con))
    need = [(date.fromisoformat(day) + timedelta(days=k)).isoformat()
            for k in (-1, 0, 1)]
    if all(d in have for d in need):
        print("      already in the archive")
        return
    print("      fetching from Open-Meteo")
    ingest.backfill(con, need[0], need[-1])
    con.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", help="folder of photographs")
    ap.add_argument("date", help="evening date YYYY-MM-DD")
    ap.add_argument("--time", help="local clock time HH:MM if you know it")
    ap.add_argument("--note", default=None, help="anything worth remembering")
    ap.add_argument("--not-a-keeper", action="store_true",
                    help="mark explicitly as seen but not special")
    ap.add_argument("--unseen", action="store_true",
                    help="you were not there; exclude from the statistics")
    a = ap.parse_args()

    con = store.connect()
    day = date.fromisoformat(a.date).isoformat()

    if a.unseen:
        con.execute("DELETE FROM labels WHERE date=?", (day,))
        store.set_label(con, day, "unseen", note=a.note)
        store.export_labels(con)
        con.commit()
        print(f"{day} marked unseen; it will be left out of the statistics.")
        return

    if a.not_a_keeper:
        store.set_label(con, day, "not_favorite", note=a.note)
        store.export_labels(con)
        con.commit()
        print(f"{day} marked as seen but not a keeper.")
        return

    if not a.folder:
        raise SystemExit("Give me a folder of photographs, or use --not-a-keeper.")

    print(f"[1/4] resizing photographs")
    resize_in(a.folder)
    names = landed(a.folder)
    if not names:
        raise SystemExit("Nothing landed in photos/. Check the folder path.")

    print(f"[2/4] measuring the sun")
    shot, confidence = decide_time(names, date.fromisoformat(day), a.time)

    print(f"[3/4] weather")
    ensure_weather(con, day)
    ingest.ensure_evenings(con, day, day)

    print(f"[4/4] labelling")
    store.set_label(con, day, "favorite", photos=names, shot_time=shot,
                    note=a.note or confidence)
    if not store.get_meta(con, "watch_start"):
        store.set_meta(con, "watch_start", day)
    store.set_meta(con, "watch_end", date.today().isoformat())
    store.export_labels(con)  # the part that cannot be re-fetched
    con.commit()

    ss = solar.sunset(date.fromisoformat(day))
    print(f"      {day} recorded as a favorite: {len(names)} photo(s), "
          f"shot {shot or '?'}, sunset {ss.strftime('%H:%M')}")
    print(f"      {confidence}")

    subprocess.run([sys.executable, os.path.join(HERE, "publish.py")], check=False)
    print("\nNext: python trends.py    (what your favorites have in common)")
    print("      python forecast.py  (whether the next few evenings look worth it)")


if __name__ == "__main__":
    main()
