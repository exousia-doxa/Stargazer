package net.sourceforge.opencamera;

import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

public class MetadataFormatter {
    private static final String TAG = "MetadataFormatter";

    /**
     * Format photo metadata as delimited string for EXIF USER_COMMENT.
     * Format: META|timestamp|photoW|photoH|matrixW|matrixH|focalLen|gravityX|gravityY|gravityZ|lat|lon|v00|v01|v02|v10|v11|v12|v20|v21|v22|degree|quality_score|observed_zenith_offset
     *
     * @param photoDataJson JSON object containing photo_data, camera_data, orientation_data
     * @param solveResultJson JSON object with correction_vector_matrix, correction_degree, calibration_quality_score, zenith_offset_degrees (can be null)
     * @return delimited metadata string, or null on error
     */
    public static String formatMetadata(String photoDataJson, String solveResultJson) {
        try {
            JSONObject input = new JSONObject(photoDataJson);
            JSONObject result = solveResultJson != null ? new JSONObject(solveResultJson) : new JSONObject();
            StringBuilder meta = new StringBuilder("META");

            // 1. Timestamp from photo_data[1]
            String timestamp = "";
            JSONArray photoData = input.optJSONArray("photo_data");
            if (photoData != null && photoData.length() > 1) {
                timestamp = photoData.optString(1, "");
            }
            meta.append("|").append(timestamp);

            // 2-3. Photo dimensions from camera_data[0]
            int photoW = 0, photoH = 0;
            JSONArray cameraData = input.optJSONArray("camera_data");
            if (cameraData != null && cameraData.length() > 0) {
                JSONArray photoSize = cameraData.optJSONArray(0);
                if (photoSize != null && photoSize.length() >= 2) {
                    photoW = photoSize.optInt(0, 0);
                    photoH = photoSize.optInt(1, 0);
                }
            }
            meta.append("|").append(photoW);
            meta.append("|").append(photoH);

            // 4-5. Sensor matrix size from camera_data[1]
            double matrixW = 0, matrixH = 0;
            if (cameraData != null && cameraData.length() > 1) {
                JSONArray matrixSize = cameraData.optJSONArray(1);
                if (matrixSize != null && matrixSize.length() >= 2) {
                    matrixW = matrixSize.optDouble(0, 0);
                    matrixH = matrixSize.optDouble(1, 0);
                }
            }
            meta.append("|").append(matrixW);
            meta.append("|").append(matrixH);

            // 6. Focal length from camera_data[2]
            double focalLen = 0;
            if (cameraData != null && cameraData.length() > 2) {
                focalLen = cameraData.optDouble(2, 0);
            }
            meta.append("|").append(focalLen);

            // 7-9. Gravity vector from orientation_data[0]
            double gravityX = 0, gravityY = 0, gravityZ = 0;
            JSONArray orientationData = input.optJSONArray("orientation_data");
            if (orientationData != null && orientationData.length() > 0) {
                JSONArray gravity = orientationData.optJSONArray(0);
                if (gravity != null && gravity.length() >= 3) {
                    gravityX = gravity.optDouble(0, 0);
                    gravityY = gravity.optDouble(1, 0);
                    gravityZ = gravity.optDouble(2, 0);
                }
            }
            meta.append("|").append(gravityX);
            meta.append("|").append(gravityY);
            meta.append("|").append(gravityZ);

            // 10-11. Location from photo_data[2]
            double lat = 0, lon = 0;
            JSONArray location = photoData != null && photoData.length() > 2 ?
                photoData.optJSONArray(2) : null;
            if (location != null && location.length() >= 2) {
                lat = location.optDouble(0, 0);
                lon = location.optDouble(1, 0);
            }
            meta.append("|").append(lat);
            meta.append("|").append(lon);

            // 12-20. Correction matrix from solve result (9 values in 3x3)
            JSONArray matrix = result.optJSONArray("correction_vector_matrix");
            if (matrix != null && matrix.length() >= 3) {
                for (int i = 0; i < 3; i++) {
                    JSONArray row = matrix.optJSONArray(i);
                    if (row != null && row.length() >= 3) {
                        for (int j = 0; j < 3; j++) {
                            meta.append("|").append(row.optDouble(j, 0));
                        }
                    }
                }
            } else {
                // No matrix, add 9 zeros
                for (int i = 0; i < 9; i++) {
                    meta.append("|0");
                }
            }

            // 21. Correction degree from solve result
            double degree = result.optDouble("correction_degree", -1);
            meta.append("|").append(degree);

            // 22. Calibration quality score from solve result
            double qualityScore = result.optDouble("calibration_quality_score", -1);
            meta.append("|").append(qualityScore);

            // 23. Observed zenith offset (where phone thinks zenith is) - used for binning
            double observedZenithOffset = result.optDouble("zenith_offset_degrees", -1);
            meta.append("|").append(observedZenithOffset);

            Log.d(TAG, "Formatted metadata (24 fields): " + meta.toString());
            return meta.toString();
        } catch (Exception e) {
            Log.e(TAG, "Error formatting metadata: " + e.getMessage());
            return null;
        }
    }

    /**
     * Parse delimited metadata string from EXIF USER_COMMENT.
     * Returns array: [timestamp, photoW, photoH, matrixW, matrixH, focalLen,
     *                 gravityX, gravityY, gravityZ, lat, lon,
     *                 v00, v01, v02, v10, v11, v12, v20, v21, v22, degree]
     */
    public static class Metadata {
        public String timestamp;
        public int photoW, photoH;
        public double matrixW, matrixH, focalLen;
        public double gravityX, gravityY, gravityZ;
        public double lat, lon;
        public double[][] matrix = new double[3][3];
        public double degree;  // actual zenith offset (from GPS + WCS)
        public double observedZenithOffset = -1;  // observed zenith offset (from phone sensors)
        public double qualityScore = -1;
        public boolean hasCalibration;
    }

    public static Metadata parseMetadata(String metaString) {
        Metadata meta = new Metadata();

        if (metaString == null || !metaString.startsWith("META")) {
            return meta;
        }

        try {
            String[] parts = metaString.split("\\|");
            if (parts.length < 22) {
                Log.d(TAG, "Invalid metadata format, expected 22 parts, got " + parts.length);
                return meta;
            }

            meta.timestamp = parts[1];
            meta.photoW = Integer.parseInt(parts[2]);
            meta.photoH = Integer.parseInt(parts[3]);
            meta.matrixW = Double.parseDouble(parts[4]);
            meta.matrixH = Double.parseDouble(parts[5]);
            meta.focalLen = Double.parseDouble(parts[6]);
            meta.gravityX = Double.parseDouble(parts[7]);
            meta.gravityY = Double.parseDouble(parts[8]);
            meta.gravityZ = Double.parseDouble(parts[9]);
            meta.lat = Double.parseDouble(parts[10]);
            meta.lon = Double.parseDouble(parts[11]);

            // Parse 3x3 matrix
            boolean hasMatrix = false;
            for (int i = 0; i < 3; i++) {
                for (int j = 0; j < 3; j++) {
                    int idx = 12 + i * 3 + j;
                    double val = Double.parseDouble(parts[idx]);
                    meta.matrix[i][j] = val;
                    if (val != 0) {
                        hasMatrix = true;
                    }
                }
            }
            meta.hasCalibration = hasMatrix;

            if (parts.length > 21) {
                meta.degree = Double.parseDouble(parts[21]);
            }

            // Parse quality score (backwards compatible - optional field 22)
            if (parts.length > 22) {
                meta.qualityScore = Double.parseDouble(parts[22]);
            }

            // Parse observed zenith offset (backwards compatible - optional field 23)
            if (parts.length > 23) {
                meta.observedZenithOffset = Double.parseDouble(parts[23]);
            }

            Log.d(TAG, "Parsed metadata: calibration=" + meta.hasCalibration + ", degree=" + meta.degree + ", observed=" + meta.observedZenithOffset + ", quality=" + meta.qualityScore);
            return meta;
        } catch (Exception e) {
            Log.d(TAG, "Error parsing metadata: " + e.getMessage());
            return meta;
        }
    }
}
