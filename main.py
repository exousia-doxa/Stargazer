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
        return str(out_path)
    except Exception as e:
        return None
    
def process_metadata_file(input_arg, arguments_c, flags):
    """Process one metadata JSON file path and return dict of results (no prints).
    flags: dict with booleans is_calibrating, is_imu_correction_get, is_imu_correction_global_set, is_imu_correction_local_set
    """
    results = {
        "file": str(input_arg),
        "correction_matrix": None,
        "charted_image": None,
        "calculated_photo_coordinates": None,
        "calculated_icrs_coordinates_epoch": None,
        "calculated_icrs_coordinates_j2000": None,
        "calculated_location": None,
        "approx_photo_coordinates": None,
        "approx_icrs_coordinated": None,
        "actual_location": None,
        "location_precision_km": None,
        "saved_combined_global_correction": None,
        "no_local_found_message": None,
        "error": None,
    }

    try:
        arguments_m = load_config(Path(input_arg))
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
        orientation_vector = np.asarray(od[0], dtype=np.float64) if len(od) > 0 else np.zeros(3, dtype=np.float64)
        orientation_local_entry = od[1] if len(od) > 1 else None
        orientation_data = [orientation_vector, orientation_local_entry]

        cm_raw = arguments_c.get("correction_matrix", [])
        correction_matrix_entries = cm_raw

        wcs_fits = "./" + arguments_m["input_image"] + ".d/wcs.fits"

        # Plate solving
        plate_solve.plate_solve(input_image, output_directory, plate_solve_parameters)

        # Calculate zenith photo coordinates
        obs_zenith_xy = tools.find_xy_via_orientation(
            camera_data[0], camera_data[1], camera_data[2], photo_data[0], orientation_data[0] / np.linalg.norm(orientation_data[0]))

        # Compute angular offset (degrees) between center and observed zenith
        obs_angle_deg = tools.pixel_angle_deg_from_center(obs_zenith_xy, camera_data)

        # If a global correction (config) is present and requested, select appropriate matrix by degree bin
        if flags.get("is_imu_correction_get") and len(correction_matrix_entries) > 0:
            selected_matrix = None
            try:
                if (isinstance(correction_matrix_entries, list)
                        and len(correction_matrix_entries) == 3
                        and all(isinstance(r, list) and len(r) == 3 for r in correction_matrix_entries)):
                    selected_matrix = np.asarray(correction_matrix_entries, dtype=np.float64)
            except Exception:
                selected_matrix = None

            if selected_matrix is None:
                for entry in correction_matrix_entries:
                    try:
                        rng = entry[0]
                        mat = np.asarray(entry[1], dtype=np.float64)
                        if len(rng) >= 2 and rng[0] <= obs_angle_deg < rng[1]:
                            selected_matrix = mat
                            break
                    except Exception:
                        continue

            if selected_matrix is not None:
                orientation_data[0] = selected_matrix @ orientation_data[0]
                obs_zenith_xy = tools.find_xy_via_orientation(camera_data[0], camera_data[1], camera_data[2], photo_data[0], orientation_data[0] / np.linalg.norm(orientation_data[0]))
                obs_angle_deg = tools.pixel_angle_deg_from_center(obs_zenith_xy, camera_data)

        # Calculate zenith ICRS coordinates
        obs_zenith_icrs = tools.find_icrs_via_xy(wcs_fits, obs_zenith_xy)

        obs_epoch = Time(Time(photo_data[1], scale='utc').to_value('decimalyear'), format='jyear')
        source = SkyCoord(ra=obs_zenith_icrs[0] * u.deg, dec=obs_zenith_icrs[1] * u.deg, frame=FK5(equinox=obs_epoch))
        result = source.transform_to(FK5(equinox=Time(2000.0, format='jyear')))
        obs_zenith_icrs_j2000 = [float(result.ra.deg), float(result.dec.deg)]

        obs_location = tools.find_location_via_icrs(obs_zenith_icrs_j2000[0], obs_zenith_icrs_j2000[1], photo_data[1])

        results.update({
            "calculated_photo_coordinates": obs_zenith_xy,
            "calculated_icrs_coordinates_epoch": obs_zenith_icrs,
            "calculated_icrs_coordinates_j2000": obs_zenith_icrs_j2000,
            "calculated_location": obs_location,
        })

        if flags.get("is_calibrating"):
            apr_zenith_icrs = tools.find_icrs_via_location(photo_data[1], photo_data[2][0], photo_data[2][1])
            apr_zenith_xy = tools.find_xy_via_icrs(wcs_fits, apr_zenith_icrs)
            results["approx_photo_coordinates"] = apr_zenith_xy
            results["approx_icrs_coordinated"] = apr_zenith_icrs
            results["actual_location"] = photo_data[2]

            if flags.get("is_imu_correction_local_set") and not flags.get("is_imu_correction_get"):
                apr_zenith_vector = tools.pixel_to_ray(apr_zenith_xy[0], apr_zenith_xy[1], camera_data)
                obs_zenith_vector = tools.pixel_to_ray(obs_zenith_xy[0], obs_zenith_xy[1], camera_data)
                cor_matrix = tools.rotation_from_vectors(obs_zenith_vector, apr_zenith_vector)
                apr_angle_deg = tools.pixel_angle_deg_from_center(apr_zenith_xy, camera_data)
                od = arguments_m.get("orientation_data", [])
                od[1] = [cor_matrix.tolist(), [float(apr_zenith_xy[0]), float(apr_zenith_xy[1])], float(apr_angle_deg)]
                save_config(Path(input_arg), arguments_m)
                results["correction_matrix"] = cor_matrix.tolist()

        if flags.get("is_imu_correction_global_set") and flags.get("is_calibrating"):
            metadata_dir = Path("metadata")
            local_by_bin = {}
            degree_step = float(arguments_c.get("degree_step", 5.0))

            for meta_file in metadata_dir.glob("meta*.json"):
                try:
                    meta = load_config(meta_file)
                    od_local = meta.get("orientation_data", [])
                    if len(od_local) > 1:
                        entry = od_local[1]
                        if isinstance(entry, list) and len(entry) >= 3 and isinstance(entry[0], list):
                            mat = np.asarray(entry[0], dtype=np.float64)
                            angle = float(entry[2])
                            if mat.shape == (3, 3):
                                bin_start = (int(angle // degree_step) * int(degree_step))
                                bin_key = (bin_start, bin_start + int(degree_step))
                                local_by_bin.setdefault(bin_key, []).append(mat)
                except Exception:
                    continue

            if len(local_by_bin) > 0:
                cm_list = []
                for bin_key, mats in sorted(local_by_bin.items()):
                    combined = tools.combine_rotation_corrections(mats)
                    cm_list.append([[float(bin_key[0]), float(bin_key[1])], combined.tolist()])

                arguments_c["correction_matrix"] = cm_list
                save_config(Path("config.json"), arguments_c)
                results["saved_combined_global_correction"] = f"Saved combined global correction for {len(cm_list)} degree bins."
            else:
                results["no_local_found_message"] = "No local orientation_data[1] corrections with angle info found in metadata."

        # drawing
        charted = drawing(arguments_m, obs_zenith_xy, apr_zenith_xy if flags.get("is_calibrating") else None)
        results["charted_image"] = charted

        # compute location precision if possible
        if results.get("actual_location") and results.get("calculated_location"):
            loc_prec = round(((results["actual_location"][0] - results["calculated_location"][0])**2 + (results["actual_location"][1] - results["calculated_location"][1])**2) ** 0.5 * 111, 2)
            results["location_precision_km"] = loc_prec

    except Exception as e:
        results["error"] = str(e)

    return results


if __name__ == "__main__":
    # default single-file behavior
    input_arg = "metadata/meta_cal20.json"
    is_calibrating = True
    is_imu_correction_get = True
    is_imu_correction_global_set = False
    is_imu_correction_local_set = False

    # Load common config
    arguments_c = load_config(Path("config.json"))
    # control batch processing via config.json keys (can be toggled by user)
    process_all = bool(arguments_c.get("process_all_metadata", False))
    report_md = arguments_c.get("report_md", None)

    # Decide files to process
    metadata_files = []
    if process_all:
        metadata_dir = Path("metadata")
        for meta_file in metadata_dir.glob("meta*.json"):
            metadata_files.append(str(meta_file))
    else:
        metadata_files = [input_arg]
    
    # Process files and gather results
    flags = {
        "is_calibrating": is_calibrating,
        "is_imu_correction_get": is_imu_correction_get,
        "is_imu_correction_global_set": is_imu_correction_global_set,
        "is_imu_correction_local_set": is_imu_correction_local_set,
    }

    rows = []
    for mf in metadata_files:
        res = process_metadata_file(mf, arguments_c, flags)
        rows.append(res)

    # Write markdown report if requested
    if report_md:
        md_path = Path(report_md)
        with md_path.open("w", encoding="utf-8") as fh:
            # Table header
            headers = [
                "file",
                "correction_matrix",
                "charted_image",
                "calculated_photo_coordinates",
                "calculated_icrs_coordinates_epoch",
                "calculated_icrs_coordinates_j2000",
                "calculated_location",
                "approx_photo_coordinates",
                "approx_icrs_coordinated",
                "actual_location",
                "location_precision_km",
                "saved_combined_global_correction",
                "no_local_found_message",
                "error",
            ]
            fh.write("| " + " | ".join(headers) + " |\n")
            fh.write("|" + "---|" * len(headers) + "\n")
            for r in rows:
                def fmt(v):
                    if v is None:
                        return ""
                    if isinstance(v, (list, tuple)):
                        return '"' + str([round(float(x), 6) if isinstance(x, (int,float)) else x for x in v]) + '"'
                    return '"' + str(v) + '"'
                fh.write("| " + " | ".join(fmt(r.get(h)) for h in headers) + " |\n")
        print(f"Wrote markdown report to {md_path}")
    else:
        # Print short summary to stdout
        for r in rows:
            print(r)