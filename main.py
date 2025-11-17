import json
import sys
from pathlib import Path


import numpy as np
from PIL import Image, ImageDraw
from astropy.time import Time
from astropy.coordinates import SkyCoord, FK5, CIRS, GCRS
import astropy.units as u

import plate_solve
import calculate_zenith_photo_coordinates
import calculate_zenith_icrs_coordinates
import approximate_location
import approximate_time

global correction_coefficients

def load_config(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)

if __name__ == "__main__":
    correction_coefficients = True

    arguments = load_config(Path("arguments6.json"))
    wcs_fits = "./" + arguments["input_image"] + ".d/wcs.fits"
    ''''''
    plate_solve.plate_solve(
        arguments["input_image"],
        arguments["output_directory"],
        arguments["plate_solve_parameters"])
    ''''''
    zenith_photo_coordinates, zenith_photo_angles = calculate_zenith_photo_coordinates.calculate_zenith_photo_coordinates_gravity(
        arguments["camera_data"],
        arguments["photo_data"],
        arguments["orientation_data"],
        correction_coefficients)
    print("(Calculated) Coordinates: ", zenith_photo_coordinates, "\n(Calculated) Angles: ", zenith_photo_angles)
    zenith_icrs_coordinates_gravity = calculate_zenith_icrs_coordinates.calculate_zenith_icrs_coordinates(
        wcs_fits,
        zenith_photo_coordinates)
    print("(Calculated) ICRS Coordinates: ", zenith_icrs_coordinates_gravity)

    source = SkyCoord(ra=zenith_icrs_coordinates_gravity[0] * u.deg, dec=zenith_icrs_coordinates_gravity[1] * u.deg, frame=FK5(equinox=Time('J2000')))
    result = source.transform_to(FK5(equinox=Time('J2025')))
    zenith_icrs_coordinates_gravity = (result.ra.deg, result.dec.deg)

    print("(Calculated) ICRS Coordinates J2000: ", result.ra.deg, result.dec.deg)


    location = approximate_location.approximate_location(
        zenith_icrs_coordinates_gravity[0],
        zenith_icrs_coordinates_gravity[1],
        arguments["photo_data"][1])
    print("(Calculated) Location: ", location)

    reversed_location = approximate_location.reverse_approximate_location(
        arguments["photo_data"][1],
        arguments["photo_data"][2][0],
        arguments["photo_data"][2][1])
    print("(Actual) ICRS Coordinated: ", reversed_location)
    coefficient_location = calculate_zenith_icrs_coordinates.calculate_pixel_coordinates_from_icrs(
        wcs_fits,
        reversed_location)
    print("(Actual) Coordinates: ", coefficient_location)

    print(coefficient_location / zenith_photo_coordinates)

    # --------------------------
    # Drawing overlay on the image
    # --------------------------
    try:
        img_path = Path("./" + arguments["input_image"])
        img = Image.open(img_path).convert("RGB")
        draw = ImageDraw.Draw(img)


        def to_int_xy(pt):
            # Accept sequences (list/tuple/numpy array) with at least two entries
            try:
                x = float(pt[0])
                y = float(pt[1])
            except Exception as e:
                raise ValueError(f"Couldn't convert point {pt} to (x,y): {e}")
            return int(round(x)), int(round(y))


        # Convert coordinates
        p_grav = to_int_xy(zenith_photo_coordinates)
        p_coeff = to_int_xy(coefficient_location)

        # center of image as specified: arguments["photo_data"][0][0]/2, arguments["photo_data"][0][1]/2
        center_x = arguments["photo_data"][0][0] / 2
        center_y = arguments["photo_data"][0][1] / 2
        p_center = int(round(center_x)), int(round(center_y))

        # Draw red lines between points
        draw.line([p_grav, p_coeff], fill="red", width=10)
        draw.line([p_grav, p_center], fill="red", width=10)
        draw.line([p_coeff, p_center], fill="red", width=10)


        # Draw filled blue 10x10 squares centered at given points
        def draw_centered_square(draw_obj, center, size=10, fill="blue"):
            cx, cy = center
            half = size // 2
            bbox = [cx - half, cy - half, cx + half, cy + half]
            draw_obj.rectangle(bbox, fill=fill)


        draw_centered_square(draw, p_grav, size=10, fill="green")
        draw_centered_square(draw, p_coeff, size=10, fill="blue")
        draw_centered_square(draw, p_center, size=10, fill="blue")

        # Save result as "charted_<original_filename>" next to input image
        out_path = img_path.parent / ("charted_" + img_path.name)
        img.save(out_path)
        print(f"Charted image saved to: {out_path}")
    except Exception as e:
        print(f"Could not create charted image: {e}", file=sys.stderr)