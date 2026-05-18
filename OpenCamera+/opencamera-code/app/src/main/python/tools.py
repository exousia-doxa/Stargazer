from astropy.time import Time
from astropy import units as u
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
from astropy.utils.iers import iers, IERS_A
import numpy as np
from astropy import wcs
from astropy.io import fits
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
import urllib.request
import urllib.error
import socket

# Keep auto_download enabled by default; only disable if cache successfully loads
# If cache load fails, astropy will auto-download or use IERS-B as fallback
# This ensures coordinate transforms work even without cached IERS

### IERS SYNC & CACHE MANAGEMENT

def sync_iers_data(cache_dir: str) -> dict:
    """Download IERS Finals2000A data from official sources, cache locally.

    Returns: {"success": bool, "message": str, "timestamp": str|None}
    """
    result = {"success": False, "message": "", "timestamp": None}
    try:
        cache_path = Path(cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)
        iers_file = cache_path / "finals2000A.all"

        print(f"[IERS] Starting sync to {iers_file}")
        sys.stdout.flush()

        # Try primary source
        urls = [
            "https://datacenter.iers.org/data/9/finals2000A.all",
            "https://maia.usno.navy.mil/ser7/finals2000A.all"
        ]

        downloaded = False
        for url in urls:
            try:
                print(f"[IERS] Attempting download from {url}")
                sys.stdout.flush()

                # Add User-Agent header for compatibility with strict servers
                req = urllib.request.Request(
                    url,
                    headers={'User-Agent': 'Stargazer/1.0 (Android Astronomy App)'}
                )
                # Increased timeout for slow/congested networks
                with urllib.request.urlopen(req, timeout=30) as response:
                    data = response.read()

                with open(iers_file, 'wb') as f:
                    f.write(data)

                downloaded = True
                size_kb = len(data) / 1024
                print(f"[IERS] Downloaded {size_kb:.1f} KB from {url}")
                sys.stdout.flush()
                break

            except urllib.error.HTTPError as e:
                print(f"[IERS] HTTP {e.code} from {url}")
                sys.stdout.flush()
            except urllib.error.URLError as e:
                print(f"[IERS] URL error from {url}: {e.reason}")
                sys.stdout.flush()
            except socket.timeout:
                print(f"[IERS] Timeout from {url}")
                sys.stdout.flush()
            except Exception as e:
                print(f"[IERS] Error from {url}: {type(e).__name__}: {e}")
                sys.stdout.flush()

        if not downloaded:
            result["message"] = "Could not download from any IERS source (network unavailable?)"
            print(f"[IERS] {result['message']}")
            sys.stdout.flush()
            return result

        # Validate file exists and has reasonable size
        if not iers_file.exists():
            result["message"] = "Downloaded file disappeared"
            print(f"[IERS] ERROR: {result['message']}")
            sys.stdout.flush()
            return result

        file_size = iers_file.stat().st_size
        if file_size < 10000:  # IERS files are ~90KB
            result["message"] = f"Downloaded file too small ({file_size} bytes)"
            print(f"[IERS] ERROR: {result['message']}")
            sys.stdout.flush()
            return result

        # Validate it's actual IERS format (starts with version line)
        try:
            with open(iers_file, 'r', errors='ignore') as f:
                first_line = f.readline()
                if not ('2000' in first_line or 'IERS' in first_line):
                    result["message"] = "Downloaded file does not appear to be valid IERS data"
                    print(f"[IERS] WARNING: {result['message']}")
                    sys.stdout.flush()
        except Exception as e:
            print(f"[IERS] Could not validate file format: {e}")
            sys.stdout.flush()

        # Record sync timestamp
        now_iso = datetime.utcnow().isoformat() + "Z"

        # Write metadata
        meta_file = cache_path / "iers_sync_meta.json"
        meta = {
            "last_sync": now_iso,
            "file_size": file_size,
            "source": url
        }
        with open(meta_file, 'w') as f:
            json.dump(meta, f)

        result["success"] = True
        result["timestamp"] = now_iso
        result["message"] = f"Synced {file_size/1024:.1f} KB from IERS"
        print(f"[IERS] SUCCESS: {result['message']}")
        sys.stdout.flush()
        return result

    except Exception as e:
        import traceback
        result["message"] = f"Sync exception: {type(e).__name__}: {e}"
        print(f"[IERS] ERROR: {result['message']}")
        print(f"[IERS] Traceback: {traceback.format_exc()}")
        sys.stdout.flush()
        return result


def load_iers_from_cache(cache_dir: str) -> dict:
    """Load cached IERS data into astropy. Configure astropy to use it.

    Returns: {"success": bool, "message": str, "using_cache": bool}
    """
    result = {"success": False, "message": "", "using_cache": False}
    try:
        cache_path = Path(cache_dir)
        iers_file = cache_path / "finals2000A.all"

        if not iers_file.exists():
            result["message"] = f"Cache file not found: {iers_file}"
            print(f"[IERS] WARNING: {result['message']}")
            sys.stdout.flush()
            return result

        print(f"[IERS] Loading cached IERS from {iers_file}")
        sys.stdout.flush()

        try:
            # Load cached IERS data and register with astropy
            iers_data = IERS_A.read(str(iers_file))

            # Update astropy's active IERS table so FK5 transforms use loaded data
            # This ensures all coordinate transformations use the cached IERS
            iers.IERS_A_FILE = str(iers_file)

            # Keep auto_download enabled: astropy will prefer loaded cache,
            # but can auto-fetch if needed. This ensures FK5 transforms always have valid IERS.
            # (auto_download was already default=True, no need to change)

            result["success"] = True
            result["using_cache"] = True
            result["message"] = f"Loaded IERS cache ({len(iers_data)} entries)"
            print(f"[IERS] SUCCESS: Cache loaded with {len(iers_data)} entries, registered with astropy")
            print(f"[IERS] IERS_A_FILE: {iers.IERS_A_FILE}")
            sys.stdout.flush()
            return result
        except Exception as e:
            result["message"] = f"Could not load IERS file: {e}"
            print(f"[IERS] ERROR: {result['message']}")
            print(f"[IERS] WARNING: Keeping auto_download enabled for fallback")
            sys.stdout.flush()
            return result

    except Exception as e:
        import traceback
        result["message"] = f"Load exception: {type(e).__name__}: {e}"
        print(f"[IERS] ERROR: {result['message']}")
        print(f"[IERS] Traceback: {traceback.format_exc()}")
        sys.stdout.flush()
        return result


def iers_needs_sync(last_sync_iso: str, hours_interval: int) -> bool:
    """Check if IERS cache needs refresh based on interval.

    last_sync_iso: ISO 8601 timestamp string (or None for never)
    hours_interval: threshold in hours

    Returns: True if sync needed, False otherwise
    """
    try:
        if not last_sync_iso:
            print(f"[IERS] Never synced before, sync needed")
            return True

        try:
            last_sync = datetime.fromisoformat(last_sync_iso.replace('Z', '+00:00'))
        except Exception as e:
            print(f"[IERS] Could not parse last_sync timestamp: {e}, forcing sync")
            return True

        now = datetime.utcnow()
        elapsed = now - last_sync
        threshold = timedelta(hours=hours_interval)

        needs_sync = elapsed > threshold
        if needs_sync:
            hours_old = elapsed.total_seconds() / 3600
            print(f"[IERS] Cache is {hours_old:.1f}h old, sync needed (interval={hours_interval}h)")
        else:
            hours_remain = (threshold - elapsed).total_seconds() / 3600
            print(f"[IERS] Cache fresh, next sync in {hours_remain:.1f}h")

        return needs_sync

    except Exception as e:
        print(f"[IERS] Error checking sync need: {e}, forcing sync")
        return True


def read_iers_sync_metadata(cache_dir: str) -> dict:
    """Read last sync timestamp from metadata file.

    Returns: {"last_sync": str|None, "file_size": int, "source": str}
    """
    try:
        meta_file = Path(cache_dir) / "iers_sync_meta.json"
        if not meta_file.exists():
            return {"last_sync": None, "file_size": 0, "source": ""}

        with open(meta_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[IERS] Could not read metadata: {e}")
        return {"last_sync": None, "file_size": 0, "source": ""}


### LEGACY

def find_location_via_icrs(
        ra_deg: float,
        dec_deg: float,
        obs_time,
        init_guess=(0.0, 0.0),
        coarse_search: bool = False):
    """Estimate Earth location via adaptive grid search.

    coarse_search=True: Start 10° step (global search)
    coarse_search=False: Start 0.1° step (local refinement from cached location)
    """
    target_coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame='icrs')
    best_lat, best_lon = float(init_guess[0]), float(init_guess[1])
    best_sep_deg = float('inf')

    step_deg = 10.0 if coarse_search else 0.1
    precision_deg = 1e-4

    while step_deg >= precision_deg:
        sel_lat = (best_lat - step_deg, best_lat, best_lat + step_deg)
        sel_lon = (best_lon - step_deg, best_lon, best_lon + step_deg)
        improved = False

        for lat in sel_lat:
            if lat < -90.0 or lat > 90.0:
                continue
            for lon in sel_lon:
                lon_wrap = ((lon + 180.0) % 360.0) - 180.0
                location = EarthLocation(lat=lat * u.deg, lon=lon_wrap * u.deg, height=0 * u.m)
                point_altaz = SkyCoord(alt=90 * u.deg, az=0 * u.deg, frame=AltAz(obstime=Time(obs_time, scale='utc'), location=location))
                point_icrs = point_altaz.transform_to('icrs')
                sep_deg = target_coord.separation(point_icrs).deg
                if sep_deg < best_sep_deg:
                    best_sep_deg = sep_deg
                    best_lat, best_lon = lat, lon_wrap
                    improved = True

        if not improved:
            step_deg /= 10.0

    return [round(float(best_lat), 4), round(float(best_lon), 4)]

def find_icrs_via_location(obs_time, lat_deg: float, lon_deg: float):
    """Compute ICRS sky coordinates of zenith (alt=90°, az=0°) at Earth location and observation time."""
    location = EarthLocation(lat=lat_deg * u.deg, lon=lon_deg * u.deg, height=0 * u.m)
    point_altaz = SkyCoord(alt=90 * u.deg, az=0 * u.deg, frame=AltAz(obstime=Time(obs_time, scale='utc'), location=location))
    point_icrs = point_altaz.transform_to('icrs')

    return [float(point_icrs.ra.to(u.deg).value), float(point_icrs.dec.to(u.deg).value)]

def find_icrs_via_xy(wcs_filename, point_xy):
    """Convert pixel coordinates to ICRS (J2000) sky coordinates using linear WCS (no SIP distortion)."""
    with fits.open(wcs_filename) as hdulist:
        w = wcs.WCS(hdulist[0].header)

    return [float(w.wcs_pix2world(np.array([point_xy], dtype=np.float64), 0)[0][0]), float(w.wcs_pix2world(np.array([point_xy], dtype=np.float64), 0)[0][1])]

def check_wcs_has_sip(wcs_filename):
    """Check if WCS header contains SIP polynomial distortion coefficients."""
    try:
        with fits.open(wcs_filename) as hdulist:
            w = wcs.WCS(hdulist[0].header)
        return w.sip is not None
    except Exception:
        return False

def find_xy_via_icrs(wcs_filename, point_icrs):
    """Convert ICRS sky coordinates to distorted image pixel coordinates (includes SIP if present)."""
    with fits.open(wcs_filename) as hdulist:
        w = wcs.WCS(hdulist[0].header)

    return w.all_world2pix(np.array([point_icrs], dtype=np.float64), 0)[0]

def find_xy_via_icrs_linear(wcs_filename, point_icrs):
    """Convert ICRS sky coordinates to undistorted (linear WCS only) image pixels for ray computations."""
    with fits.open(wcs_filename) as hdulist:
        w = wcs.WCS(hdulist[0].header)

    return w.wcs_world2pix(np.array([point_icrs], dtype=np.float64), 0)[0]

def find_xy_via_orientation(camera_res, sensor_size, focal_length, image_res, vector):
    """Project 3D orientation vector to image pixel coordinates using pinhole camera model."""
    camera_res = np.asarray(camera_res, dtype=np.float64)
    sensor_size = np.asarray(sensor_size, dtype=np.float64)
    focal_length = float(focal_length)
    image_res = np.asarray(image_res, dtype=np.float64)
    # Invert vector
    z = -vector
    # Image plane coordinates in mm
    x_mm = focal_length * (z[0] / -z[2])
    y_mm = focal_length * (z[1] / -z[2])
    # Convert mm to pixels
    px_per_mm_x = camera_res[0] / sensor_size[0]
    px_per_mm_y = camera_res[1] / sensor_size[1]
    dx_px = x_mm * px_per_mm_x
    dy_px = y_mm * px_per_mm_y
    # Image center
    cx = image_res[0] / 2.0
    cy = image_res[1] / 2.0
    # Final pixel coordinates
    x_px = cx + dx_px
    y_px = cy - dy_px

    return [float(x_px), float(y_px)]

def pixel_to_ray(px, py, camera_data):
    """Convert pixel coordinates to 3D ray direction in camera frame using pinhole projection model."""
    cam0 = np.asarray(camera_data[0], dtype=np.float64)   # [w_px, h_px]
    cam1 = np.asarray(camera_data[1], dtype=np.float64)   # [w_mm, h_mm]
    f = float(camera_data[2])                             # mm

    cx = cam0[0] / 2.0
    cy = cam0[1] / 2.0

    px_per_mm_x = cam0[0] / cam1[0]
    px_per_mm_y = cam0[1] / cam1[1]

    x_mm = (px - cx) / px_per_mm_x
    y_mm = (cy - py) / px_per_mm_y

    ray = np.array([x_mm, y_mm, -f])
    return ray / np.linalg.norm(ray)

def rotation_from_vectors(v1, v2):
    """Compute 3×3 rotation matrix mapping v1 → v2 using Rodriguez formula."""
    v1 = v1 / np.linalg.norm(v1)
    v2 = v2 / np.linalg.norm(v2)

    axis = np.cross(v1, v2)
    sin_a = np.linalg.norm(axis)
    cos_a = np.dot(v1, v2)

    if sin_a < 1e-8:
        return np.eye(3)

    axis /= sin_a

    K = np.array([
        [0, -axis[2], axis[1]],
        [axis[2], 0, -axis[0]],
        [-axis[1], axis[0], 0]
    ])

    R = np.eye(3) + K * sin_a + K @ K * (1 - cos_a)
    return R

def rotation_matrix_to_quaternion(R):
    """Convert 3×3 rotation matrix to unit quaternion [w, x, y, z]."""
    w = np.sqrt(1.0 + np.trace(R)) / 2.0
    x = (R[2,1] - R[1,2]) / (4*w)
    y = (R[0,2] - R[2,0]) / (4*w)
    z = (R[1,0] - R[0,1]) / (4*w)
    q = np.array([w, x, y, z])
    return q / np.linalg.norm(q)

def rotation_angle(R):
    """Compute rotation angle (radians) from 3×3 rotation matrix trace."""
    cos_a = (np.trace(R) - 1) / 2
    cos_a = np.clip(cos_a, -1.0, 1.0)
    return np.arccos(cos_a)


def pixel_angle_deg_from_center(point_xy, camera_data):
    """
    Compute angular distance (degrees) between image center and a pixel coordinate.

    point_xy: [x_px, y_px]
    camera_data: [[w_px,h_px], [w_mm,h_mm], focal_length_mm]
    """
    cam0 = np.asarray(camera_data[0], dtype=np.float64)   # [w_px, h_px]
    cam1 = np.asarray(camera_data[1], dtype=np.float64)   # [w_mm, h_mm]
    f = float(camera_data[2])                             # mm

    cx = cam0[0] / 2.0
    cy = cam0[1] / 2.0

    dx = float(point_xy[0]) - cx
    dy = cy - float(point_xy[1])

    # convert pixel offsets to mm on sensor
    px_per_mm_x = cam0[0] / cam1[0]
    px_per_mm_y = cam0[1] / cam1[1]

    x_mm = dx / px_per_mm_x
    y_mm = dy / px_per_mm_y

    r_mm = np.sqrt(x_mm**2 + y_mm**2)

    # angular separation between optical axis and the ray through the pixel
    theta_rad = np.arctan2(r_mm, f)
    return float(np.degrees(theta_rad))

def average_quaternions(quats, weights=None):
    """Compute weighted geodesic mean of quaternions using eigenvalue decomposition on SO(3) manifold."""
    if weights is None:
        weights = np.ones(len(quats))

    A = np.zeros((4,4))
    for q, w in zip(quats, weights):
        q = q / np.linalg.norm(q)
        A += w * np.outer(q, q)

    eigvals, eigvecs = np.linalg.eigh(A)
    q_avg = eigvecs[:, np.argmax(eigvals)]
    return q_avg / np.linalg.norm(q_avg)

def quaternion_to_rotation_matrix(q):
    """Convert unit quaternion [w, x, y, z] to 3×3 rotation matrix."""
    w, x, y, z = q
    return np.array([
        [1 - 2*(y*y + z*z), 2*(x*y - z*w),     2*(x*z + y*w)],
        [2*(x*y + z*w),     1 - 2*(x*x + z*z), 2*(y*z - x*w)],
        [2*(x*z - y*w),     2*(y*z + x*w),     1 - 2*(x*x + y*y)]
    ])


def combine_rotation_corrections(
    R_list,
    quality_scores=None,
    max_angle_deg=30
):
    """Combine rotation corrections using quaternion geodesic mean.

    Args:
        R_list: List of 3x3 rotation matrices
        quality_scores: Optional list of quality scores (0-100) corresponding to each matrix
        max_angle_deg: Reject corrections with angle > this threshold
    """
    quats = []
    weights = []

    for i, R in enumerate(R_list):
        angle = np.degrees(rotation_angle(R))

        # Reject outliers
        if angle > max_angle_deg:
            continue

        q = rotation_matrix_to_quaternion(R)
        quats.append(q)

        angle_weight = 1.0 / (1e-6 + angle**2)

        if quality_scores is not None and i < len(quality_scores):
            quality_weight = max(0, min(100, quality_scores[i])) / 100.0
            combined_weight = 0.7 * angle_weight + 0.3 * quality_weight
        else:
            combined_weight = angle_weight

        weights.append(combined_weight)

    if len(quats) == 0:
        return np.eye(3)

    q_avg = average_quaternions(quats, weights)
    return quaternion_to_rotation_matrix(q_avg)

from PIL import Image, ImageDraw

def drawing(arguments, zenith_photo_coordinates, coefficient_location):
    """Draw overlay lines on image: IMU zenith → GPS zenith → center, mark each point with colored square."""
    try:
        linked = arguments.get("linked_image")
        if linked is None:
            raise ValueError("No linked image found in metadata for drawing")
        img_path = Path(linked) if Path(linked).is_absolute() else Path("./") / linked
        img = Image.open(img_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        def to_int_xy(pt):
            try:
                x = float(pt[0])
                y = float(pt[1])
            except Exception as e:
                raise ValueError(f"Couldn't convert point {pt} to (x,y): {e}")
            return int(round(x)), int(round(y))
        p_grav = to_int_xy(zenith_photo_coordinates)
        p_coeff = to_int_xy(coefficient_location)
        pf = arguments.get("photo_full_resolution")
        if pf is None:
            center_x = img.width / 2
            center_y = img.height / 2
        else:
            center_x = pf[0] / 2
            center_y = pf[1] / 2
        p_center = int(round(center_x)), int(round(center_y))
        draw.line([p_grav, p_coeff], fill="red", width=10)
        draw.line([p_grav, p_center], fill="red", width=10)
        draw.line([p_coeff, p_center], fill="red", width=10)
        def draw_centered_square(draw_obj, center, size=10, fill="blue"):
            cx, cy = center
            half = size // 2
            bbox = [cx - half, cy - half, cx + half, cy + half]
            draw_obj.rectangle(bbox, fill=fill)
        draw_centered_square(draw, p_grav, size=10, fill="green")
        draw_centered_square(draw, p_coeff, size=10, fill="blue")
        draw_centered_square(draw, p_center, size=10, fill="blue")
        out_path = img_path.parent / ("charted_" + img_path.name)
        img.save(out_path)
        return str(out_path)
    except Exception:
        return None

