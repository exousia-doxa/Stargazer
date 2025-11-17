import astropy.units as u
from astropy.coordinates import SkyCoord, GCRS, ICRS
from astropy.time import Time

# 1. Define the observation time for the apparent coordinates
obstime = Time("2024-11-14T12:00:00")

from astropy.coordinates import ICRS, GCRS, SkyCoord
from astropy.time import Time
import astropy.units as u
from astropy.coordinates.solar_system import solar_system_ephemeris

# Create an ICRS coordinate
c_icrs = SkyCoord(ra=2.35609038*u.degree, dec=47.29777418*u.degree, frame='icrs', obstime=Time("2024-11-14T12:00:00"))

# Perform the transformation with a more accurate ephemeris
with solar_system_ephemeris.set('builtin'): # or other ephemeris
    c_gcrs_precise = c_icrs.gcrs

# 3. Transform the GCRS coordinates to the ICRS frame
# The transformation to ICRS removes time-dependent orientation effects
# like precession and nutation, yielding the "true" inertial coordinates.

true_icrs_coord = c_gcrs_precise.transform_to(GCRS(obstime="J2000")).transform_to(ICRS())

# Print the results
print(f"Apparent coordinates (GCRS, {obstime.iso}):")
print(f"RA: {c_gcrs_precise.ra.deg} deg, Dec: {c_gcrs_precise.dec.deg} deg")
print("\nTrue ICRS coordinates:")
print(f"RA: {true_icrs_coord.ra.deg} deg, Dec: {true_icrs_coord.dec.deg} deg")
