package net.sourceforge.opencamera;

import android.content.ClipData;
import android.content.Intent;
import android.database.Cursor;
import android.media.ExifInterface;
import android.net.Uri;
import android.os.Bundle;
import android.provider.MediaStore;
import android.util.Log;
import android.widget.Button;
import android.widget.TableLayout;
import android.widget.TableRow;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import com.chaquo.python.Python;
import com.chaquo.python.PyObject;
import com.chaquo.python.android.AndroidPlatform;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.List;

/**
 * Calibration UI activity: select photos with metadata, compute correction matrices via Python,
 * aggregate into global correction bins by zenith offset, display results and statistics.
 */
public class CalibrationActivity extends AppCompatActivity {
    private static final String TAG = "CalibrationActivity";
    private static final int REQUEST_SELECT_PHOTOS = 200;

    private TableLayout calibrationListTable;
    private TableLayout globalCalibrationsTable;
    private TextView statusTextView;
    private Button selectPhotosButton;
    private Button regenerateButton;
    private List<CalibrationPhotoInfo> selectedPhotos = new ArrayList<>();

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_calibration);

        calibrationListTable = findViewById(R.id.calibration_list_table);
        globalCalibrationsTable = findViewById(R.id.global_calibrations_table);
        statusTextView = findViewById(R.id.calibration_status_textview);
        selectPhotosButton = findViewById(R.id.select_photos_button);
        regenerateButton = findViewById(R.id.regenerate_button);

        selectPhotosButton.setOnClickListener(v -> selectPhotos());
        regenerateButton.setOnClickListener(v -> regenerateGlobalCalibration());

        displayGlobalCalibrations();
        updateStatusDisplay();
    }

    /**
     * Open image picker to select calibration photos from device storage.
     */
    private void selectPhotos() {
        Intent intent = new Intent(Intent.ACTION_PICK, MediaStore.Images.Media.EXTERNAL_CONTENT_URI);
        intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        intent.setType("image/*");
        startActivityForResult(intent, REQUEST_SELECT_PHOTOS);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQUEST_SELECT_PHOTOS && resultCode == RESULT_OK && data != null) {
            new Thread(() -> {
                try {
                    selectedPhotos.clear();
                    ClipData clipData = data.getClipData();
                    if (clipData != null) {
                        for (int i = 0; i < clipData.getItemCount(); i++) {
                            Uri uri = clipData.getItemAt(i).getUri();
                            processPhotoUri(uri);
                        }
                    } else {
                        Uri singleUri = data.getData();
                        if (singleUri != null) {
                            processPhotoUri(singleUri);
                        }
                    }
                    runOnUiThread(this::updateStatusDisplay);
                } catch (Exception e) {
                    Log.e(TAG, "Error processing photos", e);
                    runOnUiThread(() -> Toast.makeText(CalibrationActivity.this,
                        "Error: " + e.getMessage(), Toast.LENGTH_LONG).show());
                }
            }).start();
        }
    }

    /**
     * Extract real filesystem path from content URI (handles SAF and MediaStore URIs).
     */
    private String getRealPathFromUri(Uri uri) {
        String filePath = null;
        if ("file".equals(uri.getScheme())) {
            filePath = uri.getPath();
        } else {
            try (android.database.Cursor cursor = getContentResolver().query(
                    MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                    new String[]{MediaStore.Images.Media.DATA},
                    MediaStore.Images.Media._ID + "=?",
                    new String[]{uri.getLastPathSegment()},
                    null)) {
                if (cursor != null && cursor.moveToFirst()) {
                    filePath = cursor.getString(cursor.getColumnIndexOrThrow(MediaStore.Images.Media.DATA));
                }
            } catch (Exception e) {
                Log.w(TAG, "Could not resolve URI to path via MediaStore: " + e.getMessage());
            }
        }
        return filePath;
    }

    /**
     * Extract display name from content URI (handles all providers: MediaStore, SAF, cloud, etc).
     */
    private String getDisplayNameFromUri(Uri uri) {
        String displayName = null;
        try (android.database.Cursor cursor = getContentResolver().query(uri, null, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                int nameIndex = cursor.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME);
                if (nameIndex >= 0) {
                    displayName = cursor.getString(nameIndex);
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "Could not resolve display name from URI: " + e.getMessage());
        }
        return displayName;
    }

    /**
     * Read metadata from JSON sidecar file (legacy format fallback if not in EXIF).
     */
    private String readMetadataSidecar(String originalPath) {
        try {
            File imageFile = new File(originalPath);
            String baseName = imageFile.getName();
            if (baseName.lastIndexOf('.') > 0) {
                baseName = baseName.substring(0, baseName.lastIndexOf('.'));
            }
            File sidecarFile = new File(imageFile.getParent(), baseName + ".stargazer.json");

            if (sidecarFile.exists()) {
                StringBuilder content = new StringBuilder();
                try (java.io.BufferedReader reader = new java.io.BufferedReader(new java.io.FileReader(sidecarFile))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        content.append(line);
                    }
                }
                Log.d(TAG, "Read metadata from sidecar: " + sidecarFile.getAbsolutePath());
                return content.toString();
            }
        } catch (Exception e) {
            Log.d(TAG, "No sidecar file found or error reading: " + e.getMessage());
        }
        return null;
    }

    /**
     * Process selected photo: extract metadata from EXIF, add to UI table.
     */
    private void processPhotoUri(Uri uri) throws IOException {
        File tempFile = new File(getCacheDir(), "temp_calib_" + System.currentTimeMillis() + ".jpg");
        try (InputStream in = getContentResolver().openInputStream(uri);
             OutputStream out = new java.io.FileOutputStream(tempFile)) {
            byte[] buf = new byte[4096];
            int len;
            while ((len = in.read(buf)) > 0) {
                out.write(buf, 0, len);
            }
        }

        // Try to get original photo name (works for all URI types: file, MediaStore, SAF, cloud)
        String originalRealPath = getRealPathFromUri(uri);
        String originalDisplayName = getDisplayNameFromUri(uri);
        if (originalDisplayName == null) {
            // Fallback: try real path
            if (originalRealPath != null) {
                originalDisplayName = new File(originalRealPath).getName();
                Log.d(TAG, "Got name from real path: " + originalDisplayName);
            } else {
                // Last resort: use temp name
                originalDisplayName = new File(tempFile.getAbsolutePath()).getName();
                Log.d(TAG, "Using temp name fallback: " + originalDisplayName);
            }
        } else {
            Log.d(TAG, "Got display name from URI: " + originalDisplayName);
        }

        CalibrationPhotoInfo info = new CalibrationPhotoInfo();
        info.filePath = tempFile.getAbsolutePath();
        info.fileName = originalDisplayName;
        Log.d(TAG, "Photo display name: " + info.fileName);

        try {
            if (!Python.isStarted()) {
                Python.start(new AndroidPlatform(this));
            }
            Python py = Python.getInstance();
            PyObject mainModule = py.getModule("main");

            // Read EXIF from temp copy (created from URI, includes original metadata)
            String metaString = null;

            try {
                // Try to extract USER_COMMENT from EXIF
                ExifInterface exif = new ExifInterface(info.filePath);
                String userComment = exif.getAttribute(ExifInterface.TAG_USER_COMMENT);
                if (userComment != null && !userComment.isEmpty()) {
                    metaString = userComment;
                    Log.d(TAG, "Read metadata from EXIF");
                }
            } catch (Exception e) {
                Log.d(TAG, "Error reading EXIF from temp copy: " + e.getMessage());
            }

            // If no EXIF, try sidecar (fallback)
            if (metaString == null || metaString.isEmpty()) {
                metaString = readMetadataSidecar(originalRealPath);
                if (metaString != null) {
                    Log.d(TAG, "Read metadata from sidecar");
                }
            }

            // Parse metadata if found
            if (metaString != null && !metaString.isEmpty()) {
                MetadataFormatter.Metadata meta = MetadataFormatter.parseMetadata(metaString);
                if (meta.hasCalibration) {
                    info.hasCalibration = true;
                    info.correctionMatrix = meta.matrix;
                    info.zenithOffset = meta.degree;
                }
                if (meta.lat != 0 || meta.lon != 0) {
                    JSONArray locArray = new JSONArray();
                    locArray.put(meta.lat);
                    locArray.put(meta.lon);
                    info.locationLatitude = locArray;
                    info.hasLocation = true;
                }
            }
        } catch (Exception e) {
            Log.d(TAG, "Error reading metadata for " + info.fileName + ": " + e.getMessage());
        }

        selectedPhotos.add(info);
    }

    /**
     * Update status text with selected photo count and calibration summary.
     */
    private void updateStatusDisplay() {
        calibrationListTable.removeAllViews();
        statusTextView.setText("Photos: " + selectedPhotos.size() + " selected");

        for (CalibrationPhotoInfo photo : selectedPhotos) {
            addPhotoRow(photo);
        }

        if (selectedPhotos.isEmpty()) {
            statusTextView.setText("No photos selected. Tap 'Select Photos' to begin.");
            regenerateButton.setEnabled(false);
        } else {
            long photosWithCalib = selectedPhotos.stream().filter(p -> p.hasCalibration).count();
            statusTextView.setText("Photos: " + selectedPhotos.size() + " | With calib: " + photosWithCalib);
            regenerateButton.setEnabled(true);
        }
    }

    /**
     * Add photo metadata row to calibration list table.
     */
    private void addPhotoRow(CalibrationPhotoInfo photo) {
        TableRow row = new TableRow(this);

        TextView nameView = new TextView(this);
        nameView.setText(photo.fileName);
        nameView.setTextSize(12);
        nameView.setTextColor(0xFFb3b3b3);
        nameView.setPadding(8, 8, 8, 8);
        row.addView(nameView);

        TextView statusView = new TextView(this);
        if (photo.hasCalibration) {
            statusView.setText(String.format("✓ Zenith: %.1f°", photo.zenithOffset));
            statusView.setTextColor(0xFF00e676);
        } else {
            statusView.setText("No calib");
            statusView.setTextColor(0xFFff9100);
        }
        statusView.setTextSize(12);
        statusView.setPadding(8, 8, 8, 8);
        row.addView(statusView);

        calibrationListTable.addView(row);
    }

    /**
     * Load and display current global correction matrix bins from configuration.
     */
    private void displayGlobalCalibrations() {
        globalCalibrationsTable.removeAllViews();
        ConfigManager configMgr = new ConfigManager(this);
        JSONObject config = configMgr.getConfig();
        JSONArray matrices = config.optJSONArray("correction_matrix");

        if (matrices == null || matrices.length() == 0) {
            addCalibrationRow("Status", "No calibrations stored");
        } else {
            try {
                for (int i = 0; i < matrices.length(); i++) {
                    JSONArray binData = matrices.getJSONArray(i);
                    JSONArray degreeRange = binData.getJSONArray(0);
                    double minDeg = degreeRange.getDouble(0);
                    double maxDeg = degreeRange.getDouble(1);
                    String binLabel = String.format("Bin %d (%.0f°-%.0f°)", i + 1, minDeg, maxDeg);

                    // Extract num_photos and avg_quality if present (new format)
                    String details = "";
                    if (binData.length() >= 4) {
                        int numPhotos = binData.getInt(2);
                        double avgQuality = binData.getDouble(3);
                        if (avgQuality >= 0) {
                            details = String.format("%d photos, %.0f%%", numPhotos, avgQuality);
                        } else {
                            details = String.format("%d photos", numPhotos);
                        }
                    } else {
                        details = String.valueOf(i + 1);
                    }
                    addCalibrationRow(binLabel, details);
                }
            } catch (JSONException e) {
                Log.e(TAG, "Error displaying calibrations", e);
                addCalibrationRow("Error", "Failed to read calibrations");
            }
        }
    }

    /**
     * Add calibration summary row (bin range + quality) to global calibrations table.
     */
    private void addCalibrationRow(String label, String value) {
        TableRow row = new TableRow(this);

        TextView labelView = new TextView(this);
        labelView.setText(label);
        labelView.setTextSize(13);
        labelView.setTextColor(0xFFb3b3b3);
        labelView.setPadding(0, 8, 12, 8);
        row.addView(labelView);

        TextView valueView = new TextView(this);
        valueView.setText(value);
        valueView.setTextSize(13);
        valueView.setTextColor(0xFFe0e0e0);
        valueView.setPadding(12, 8, 0, 8);
        row.addView(valueView);

        globalCalibrationsTable.addView(row);
    }

    /**
     * Invoke Python calibrate_correction() on selected photos to compute global correction matrix bins.
     * Updates configuration and UI display on completion.
     */
    private void regenerateGlobalCalibration() {
        new Thread(() -> {
            try {
                List<String> imagePaths = new ArrayList<>();
                for (CalibrationPhotoInfo photo : selectedPhotos) {
                    if (photo.hasCalibration) {
                        imagePaths.add(photo.filePath);
                    }
                }

                if (imagePaths.isEmpty()) {
                    runOnUiThread(() -> Toast.makeText(CalibrationActivity.this,
                        "No calibrations to process", Toast.LENGTH_SHORT).show());
                    return;
                }

                if (!Python.isStarted()) {
                    Python.start(new AndroidPlatform(this));
                }
                Python py = Python.getInstance();
                PyObject mainModule = py.getModule("main");

                // Load config from SharedPreferences
                ConfigManager configMgr = new ConfigManager(CalibrationActivity.this);
                JSONObject configDict = configMgr.getConfig();

                // Call Python calibrate_correction with config dict (no file path)
                PyObject result = mainModule.callAttr("calibrate_correction", configDict.toString(), imagePaths);

                int numBins = 0;
                JSONObject updatedConfig = configDict;
                if (result != null && !result.toString().equals("None")) {
                    try {
                        JSONObject resultObj = new JSONObject(result.toString());
                        // Get matrices
                        JSONArray matrices = resultObj.optJSONArray("matrices");
                        if (matrices != null) {
                            numBins = matrices.length();
                        }
                        // Get updated config
                        JSONObject config = resultObj.optJSONObject("config");
                        if (config != null) {
                            updatedConfig = config;
                        }
                    } catch (Exception e) {
                        Log.d(TAG, "Error parsing calibration result: " + e.getMessage());
                    }
                }

                // Save updated config to SharedPreferences
                final JSONObject finalConfig = updatedConfig;
                configMgr.saveConfig(finalConfig);

                final int finalNumBins = numBins;
                final int photoCount = imagePaths.size();
                runOnUiThread(() -> {
                    displayGlobalCalibrations();
                    String message = finalNumBins > 0 ?
                        "Calibration: " + finalNumBins + " bins from " + photoCount + " photos" :
                        "Calibration completed (" + photoCount + " photos)";
                    Toast.makeText(CalibrationActivity.this, message, Toast.LENGTH_LONG).show();
                });
            } catch (Exception e) {
                Log.e(TAG, "Error regenerating calibration", e);
                runOnUiThread(() -> Toast.makeText(CalibrationActivity.this,
                    "Error: " + e.getMessage(), Toast.LENGTH_LONG).show());
            }
        }).start();
    }


    static class CalibrationPhotoInfo {
        String filePath;
        String fileName;
        boolean hasCalibration = false;
        boolean hasLocation = false;
        double zenithOffset = -1;
        JSONArray locationLatitude;
        double[][] correctionMatrix;
    }
}
