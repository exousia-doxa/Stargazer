from astropy.time import Time
from astropy import units as u
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
from astropy.utils.iers import iers

iers.conf.auto_download = True

def approximate_location(
        ra_deg: float,
        dec_deg: float,
        photo_time,
        initial_guess=(0.0, 0.0),
        coarse_step_deg: float = 0.1,
        target_precision_deg: float = 1e-4):
    time = Time(photo_time, scale='utc')
    target_coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame='icrs')

    best_latitude, best_longitude = float(initial_guess[0]), float(initial_guess[1])
    step = float(coarse_step_deg)
    best_sep_deg = float('inf')

    while step >= float(target_precision_deg):
        lat_candidates = (best_latitude - step, best_latitude, best_latitude + step)
        lon_candidates = (best_longitude - step, best_longitude, best_longitude + step)
        improved = False

        for lat in lat_candidates:
            if lat < -90.0 or lat > 90.0:
                continue
            for lon in lon_candidates:
                lon_wrapped = ((lon + 180.0) % 360.0) - 180.0
                location = EarthLocation(lat=lat * u.deg, lon=lon_wrapped * u.deg, height=0 * u.m)
                zenith_altaz = SkyCoord(alt=90 * u.deg, az=0 * u.deg, frame=AltAz(obstime=time, location=location))
                zenith_icrs = zenith_altaz.transform_to('icrs')
                sep_deg = target_coord.separation(zenith_icrs).deg
                if sep_deg < best_sep_deg:
                    best_sep_deg = sep_deg
                    best_latitude, best_longitude = lat, lon_wrapped
                    improved = True

        if not improved:
            step /= 10.0

    return round(float(best_latitude), 4), round(float(best_longitude), 4)


def reverse_approximate_location(observation_time, latitude_deg: float, longitude_deg: float):
    time = Time(observation_time, scale='utc')
    location = EarthLocation(lat=latitude_deg * u.deg, lon=longitude_deg * u.deg, height=0 * u.m)
    zenith_altaz = SkyCoord(alt=90 * u.deg, az=0 * u.deg, frame=AltAz(obstime=time, location=location))
    zenith_icrs = zenith_altaz.transform_to('icrs')
    return float(zenith_icrs.ra.to(u.deg).value), float(zenith_icrs.dec.to(u.deg).value)