import numpy as np

def calculate_zenith_photo_coordinates_gravity(camera_data, photo_data, orientation_data, correction_coefficient=True):
    fov = []
    correction = []
    gravity_metrics = orientation_data[0]/np.linalg.norm(orientation_data[0])
    target_metrics = [0, 0, -np.linalg.norm(gravity_metrics)]
    target_metrics_photo_coordinates = []
    target_metrics_photo_angles = []

    fov.append(2 * (np.arctan(camera_data[1][0] / (2 * camera_data[2]))) * (180.0 / np.pi))
    fov.append(2 * (np.arctan(camera_data[1][1] / (2 * camera_data[2]))) * (180.0 / np.pi))

    correction.append(camera_data[0][0] / fov[0])
    correction.append(camera_data[0][1] / fov[1])

    z_angle = np.arccos(np.dot(gravity_metrics.copy(), target_metrics)/(np.linalg.norm(target_metrics)*np.linalg.norm(gravity_metrics.copy())))

    target_xy_vector = [1, 0]
    xy_vector = [gravity_metrics.copy()[0], gravity_metrics.copy()[1]]
    if xy_vector[0] >= xy_vector[1]:
        xy_angle = -np.arccos(np.dot(xy_vector, target_xy_vector)/(np.linalg.norm(target_xy_vector)*np.linalg.norm(xy_vector)))
    else:
        xy_angle = np.arccos(np.dot(xy_vector, target_xy_vector) / (np.linalg.norm(target_xy_vector) * np.linalg.norm(xy_vector)))

    target_metrics_photo_angles.append(float(z_angle * (180 / np.pi)))
    target_metrics_photo_angles.append(float(xy_angle * (180 / np.pi)))

    if correction_coefficient:
        target_metrics_photo_coordinates.append(float((photo_data[0][0]/2 + (z_angle*(180/np.pi)*correction[0])*np.cos(xy_angle)) * orientation_data[2][0]))
        target_metrics_photo_coordinates.append(float((photo_data[0][1]/2 - (z_angle*(180/np.pi)*correction[1])*np.sin(xy_angle)) * orientation_data[2][1]))
    else:
        target_metrics_photo_coordinates.append(float((photo_data[0][0]/2 + (z_angle*(180/np.pi)*correction[0])*np.cos(xy_angle))))
        target_metrics_photo_coordinates.append(float((photo_data[0][1]/2 - (z_angle*(180/np.pi)*correction[1])*np.sin(xy_angle))))

    return target_metrics_photo_coordinates, target_metrics_photo_angles