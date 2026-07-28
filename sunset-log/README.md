# Sunset log

An observation log of the sunsets worth photographing from Ocean Beach, San Francisco,
set against what the atmosphere was measurably doing at the time.

Live at **https://sunset-log-henna.vercel.app**

Station: 37.7594 N, 122.5107 W, looking west over the Pacific.

---

## Adding an evening

Put the new photographs in a folder and run one command:

```powershell
python add_evening.py "C:\path\to\new photos" 2026-08-14
```

If you know roughly when you took them, say so and it will check you:

```powershell
python add_evening.py "C:\path\to\new photos" 2026-08-14 --time 20:03
```

That single command resizes the photographs into `photos/`, measures the sun in each
frame to work out when it was actually taken, computes the solar geometry, pulls a
±10 day weather window from Open-Meteo, computes the low-cloud trace and swing with its
rank, and appends a draft entry to `data/evenings.json`.

It leaves three fields as `TODO` — `type`, `read` and `note` — because those are prose
written by a person looking at the photograph. It deploys nothing.

Then fill in the prose, and publish:

```powershell
python -c "import json;json.load(open(r'data\evenings.json'));print('ok')"
vercel deploy --prod --cwd C:\Users\Julia\JulianB\sunset-log
git -C C:\Users\Julia\JulianB add -A
git -C C:\Users\Julia\JulianB commit -m "Sunset log: add 2026-08-14"
git -C C:\Users\Julia\JulianB push origin master
```

**Pushing to GitHub does not deploy.** There is no git integration on this Vercel
project. Always do both or the live site and the repo drift apart.

---

## Why it measures the time from the photograph

The image files carry **no EXIF at all** — no `DateTimeOriginal`, no GPS, no camera
model. A stated time therefore cannot be checked against metadata. It can be checked
against the sun.

The sun's angular diameter is a fixed 0.5333°, so measuring the disk in pixels and its
height above the horizon in pixels gives the apparent elevation regardless of focal
length or crop:

```
apparent_elevation_deg = (horizon_y − sun_centre_y) / disk_diameter_px × 0.5333
```

Feed that through `solar.py` and you get the time the frame implies. If that disagrees
with what you typed by more than six minutes, `add_evening.py` stops and makes you
decide rather than quietly picking one. This check previously caught a stated time that
was 43 minutes wrong.

Two details that are easy to get wrong, both learned the hard way:

- **The horizon is found by texture, not brightness.** On a hazy evening the sea horizon
  is a soft ramp spread over ~20 rows while the surf line lower down is a genuinely sharp
  step, so "sharpest bright-to-dark step" reliably finds the beach instead. Across
  columns, sky varies by about 2–3 grey levels, open water by 5–30. The horizon is where
  that variance first rises.
- **The disk is measured at its widest row, not its centroid.** Cloud often clips the top
  of the disk, which drags a centroid downward; and refraction flattens the disk
  vertically near the horizon, so its height understates the diameter while its width
  does not.

Afterglow frames have no disk. `add_evening.py` will say so and ask you for `--time`.

---

## Finding out what actually makes a sunset compelling

```powershell
python analyse.py
```

Each photographed evening is compared **only against the evenings within ±10 days of
it**, which controls for season. Every variable gets a percentile rank inside that local
window; under the null hypothesis that a variable has nothing to do with whether you
took a photograph, those percentiles are uniform, so the deviation is testable rather
than a matter of opinion.

It prints a Bonferroni-corrected threshold and tells you plainly whether anything clears
it. As of six evenings, **nothing does** — the strongest candidate would need roughly 18
evenings to become evidence. It also warns when evenings sit close enough together to
share a comparison window, because their percentiles are then correlated and the
threshold is flattered.

This is the point of the project. It is easy to find a statistic that fits six
photographs; the log exists to find one that survives the seventh.

---

## What is established, and what isn't

**Holds up.** Every evening on record had a clear slot at the western horizon — six
evenings, three seasons, no exceptions. It is the only claim that has never needed
revising.

**Falsified.** The low-cloud "swing" statistic ranked the three July evenings 1st, 2nd
and 3rd of twenty-one and looked compelling. Tested out of sample on the three non-July
evenings it scores 0, 9 and 4 — ranks 20th, 5th and 11th, an average of 12th against a
random expectation of 11th. February 20 is the clearest refutation: six evenings in its
window swung 70 points or more and the one that was photographed swung zero. The
statistic describes July and does not generalise.

**Open.** Offshore sampling 25–150 km along the sunset bearing is mixed. For the July 27
/ July 17 pair it works decisively — the station cannot tell them apart at 99% and 100%
low cloud, while offshore they separate 24 against 99. For the July 21 / July 13 pair it
fails: July 13 was never photographed yet had the second-clearest offshore sky of the
month. Offshore values are computed but deliberately not yet written into the dataset.

**The trap to keep in mind.** In a frame exposed for the horizon band, a uniformly lit
cloud deck and clear sky are not visually distinguishable — both render as a smooth
gradient. Cloud read from a photograph is reliable when the cloud has visible *texture*
and unreliable otherwise. Two early reads were wrong in opposite directions for exactly
this reason. Check a photographic cloud read against the retrieved data before writing
it into `read`, and record the correction in `revision` rather than quietly presenting
the corrected version.

---

## Files

| | |
|---|---|
| `index.html` | the entire site — HTML, CSS, JS. Fetches `data/evenings.json`. |
| `data/evenings.json` | the dataset. The file you edit routinely. |
| `photos/` | JPEGs at 1600 px long edge. |
| `add_evening.py` | the one command that ingests a new evening. |
| `measure_time.py` | measures the sun in a frame; `--validate` must pass first. |
| `solar.py` | NOAA solar position — sunset, elevation, azimuth. `--validate`. |
| `weather.py` | Open-Meteo pulls and the trace/swing definitions. |
| `resize.py` | photographs into `photos/` at web size. |
| `analyse.py` | what separates photographed evenings from the rest. |

Both validators should pass before you trust a new measurement:

```powershell
python solar.py --validate
python measure_time.py --validate
```

`solar.py` and `weather.py` use the standard library only. `resize.py`, `measure_time.py`
and `add_evening.py` need:

```powershell
pip install pillow numpy
pip install pillow-heif   # only if you drop HEIC files straight off an iPhone
```

The site itself has no dependencies, no framework and no build step.

---

## Gotchas

- The branch is **`master`**, not `main`.
- **Open-Meteo stamps a whole response with one UTC offset** taken from the request's
  current season, so a February window comes back labelled PDT and every sunset reads an
  hour late. The hourly timestamps shift by the same amount, so matching an hour against
  the API's own labels still picks the correct physical hour — but any label shown to a
  human is wrong. `weather.py` corrects this and warns when it fires.
- **The swing window and the trace window differ on purpose.** The trace is seven values,
  sunset−3h to +3h. The swing is the range over six values, sunset−2h to +3h. Don't unify
  them; the existing numbers use exactly this definition.
- **Sunset within a minute of the half hour** flips which hour it rounds to, which is
  enough to change a swing. Two July evenings differ from their originally recorded
  values for precisely this reason.
- Validate the JSON before deploying. A broken file yields a silently blank page rather
  than a visible error.
- `.vercel` is gitignored, so link folders are invisible to `git status`.
- Open-Meteo needs no API key. Data is CC BY 4.0, attributed in the site footer.
