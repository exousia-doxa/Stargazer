import json
import sys
from pathlib import Path
import numpy as np
from PIL import Image
from astropy.time import Time
from astropy.coordinates import SkyCoord, FK5
import astropy.units as u
import plate_solve
import tools
import subprocess
from dataclasses import dataclass, asdict
import argparse
import piexif


# PhotoMeta: a clear, explicit representation of all photo metadata fields.
# Inputs: fields extracted from embedded image metadata (ICRS, camera, orientation, etc.)
# Output: dataclass instance with typed attributes for downstream processing.
@dataclass
class PhotoMeta:
    linked_image: str
    plate_solve_arguments: list
    photo_full_resolution: tuple
    phone_sensor_size: tuple
    phone_focal_length: float
    photo_utc_timestamp: str
    photo_location: tuple
    phone_gravity_vector: tuple
    correction_vector_matrix: object
    photo_coordinates: tuple
    correction_degree: object
    photo_icrs: object


# load_config: read JSON file and return parsed dict
# Input: path to JSON file
# Output: Python dict
def load_config(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# save_config: write dict to JSON file
# Input: path and data dict
# Output: path
def save_config(path: Path, data):
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return path


# set_meta_scheme: embed a metadata dict into an image's EXIF UserComment
# Input: image path and explicit metadata fields (see PhotoMeta)
# Output: True on success, False on error (prints message)
def set_meta_scheme(image_path,
                    linked_image=None,
                    plate_solve_arguments=None,
                    photo_full_resolution=None,
                    phone_sensor_size=None,
                    phone_focal_length=None,
                    photo_utc_timestamp=None,
                    photo_location=None,
                    phone_gravity_vector=None,
                    correction_vector_matrix=None,
                    photo_coordinates=None,
                    correction_degree=None,
                    photo_icrs=None):
    try:
        img_path = Path(image_path)
        if not img_path.exists():
            print(f"Error: image not found: {image_path}")
            return False
        meta = {}
        if linked_image is not None:
            meta['linked_image'] = linked_image
        if plate_solve_arguments is not None:
            meta['plate_solve_arguments'] = plate_solve_arguments
        if photo_full_resolution is not None:
            meta['photo_full_resolution'] = [float(photo_full_resolution[0]), float(photo_full_resolution[1])]
        if phone_sensor_size is not None:
            meta['phone_sensor_size'] = [float(phone_sensor_size[0]), float(phone_sensor_size[1])]
        if phone_focal_length is not None:
            meta['phone_focal_length'] = float(phone_focal_length)
        if photo_utc_timestamp is not None:
            meta['photo_utc_timestamp'] = photo_utc_timestamp
        if photo_location is not None:
            meta['photo_location'] = photo_location
        if phone_gravity_vector is not None:
            meta['phone_gravity_vector'] = list(np.asarray(phone_gravity_vector).tolist())
        if correction_vector_matrix is not None:
            meta['correction_vector_matrix'] = np.asarray(correction_vector_matrix).tolist()
        if photo_coordinates is not None:
            meta['photo_coordinates'] = [float(photo_coordinates[0]), float(photo_coordinates[1])]
        if correction_degree is not None:
            meta['correction_degree'] = float(correction_degree)
        if photo_icrs is not None:
            meta['photo_icrs'] = [float(photo_icrs[0]), float(photo_icrs[1])]

        try:
            exif_dict = piexif.load(str(img_path))
            user_comment = json.dumps(meta, ensure_ascii=False, indent=2)
            exif_dict['Exif'][piexif.ExifIFD.UserComment] = user_comment.encode('utf-8')
            exif_bytes = piexif.dump(exif_dict)
            piexif.insert(exif_bytes, str(img_path))
        except Exception as e:
            print(f"Error: failed to write EXIF data: {e}")
            return False
        return True
    except Exception as e:
        print(f"Error in set_meta_scheme: {e}")
        return False


# get_meta_scheme: extract and normalize embedded metadata from an image
# Input: image path
# Output: PhotoMeta instance or None
def get_meta_scheme(image_path):
    try:
        img_path = Path(image_path)
        if not img_path.exists():
            print(f"Error: image not found: {image_path}")
            return None
        try:
            exif_dict = piexif.load(str(img_path))
            user_comment = exif_dict.get('Exif', {}).get(piexif.ExifIFD.UserComment)
        except Exception as e:
            print(f"Error: cannot read EXIF data: {e}")
            return None
        if user_comment is None:
            info = getattr(img_path, 'info', {})
            user_comment = info.get('comment') or info.get('description') or info.get('xml') or info.get('xmp')
        if user_comment is None:
            return None
        if isinstance(user_comment, bytes):
            try:
                user_comment = user_comment.decode('utf-8', errors='ignore')
            except Exception:
                user_comment = user_comment.decode('latin-1', errors='ignore')
        if isinstance(user_comment, str):
            s = user_comment
            s = s.lstrip('\x00\ufeff\ufeff \n\r\t')
            for marker in ['ASCII\x00\x00\x00', 'UNICODE\x00', 'JIS\x00']:
                if s.startswith(marker):
                    s = s[len(marker):]
            idx = None
            for ch in ['{', '[']:
                i = s.find(ch)
                if i != -1:
                    if idx is None or i < idx:
                        idx = i
            if idx is not None and idx > 0:
                s = s[idx:]
            user_comment = s
        try:
            arguments = json.loads(user_comment)
        except Exception as e:
            print(f"Error: embedded metadata is not valid JSON: {e}")
            return None
        try:
            linked_image = arguments.get('linked_image') or img_path.name
            plate_args = arguments.get('plate_solve_arguments', [])
            pf = arguments.get('photo_full_resolution')
            ps = arguments.get('phone_sensor_size')
            fl = arguments.get('phone_focal_length')
            ts = arguments.get('photo_utc_timestamp')
            loc = arguments.get('photo_location')
            grav = arguments.get('phone_gravity_vector')
            corr_mat = arguments.get('correction_vector_matrix')
            photo_coords = arguments.get('photo_coordinates')
            corr_deg = arguments.get('correction_degree')
            picrs = arguments.get('photo_icrs')
            meta = PhotoMeta(
                linked_image=linked_image,
                plate_solve_arguments=plate_args,
                photo_full_resolution=tuple(pf) if pf else None,
                phone_sensor_size=tuple(ps) if ps else None,
                phone_focal_length=float(fl) if fl is not None else None,
                photo_utc_timestamp=ts,
                photo_location=tuple(loc) if loc else None,
                phone_gravity_vector=tuple(grav) if grav else (0.0, 0.0, 0.0),
                correction_vector_matrix=corr_mat,
                photo_coordinates=tuple(photo_coords) if photo_coords else None,
                correction_degree=float(corr_deg) if corr_deg is not None else None,
                photo_icrs=tuple(picrs) if picrs else None,
            )
            return meta
        except Exception as e:
            print(f"Error preparing metadata: {e}")
            return None
    except Exception as e:
        print(f"Error in get_meta_scheme: {e}")
        return None


# drawing: wrapper to call tools.drawing
# Input: metadata dict, zenith pixel coords, coefficient location
# Output: path to charted image or None
drawing = tools.drawing


# solve_photo: perform plate solving and compute sky/location results for a single photo
# Input: PhotoMeta, config dict, and boolean flags controlling calibration/IMU behavior
# Output: dict with computed results and any updated metadata written back to image
def solve_photo(meta, arguments_c, is_calibrating=True, is_imu_correction_get=True, is_imu_correction_local_set=False):
    results = {
        'file': meta.linked_image,
        'correction_matrix': None,
        'charted_image': None,
        'calculated_photo_coordinates': None,
        'calculated_icrs_coordinates_epoch': None,
        'calculated_icrs_coordinates_j2000': None,
        'calculated_location': None,
        'approx_photo_coordinates': None,
        'approx_icrs_coordinated': None,
        'actual_location': None,
        'location_precision_km': None,
        'saved_combined_global_correction': None,
        'no_local_found_message': None,
        'no_match': False,
        'no_match_message': None,
        'error': None,
    }
    try:
        # Validate required parameters
        if meta.photo_full_resolution is None:
            raise ValueError("photo_full_resolution is required")
        if meta.phone_sensor_size is None:
            raise ValueError("phone_sensor_size is required")
        if meta.phone_focal_length is None:
            raise ValueError("phone_focal_length is required")
        if meta.photo_utc_timestamp is None:
            raise ValueError("photo_utc_timestamp is required")
        if meta.photo_location is None:
            raise ValueError("photo_location is required")
        
        # Explicitly name variables for clarity
        linked_image = meta.linked_image
        plate_solve_arguments = list(meta.plate_solve_arguments) if meta.plate_solve_arguments is not None else []
        full_width_px, full_height_px = meta.photo_full_resolution if meta.photo_full_resolution is not None else (None, None)
        sensor_width_mm, sensor_height_mm = meta.phone_sensor_size if meta.phone_sensor_size is not None else (None, None)
        focal_length_mm = meta.phone_focal_length
        observation_timestamp = meta.photo_utc_timestamp
        actual_latitude, actual_longitude = meta.photo_location if meta.photo_location is not None else (None, None)
        gravity_x, gravity_y, gravity_z = meta.phone_gravity_vector
        local_correction_matrix = np.asarray(meta.correction_vector_matrix) if meta.correction_vector_matrix is not None else None
        local_photo_x, local_photo_y = meta.photo_coordinates if meta.photo_coordinates is not None else (None, None)
        local_correction_degree = meta.correction_degree
        photo_icrs = meta.photo_icrs

        camera_data = [[full_width_px, full_height_px], [sensor_width_mm, sensor_height_mm], focal_length_mm]
        photo_data = [[full_width_px, full_height_px], observation_timestamp, [actual_latitude, actual_longitude]]
        orientation_vector = np.array([gravity_x, gravity_y, gravity_z], dtype=np.float64)

        # ensure WCS present or run plate solver
        output_directory = arguments_c.get('output_directory')
        if output_directory is None:
            output_directory = str(Path(linked_image).with_suffix('.jpg.d'))
        wcs_fits = str(Path(output_directory) / "wcs.fits")

        print(f"\n{'='*60}")
        print(f"PLATE SOLVE PHASE")
        print(f"{'='*60}")
        print(f"Checking for WCS at: {wcs_fits}")
        sys.stdout.flush()
        
        if not Path(wcs_fits).exists():
            print(f"Creating output directory: {output_directory}")
            Path(output_directory).mkdir(parents=True, exist_ok=True)
            print("WCS file not found - running plate solver...")
            print()
            sys.stdout.flush()
            solved = plate_solve.plate_solve(
                str(Path(linked_image)), output_directory,
                plate_solve_arguments, arguments_c,
            )
            print()
            sys.stdout.flush()
            # `plate_solve` returns False when the solver ran cleanly but
            # could not match the field (e.g. not enough stars / image is
            # not of the sky). This is an expected outcome, not an error.
            if solved is False:
                results['no_match'] = True
                results['no_match_message'] = (
                    "Could not identify any stars in this image."
                )
                print("INFO: plate solver finished without a match; "
                      "returning no-match result without computing coordinates.")
                sys.stdout.flush()
                return _sanitize(results)
        else:
            print("WCS file already exists - skipping solve")
            sys.stdout.flush()

        if not Path(wcs_fits).exists():
            # Defensive: solver said it succeeded but no WCS on disk.
            # Treat as a real error (rare; usually indicates a bug).
            raise RuntimeError(f"WCS file still missing after solve attempt: {wcs_fits}")
        
        print(f"✓ WCS file verified: {wcs_fits}")
        print(f"{'='*60}\n")
        sys.stdout.flush()

        # compute observed zenith pixel coordinates
        print(f"COORDINATE COMPUTATION PHASE")
        print(f"{'='*60}")
        print("Computing zenith pixel coordinates...")
        sys.stdout.flush()
        obs_zenith_xy = tools.find_xy_via_orientation(camera_data[0], camera_data[1], camera_data[2], photo_data[0], orientation_vector / np.linalg.norm(orientation_vector))
        obs_angle_deg = tools.pixel_angle_deg_from_center(obs_zenith_xy, camera_data)
        print(f"Observed zenith angle: {obs_angle_deg}°")

        # apply global correction if found in config and requested
        cm_list = arguments_c.get('correction_matrix', [])
        selected_matrix = None
        for entry in cm_list:
            try:
                rng = entry[0]
                mat = np.asarray(entry[1], dtype=np.float64)
                if len(rng) >= 2 and rng[0] <= obs_angle_deg < rng[1]:
                    selected_matrix = mat
                    break
            except Exception:
                continue
        if selected_matrix is not None and is_imu_correction_get:
            orientation_vector = selected_matrix @ orientation_vector
            obs_zenith_xy = tools.find_xy_via_orientation(camera_data[0], camera_data[1], camera_data[2], photo_data[0], orientation_vector / np.linalg.norm(orientation_vector))
            obs_angle_deg = tools.pixel_angle_deg_from_center(obs_zenith_xy, camera_data)

        # compute ICRS coordinates via WCS
        print(f"DEBUG: Computing ICRS via WCS: {wcs_fits}")
        obs_zenith_icrs = tools.find_icrs_via_xy(wcs_fits, obs_zenith_xy)
        print(f"DEBUG: Obs zenith ICRS: {obs_zenith_icrs}")
        obs_epoch = Time(Time(observation_timestamp, scale='utc').to_value('decimalyear'), format='jyear')
        source = SkyCoord(ra=obs_zenith_icrs[0] * u.deg, dec=obs_zenith_icrs[1] * u.deg, frame=FK5(equinox=obs_epoch))
        result = source.transform_to(FK5(equinox=Time(2000.0, format='jyear')))
        obs_zenith_icrs_j2000 = [float(result.ra.deg), float(result.dec.deg)]

        # location initial guess: use embedded photo_icrs if available, otherwise compute
        loc_best_guess = None
        if photo_icrs is not None:
            try:
                loc_best_guess = [float(photo_icrs[0]), float(photo_icrs[1])]
            except Exception:
                loc_best_guess = None
        if loc_best_guess is None:
            try:
                loc_best_guess = tools.find_location_via_icrs(obs_zenith_icrs_j2000[0], obs_zenith_icrs_j2000[1], observation_timestamp)
                set_meta_scheme(linked_image,
                                linked_image=linked_image,
                                plate_solve_arguments=plate_solve_arguments,
                                photo_full_resolution=[full_width_px, full_height_px] if full_width_px and full_height_px else None,
                                phone_sensor_size=[sensor_width_mm, sensor_height_mm] if sensor_width_mm and sensor_height_mm else None,
                                phone_focal_length=focal_length_mm,
                                photo_utc_timestamp=observation_timestamp,
                                photo_location=[actual_latitude, actual_longitude] if actual_latitude is not None else None,
                                phone_gravity_vector=[gravity_x, gravity_y, gravity_z],
                                correction_vector_matrix=meta.correction_vector_matrix,
                                photo_coordinates=[local_photo_x, local_photo_y] if local_photo_x is not None else None,
                                correction_degree=local_correction_degree,
                                photo_icrs=loc_best_guess)
                results['photo_icrs_saved'] = loc_best_guess
            except Exception:
                loc_best_guess = None

        obs_location = tools.find_location_via_icrs(obs_zenith_icrs_j2000[0], obs_zenith_icrs_j2000[1], observation_timestamp, loc_best_guess)
        print(f"DEBUG: Computed location: {obs_location}")

        results.update({'calculated_photo_coordinates': obs_zenith_xy,
                        'calculated_icrs_coordinates_epoch': obs_zenith_icrs,
                        'calculated_icrs_coordinates_j2000': obs_zenith_icrs_j2000,
                        'calculated_location': obs_location})

        # perform local calibration if requested and actual GPS is available
        if is_calibrating and actual_latitude is not None:
            print(f"DEBUG: Calibrating with actual location: {actual_latitude}, {actual_longitude}")
            apr_zenith_icrs = tools.find_icrs_via_location(observation_timestamp, actual_latitude, actual_longitude)
            apr_zenith_xy = tools.find_xy_via_icrs(wcs_fits, apr_zenith_icrs)
            results['approx_photo_coordinates'] = apr_zenith_xy
            results['approx_icrs_coordinated'] = apr_zenith_icrs
            results['actual_location'] = [actual_latitude, actual_longitude]
            if is_imu_correction_local_set and not is_imu_correction_get:
                apr_zenith_vector = tools.pixel_to_ray(apr_zenith_xy[0], apr_zenith_xy[1], camera_data)
                obs_zenith_vector = tools.pixel_to_ray(obs_zenith_xy[0], obs_zenith_xy[1], camera_data)
                cor_matrix = tools.rotation_from_vectors(obs_zenith_vector, apr_zenith_vector)
                apr_angle_deg = tools.pixel_angle_deg_from_center(apr_zenith_xy, camera_data)
                set_meta_scheme(linked_image,
                                linked_image=linked_image,
                                plate_solve_arguments=plate_solve_arguments,
                                photo_full_resolution=[full_width_px, full_height_px] if full_width_px and full_height_px else None,
                                phone_sensor_size=[sensor_width_mm, sensor_height_mm] if sensor_width_mm and sensor_height_mm else None,
                                phone_focal_length=focal_length_mm,
                                photo_utc_timestamp=observation_timestamp,
                                photo_location=[actual_latitude, actual_longitude],
                                phone_gravity_vector=[gravity_x, gravity_y, gravity_z],
                                correction_vector_matrix=cor_matrix.tolist(),
                                photo_coordinates=[float(apr_zenith_xy[0]), float(apr_zenith_xy[1])],
                                correction_degree=float(apr_angle_deg),
                                photo_icrs=photo_icrs)
                results['correction_matrix'] = cor_matrix.tolist()

        # global calibration is handled by `calibrate_correction` (operates across images)
        results['no_local_found_message'] = None

        charted = drawing(asdict(meta), obs_zenith_xy, apr_zenith_xy if is_calibrating and actual_latitude is not None else None)
        results['charted_image'] = charted

        if results.get('actual_location') and results.get('calculated_location'):
            location_precision_km = round(((results['actual_location'][0] - results['calculated_location'][0])**2 + (results['actual_location'][1] - results['calculated_location'][1])**2) ** 0.5 * 111, 2)
            results['location_precision_km'] = location_precision_km
    except Exception as e:
        import traceback
        error_msg = str(e)
        tb_msg = traceback.format_exc()
        print(f"ERROR in solve_photo: {error_msg}")
        print(f"Traceback: {tb_msg}")
        results['error'] = error_msg

    return _sanitize(results)


def _sanitize(obj):
    """Recursively convert numpy types and arrays into plain Python so the
    result dict is JSON-serializable by `solve_photo_from_json`."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if hasattr(obj, 'tolist') and not isinstance(obj, str):
        try:
            return _sanitize(obj.tolist())
        except Exception:
            pass
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    return obj


def solve_photo_from_json(json_string):
    try:
        data = json.loads(json_string)
        image_name = data.get("input_image")
        
        print(f"\n{'#'*60}")
        print(f"# STARGAZER PLATE SOLVE - STARTED")
        print(f"{'#'*60}")
        print(f"Image: {image_name}")
        print(f"Timestamp: {data.get('photo_data', [None, None])[1]}")
        print(f"Location: {data.get('photo_data', [None, None, None])[2]}")
        print(f"Plate solver parameters: {data.get('plate_solve_parameters', [])}")
        print(f"{'#'*60}\n")
        sys.stdout.flush()
        
        if not image_name:
            return json.dumps({"error": "'input_image' not found in JSON data"})

        # Build a minimal PhotoMeta from the provided JSON
        camera_data = data.get("camera_data", [])
        photo_data = data.get("photo_data", [])
        orientation_data = data.get("orientation_data", [])

        photo_size = tuple(camera_data[0]) if len(camera_data) > 0 else None
        sensor_size = tuple(camera_data[1]) if len(camera_data) > 1 else None
        focal_length = float(camera_data[2]) if len(camera_data) > 2 else None

        timestamp = photo_data[1] if len(photo_data) > 1 else None
        location = tuple(photo_data[2]) if len(photo_data) > 2 and photo_data[2] else None

        gravity = tuple(orientation_data[0]) if len(orientation_data) > 0 else (0.0, 0.0, 0.0)

        meta = PhotoMeta(
            linked_image=image_name,
            plate_solve_arguments=data.get("plate_solve_parameters", []),
            photo_full_resolution=photo_size,
            phone_sensor_size=sensor_size,
            phone_focal_length=focal_length,
            photo_utc_timestamp=timestamp,
            photo_location=location,
            phone_gravity_vector=gravity,
            correction_vector_matrix=None,
            photo_coordinates=None,
            correction_degree=None,
            photo_icrs=None,
        )

        config_path = data.get("app_config")
        if config_path:
            try:
                arguments_c = load_config(Path(config_path))
            except Exception:
                arguments_c = {}
        else:
            # Load config.json from working directory
            try:
                arguments_c = load_config(Path('config.json'))
            except Exception:
                arguments_c = {}
        backend_config_path = data.get("backend_config")
        if backend_config_path:
            arguments_c['backend_config'] = backend_config_path
        if data.get("output_directory"):
            arguments_c['output_directory'] = data.get("output_directory")
        if data.get("index_directory"):
            arguments_c['index_directory'] = data.get("index_directory") # Pass index directory

        res = solve_photo(meta, arguments_c)

        if res.get('error'):
            print(f"\n{'#'*60}")
            print(f"# STARGAZER PLATE SOLVE - FAILED")
            print(f"{'#'*60}")
            print(f"Error: {res['error']}")
            print(f"{'#'*60}\n")
            sys.stdout.flush()
        elif res.get('no_match'):
            print(f"\n{'#'*60}")
            print(f"# STARGAZER PLATE SOLVE - NO MATCH")
            print(f"{'#'*60}")
            print(res.get('no_match_message', 'Could not identify any stars in this image.'))
            print(f"{'#'*60}\n")
            sys.stdout.flush()
        else:
            print(f"\n{'#'*60}")
            print(f"# STARGAZER PLATE SOLVE - COMPLETED SUCCESSFULLY")
            print(f"{'#'*60}")
            print(f"ICRS (J2000): RA={res.get('calculated_icrs_coordinates_j2000', [None])[0]}°, Dec={res.get('calculated_icrs_coordinates_j2000', [None, None])[1]}°")
            print(f"Location: Lat={res.get('calculated_location', [None])[0]}, Lon={res.get('calculated_location', [None, None])[1]}")
            print(f"Location precision: {res.get('location_precision_km')} km")
            print(f"{'#'*60}\n")
            sys.stdout.flush()
        
        return json.dumps(res, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"\n{'#'*60}")
        print(f"# STARGAZER PLATE SOLVE - EXCEPTION")
        print(f"{'#'*60}")
        print(f"Exception: {str(e)}")
        print(f"{'#'*60}\n")
        sys.stdout.flush()
        return json.dumps({"error": str(e)})


# calibrate_correction: aggregate per-photo local corrections into global bins
# Input: config dict and optional list of image paths
# Output: list of combined matrices per degree bin, saved into config.json
def calibrate_correction(arguments_c, images=None):
    local_by_bin = {}
    degree_step = float(arguments_c.get('degree_step', 5.0))
    imgs = images if images is not None else list(Path('.').rglob('*.jpg'))
    for img in imgs:
        meta = get_meta_scheme(str(img))
        if not meta:
            continue
        if getattr(meta, 'correction_vector_matrix', None) is not None:
            try:
                mat = np.asarray(meta.correction_vector_matrix, dtype=np.float64)
                angle = float(meta.correction_degree or 0.0)
                if mat.shape == (3, 3):
                    bin_start = (int(angle // degree_step) * int(degree_step))
                    bin_key = (bin_start, bin_start + int(degree_step))
                    local_by_bin.setdefault(bin_key, []).append(mat)
            except Exception:
                continue
    if len(local_by_bin) == 0:
        return None
    cm_list = []
    for bin_key, mats in sorted(local_by_bin.items()):
        combined = tools.combine_rotation_corrections(mats)
        cm_list.append([[float(bin_key[0]), float(bin_key[1])], combined.tolist()])
    arguments_c['correction_matrix'] = cm_list
    config_path = Path(arguments_c.get('config_path', 'config.json'))
    save_config(config_path, arguments_c)
    return cm_list


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='cmd')

    p_set = sub.add_parser('set')
    p_set.add_argument('metadata_json')
    p_set.add_argument('image')

    p_get = sub.add_parser('get')
    p_get.add_argument('image')

    p_solve = sub.add_parser('solve')
    p_solve.add_argument('image')
    p_solve.add_argument('--no-calibrate', dest='calibrate', action='store_false')
    p_solve.add_argument('--no-imu-get', dest='imu_get', action='store_false')
    p_solve.add_argument('--imu-local-set', dest='imu_local_set', action='store_true')

    p_cal = sub.add_parser('calibrate')
    p_cal.add_argument('--images', nargs='*')

    p_json_solve = sub.add_parser('json_solve')
    p_json_solve.add_argument('json_string')

    args = parser.parse_args()
    if args.cmd == 'set':
        try:
            meta = load_config(Path(args.metadata_json))
        except Exception as e:
            print(f"Error: cannot load metadata file: {e}")
            sys.exit(1)
        res = set_meta_scheme(args.image,
                              linked_image=meta.get('linked_image'),
                              plate_solve_arguments=meta.get('plate_solve_arguments'),
                              photo_full_resolution=meta.get('photo_full_resolution'),
                              phone_sensor_size=meta.get('phone_sensor_size'),
                              phone_focal_length=meta.get('phone_focal_length'),
                              photo_utc_timestamp=meta.get('photo_utc_timestamp'),
                              photo_location=meta.get('photo_location'),
                              phone_gravity_vector=meta.get('phone_gravity_vector'),
                              correction_vector_matrix=meta.get('correction_vector_matrix'),
                              photo_coordinates=meta.get('photo_coordinates'),
                              correction_degree=meta.get('correction_degree'),
                              photo_icrs=meta.get('photo_icrs'))
        sys.exit(0 if res else 2)

    if args.cmd == 'get':
        meta = get_meta_scheme(args.image)
        if meta is None:
            print('{}')
        else:
            print(json.dumps(asdict(meta), ensure_ascii=False, indent=2))
        sys.exit(0)

    if args.cmd == 'solve':
        img = args.image
        arguments_c = load_config(Path('config.json'))
        meta = get_meta_scheme(img)
        if not meta:
            print('No metadata found in image')
            sys.exit(2)
        res = solve_photo(meta,
                  arguments_c,
                  is_calibrating=args.calibrate,
                  is_imu_correction_get=args.imu_get,
                  is_imu_correction_local_set=args.imu_local_set)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        sys.exit(0)

    if args.cmd == 'json_solve':
        solve_photo_from_json(args.json_string)
        sys.exit(0)

    if args.cmd == 'calibrate':
        arguments_c = load_config(Path('config.json'))
        imgs = args.images if args.images else None
        cm = calibrate_correction(arguments_c, images=[Path(i) for i in imgs] if imgs else None)
        if cm is None:
            print('No local corrections found in images')
            sys.exit(2)
        print('Saved combined global correction for %d bins' % len(cm))
        sys.exit(0)

    parser.print_help()
    sys.exit(1)
