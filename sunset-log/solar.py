"""NOAA solar position for the station: sunset time, elevation, azimuth.

Self-test reproduces the six evenings already on record:

    python solar.py --validate

Query a single moment:

    python solar.py 2026-08-14 20:03
"""

import math
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

LAT, LON = 37.7594, -122.5107
TZ = ZoneInfo("America/Los_Angeles")

# Sunset is defined as the moment the sun's centre sits 0.833 deg below the
# horizon: 0.583 deg of refraction plus 0.25 deg of solar semidiameter.
SUNSET_ZENITH = 90.833

rad, deg = math.radians, math.degrees


def _julian_day(dt_utc):
    y, m = dt_utc.year, dt_utc.month
    d = dt_utc.day + (dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600) / 24
    if m <= 2:
        y, m = y - 1, m + 12
    a = y // 100
    b = 2 - a + a // 4
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + d + b - 1524.5


def _sun_params(jd):
    """Declination (deg) and equation of time (minutes) for a Julian day."""
    t = (jd - 2451545.0) / 36525.0
    l0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    c = (math.sin(rad(m)) * (1.914602 - t * (0.004817 + 0.000014 * t))
         + math.sin(rad(2 * m)) * (0.019993 - 0.000101 * t)
         + math.sin(rad(3 * m)) * 0.000289)
    true_long = l0 + c
    omega = 125.04 - 1934.136 * t
    app_long = true_long - 0.00569 - 0.00478 * math.sin(rad(omega))
    eps0 = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
    eps = eps0 + 0.00256 * math.cos(rad(omega))
    decl = deg(math.asin(math.sin(rad(eps)) * math.sin(rad(app_long))))

    yv = math.tan(rad(eps / 2)) ** 2
    eqtime = 4 * deg(
        yv * math.sin(2 * rad(l0))
        - 2 * e * math.sin(rad(m))
        + 4 * e * yv * math.sin(rad(m)) * math.cos(2 * rad(l0))
        - 0.5 * yv * yv * math.sin(4 * rad(l0))
        - 1.25 * e * e * math.sin(2 * rad(m))
    )
    return decl, eqtime


def refraction(true_el):
    """Atmospheric lift in degrees, applied to a true geometric elevation."""
    if true_el > 85:
        return 0.0
    tan_e = math.tan(rad(true_el))
    if true_el > 5:
        arcsec = 58.1 / tan_e - 0.07 / tan_e**3 + 0.000086 / tan_e**5
    elif true_el > -0.575:
        arcsec = 1735 + true_el * (-518.2 + true_el * (103.4 + true_el * (-12.79 + true_el * 0.711)))
    else:
        arcsec = -20.772 / tan_e
    return arcsec / 3600


def position(when_local, lat=LAT, lon=LON):
    """(true elevation, apparent elevation, azimuth) in degrees for a local datetime."""
    if when_local.tzinfo is None:
        when_local = when_local.replace(tzinfo=TZ)
    utc = when_local.astimezone(ZoneInfo("UTC"))
    jd = _julian_day(utc)
    decl, eqtime = _sun_params(jd)

    mins = utc.hour * 60 + utc.minute + utc.second / 60
    true_solar = (mins + eqtime + 4 * lon) % 1440
    ha = true_solar / 4 - 180

    cos_z = (math.sin(rad(lat)) * math.sin(rad(decl))
             + math.cos(rad(lat)) * math.cos(rad(decl)) * math.cos(rad(ha)))
    cos_z = max(-1.0, min(1.0, cos_z))
    zenith = deg(math.acos(cos_z))
    true_el = 90 - zenith

    sin_z = math.sin(rad(zenith))
    if abs(sin_z) < 1e-9:
        az = 0.0
    else:
        c = (math.sin(rad(lat)) * cos_z - math.sin(rad(decl))) / (math.cos(rad(lat)) * sin_z)
        az = deg(math.acos(max(-1.0, min(1.0, c))))
        az = (180 + az) % 360 if ha > 0 else (180 - az) % 360
    return true_el, true_el + refraction(true_el), az


def sunset(on_date, lat=LAT, lon=LON):
    """Local datetime of sunset, to the nearest second."""
    noon_utc = datetime(on_date.year, on_date.month, on_date.day, 12,
                        tzinfo=ZoneInfo("UTC"))
    decl, eqtime = _sun_params(_julian_day(noon_utc))
    cos_ha = (math.cos(rad(SUNSET_ZENITH)) / (math.cos(rad(lat)) * math.cos(rad(decl)))
              - math.tan(rad(lat)) * math.tan(rad(decl)))
    if not -1 <= cos_ha <= 1:
        raise ValueError("no sunset on this date at this latitude")
    ha = deg(math.acos(cos_ha))
    # solar noon (UTC minutes) is 720 - 4*lon - eqtime; sunset is +4*HA past it.
    # Using -4*HA here would silently return sunrise.
    minutes_utc = 720 - 4 * (lon - ha) - eqtime
    t = datetime(on_date.year, on_date.month, on_date.day,
                 tzinfo=ZoneInfo("UTC")) + timedelta(minutes=minutes_utc)
    return t.astimezone(TZ)


def sunset_azimuth(on_date, lat=LAT, lon=LON):
    return position(sunset(on_date, lat, lon).replace(tzinfo=TZ), lat, lon)[2]


def describe(on_date, shot_hhmm):
    """Everything an evening entry needs, given a date and a local clock time."""
    h, m = (int(x) for x in shot_hhmm.split(":"))
    shot = datetime(on_date.year, on_date.month, on_date.day, h, m, tzinfo=TZ)
    ss = sunset(on_date)
    _, app_el, _ = position(shot)
    return {
        "shot_time": shot.strftime("%H:%M"),
        "sunset": ss.strftime("%H:%M"),
        "offset_min": round((shot - ss).total_seconds() / 60),
        "sun_elev_apparent": round(app_el, 2),
        "sunset_azimuth": round(sunset_azimuth(on_date), 1),
    }


# Section 7 of the handoff: every value here came from real computation.
VALIDATION = [
    ("2026-02-20", "18:18", "17:54", 24, -4.12, 257.1),
    ("2026-03-18", "19:09", "19:20", -11, 1.70, 269.9),
    ("2026-03-27", "19:32", "19:28", 4, -0.27, 274.3),
    ("2026-07-12", "20:32", "20:33", -1, 0.56, 298.8),
    ("2026-07-21", "20:27", "20:28", -1, 0.54, 296.6),
    ("2026-07-27", "20:19", "20:23", -4, 0.53, 295.0),
]


def validate(tol_min=2, tol_deg=0.2):
    """Check the two quantities this module is authoritative for.

    Sunset time and sunset azimuth are pure computation and must reproduce the
    reference table. Apparent elevation is NOT asserted: for most of the six
    evenings the recorded figure was measured off the photograph (the sun's disk
    against the horizon), not computed from the stated clock time. Comparing the
    two is the timestamp check in measure_time.py, not a test of this module —
    so the elevation column here is reported for information only.
    """
    print("Asserted: sunset time and azimuth (recorded / computed)\n")
    print(f"{'date':<12}{'sunset':>18}{'azimuth':>18}")
    ok = True
    rows = []
    for d, shot, exp_ss, exp_off, exp_el, exp_az in VALIDATION:
        got = describe(date.fromisoformat(d), shot)
        dss = abs((datetime.strptime(got["sunset"], "%H:%M")
                   - datetime.strptime(exp_ss, "%H:%M")).total_seconds()) / 60
        dss = min(dss, 1440 - dss)
        da = abs(got["sunset_azimuth"] - exp_az)
        good = dss <= tol_min and da <= tol_deg
        ok &= good
        ss_cell = "{} / {}".format(exp_ss, got["sunset"])
        az_cell = "{} / {}".format(exp_az, got["sunset_azimuth"])
        print(f"{d:<12}{ss_cell:>18}{az_cell:>18}   {'ok' if good else 'OFF'}")
        rows.append((d, shot, exp_el, got["sun_elev_apparent"]))

    print("\nInformational: apparent elevation (recorded / computed for the stated time)")
    print(f"{'date':<12}{'shot':>7}{'recorded':>11}{'computed':>11}{'implied drift':>15}")
    for d, shot, exp_el, got_el in rows:
        # how many minutes of solar motion separate the two figures
        drift = (exp_el - got_el) / 0.18  # deg per minute near this horizon
        print(f"{d:<12}{shot:>7}{exp_el:>+11.2f}{got_el:>+11.2f}"
              f"{drift:>+14.1f}m")

    print("\n" + ("Sunset time and azimuth reproduce the table."
                  if ok else "MISMATCH on sunset/azimuth - do not use."))
    return ok


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--validate":
        raise SystemExit(0 if validate() else 1)
    if len(sys.argv) == 3:
        d = date.fromisoformat(sys.argv[1])
        for k, v in describe(d, sys.argv[2]).items():
            print(f"  {k:<20} {v}")
    else:
        print(__doc__)
