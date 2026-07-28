"""What separates the evenings you keep from the evenings you don't?

    python trends.py

Method
------
Every favorite is scored against the evenings within +/-15 days of it, not
against the whole archive. Season is the biggest confounder here - a low-cloud
swing of 9 means something completely different in March than in July - and
comparing locally removes it by construction.

The statistic for a feature is the mean local percentile of the favorites.
Under the null hypothesis that the feature has nothing to do with your choice,
that number sits at 0.5.

Significance comes from a circular-shift test rather than a formula. The whole
set of favorite dates is slid through the archive by a random offset, keeping
the spacing between them intact, and the statistic is recomputed a few thousand
times. Preserving the spacing matters: your favorites cluster, clustered dates
share comparison windows, and a test that assumed independence would report
confidence it has not earned.

The Benjamini-Hochberg step at the end controls for the fact that we are asking
this question of nineteen features at once.
"""

import os
import random
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import features as F  # noqa: E402
import store  # noqa: E402

WINDOW_DAYS = 15
N_SHUFFLE = 4000
random.seed(20260727)


def local_percentile(feats, all_dates, day, key):
    """Percentile of `day` for `key` among evenings within +/-WINDOW_DAYS."""
    o = date.fromisoformat(day).toordinal()
    lo = date.fromordinal(o - WINDOW_DAYS).isoformat()
    hi = date.fromordinal(o + WINDOW_DAYS).isoformat()
    vals = [feats[d][key] for d in all_dates if lo <= d <= hi and d in feats]
    if len(vals) < 8 or day not in feats:
        return None
    t = feats[day][key]
    below = sum(1 for v in vals if v < t)
    equal = sum(1 for v in vals if v == t)
    return (below + 0.5 * equal) / len(vals)


def statistic(feats, all_dates, dates, key):
    ps = [local_percentile(feats, all_dates, d, key) for d in dates]
    ps = [p for p in ps if p is not None]
    return (sum(ps) / len(ps), len(ps)) if ps else (None, 0)


def circular_shifts(all_dates, dates, n):
    """Slide the favorite pattern through the archive, keeping its spacing."""
    span = [date.fromisoformat(d).toordinal() for d in all_dates]
    lo, hi = min(span), max(span)
    base = [date.fromisoformat(d).toordinal() for d in dates]
    origin = base[0]
    offsets = [b - origin for b in base]
    width = hi - lo + 1
    out = []
    for _ in range(n):
        start = random.randrange(lo, hi + 1)
        shifted = [date.fromordinal(lo + ((start - lo + o) % width)).isoformat()
                   for o in offsets]
        out.append(shifted)
    return out


def benjamini_hochberg(pvals, alpha=0.05):
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m = len(pvals)
    keep = set()
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= alpha * rank / m:
            keep = set(order[:rank])
    return keep


def main():
    con = store.connect()
    feats = F.all_features(con)
    all_dates = sorted(feats)
    if not all_dates:
        raise SystemExit("Archive is empty. Run: python ingest.py backfill <from> <to>")

    favs = [d for d in store.favorites(con) if d in feats]
    start, end = store.watch_window(con)
    print(f"archive      {all_dates[0]} .. {all_dates[-1]}  "
          f"({len(all_dates):,} evenings with complete features)")
    print(f"favorites    {len(favs)}  {', '.join(favs) if len(favs) < 10 else ''}")
    if start:
        print(f"watch window {start} .. {end}  "
              "(unlabelled evenings in this span count as 'seen, not a keeper')")
    if not favs:
        raise SystemExit("\nNo favorites labelled yet. Add one with add_favorite.py.")
    if len(favs) < 3:
        print("\nToo few favorites to say anything. Keep sending them.")

    print(f"\nSliding the favorite pattern through the archive {N_SHUFFLE:,} times "
          f"to build the null.\n")
    nulls = circular_shifts(all_dates, favs, N_SHUFFLE)

    rows = []
    for key in F.FEATURE_NAMES:
        obs, n = statistic(feats, all_dates, favs, key)
        if obs is None:
            continue
        null = []
        for shifted in nulls:
            s, _ = statistic(feats, all_dates, shifted, key)
            if s is not None:
                null.append(s)
        if not null:
            continue
        # two-sided: how often is the null at least as extreme as observed?
        extreme = sum(1 for v in null if abs(v - 0.5) >= abs(obs - 0.5))
        p = (extreme + 1) / (len(null) + 1)
        rows.append((key, obs, p, n))

    rows.sort(key=lambda r: r[2])
    sig = benjamini_hochberg([r[2] for r in rows])

    print(f"{'feature':<20}{'mean pct':>10}{'direction':>12}{'p':>9}   verdict")
    print("-" * 72)
    for i, (key, obs, p, n) in enumerate(rows):
        direction = "higher" if obs > 0.5 else "lower"
        mark = "SURVIVES" if i in sig else ""
        print(f"{key:<20}{obs:>10.2f}{direction:>12}{p:>9.4f}   {mark}")

    print()
    if sig:
        names = [rows[i][0] for i in sorted(sig)]
        print("Clears Benjamini-Hochberg at 5%: " + ", ".join(names))
        print("That is a real association in this archive. It is not yet a")
        print("demonstration that it causes a good sunset, and it has not been")
        print("tested on evenings collected after the pattern was noticed.")
    else:
        best = rows[0]
        print(f"Nothing clears the correction. Strongest candidate is "
              f"'{best[0]}' at p={best[2]:.3f}.")
        print(f"With {len(favs)} favorites that is expected even if the effect is")
        print("real. The fix is more favorites, not more features.")

    print(f"\nEvery number above uses only data already in the archive - "
          f"no network calls.")


if __name__ == "__main__":
    main()
