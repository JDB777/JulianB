# Sunset log — Ocean Beach, San Francisco

Two things live here:

1. **An archive** of San Francisco sunset weather that grows over time and is never
   re-downloaded. Fetch once, keep forever.
2. **A predictor** that learns what your favorite evenings have in common and tells you
   whether the next few are worth walking down for.

The public page is at **https://sunset-log-henna.vercel.app**

Station: 37.7594 N, 122.5107 W, looking west over the Pacific.

---

## The two commands you will actually use

**When you get a sunset you liked:**

```powershell
python add_favorite.py "C:\path\to\photos" 2026-08-14
```

It resizes the photographs in, works out when they were taken by measuring the sun,
makes sure that evening's weather is in the archive, labels the date, and refreshes the
website's data file.

**When you want to know whether to bother tonight:**

```powershell
python forecast.py --refresh
```

```
date          sunset  canvas   slot   score   pctile   verdict
2026-08-14     20:07      88     91    80.1      96%   exceptional - go
2026-08-15     20:06      12     44     5.3      31%   unlikely
```

That is the whole loop. Everything below is detail.

---

## Why it is built this way

### The archive is the point

Weather APIs are for fetching, not for storing. Every reading this project has ever
pulled is kept in `data/sunsets.db`, a single SQLite file, as **raw hourly values rather
than summaries**. That matters: when a better idea about what makes a good sunset comes
along in a year's time, it can be applied to the entire history without touching the
network.

```powershell
python ingest.py backfill 2025-01-01 2026-07-27   # history, one time
python ingest.py update                           # catch up, run whenever
python ingest.py forecast                         # next 7 days
python store.py                                   # what the archive holds
```

`ingest.py` only fetches gaps. Running `update` twice does nothing the second time.
An interrupted backfill resumes where it stopped.

### It samples offshore, not just the beach

The sun sets about 60° further north in June than in December, so "due west" is wrong
most of the year. The archive samples the station plus **ten offshore points** — five
bearings from 240° to 300°, at 50 km and 100 km — and features pick the bearing nearest
each evening's actual sunset azimuth.

This is not decoration. A vivid sunset here needs two separate things:

- **a canvas** — mid and high cloud overhead to catch the light
- **a slot** — a gap at the western horizon for the light to get through on its way

The station cannot see the slot; it is below the horizon from the beach. Two evenings
can be identical at the station and completely different 50 km out, and in this archive
that has already happened: 27 July and 17 July 2026 read 99% and 100% low cloud at the
station, and 24% against 99% offshore. One was a keeper. The other was not.

The score is `canvas × slot / 100`, so an evening only scores high if **both** are
present. Overcast with no gap scores zero. An empty clear sky scores zero. That asymmetry
is why a single "how cloudy is it" number has never worked here.

### Your negatives are real, which is unusual

You see the sunset nearly every evening and send only the ones worth keeping. That makes
an unlabelled evening inside the watch window a genuine negative — you saw it and it
wasn't special. Most projects like this have to guess at their negatives; this one
doesn't, and that is what makes the statistics worth running at all.

If you were away, say so, and the evening is dropped rather than counted against:

```powershell
python add_favorite.py --unseen 2026-08-20
```

---

## Finding the trend

```powershell
python trends.py
```

Each favorite is scored against evenings within ±15 days of it, so season is controlled
for by construction — a low-cloud swing of 9 means something very different in March
than in July, and pooling them is how the previous version of this project fooled itself.

Significance comes from a **circular-shift test**, not a formula: the whole set of
favorite dates is slid through the archive by a random offset, keeping the spacing
between them intact, and the statistic is recomputed a few thousand times. Preserving
spacing matters because your favorites cluster, clustered dates share comparison windows,
and a test assuming independence would claim confidence it hasn't earned. A
Benjamini-Hochberg step then accounts for asking the question of nineteen features at
once.

It will tell you plainly when nothing survives. That is the normal state early on and is
not a failure — it is the tool refusing to sell you a pattern it cannot support.

`forecast.py` prints a calibration block on every run showing where your known favorites
landed on the same scale, so you can see whether the score tracks your taste or is
flattering itself.

---

## What is known so far

**Holds up.** Every evening on record had a clear slot at the western horizon. Across six
evenings and three seasons there are no exceptions. It is the only claim never to need
revising, and it is the mechanism the score is built on.

**Falsified.** An earlier statistic — the range of low cloud across the sunset window,
"swing" — ranked the three July evenings 1st, 2nd and 3rd of twenty-one and looked
convincing. Tested against the three non-July evenings it scored 0, 9 and 4: ranks 20th,
5th and 11th, an average of 12th against a random expectation of 11th. On 20 February,
six evenings in the surrounding window swung 70 points or more and the one photographed
swung zero. It described July and nothing else. It is retained as one feature among
nineteen, not as the answer.

**The trap.** In a frame exposed for the horizon band, a uniformly lit cloud deck and a
clear sky are not visually distinguishable — both render as a smooth gradient. Cloud read
off a photograph is reliable only when it has visible texture. Check any photographic
cloud read against the archive before writing it down.

---

## The photographs have no EXIF

Not stripped of location — stripped of everything. No `DateTimeOriginal`, no camera
model, no GPS. A stated time cannot be checked against metadata, so it is checked against
the sun instead. Angular diameter is a fixed 0.5333°, so measuring the disk and its
height above the horizon in pixels gives apparent elevation regardless of focal length:

```
apparent_elevation_deg = (horizon_y − sun_centre_y) / disk_diameter_px × 0.5333
```

Two details had to be right, both found by looking at the pixels rather than reasoning
about them:

- **The horizon is found by texture, not brightness.** On a hazy evening the sea horizon
  is a soft ramp over ~20 rows while the surf line below is a genuinely sharp step, so
  "sharpest bright-to-dark step" reliably finds the beach. Across columns, sky varies by
  2–3 grey levels and open water by 5–30.
- **The disk is measured at its widest row, not its centroid.** Cloud often clips the top,
  which drags a centroid down, and refraction flattens the disk vertically so its height
  understates the diameter.

Validated at +0.49° and +0.52° against a known +0.53°. Where a disk is measurable the
measurement beats a remembered time, and a disagreement over six minutes stops the run.
Afterglow frames have no disk; supply `--time` for those.

---

## Files

| | |
|---|---|
| `store.py` | the archive: schema, points, labels. `python store.py` prints its state. |
| `ingest.py` | fetch and store. Backfill, update, forecast. |
| `features.py` | raw hourly → one feature vector per evening. |
| `trends.py` | what your favorites have in common, honestly tested. |
| `forecast.py` | whether the next few evenings look worth it. |
| `add_favorite.py` | record an evening you liked. |
| `publish.py` | regenerate the website's data file from the archive. |
| `measure_time.py` | measure the sun in a frame. `--validate` first. |
| `solar.py` | NOAA solar position. `--validate` first. |
| `resize.py` | photographs into `photos/` at web size. |
| `index.html` | the public page. Reads `data/evenings.json`. |

Both validators should pass before you trust a new measurement:

```powershell
python solar.py --validate
python measure_time.py --validate
```

Requirements: `pip install pillow numpy`. `store.py`, `ingest.py`, `features.py`,
`trends.py`, `forecast.py` and `solar.py` are standard library only. The website has no
dependencies and no build step.

---

## Gotchas

- The git branch is **`master`**, not `main`.
- **Pushing to GitHub does not deploy.** There is no git integration on this Vercel
  project. Deploy with `vercel deploy --prod --cwd <this folder>` *and* push, every time,
  or the live site and the repo drift apart.
- **`data/sunsets.db` is gitignored.** Weather is re-fetchable, and a binary file that
  grows ~12 MB a year would bloat the repository on every commit. What is *not*
  re-fetchable is which evenings you liked, so labels are mirrored to
  `data/favorites.json`, which **is** committed. Losing the db costs a re-fetch; losing
  the labels costs the project.
- **Open-Meteo stamps a whole response with one UTC offset** taken from the request's
  current season, so a February window comes back labelled PDT with every timestamp an
  hour late. Hourly fields shift together so the data is internally consistent, but
  storing those labels would corrupt the archive the moment it was queried across a DST
  boundary. `ingest.py` normalises to true local time on the way in.
- **Sunset within a minute of the half hour** flips which hour it rounds to, which is
  enough to change a swing value.
- Validate the JSON before deploying. A broken file yields a silently blank page rather
  than a visible error.
- Open-Meteo needs no API key. Data is CC BY 4.0, attributed in the site footer.
