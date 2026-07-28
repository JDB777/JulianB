"""Should you bother going down to the beach tonight?

    python forecast.py            # next 7 evenings
    python forecast.py --refresh  # pull a fresh forecast first

How it scores
-------------
With only a handful of labelled favorites, fitting a model would be fitting
noise. So the score is the mechanism stated plainly - light needs a way in and
something to hit:

    canvas      mid + high cloud overhead, capped at 100
    slot        how open the western horizon is, 50-100 km out along the
                evening's actual sunset bearing (100 = wide open)
    score       canvas * slot / 100

An evening only scores high if BOTH are present. Overcast with no gap scores
zero. A clear empty sky scores zero. That asymmetry is the whole point, and it
is why a single "cloudiness" number has never worked here.

The raw score means nothing on its own, so it is reported as a percentile
against evenings from the same time of year across the whole archive. "Top 5%
for early August" is a statement you can act on; "score 61" is not.

Calibration is shown, not asserted: every run prints where your existing
favorites landed on this same scale, so you can see for yourself whether it is
tracking your taste or flattering itself.
"""

import os
import subprocess
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import features as F  # noqa: E402
import store  # noqa: E402

SEASON_HALF_WIDTH = 21  # days either side of the same calendar date, any year

# Chosen by calibration against the labelled favorites, not by argument. On the
# six evenings so far, visibility at the sunset hour puts four of them in the top
# 15% for their season and five in the top 30% - better than canvas x slot (two
# and three) and better than the old swing statistic, which has a strong median
# but sits at the 9th percentile for 20 February and is therefore blind to a mode
# it never saw. Change it with:
#     python -c "import store;c=store.connect();
#                store.set_meta(c,'score_feature','dryness');c.commit()"
DEFAULT_SCORE = "vis"


def day_of_year(d):
    return date.fromisoformat(d).timetuple().tm_yday


def seasonal_baseline(feats, target_date, key):
    """Values for this feature from the same part of the year, across all years."""
    t = day_of_year(target_date)
    out = []
    for d, f in feats.items():
        delta = abs(day_of_year(d) - t)
        delta = min(delta, 365 - delta)
        if delta <= SEASON_HALF_WIDTH:
            out.append(f[key])
    return out


def percentile_of(values, x):
    if not values:
        return None
    below = sum(1 for v in values if v < x)
    equal = sum(1 for v in values if v == x)
    return (below + 0.5 * equal) / len(values)


def verdict(pct, beyond=False):
    if pct is None:
        return "no baseline"
    if beyond:
        # The forecast is outside everything the archive has seen for this time
        # of year. That is either a genuinely unusual evening or the model being
        # optimistic, and a percentile cannot tell the two apart - so say so
        # rather than dressing extrapolation up as a 100th percentile.
        return "beyond baseline - unverified"
    if pct >= 0.95:
        return "exceptional - go"
    if pct >= 0.85:
        return "promising"
    if pct >= 0.6:
        return "above average"
    if pct >= 0.35:
        return "ordinary"
    return "unlikely"


def main():
    if "--refresh" in sys.argv:
        print("Refreshing the forecast...\n")
        subprocess.run([sys.executable, os.path.join(HERE, "ingest.py"), "forecast"],
                       check=True)
        print()

    con = store.connect()
    key = store.get_meta(con, "score_feature", DEFAULT_SCORE)
    feats = F.all_features(con)
    if not feats:
        raise SystemExit("Archive is empty. Run: python ingest.py backfill <from> <to>")

    today = date.today()
    upcoming = [(today + timedelta(days=i)).isoformat() for i in range(0, 8)]
    have = [d for d in upcoming if d in feats]
    if not have:
        raise SystemExit("No forecast data. Run: python forecast.py --refresh")

    hist = {d: f for d, f in feats.items() if d < today.isoformat()}
    print(f"Scoring on '{key}'. Baseline is {len(hist):,} past evenings, "
          f"matched to within {SEASON_HALF_WIDTH} days of the same time of year.\n")

    print(f"{'date':<12}{'sunset':>8}{'vis km':>8}{'dry':>6}{'canvas':>8}"
          f"{'slot':>6}{'pctile':>9}   verdict")
    print("-" * 78)
    top = 0
    for d in have:
        f = feats[d]
        ss = con.execute("SELECT sunset_local FROM evenings WHERE date=?",
                         (d,)).fetchone()
        base = seasonal_baseline(hist, d, key)
        pct = percentile_of(base, f[key])
        beyond = bool(base) and f[key] > max(base)
        if pct is not None and pct >= 0.95:
            top += 1
        label = "  <- tonight" if d == today.isoformat() else ""
        print(f"{d:<12}{ss['sunset_local'] if ss else '--':>8}"
              f"{f['vis']:>8.1f}{f['dryness']:>6.0f}{f['canvas_any']:>8.0f}"
              f"{f['slot_best']:>6.0f}"
              f"{(pct * 100 if pct is not None else 0):>8.0f}%   "
              f"{verdict(pct, beyond)}{label}")

    if top >= max(3, len(have) // 2):
        print(f"\n  {top} of {len(have)} evenings score in the top 5%. A forecast that")
        print("  says 'go' almost every night is not telling you anything. This")
        print("  usually means the model is predicting a value near or past the edge")
        print("  of what the archive has seen for this time of year, so the baseline")
        print("  cannot rank it. Trust the nearest day or two and re-run later.")
    print("\nvis = visibility at the sunset hour, the column being scored.")
    print("dry, canvas and slot are shown for context, not scored: a high score")
    print("with no canvas and no slot means clean air and an empty sky, which")
    print("gives colour from path length alone rather than anything lit.")

    # Calibration: where did the known favorites land on this same scale?
    favs = [d for d in store.favorites(con) if d in feats]
    if favs:
        print(f"\nCalibration - your {len(favs)} favorites on this scale:")
        pcts = []
        for d in sorted(favs):
            base = seasonal_baseline(hist, d, key)
            p = percentile_of(base, feats[d][key])
            pcts.append(p)
            print(f"  {d}   score {feats[d][key]:>6.1f}   "
                  f"{p * 100:>3.0f}th percentile for that time of year")
        good = sum(1 for p in pcts if p and p >= 0.85)
        print(f"\n  {good} of {len(pcts)} landed in the top 15% for their season.")
        if good <= len(pcts) / 2:
            print("  That is poor calibration: this score is not yet capturing what")
            print("  you actually respond to. Treat the column above with suspicion")
            print("  and keep sending favorites - trends.py will find a better")
            print("  feature once there are enough of them.")
        else:
            print("  Reasonable so far, on a small number of evenings.")

    print("\nForecast cloud beyond about three days is not worth much. Re-run")
    print("closer to the evening you care about.")


if __name__ == "__main__":
    main()
