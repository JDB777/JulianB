"""Measure when a photograph was taken, from the photograph itself.

There is no EXIF in these files, so a stated time cannot be checked against
metadata. It can be checked against the sun. The sun's angular diameter is a
fixed 0.5333 deg, so measuring the disk in pixels and its height above the
horizon in pixels gives apparent elevation independently of focal length:

    apparent_elevation_deg = (horizon_y - sun_centre_y) / disk_diameter_px * 0.5333

Feed that back through solar.py and you get the time the frame implies.

Usage:
    python measure_time.py --validate            # known frames, must agree
    python measure_time.py <image> 2026-08-14    # measure one photograph

Only works when the disk is visible. Afterglow frames have no disk to measure
and will be reported as such rather than guessed at.
"""

import sys
from datetime import date, datetime, timedelta

import numpy as np
from PIL import Image

import solar

SUN_DIAMETER_DEG = 0.5333
PHOTOS = __file__.rsplit("\\", 1)[0] + "\\photos\\"


def find_disk(rgb):
    """Locate the solar disk. Returns (centre_y, centre_x, diameter_px) or None."""
    r, g, b = rgb[:, :, 0].astype(int), rgb[:, :, 1].astype(int), rgb[:, :, 2].astype(int)

    # A blown-out white disk, and a deep orange one low to the horizon.
    masks = {
        "white": rgb.min(axis=2) > 235,
        "orange": (r > 248) & (g > 55) & (g < 205) & (b < g),
    }

    best = None
    for name, mask in masks.items():
        if mask.sum() < 40:
            continue
        ys, xs = np.nonzero(mask)
        # Keep the largest connected blob by a cheap proximity filter: the disk is
        # compact, so clip to the densest region rather than glitter on the water.
        cy, cx = np.median(ys), np.median(xs)
        keep = (np.abs(ys - cy) < 0.12 * rgb.shape[0]) & (np.abs(xs - cx) < 0.12 * rgb.shape[1])
        if keep.sum() < 40:
            continue
        ys, xs = ys[keep], xs[keep]

        # The widest row of a circle passes through its centre. Using that row
        # rather than the centroid keeps both the centre and the diameter honest
        # when cloud clips the top of the disk, which is common in these frames.
        # Horizontal width is also the right measure because refraction flattens
        # the disk vertically near the horizon, so height would understate it.
        rows = np.unique(ys)
        widths = np.array([np.ptp(xs[ys == row]) + 1 for row in rows])
        diameter = float(widths.max())
        centre_y = float(rows[int(np.argmax(widths))])
        centre_x = float(np.mean(xs[ys == rows[int(np.argmax(widths))]]))
        cand = (centre_y, centre_x, diameter, name, int(keep.sum()))
        if best is None or cand[4] > best[4]:
            best = cand
    return best


def find_horizon(rgb, sun_x, sun_y):
    """First row below the disk where smooth sky gives way to textured water.

    Brightness gradient does NOT work here. On a hazy evening the sea horizon is
    a soft ramp spread over ~20 rows, while the surf/beach edge lower down is a
    genuinely sharp step - so "sharpest bright-to-dark step" reliably picks the
    foreground, and so does "darkest row". Texture separates them cleanly:
    across columns, sky varies by ~2-3 grey levels, open water by 5-30, and the
    beach drops back to ~4. The horizon is where that variance first rises.
    """
    h, w = rgb.shape[:2]
    lum = rgb.astype(float).mean(axis=2)

    # Sample columns well clear of the sun and the vertical glitter beneath it.
    band = max(1, int(0.12 * w))
    cols = np.r_[0:max(1, int(sun_x) - band), min(w - 1, int(sun_x) + band):w]
    if cols.size < 20:
        cols = np.arange(w)
    std = lum[:, cols].std(axis=1)
    # smooth lightly so a single noisy row cannot trigger the crossing
    k = 5
    std = np.convolve(std, np.ones(k) / k, mode="same")

    start = int(sun_y) + 2
    end = int(h * 0.95)
    if end - start < 10:
        return None

    # Baseline from the sky just above the search start, which is smooth.
    sky_top = max(0, int(sun_y) - 120)
    baseline = float(np.median(std[sky_top:int(sun_y) - 2])) if sun_y > 20 else float(std[:20].mean())
    threshold = max(baseline * 1.8, baseline + 1.5)

    above = np.nonzero(std[start:end] > threshold)[0]
    if above.size == 0:
        return None
    return start + int(above[0])


def measure(path):
    """Apparent elevation of the sun in one photograph, in degrees."""
    with Image.open(path) as im:
        rgb = np.array(im.convert("RGB"))
    disk = find_disk(rgb)
    if disk is None:
        return None, "no solar disk found (afterglow frame, or the sun is hidden)"
    cy, cx, diameter, kind, npix = disk
    if diameter < 4:
        return None, f"disk too small to measure ({diameter:.1f} px)"
    hz = find_horizon(rgb, cx, cy)
    if hz is None:
        return None, "no horizon step found below the disk"
    el = (hz - cy) / diameter * SUN_DIAMETER_DEG
    return el, (f"{kind} disk, {diameter:.1f} px across at row {cy:.0f}, "
                f"horizon row {hz}, {npix} px")


def implied_time(on_date, elevation_deg, window_min=180):
    """The local time whose computed apparent elevation matches the measurement.

    Searched on the descending limb only, so the answer is the evening one.
    """
    ss = solar.sunset(on_date)
    best, best_err = None, 1e9
    for delta in range(-window_min, window_min + 1):
        t = ss + timedelta(minutes=delta)
        _, app, _ = solar.position(t)
        err = abs(app - elevation_deg)
        if err < best_err:
            best, best_err = t, err
    return best, best_err


# Frames the handoff names as trustworthy, with the elevation they should give.
KNOWN = [("IMG_4769.jpg", 0.53), ("IMG_4770.jpg", 0.53)]


def validate(tol=0.1):
    print("Horizon detection must reproduce these before it is trusted elsewhere.\n")
    ok = True
    for name, expected in KNOWN:
        el, info = measure(PHOTOS + name)
        if el is None:
            print(f"  {name:<16} FAILED - {info}")
            ok = False
            continue
        good = abs(el - expected) <= tol
        ok &= good
        print(f"  {name:<16} expected {expected:+.2f}  measured {el:+.2f}  "
              f"{'ok' if good else 'OFF by %.2f' % abs(el - expected)}")
        print(f"  {'':<16} {info}")
    print("\n" + ("Validated." if ok else
                  "NOT validated - do not trust this on a new photograph."))
    return ok


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--validate":
        raise SystemExit(0 if validate() else 1)
    if len(sys.argv) == 3:
        el, info = measure(sys.argv[1])
        if el is None:
            print("Could not measure:", info)
            raise SystemExit(1)
        d = date.fromisoformat(sys.argv[2])
        t, err = implied_time(d, el)
        print(f"  apparent elevation  {el:+.2f} deg   ({info})")
        print(f"  implied shot time   {t.strftime('%H:%M')}  "
              f"(sunset {solar.sunset(d).strftime('%H:%M')}, "
              f"residual {err:.2f} deg)")
    else:
        print(__doc__)
