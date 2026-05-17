import json
import sys
import time
from pathlib import Path
from io import StringIO
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


class DualWriter:
    def __init__(self, log_file_path):
        self.log_file = open(log_file_path, 'w', buffering=1)
        self.original_stdout = sys.stdout

    def write(self, text):
        self.log_file.write(text)
        self.log_file.flush()
        self.original_stdout.write(text)
        self.original_stdout.flush()

    def flush(self):
        self.log_file.flush()
        self.original_stdout.flush()

    def close(self):
        self.log_file.close()


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
    correction_degree: object  # actual zenith offset (from GPS + WCS)
    photo_icrs: object
    calibration_quality_score: float = -1.0
    observed_zenith_offset: float = -1.0  # observed zenith offset (from phone sensors) - used for binning


def format_metadata_delimited(meta, correction_matrix=None, correction_degree=None):
    """Format PhotoMeta to delimited string for EXIF storage.
    Format: META|timestamp|photoW|photoH|matrixW|matrixH|focalLen|gravityX|gravityY|gravityZ|lat|lon|v00|v01|v02|v10|v11|v12|v20|v21|v22|degree
    """
    try:
        parts = ["META"]

        # timestamp
        parts.append(meta.photo_utc_timestamp or "")

        # photo dimensions
        if meta.photo_full_resolution:
            parts.append(str(int(meta.photo_full_resolution[0])))
            parts.append(str(int(meta.photo_full_resolution[1])))
        else:
            parts.append("0")
            parts.append("0")

        # sensor matrix dimensions
        if meta.phone_sensor_size:
            parts.append(str(float(meta.phone_sensor_size[0])))
            parts.append(str(float(meta.phone_sensor_size[1])))
        else:
            parts.append("0")
            parts.append("0")

        # focal length
        parts.append(str(float(meta.phone_focal_length)) if meta.phone_focal_length else "0")

        # gravity vector
        if meta.phone_gravity_vector and len(meta.phone_gravity_vector) >= 3:
            parts.append(str(float(meta.phone_gravity_vector[0])))
            parts.append(str(float(meta.phone_gravity_vector[1])))
            parts.append(str(float(meta.phone_gravity_vector[2])))
        else:
            parts.append("0")
            parts.append("0")
            parts.append("0")

        # location
        if meta.photo_location and len(meta.photo_location) >= 2:
            parts.append(str(float(meta.photo_location[0])))
            parts.append(str(float(meta.photo_location[1])))
        else:
            parts.append("0")
            parts.append("0")

        # correction matrix (9 values)
        if correction_matrix is not None:
            try:
                mat = np.asarray(correction_matrix, dtype=np.float64)
                if mat.shape == (3, 3):
                    for i in range(3):
                        for j in range(3):
                            parts.append(str(float(mat[i, j])))
                else:
                    # Invalid shape, add zeros
                    for _ in range(9):
                        parts.append("0")
            except Exception:
                for _ in range(9):
                    parts.append("0")
        else:
            for _ in range(9):
                parts.append("0")

        # correction degree
        if correction_degree is not None:
            parts.append(str(float(correction_degree)))
        else:
            parts.append("-1.0")

        return "|".join(parts)
    except Exception as e:
        print(f"Error formatting delimited metadata: {e}")
        return None


def parse_metadata_delimited(delimited_str):
    """Parse delimited metadata string back to PhotoMeta.
    Backwards compatible - quality_score is optional (field 23).
    Returns PhotoMeta instance or None on error.
    """
    try:
        if not delimited_str or not delimited_str.startswith("META"):
            return None

        parts = delimited_str.split("|")
        if len(parts) < 22:  # META + 21 fields minimum
            print(f"Invalid delimited metadata: expected >= 22 parts, got {len(parts)}")
            return None

        idx = 1
        timestamp = parts[idx]; idx += 1
        photoW = int(parts[idx]); idx += 1
        photoH = int(parts[idx]); idx += 1
        matrixW = float(parts[idx]); idx += 1
        matrixH = float(parts[idx]); idx += 1
        focalLen = float(parts[idx]); idx += 1
        gravityX = float(parts[idx]); idx += 1
        gravityY = float(parts[idx]); idx += 1
        gravityZ = float(parts[idx]); idx += 1
        lat = float(parts[idx]); idx += 1
        lon = float(parts[idx]); idx += 1

        # Parse 3x3 matrix
        matrix = [[0.0]*3 for _ in range(3)]
        has_matrix = False
        for i in range(3):
            for j in range(3):
                val = float(parts[idx]); idx += 1
                matrix[i][j] = val
                if val != 0:
                    has_matrix = True

        degree = float(parts[idx]) if len(parts) > 21 else -1.0; idx += 1

        # Parse quality score (optional, backwards compatible)
        quality_score = -1.0
        if len(parts) > 22:
            try:
                quality_score = float(parts[22])
            except (ValueError, IndexError):
                quality_score = -1.0

        # Parse observed zenith offset (optional, backwards compatible)
        observed_zenith = -1.0
        if len(parts) > 23:
            try:
                observed_zenith = float(parts[23])
            except (ValueError, IndexError):
                observed_zenith = -1.0

        # Build PhotoMeta
        meta = PhotoMeta(
            linked_image="",
            plate_solve_arguments=[],
            photo_full_resolution=(photoW, photoH) if photoW and photoH else None,
            phone_sensor_size=(matrixW, matrixH) if matrixW and matrixH else None,
            phone_focal_length=focalLen if focalLen else None,
            photo_utc_timestamp=timestamp if timestamp else None,
            photo_location=(lat, lon) if lat or lon else None,
            phone_gravity_vector=(gravityX, gravityY, gravityZ),
            correction_vector_matrix=matrix if has_matrix else None,
            photo_coordinates=None,
            correction_degree=degree if degree >= 0 else None,
            photo_icrs=None,
            calibration_quality_score=quality_score,
            observed_zenith_offset=observed_zenith,
        )
        return meta
    except Exception as e:
        print(f"Error parsing delimited metadata: {e}")
        return None


# load_config: read JSON file and return parsed dict
# Input: path to JSON file (string or Path)
# Output: Python dict (empty dict if file missing)
def load_config(path):
    if isinstance(path, str):
        path = Path(path)
    if not path.exists():
        print(f"Config file not found: {path}, using defaults")
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# save_config: write dict to JSON file
# Input: path (string or Path) and data dict
# Output: path
def save_config(path, data):
    if isinstance(path, str):
        path = Path(path)
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
                    photo_icrs=None,
                    calibration_quality_score=None,
                    observed_zenith_offset=None):
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
        if calibration_quality_score is not None:
            meta['calibration_quality_score'] = float(calibration_quality_score)
        if observed_zenith_offset is not None:
            meta['observed_zenith_offset'] = float(observed_zenith_offset)

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
            user_comment = s

        # Try delimited format first (new schema: META|...)
        if isinstance(user_comment, str) and user_comment.startswith('META'):
            meta = parse_metadata_delimited(user_comment)
            if meta is not None:
                meta.linked_image = img_path.name
                print(f"Parsed delimited metadata from {img_path}")
                return meta
            # Fall through to JSON parsing if delimited parse fails

        # Fall back to JSON format (legacy)
        if isinstance(user_comment, str):
            idx = None
            for ch in ['{', '[']:
                i = user_comment.find(ch)
                if i != -1:
                    if idx is None or i < idx:
                        idx = i
            if idx is not None and idx > 0:
                user_comment = user_comment[idx:]

        try:
            arguments = json.loads(user_comment)
        except Exception as e:
            print(f"Error: embedded metadata is not valid JSON or delimited format: {e}")
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
            qual_score = arguments.get('calibration_quality_score')
            obs_zenith = arguments.get('observed_zenith_offset')
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
                calibration_quality_score=float(qual_score) if qual_score is not None else -1.0,
                observed_zenith_offset=float(obs_zenith) if obs_zenith is not None else -1.0,
            )
            return meta
        except Exception as e:
            print(f"Error preparing metadata: {e}")
            return None
    except Exception as e:
        print(f"Error in get_meta_scheme: {e}")
        return None


# get_meta_scheme_json: wrapper to return metadata as JSON string
# Input: image path
# Output: JSON string or empty object
def get_meta_scheme_json(image_path):
    meta = get_meta_scheme(image_path)
    if meta is None:
        return json.dumps({})
    return json.dumps(asdict(meta), ensure_ascii=False, indent=2)


# drawing: wrapper to call tools.drawing
# Input: metadata dict, zenith pixel coords, coefficient location
# Output: path to charted image or None
drawing = tools.drawing


# solve_photo: perform plate solving and compute sky/location results for a single photo
# Input: PhotoMeta, config dict, and boolean flags controlling calibration/IMU behavior
# Output: dict with computed results and any updated metadata written back to image
def solve_photo(meta, arguments_c, is_calibrating=True, is_imu_correction_get=True, is_imu_correction_local_set=False):
    start_time = time.time()
    print(f"DEBUG SOLVE_START: local_set={is_imu_correction_local_set}, global_get={is_imu_correction_get}, calibrating={is_calibrating}")
    print(f"DEBUG: Config has {len(arguments_c.get('correction_matrix', []))} bins")
    sys.stdout.flush()
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
        'calibration_quality_score': None,
        'execution_time_ms': None,
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

        if not Path(wcs_fits).exists():
            Path(output_directory).mkdir(parents=True, exist_ok=True)
            print("Running astrometry.net solver...")
            sys.stdout.flush()
            solved = plate_solve.plate_solve(
                str(Path(linked_image)), output_directory,
                plate_solve_arguments, arguments_c,
            )
            if solved is False:
                results['no_match'] = True
                results['no_match_message'] = "Could not identify any stars in this image."
                print("No matching star pattern found")
                print()
                sys.stdout.flush()
                return _sanitize(results)

        if not Path(wcs_fits).exists():
            raise RuntimeError(f"WCS file missing after solve: {wcs_fits}")

        obs_zenith_xy = tools.find_xy_via_orientation(camera_data[0], camera_data[1], camera_data[2], photo_data[0], orientation_vector / np.linalg.norm(orientation_vector))
        obs_angle_deg = tools.pixel_angle_deg_from_center(obs_zenith_xy, camera_data)
        print(f"Zenith offset from center: {obs_angle_deg:.1f}°")
        sys.stdout.flush()

        # apply global correction if found in config and requested
        # Format: [[bin_min, bin_max], matrix, num_photos, avg_quality] (backwards compatible with old 2-element format)
        cm_list = arguments_c.get('correction_matrix', [])
        print(f"DEBUG: is_imu_correction_get={is_imu_correction_get}, cm_list length={len(cm_list)}")
        if len(cm_list) > 0:
            print(f"DEBUG: Available bins: {[entry[0] for entry in cm_list]}")
        selected_matrix = None
        selected_bin_info = None
        for entry in cm_list:
            try:
                rng = entry[0]
                mat = np.asarray(entry[1], dtype=np.float64)
                print(f"DEBUG: Checking bin {rng} against obs_angle_deg={obs_angle_deg}")
                if len(rng) >= 2 and rng[0] <= obs_angle_deg < rng[1]:
                    selected_matrix = mat
                    # Extract metadata if present (new format)
                    if len(entry) >= 4:
                        selected_bin_info = {"num_photos": entry[2], "avg_quality": entry[3]}
                    print(f"DEBUG: BIN MATCHED! {rng}")
                    break
            except Exception as e:
                print(f"DEBUG: Error checking bin: {e}")
                continue
        if selected_matrix is None:
            print(f"DEBUG: No matching bin found for obs_angle_deg={obs_angle_deg}")
        if selected_matrix is not None and is_imu_correction_get:
            bin_info_str = ""
            if selected_bin_info:
                bin_info_str = f" (based on {selected_bin_info['num_photos']} photos, avg quality {selected_bin_info['avg_quality']}/100)"
            print(f"Applied global correction for zenith offset {obs_angle_deg:.1f}°{bin_info_str}")
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
        print(f"Location computed from sky: {obs_location[0]}, {obs_location[1]}")

        # Extract index name from solver output log
        index_name = "Unknown"
        try:
            log_path = Path(output_directory) / "solve.log"
            if log_path.exists():
                with open(log_path, 'r') as f:
                    for line in f:
                        if "solved with index" in line.lower():
                            # Extract index name: "solved with index <name>"
                            parts = line.split("index", 1)
                            if len(parts) > 1:
                                raw_name = parts[1].strip()
                                # Trim everything after first "."
                                if '.' in raw_name:
                                    index_name = raw_name.split('.')[0].strip()
                                else:
                                    index_name = raw_name.strip()
                                break
        except Exception as e:
            print(f"DEBUG: Could not extract index name from log: {e}")

        # Calculate zenith offset in km (~111 km/degree)
        zenith_offset_km = obs_angle_deg * 111.0

        results.update({'calculated_photo_coordinates': obs_zenith_xy,
                        'calculated_icrs_coordinates_epoch': obs_zenith_icrs,
                        'calculated_icrs_coordinates_j2000': obs_zenith_icrs_j2000,
                        'calculated_location': obs_location,
                        'zenith_offset_degrees': round(float(obs_angle_deg), 2),
                        'zenith_offset_km': round(float(zenith_offset_km), 2),
                        'index_name': index_name})

        # Default quality score (no GPS available)
        quality_score = -1.0

        # perform local calibration if requested and actual GPS is available
        if is_calibrating and actual_latitude is not None:
            print(f"GPS location: {actual_latitude}, {actual_longitude}")
            from math import radians, cos, sin, asin, sqrt
            lat1, lon1 = radians(actual_latitude), radians(actual_longitude)
            lat2, lon2 = radians(obs_location[0]), radians(obs_location[1])
            dlat, dlon = lat2 - lat1, lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * asin(sqrt(a))
            km = 6371 * c
            print(f"Location precision: {km:.1f} km")
            apr_zenith_icrs = tools.find_icrs_via_location(observation_timestamp, actual_latitude, actual_longitude)
            apr_zenith_xy = tools.find_xy_via_icrs(wcs_fits, apr_zenith_icrs)
            results['approx_photo_coordinates'] = apr_zenith_xy
            results['approx_icrs_coordinated'] = apr_zenith_icrs
            results['actual_location'] = [actual_latitude, actual_longitude]

            # Calculate quality score based on ERROR angle between observed and calculated zenith
            # Higher error = lower quality (not based on position in photo)
            try:
                obs_ray = tools.pixel_to_ray(obs_zenith_xy[0], obs_zenith_xy[1], camera_data)
                apr_ray = tools.pixel_to_ray(apr_zenith_xy[0], apr_zenith_xy[1], camera_data)
                cos_angle = np.clip(np.dot(obs_ray, apr_ray), -1, 1)
                error_angle_deg = np.degrees(np.arccos(cos_angle))
                # Quality: 0° error = 100, 20° error = 0 (stricter scale for IMU accuracy)
                max_error_deg = 20.0
                quality_score = max(0, 100 * (1 - error_angle_deg / max_error_deg))
                quality_score = round(quality_score, 1)
                print(f"Zenith error angle: {error_angle_deg:.2f}°, quality score: {quality_score}/100")
            except Exception as e:
                print(f"Error calculating quality score: {e}")
                quality_score = -1.0

            # Compute apr_angle_deg for correction_degree
            apr_angle_deg = tools.pixel_angle_deg_from_center(apr_zenith_xy, camera_data)

            print(f"DEBUG: Checking matrix write condition: local_set={is_imu_correction_local_set}, not global_get={not is_imu_correction_get}")
            sys.stdout.flush()
            if is_imu_correction_local_set and not is_imu_correction_get:
                print(f"DEBUG: Writing correction matrix to {linked_image}")
                sys.stdout.flush()
                apr_zenith_vector = tools.pixel_to_ray(apr_zenith_xy[0], apr_zenith_xy[1], camera_data)
                obs_zenith_vector = tools.pixel_to_ray(obs_zenith_xy[0], obs_zenith_xy[1], camera_data)
                cor_matrix = tools.rotation_from_vectors(obs_zenith_vector, apr_zenith_vector)
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
                                photo_icrs=photo_icrs,
                                calibration_quality_score=quality_score,
                                observed_zenith_offset=obs_angle_deg)
                results['correction_vector_matrix'] = cor_matrix.tolist()
                results['correction_degree'] = float(apr_angle_deg)
                print(f"DEBUG: Correction matrix saved to results: degree={apr_angle_deg}")
                sys.stdout.flush()
        else:
            print(f"GPS location: not available")

        # global calibration is handled by `calibrate_correction` (operates across images)
        results['no_local_found_message'] = None

        # Use apr_zenith_xy if available, else None
        apr_zenith_xy_for_drawing = apr_zenith_xy if (is_calibrating and actual_latitude is not None and 'approx_photo_coordinates' in results) else None
        charted = drawing(asdict(meta), obs_zenith_xy, apr_zenith_xy_for_drawing)
        results['charted_image'] = charted

        if results.get('actual_location') and results.get('calculated_location'):
            from math import radians, cos, sin, asin, sqrt
            lat1, lon1 = radians(results['actual_location'][0]), radians(results['actual_location'][1])
            lat2, lon2 = radians(results['calculated_location'][0]), radians(results['calculated_location'][1])
            dlat, dlon = lat2 - lat1, lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * asin(sqrt(a))
            location_precision_km = round(6371 * c, 2)
            results['location_precision_km'] = location_precision_km

            # Calculate zenith mismatch impact percentage
            if results.get('zenith_offset_km') and results.get('zenith_offset_km') > 0:
                zenith_offset_km = float(results['zenith_offset_km'])
                mismatch_impact_percent = round((zenith_offset_km / location_precision_km * 100), 2) if location_precision_km > 0 else 0
                results['zenith_mismatch_impact_percent'] = mismatch_impact_percent
                print(f"Zenith mismatch impact: {mismatch_impact_percent}%")

        # Set quality score in results (calculated above when GPS available)
        if quality_score >= 0:
            results['calibration_quality_score'] = quality_score
            print(f"Final quality score: {quality_score}/100")
        else:
            results['calibration_quality_score'] = -1.0
            print(f"Quality score: unavailable (no GPS data)")
    except Exception as e:
        import traceback
        error_msg = str(e)
        tb_msg = traceback.format_exc()
        print(f"ERROR in solve_photo: {error_msg}")
        print(f"Traceback: {tb_msg}")
        results['error'] = error_msg
    finally:
        execution_time_ms = int((time.time() - start_time) * 1000)
        results['execution_time_ms'] = execution_time_ms

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
    original_stdout = sys.stdout
    dual_writer = None

    try:
        data = json.loads(json_string)
        image_name = data.get("input_image")

        if not image_name:
            return json.dumps({"error": "'input_image' not found in JSON data"})

        output_directory = data.get("output_directory", "")
        if output_directory:
            log_file_path = str(Path(output_directory) / "solve.log")
            dual_writer = DualWriter(log_file_path)
            sys.stdout = dual_writer

        camera_data = data.get("camera_data", [])
        photo_data = data.get("photo_data", [])
        orientation_data = data.get("orientation_data", [])

        print(f"Image: {image_name}")

        if camera_data and len(camera_data) > 0:
            w, h = camera_data[0]
            print(f"Image size: {w}x{h} px")
        if camera_data and len(camera_data) > 1:
            sw, sh = camera_data[1]
            print(f"Sensor size: {sw}x{sh} mm")
        if camera_data and len(camera_data) > 2:
            print(f"Focal length: {camera_data[2]} mm")

        if photo_data and len(photo_data) > 1:
            print(f"Timestamp: {photo_data[1]}")
        if photo_data and len(photo_data) > 2 and photo_data[2]:
            lat, lon = photo_data[2]
            print(f"GPS location: {lat}, {lon}")

        if orientation_data and len(orientation_data) > 0:
            gx, gy, gz = orientation_data[0]
            print(f"Gravity vector: [{gx}, {gy}, {gz}]")

        params = data.get("plate_solve_parameters", [])
        if params:
            print(f"Solver parameters: {params}")

        print()
        sys.stdout.flush()

        photo_size = tuple(camera_data[0]) if len(camera_data) > 0 else None
        sensor_size = tuple(camera_data[1]) if len(camera_data) > 1 else None
        focal_length = float(camera_data[2]) if len(camera_data) > 2 else None

        timestamp = photo_data[1] if len(photo_data) > 1 else None
        location = tuple(photo_data[2]) if len(photo_data) > 2 and photo_data[2] else None

        gravity = tuple(orientation_data[0]) if len(orientation_data) > 0 else (0.0, 0.0, 0.0)

        meta = PhotoMeta(
            linked_image=image_name,
            plate_solve_arguments=params,
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

        config_data = data.get("app_config")
        if config_data:
            try:
                # If it's JSON string (from Java), parse it directly
                if isinstance(config_data, str) and config_data.startswith('{'):
                    arguments_c = json.loads(config_data)
                    print(f"DEBUG: Loaded config from JSON, has {len(arguments_c.get('correction_matrix', []))} bins")
                # If it's a path, load from file
                else:
                    arguments_c = load_config(Path(config_data))
                    print(f"DEBUG: Loaded config from file {config_data}, has {len(arguments_c.get('correction_matrix', []))} bins")
            except Exception as e:
                print(f"Error loading app_config: {e}")
                arguments_c = {}
        else:
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
            arguments_c['index_directory'] = data.get("index_directory")

        is_calibrating = data.get("is_calibrating", True)
        is_imu_correction_local_set = data.get("imu_correction_local_set", False)
        is_imu_correction_get = data.get("imu_correction_get", False)
        print(f"DEBUG JSON_PARAMS: is_calibrating={is_calibrating}, imu_correction_local_set={is_imu_correction_local_set}, imu_correction_get={is_imu_correction_get}")
        print(f"DEBUG JSON_KEYS: {list(data.keys())}")

        res = solve_photo(meta, arguments_c,
                         is_calibrating=is_calibrating,
                         is_imu_correction_get=is_imu_correction_get,
                         is_imu_correction_local_set=is_imu_correction_local_set)

        if res.get('error'):
            print(f"Error: {res['error']}")
        elif res.get('no_match'):
            print(res.get('no_match_message', 'Could not identify any stars in this image.'))

        print()
        sys.stdout.flush()

        res['log_file'] = log_file_path if dual_writer else ""
        sys.stdout = original_stdout
        if dual_writer:
            dual_writer.close()
        return json.dumps(res, ensure_ascii=False, indent=2)
    except Exception as e:
        sys.stdout = original_stdout
        if dual_writer:
            dual_writer.close()
        print(f"Error: {str(e)}", file=original_stdout)
        result = {"error": str(e)}
        return json.dumps(result)


# calibrate_correction: aggregate per-photo local corrections into global bins
# Input: config dict (JSON string or dict), optional list of image paths (can be Java ArrayList from Chaquopy)
# Output: JSON string with {matrices: [...], config: {...}}
def calibrate_correction(arguments_c, images=None):
    # Parse config if string (from Java)
    if isinstance(arguments_c, str):
        try:
            arguments_c = json.loads(arguments_c)
        except Exception as e:
            print(f"Error parsing config JSON: {e}")
            arguments_c = {}

    local_by_bin = {}
    quality_by_bin = {}
    degree_step = float(arguments_c.get('degree_step', 5.0))
    if images is not None:
        # Convert Java ArrayList to Python list using indexed access
        imgs = []
        for i in range(images.size()):
            imgs.append(str(images.get(i)))
    else:
        imgs = list(Path('.').rglob('*.jpg'))
    for img in imgs:
        meta = get_meta_scheme(str(img))
        if not meta:
            continue
        if getattr(meta, 'correction_vector_matrix', None) is not None:
            try:
                mat = np.asarray(meta.correction_vector_matrix, dtype=np.float64)
                # BIN BY OBSERVED ZENITH OFFSET (phone orientation), not actual offset
                # observed_zenith_offset = where phone thinks zenith is
                # This groups corrections by phone tilt, which is what we need for future corrections
                angle = float(meta.observed_zenith_offset or meta.correction_degree or 0.0)
                if mat.shape == (3, 3):
                    bin_start = (int(angle // degree_step) * int(degree_step))
                    bin_key = (bin_start, bin_start + int(degree_step))
                    local_by_bin.setdefault(bin_key, []).append(mat)
                    quality_by_bin.setdefault(bin_key, []).append(getattr(meta, 'calibration_quality_score', -1.0))
            except Exception:
                continue
    if len(local_by_bin) == 0:
        return json.dumps({"matrices": None, "config": arguments_c})
    cm_list = []
    for bin_key, mats in sorted(local_by_bin.items()):
        # Pass quality scores to weighting algorithm
        qualities = quality_by_bin.get(bin_key, None)
        combined = tools.combine_rotation_corrections(mats, quality_scores=qualities)
        num_photos = len(mats)
        avg_quality = np.mean([q for q in qualities if q > 0]) if qualities and any(q > 0 for q in qualities) else -1
        print(f"Bin {bin_key}: {num_photos} photos, avg quality {avg_quality:.1f}/100")
        # Store: [bin_range, matrix, num_photos_used, avg_quality_score]
        cm_list.append([
            [float(bin_key[0]), float(bin_key[1])],
            combined.tolist(),
            num_photos,
            round(float(avg_quality), 1) if avg_quality >= 0 else -1.0
        ])
    arguments_c['correction_matrix'] = cm_list
    print(f"Computed {len(cm_list)} correction bins from {sum(len(mats) for mats in local_by_bin.values())} images")
    # Return both matrices and updated config for Java to save
    return json.dumps({"matrices": cm_list, "config": arguments_c}, ensure_ascii=False, indent=2)


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
