import json
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from astropy.time import Time
from astropy.coordinates import SkyCoord, FK5, CIRS, GCRS
import astropy.units as u
import plate_solve
import tools

global is_calibrating
global is_imu_correction_get
global is_imu_correction_global_set
global is_imu_correction_local_set

def load_config(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)

def save_config(path: Path, data):
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return path

def drawing(arguments, zenith_photo_coordinates, coefficient_location):

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
    
if __name__ == "__main__":
    input_arg = "metadata/meta0.json"
    is_calibrating = True
    is_imu_correction_get = True
    is_imu_correction_global_set = True
    is_imu_correction_local_set = True

    # Load arguments from JSON file
    arguments_m = load_config(Path(input_arg))
    arguments_c = load_config(Path("config.json"))

    ii = arguments_m.get("input_image", "")
    input_image = "./" + ii
    od = arguments_m.get("output_directory", "")
    output_directory = "./" + od
    ps = arguments_m.get("plate_solve_parameters", [])
    plate_solve_parameters = ps
    cd = arguments_m.get("camera_data", [])
    camera_data = [
        [float(cd[0][0]), float(cd[0][1])],
        [float(cd[1][0]), float(cd[1][1])],
        float(cd[2])
    ]
    pd = arguments_m.get("photo_data", [])
    photo_data = [
        [float(pd[0][0]), float(pd[0][1])],
        pd[1],
        [float(pd[2][0]), float(pd[2][1])]
    ]
    od = arguments_m.get("orientation_data", [])
    orientation_data = [
        np.asarray(od[0], dtype=np.float64),
        np.asarray(od[1], dtype=np.float64),
    ]

    cm = arguments_c.get("correction_matrix", [])
    correction_matrix = np.asarray(cm, dtype=np.float64) if len(cm) > 0 else np.array([])

    wcs_fits = "./" + arguments_m["input_image"] + ".d/wcs.fits"


    # Plate solving
    plate_solve.plate_solve(
        input_image,
        output_directory,
        plate_solve_parameters)
    
    if is_imu_correction_get and correction_matrix.size != 0:
        # Apply IMU correction to orientation data
        orientation_data[0] = correction_matrix @ orientation_data[0]
    # Calculate zenith photo coordinates
    obs_zenith_xy = tools.find_xy_via_orientation(
        camera_data[0],
        camera_data[1],
        camera_data[2],
        photo_data[0],
        orientation_data[0] / np.linalg.norm(orientation_data[0]))
    
    # Calculate zenith ICRS coordinates
    obs_zenith_icrs = tools.find_icrs_via_xy(
        wcs_fits,
        obs_zenith_xy)
    
    # Transform from observation epoch to J2000 using proper jyear Time
    obs_epoch = Time(Time(photo_data[1], scale='utc').to_value('decimalyear'), format='jyear')
    source = SkyCoord(ra=obs_zenith_icrs[0] * u.deg, dec=obs_zenith_icrs[1] * u.deg, frame=FK5(equinox=obs_epoch))
    result = source.transform_to(FK5(equinox=Time(2000.0, format='jyear')))
    obs_zenith_icrs_j2000 = [float(result.ra.deg), float(result.dec.deg)]

    # Approximate location
    obs_location = tools.find_location_via_icrs(
        obs_zenith_icrs_j2000[0],
        obs_zenith_icrs_j2000[1],
        photo_data[1])
    
    if (is_calibrating is True):
        # Reverse approximate location to get actual ICRS coordinates
        apr_zenith_icrs = tools.find_icrs_via_location(
            photo_data[1],
            photo_data[2][0],
            photo_data[2][1])
    
        # Calculate pixel coordinates from ICRS coordinates
        apr_zenith_xy = tools.find_xy_via_icrs(
            wcs_fits,
            apr_zenith_icrs)
    
    if (is_calibrating is True and is_imu_correction_local_set is True and is_imu_correction_get is False):
         apr_zenith_vector = tools.pixel_to_ray(apr_zenith_xy[0], apr_zenith_xy[1], camera_data)
         obs_zenith_vector = tools.pixel_to_ray(obs_zenith_xy[0], obs_zenith_xy[1], camera_data)
         cor_matrix = tools.rotation_from_vectors(obs_zenith_vector, apr_zenith_vector)
         print("Correction matrix (from approximate to observed): ", cor_matrix)
         od[1] = cor_matrix.tolist()
         save_config(Path(input_arg), arguments_m)

    if (is_imu_correction_global_set is True and is_calibrating is True):
        # Gather local correction matrices from all metadata/meta*.json files
        metadata_dir = Path("metadata")
        local_corrections = []
        for meta_file in metadata_dir.glob("meta*.json"):
            try:
                meta = load_config(meta_file)
                od = meta.get("orientation_data", [])
                if len(od) > 1 and isinstance(od[1], list):
                    mat = np.asarray(od[1], dtype=np.float64)
                    if mat.shape == (3, 3):
                        local_corrections.append(mat)
            except Exception:
                # ignore unreadable/invalid metadata files
                continue

        # If we found corrections, combine and persist as global correction
        if len(local_corrections) > 0:
            combined = tools.combine_rotation_corrections(local_corrections)
            arguments_c["correction_matrix"] = combined.tolist()
            save_config(Path("config.json"), arguments_c)
            print(f"Saved combined global correction from {len(local_corrections)} metadata files.")
        else:
            print("No local orientation_data[1] corrections found in metadata.")
    
    print("(Calculated) Photo Coordinates:", obs_zenith_xy)
    print("(Calculated) ICRS Coordinates J" + str(round(float(str(obs_epoch)), 2)) + ":", obs_zenith_icrs)
    print("(Calculated) ICRS Coordinates J2000:", obs_zenith_icrs_j2000)
    print("(Calculated) Location:", obs_location)

    if (is_calibrating is True):
        print("(Approximate) Photo Coordinates:", apr_zenith_xy)
        print("(Approximate) ICRS Coordinated:", apr_zenith_icrs)
        print("(Actual) Location:", photo_data[2])

        # print("Photo coordinates precision (pixels): ", round(((zenith_photo_coordinates[0] - actual_zenith_photo_coordinates[0])**2 + (zenith_photo_coordinates[1] - actual_zenith_photo_coordinates[1])**2) ** 0.5, 2))
        # print("Estimated ICRS precision (degrees): ", round(((zenith_icrs_coordinates_2000[0] - actual_zenith_icrs_coordinates[0])**2 + (zenith_icrs_coordinates_2000[1] - actual_zenith_icrs_coordinates[1])**2) ** 0.5, 6))
        # print("Estimated ICRS precision (km): ", round(((zenith_icrs_coordinates_2000[0] - actual_zenith_icrs_coordinates[0])**2 + (zenith_icrs_coordinates_2000[1] - actual_zenith_icrs_coordinates[1])**2) ** 0.5 * 111, 6))
        print("Location precision (km):", round(((photo_data[2][0] - obs_location[0])**2 + (photo_data[2][1] - obs_location[1])**2) ** 0.5 * 111, 2))

    if (is_calibrating is True):
        drawing(arguments_m, obs_zenith_xy, apr_zenith_xy)