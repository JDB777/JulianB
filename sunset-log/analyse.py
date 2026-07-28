"""Which measurements separate the evenings worth photographing from the rest?

Every photographed evening is compared only against the evenings within +/-10
days of it. That controls for season, which matters here: a February swing of 9
and a July swing of 9 mean completely different things, and pooling them is how
the original swing statistic came to look stronger than it was.

For each variable, each photographed evening gets a percentile rank inside its
own window (1.0 = highest in the window). Under the null hypothesis that the
variable has nothing to do with whether you took a photograph, those percentiles
are uniform, so their mean has a known distribution and the deviation is
testable. No hand-waving about "looked enriched".

    python analyse.py            # uses cached windows where possible
    python analyse.py --refresh  # re-pull every window from Open-Meteo

The multiple-comparisons warning at the bottom is not decoration. With a handful
of evenings and a dozen variables, something always looks significant.
"""

import json
import math
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import weather  # noqa: E402

DATA = os.path.join(HERE, "data", "evenings.json")
CACHE = os.path.join(HERE, "data", "window_cache.json")

# name -> (label, does a HIGH value plausibly mean a better sunset?)
VARIABLES = [
    ("cc_low", "low cloud"),
    ("cc_mid", "mid cloud"),
    ("cc_high", "high cloud"),
    ("visibility_km", "visibility"),
    ("rh", "humidity"),
    ("dew_c", "dew point"),
    ("mslp", "pressure"),
    ("rh_pre_min", "humidity, pre-sunset min"),
    ("vis_pre_max_km", "visibility, pre-sunset max"),
    ("dew_pre_min_c", "dew point, pre-sunset min"),
    ("swing", "low-cloud swing"),
]


def load_windows(dates, refresh=False):
    cache = {}
    if os.path.exists(CACHE) and not refresh:
        cache = json.load(open(CACHE, encoding="utf-8"))
    for d in dates:
        if d in cache:
            continue
        o = date.fromisoformat(d).toordinal()
        a = date.fromordinal(o - 10).isoformat()
        b = date.fromordinal(o + 10).isoformat()
        stats, _ = weather.window(weather.LAT, weather.LON, a, b, d)
        cache[d] = stats
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), indent=1)
    return cache


def percentile_rank(values, target):
    """Fraction of the window at or below the target. 1.0 = highest."""
    below = sum(1 for v in values if v < target)
    equal = sum(1 for v in values if v == target)
    return (below + 0.5 * equal) / len(values)


def main():
    refresh = "--refresh" in sys.argv
    doc = json.load(open(DATA, encoding="utf-8"))
    shot_dates = [e["date"] for e in doc["evenings"]]
    print(f"{len(shot_dates)} photographed evenings: {', '.join(shot_dates)}\n")

    windows = load_windows(shot_dates, refresh)

    print(f"{'variable':<30}{'mean pct':>10}{'z':>8}{'per-evening percentiles':>30}")
    print("-" * 78)
    results = []
    for key, label in VARIABLES:
        pcts = []
        for d in shot_dates:
            win = windows[d]
            if d not in win:
                continue
            vals = [s[key] for s in win.values() if s.get(key) is not None]
            if len(vals) < 5:
                continue
            pcts.append(percentile_rank(vals, win[d][key]))
        if not pcts:
            continue
        n = len(pcts)
        mean = sum(pcts) / n
        # under the null each percentile is uniform(0,1): sd of the mean is 1/sqrt(12n)
        z = (mean - 0.5) / (1 / math.sqrt(12 * n))
        results.append((abs(z), z, mean, label, pcts))
        cells = " ".join(f"{p:.2f}" for p in pcts)
        print(f"{label:<30}{mean:>10.2f}{z:>+8.2f}   {cells}")

    results.sort(reverse=True)
    print("\nStrongest apparent separations:")
    for _, z, mean, label, pcts in results[:3]:
        direction = "high" if z > 0 else "low"
        print(f"  {label}: consistently {direction} "
              f"(mean percentile {mean:.2f}, z {z:+.2f})")

    k, n = len(results), len(shot_dates)
    # two-sided Bonferroni-corrected 5% threshold across k variables
    from statistics import NormalDist
    crit = NormalDist().inv_cdf(1 - 0.05 / (2 * k))
    print(f"\nWith n={n} evenings and k={k} variables, the Bonferroni-corrected")
    print(f"threshold for |z| is {crit:.2f}. Anything below that is not evidence yet,")
    print(f"however suggestive the ordering looks.")

    # Evenings closer together than the window width share most of their
    # comparison set, so their percentiles are not independent draws.
    ords = sorted(date.fromisoformat(d).toordinal() for d in shot_dates)
    clustered = sum(1 for a, b in zip(ords, ords[1:]) if b - a <= 20)
    if clustered:
        print(f"Caution: {clustered} pair(s) of evenings sit within 20 days of each")
        print("other and therefore share most of their comparison window. Their")
        print("percentiles are correlated, so the true threshold is stricter than")
        print("the one above and z is flattered. Spread evenings out where you can.")
    survivors = [r for r in results if r[0] >= crit]
    if survivors:
        print("Clears the bar: " + ", ".join(r[3] for r in survivors))
    else:
        print("Nothing clears the bar. More evenings are the only fix.")
        need = math.ceil((crit / max(1e-9, max(r[0] for r in results) / math.sqrt(n))) ** 2)
        print(f"At the current strongest effect size that would take roughly "
              f"{need} evenings.")


if __name__ == "__main__":
    main()
