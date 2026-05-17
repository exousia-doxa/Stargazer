from astropy.time import Time
from astropy import units as u
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
from astropy.utils.iers import iers
import numpy as np
from astropy import wcs
from astropy.io import fits

iers.conf.auto_download = True

### LEGACY

# It computes approximate location (latitude, longitude) from given ICRS coordinates and observation time
def find_location_via_icrs(
        ra_deg: float,
        dec_deg: float,
        obs_time,
        init_guess=(0.0, 0.0),
        step_deg: float = 0.1,
        precision_deg: float = 1e-4):
    target_coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame='icrs')
    best_lat, best_lon = float(init_guess[0]), float(init_guess[1])
    best_sep_deg = float('inf')

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

# It computes ICRS coordinates from given location and observation time
def find_icrs_via_location(obs_time, lat_deg: float, lon_deg: float):
    location = EarthLocation(lat=lat_deg * u.deg, lon=lon_deg * u.deg, height=0 * u.m)
    point_altaz = SkyCoord(alt=90 * u.deg, az=0 * u.deg, frame=AltAz(obstime=Time(obs_time, scale='utc'), location=location))
    point_icrs = point_altaz.transform_to('icrs')

    return [float(point_icrs.ra.to(u.deg).value), float(point_icrs.dec.to(u.deg).value)]

# It computes ICRS coordinates from given pixel coordinates using WCS file
def find_icrs_via_xy(wcs_filename, point_xy):
    with fits.open(wcs_filename) as hdulist:
        w = wcs.WCS(hdulist[0].header)

    return [float(w.wcs_pix2world(np.array([point_xy], dtype=np.float64), 0)[0][0]), float(w.wcs_pix2world(np.array([point_xy], dtype=np.float64), 0)[0][1])]

# It computes pixel coordinates from given ICRS coordinates using WCS file
def find_xy_via_icrs(wcs_filename, point_icrs):
    with fits.open(wcs_filename) as hdulist:
        w = wcs.WCS(hdulist[0].header)

    return w.wcs_world2pix(np.array([point_icrs], dtype=np.float64), 0)[0]

# It computes pixel coordinates of given point via orientation vector
def find_xy_via_orientation(camera_res, sensor_size, focal_length, image_res, vector):
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

### SUSPICIOUS AISLOP

def pixel_to_ray(px, py, camera_data):
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

def rotmat_to_quat(R):
    w = np.sqrt(1.0 + np.trace(R)) / 2.0
    x = (R[2,1] - R[1,2]) / (4*w)
    y = (R[0,2] - R[2,0]) / (4*w)
    z = (R[1,0] - R[0,1]) / (4*w)
    q = np.array([w, x, y, z])
    return q / np.linalg.norm(q)

def rotation_angle(R):
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
    if weights is None:
        weights = np.ones(len(quats))

    A = np.zeros((4,4))
    for q, w in zip(quats, weights):
        q = q / np.linalg.norm(q)
        A += w * np.outer(q, q)

    eigvals, eigvecs = np.linalg.eigh(A)
    q_avg = eigvecs[:, np.argmax(eigvals)]
    return q_avg / np.linalg.norm(q_avg)

def quat_to_rotmat(q):
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

        q = rotmat_to_quat(R)
        quats.append(q)

        # Weight by angle (smaller = higher weight) + quality score (if available)
        angle_weight = 1.0 / (1e-6 + angle**2)

        if quality_scores is not None and i < len(quality_scores):
            # Quality score 0-100 → normalize to 0-1 weight
            quality_weight = max(0, min(100, quality_scores[i])) / 100.0
            # Combine: 70% angle, 30% quality
            combined_weight = 0.7 * angle_weight + 0.3 * quality_weight
        else:
            combined_weight = angle_weight

        weights.append(combined_weight)

    if len(quats) == 0:
        return np.eye(3)

    q_avg = average_quaternions(quats, weights)
    return quat_to_rotmat(q_avg)

from PIL import Image, ImageDraw

def drawing(arguments, zenith_photo_coordinates, coefficient_location):
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

