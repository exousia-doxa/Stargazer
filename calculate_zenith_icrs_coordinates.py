import numpy as np

from astropy import wcs
from astropy.io import fits

def calculate_zenith_icrs_coordinates(filename, zenith_coordinates):
    hdulist = fits.open(filename)

    w = wcs.WCS(hdulist[0].header)

    pixcrd = np.array([zenith_coordinates], dtype=np.float64)

    zenith_icrs_coordinates = w.wcs_pix2world(pixcrd, 0)

    return zenith_icrs_coordinates[0]

def calculate_pixel_coordinates_from_icrs(filename, icrs_coordinates):
    hdulist = fits.open(filename)
    w = wcs.WCS(hdulist[0].header)

    worldcrd = np.array([icrs_coordinates], dtype=np.float64)
    pixcrd = w.wcs_world2pix(worldcrd, 0)

    hdulist.close()
    return pixcrd[0]
