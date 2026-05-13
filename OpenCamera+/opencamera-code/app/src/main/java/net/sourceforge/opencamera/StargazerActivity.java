package net.sourceforge.opencamera;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.graphics.BitmapFactory;
import android.media.ExifInterface;
import android.net.Uri;
import android.os.Bundle;
import android.preference.PreferenceManager;
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
import java.math.BigDecimal;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class StargazerActivity extends AppCompatActivity {
    private static final String TAG = "StargazerActivity";
    private static final int REQUEST_CAPTURE = 100;
    private static final int REQUEST_GALLERY = 101;

    private String currentJsonString = null;
    private String originalPhotoName = null;
    private TableLayout photoInfoTable;
    private TextView consoleTextView;
    private TableLayout solverResultsTable;
    private Button runSolveButton;
    private Button captureButton;
    private Button galleryButton;
    private Button settingsButton;

    private ExecutorService solveExecutor = Executors.newSingleThreadExecutor();
    private Future<?> pythonSolveFuture = null;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_stargazer);

        photoInfoTable = findViewById(R.id.photo_info_table);
        consoleTextView = findViewById(R.id.console_textview);
        solverResultsTable = findViewById(R.id.solver_results_table);
        runSolveButton = findViewById(R.id.run_solve_button);
        captureButton = findViewById(R.id.capture_button);
        galleryButton = findViewById(R.id.gallery_button);
        settingsButton = findViewById(R.id.settings_button);

        captureButton.setOnClickListener(v -> onClickCapturePhoto());
        galleryButton.setOnClickListener(v -> onClickChooseFromGallery());
        runSolveButton.setOnClickListener(v -> onClickRunSolve());
        settingsButton.setOnClickListener(v -> onClickSettings());
    }

    private void onClickCapturePhoto() {
        Intent intent = new Intent(this, MainActivity.class);
        startActivityForResult(intent, REQUEST_CAPTURE);
    }

    private void onClickChooseFromGallery() {
        Intent intent = new Intent(Intent.ACTION_PICK, MediaStore.Images.Media.EXTERNAL_CONTENT_URI);
        startActivityForResult(intent, REQUEST_GALLERY);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQUEST_CAPTURE && resultCode == RESULT_OK && data != null) {
            String json = data.getStringExtra("json");
            if (json != null && !json.isEmpty()) {
                populateUiWithJson(json);
            }
        } else if (requestCode == REQUEST_GALLERY && resultCode == RESULT_OK && data != null) {
            Uri selectedUri = data.getData();
            Log.d(TAG, "Gallery selection received: " + selectedUri);
            if (selectedUri != null) {
                new Thread(() -> {
                    try {
                        Log.d(TAG, "Starting gallery image processing...");
                        File galleryImage = copyUriToInternalStorage(selectedUri);
                        Log.d(TAG, "Gallery image copied to: " + galleryImage.getAbsolutePath());
                        String json = buildJsonFromImagePath(galleryImage.getAbsolutePath());
                        Log.d(TAG, "Built JSON, first 200 chars: " + json.substring(0, Math.min(200, json.length())));
                        runOnUiThread(() -> {
                            Log.d(TAG, "Updating UI with new JSON");
                            populateUiWithJson(json);
                        });
                    } catch (Exception e) {
                        Log.e(TAG, "Error processing gallery image", e);
                        runOnUiThread(() -> Toast.makeText(StargazerActivity.this,
                            "Error loading image: " + e.getMessage(), Toast.LENGTH_LONG).show());
                    }
                }).start();
            }
        }
    }

    private void populateUiWithJson(String json) {
        Log.d(TAG, "populateUiWithJson called with JSON length: " + json.length());
        currentJsonString = json;

        populatePhotoInfoTable(json);
        consoleTextView.setText("");
        solverResultsTable.removeAllViews();
        runSolveButton.setEnabled(true);
    }

    private void populatePhotoInfoTable(String jsonString) {
        photoInfoTable.removeAllViews();
        try {
            JSONObject root = new JSONObject(jsonString);

            // Photo name (filename from input_image path) - store original
            String inputImage = root.optString("input_image", "");
            originalPhotoName = inputImage.substring(inputImage.lastIndexOf('/') + 1);
            String photoName = originalPhotoName;

            // Photo dimensions
            String dimensions = "N/A";
            JSONArray cameraData = root.optJSONArray("camera_data");
            if (cameraData != null && cameraData.length() > 0) {
                JSONArray photoSize = cameraData.optJSONArray(0);
                if (photoSize != null && photoSize.length() >= 2) {
                    int width = photoSize.optInt(0);
                    int height = photoSize.optInt(1);
                    dimensions = width + "x" + height;
                }
            }

            // Photo timestamp
            String timestamp = "N/A";
            JSONArray photoData = root.optJSONArray("photo_data");
            if (photoData != null && photoData.length() > 1) {
                timestamp = photoData.optString(1, "N/A");
            }

            // Location
            String location = "N/A";
            if (photoData != null && photoData.length() > 2) {
                JSONArray locArray = photoData.optJSONArray(2);
                if (locArray != null && locArray.length() >= 2) {
                    double lat = locArray.optDouble(0);
                    double lon = locArray.optDouble(1);
                    if (lat != 0.0 || lon != 0.0) {
                        location = String.format("%.4f, %.4f", lat, lon);
                    }
                }
            }

            // Orientation (gravity vector)
            String orientX = "N/A", orientY = "N/A", orientZ = "N/A";
            JSONArray orientData = root.optJSONArray("orientation_data");
            if (orientData != null && orientData.length() > 0) {
                JSONArray gravity = orientData.optJSONArray(0);
                if (gravity != null && gravity.length() >= 3) {
                    orientX = String.format("%.2f", gravity.optDouble(0));
                    orientY = String.format("%.2f", gravity.optDouble(1));
                    orientZ = String.format("%.2f", gravity.optDouble(2));
                }
            }

            // Add rows to table
            addTableRow("Photo Name", photoName);
            addTableRow("Dimension", dimensions);
            addTableRow("Timestamp", timestamp);
            addTableRow("Location", location);
            addTableRow("Orientation X", orientX);
            addTableRow("Orientation Y", orientY);
            addTableRow("Orientation Z", orientZ);

        } catch (JSONException e) {
            Log.e(TAG, "Error populating photo info table", e);
            addTableRow("Error", "Failed to parse photo data");
        }
    }

    private void addTableRow(String label, String value) {
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

        photoInfoTable.addView(row);
    }

    private void addSolverResultRow(String label, String value) {
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

        solverResultsTable.addView(row);
    }

    private void onClickRunSolve() {
        if (currentJsonString == null) {
            Toast.makeText(this, "No photo captured yet", Toast.LENGTH_SHORT).show();
            return;
        }

        pythonSolveFuture = solveExecutor.submit(() -> {
            try {
                runOnUiThread(() -> {
                    runSolveButton.setEnabled(false);
                    consoleTextView.setText("");
                });

                new Thread(() -> {
                    File internalImage = new File(getStargazerWorkspaceDir(), "temp_solve.jpg");
                    String logFilePath = null;
                    Thread logReaderThread = null;

                    try {
                        JSONObject rootObj = new JSONObject(currentJsonString);
                        String originalPath = rootObj.getString("input_image");

                        // Clean up temp directory before solving
                        String outputDir = rootObj.optString("output_directory");
                        if (!outputDir.isEmpty()) {
                            cleanupTempDirectory(outputDir);
                        }

                        // Calculate log file path before solve
                        logFilePath = new File(outputDir, "solve.log").getAbsolutePath();

                        // Copy image to temp location
                        try (InputStream in = new java.io.FileInputStream(originalPath);
                             OutputStream out = new java.io.FileOutputStream(internalImage)) {
                            byte[] buf = new byte[16384];
                            int len;
                            while ((len = in.read(buf)) > 0) {
                                out.write(buf, 0, len);
                            }
                            rootObj.put("input_image", internalImage.getAbsolutePath());
                        } catch (IOException e) {
                            appendConsoleLine(consoleTextView, "Error copying image: " + e.getMessage());
                            runOnUiThread(() -> runSolveButton.setEnabled(true));
                            return;
                        }

                        if (!Python.isStarted()) {
                            Python.start(new AndroidPlatform(this));
                        }
                        Python py = Python.getInstance();
                        PyObject mainModule = py.getModule("main");

                        // Start log reader in parallel with solve
                        final String finalLogPath = logFilePath;
                        final boolean[] solveDone = {false};
                        logReaderThread = new Thread(() -> {
                            try {
                                readLogFileProgressively(finalLogPath, solveDone);
                            } catch (Exception e) {
                                Log.e(TAG, "Error reading log file", e);
                            }
                        });
                        logReaderThread.start();

                        PyObject result = mainModule.callAttr("solve_photo_from_json", rootObj.toString());
                        solveDone[0] = true;
                        final String out = result == null ? "" : result.toString();

                        try {
                            org.json.JSONObject resJson = new org.json.JSONObject(out);

                            if (resJson.optBoolean("no_match", false)) {
                                String msg = resJson.optString("no_match_message", "Could not identify any stars in this image.");
                                runOnUiThread(() -> {
                                    Toast.makeText(StargazerActivity.this, msg, Toast.LENGTH_LONG).show();
                                    solverResultsTable.removeAllViews();
                                });
                            } else if (!resJson.isNull("error")) {
                                String msg = "Solver error: " + resJson.optString("error");
                                runOnUiThread(() -> {
                                    Toast.makeText(StargazerActivity.this, msg, Toast.LENGTH_LONG).show();
                                    solverResultsTable.removeAllViews();
                                });
                            } else {
                                // Successful solve - populate results table
                                runOnUiThread(() -> {
                                    solverResultsTable.removeAllViews();

                                    // Time of execution (convert ms to seconds)
                                    long executionTime = resJson.optLong("execution_time_ms", -1);
                                    if (executionTime >= 0) {
                                        double timeSeconds = executionTime / 1000.0;
                                        addSolverResultRow("Time of execution", String.format("%.1f s", timeSeconds));
                                    }

                                    // Estimated location (from sky)
                                    JSONArray estLocation = resJson.optJSONArray("calculated_location");
                                    if (estLocation != null && estLocation.length() >= 2) {
                                        double lat = estLocation.optDouble(0);
                                        double lon = estLocation.optDouble(1);
                                        addSolverResultRow("Estimated location", String.format("%.4f, %.4f", lat, lon));
                                    }

                                    // Actual location (GPS)
                                    JSONArray actualLocation = resJson.optJSONArray("actual_location");
                                    if (actualLocation != null && actualLocation.length() >= 2) {
                                        double lat = actualLocation.optDouble(0);
                                        double lon = actualLocation.optDouble(1);
                                        addSolverResultRow("Actual location", String.format("%.4f, %.4f", lat, lon));
                                    }

                                    // Precision
                                    double precision = resJson.optDouble("location_precision_km", -1);
                                    if (precision >= 0) {
                                        addSolverResultRow("Precision", String.format("%.1f km", precision));
                                    }
                                });
                            }
                        } catch (org.json.JSONException ignored) {
                            appendConsoleLine(consoleTextView, out);
                        }

                        // Wait for log reader to finish
                        if (logReaderThread != null) {
                            try {
                                logReaderThread.join();
                            } catch (InterruptedException e) {
                                Log.e(TAG, "Interrupted waiting for log reader", e);
                            }
                        }

                        // Clean up temp folder after solving
                        if (!outputDir.isEmpty()) {
                            cleanupTempDirectory(outputDir);
                        }
                    } catch (Exception e) {
                        Log.e(TAG, "Python error in solve thread", e);
                        appendConsoleLine(consoleTextView, "Python error: " + e.getMessage());
                    } finally {
                        // Clean up temp image file
                        if (internalImage.exists()) {
                            internalImage.delete();
                        }
                        pythonSolveFuture = null;
                        runOnUiThread(() -> runSolveButton.setEnabled(true));
                    }
                }).start();

            } catch (Exception e) {
                Log.e(TAG, "Error in executor task", e);
                appendConsoleLine(consoleTextView, "Error: " + e.getMessage());
                pythonSolveFuture = null;
                runOnUiThread(() -> runSolveButton.setEnabled(true));
            }
        });
    }

    private void cleanupTempDirectory(String outputDirPath) {
        File outputDir = new File(outputDirPath);
        if (!outputDir.exists() || !outputDir.isDirectory()) {
            return;
        }
        File[] files = outputDir.listFiles();
        if (files == null) {
            return;
        }
        for (File file : files) {
            if (file.isFile()) {
                file.delete();
            }
        }
    }

    private void readLogFileProgressively(String logFilePath, boolean[] solveDone) {
        File logFile = new File(logFilePath);
        long bytesRead = 0;

        while (true) {
            try {
                if (logFile.exists()) {
                    long fileSize = logFile.length();
                    if (fileSize > bytesRead) {
                        try (java.io.RandomAccessFile raf = new java.io.RandomAccessFile(logFile, "r")) {
                            raf.seek(bytesRead);
                            String newContent = raf.readLine();
                            while (newContent != null) {
                                appendConsoleLine(consoleTextView, newContent);
                                bytesRead = raf.getFilePointer();
                                newContent = raf.readLine();
                            }
                        }
                    }
                }

                // Check if solve is complete
                if (solveDone[0]) {
                    // Read any final content
                    if (logFile.exists()) {
                        try (java.io.RandomAccessFile raf = new java.io.RandomAccessFile(logFile, "r")) {
                            raf.seek(bytesRead);
                            String newContent = raf.readLine();
                            while (newContent != null) {
                                appendConsoleLine(consoleTextView, newContent);
                                newContent = raf.readLine();
                            }
                        }
                    }
                    break;
                }

                Thread.sleep(100);
            } catch (Exception e) {
                Log.e(TAG, "Error reading log file", e);
                break;
            }
        }
    }

    private void onClickSettings() {
        Intent intent = new Intent(this, SettingsActivity.class);
        startActivity(intent);
    }

    private void appendConsoleLine(TextView consoleView, String line) {
        runOnUiThread(() -> {
            String current = consoleView.getText().toString();
            if (current.isEmpty()) {
                consoleView.setText(line);
            } else {
                consoleView.append("\n" + line);
            }
        });
    }

    private File copyUriToInternalStorage(Uri uri) throws IOException {
        String originalFileName = "gallery_image.jpg";

        // Try to get original filename from URI
        android.database.Cursor cursor = getContentResolver().query(uri, new String[]{android.provider.MediaStore.MediaColumns.DISPLAY_NAME}, null, null, null);
        if (cursor != null && cursor.moveToFirst()) {
            int nameIndex = cursor.getColumnIndex(android.provider.MediaStore.MediaColumns.DISPLAY_NAME);
            if (nameIndex >= 0) {
                originalFileName = cursor.getString(nameIndex);
            }
            cursor.close();
        }

        File internalImage = new File(getStargazerWorkspaceDir(), originalFileName);
        try (InputStream in = getContentResolver().openInputStream(uri);
             OutputStream out = new java.io.FileOutputStream(internalImage)) {
            if (in == null) throw new IOException("Unable to open URI");
            byte[] buf = new byte[16384];
            int len;
            while ((len = in.read(buf)) > 0) {
                out.write(buf, 0, len);
            }
        }
        return internalImage;
    }

    private String buildJsonFromImagePath(String imagePath) throws JSONException, IOException {
        File imageFile = new File(imagePath);
        Log.d(TAG, "buildJsonFromImagePath: processing " + imagePath);

        ExifInterface exif = new ExifInterface(imagePath);

        // Try to read embedded metadata from EXIF UserComment
        String embeddedJsonString = exif.getAttribute(ExifInterface.TAG_USER_COMMENT);
        if (embeddedJsonString != null && !embeddedJsonString.isEmpty()) {
            try {
                Log.d(TAG, "Found embedded metadata in EXIF, using it");
                JSONObject embeddedJson = new JSONObject(embeddedJsonString);
                // Ensure input_image path is current (might have moved)
                embeddedJson.put("input_image", imagePath);
                // Update solve parameters with current preferences
                SharedPreferences prefs = PreferenceManager.getDefaultSharedPreferences(this);
                JSONArray plateSolveParams = buildSolverParamsFromPrefs(prefs, 0.0, 0.0,
                    embeddedJson.optJSONArray("photo_data") != null && embeddedJson.optJSONArray("photo_data").length() > 1
                        ? embeddedJson.optJSONArray("photo_data").optString(1)
                        : null);
                embeddedJson.put("plate_solve_parameters", plateSolveParams);
                return embeddedJson.toString(4);
            } catch (JSONException e) {
                Log.d(TAG, "Failed to parse embedded metadata, building default: " + e.getMessage());
            }
        }

        // No embedded metadata found, build default
        Log.d(TAG, "No embedded metadata, building default parameters");

        // Extract image dimensions
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inJustDecodeBounds = true;
        BitmapFactory.decodeFile(imagePath, options);
        int photoWidth = options.outWidth;
        int photoHeight = options.outHeight;
        Log.d(TAG, "Image dimensions: " + photoWidth + "x" + photoHeight);

        // Extract EXIF data
        String dateTime = exif.getAttribute(ExifInterface.TAG_DATETIME);
        if (dateTime == null || dateTime.isEmpty()) {
            dateTime = String.valueOf(System.currentTimeMillis());
        }

        // Get location from image EXIF if available, otherwise use zeros
        double latitude = 0.0;
        double longitude = 0.0;
        float[] gpsCoords = new float[2];
        if (exif.getLatLong(gpsCoords)) {
            latitude = gpsCoords[0];
            longitude = gpsCoords[1];
        }
        Log.d(TAG, "Image location: " + latitude + ", " + longitude);
        Log.d(TAG, "Image datetime: " + dateTime);

        // Build JSON (mirrors MainActivity.showCaptureDetailsPopup logic)
        JSONObject root = new JSONObject();
        root.put("input_image", imagePath);
        Log.d(TAG, "Set input_image to: " + imagePath);

        File workspaceDir = getStargazerWorkspaceDir();
        File tempDir = new File(workspaceDir, "temp");
        if (!tempDir.exists()) {
            tempDir.mkdirs();
        }
        root.put("output_directory", tempDir.getAbsolutePath());
        root.put("app_config", new File(getFilesDir(), "stargazer-config.json").getAbsolutePath());

        // For now, use placeholder values for these paths (would need MainActivity context)
        root.put("backend_config", new File(getFilesDir(), "backend-config.json").getAbsolutePath());
        root.put("index_directory", new File(getFilesDir(), "index").getAbsolutePath());

        // Camera and photo data
        JSONArray cameraData = new JSONArray();
        JSONArray photoSize = new JSONArray();
        photoSize.put(photoWidth);
        photoSize.put(photoHeight);
        cameraData.put(photoSize);

        JSONArray matrixSize = new JSONArray();
        matrixSize.put(BigDecimal.ZERO);
        matrixSize.put(BigDecimal.ZERO);
        cameraData.put(matrixSize);
        cameraData.put(BigDecimal.ZERO); // focal length
        root.put("camera_data", cameraData);

        JSONArray photoData = new JSONArray();
        photoData.put(photoSize);
        photoData.put(dateTime);
        JSONArray location = new JSONArray();
        if (latitude != 0.0 || longitude != 0.0) {
            location.put(latitude);
            location.put(longitude);
        }
        photoData.put(location);
        root.put("photo_data", photoData);

        // Orientation data (try to extract from EXIF, else zeros)
        JSONArray orientationData = new JSONArray();
        JSONArray gravity = new JSONArray();

        // Try to extract orientation from EXIF
        double orientX = 0.0, orientY = 0.0, orientZ = 0.0;
        String exifOrient = exif.getAttribute(ExifInterface.TAG_ORIENTATION);
        if (exifOrient != null) {
            try {
                int orientation = Integer.parseInt(exifOrient);
                Log.d(TAG, "EXIF Orientation tag: " + orientation);
                // Note: EXIF orientation (1-8) is image rotation, not device acceleration
                // Use it if available but mostly zeros since we lack accelerometer data
                if (orientation != 1) {
                    // Image is rotated, set a minimal non-zero indicator
                    orientZ = 0.1;
                }
            } catch (NumberFormatException e) {
                Log.d(TAG, "Could not parse EXIF orientation: " + exifOrient);
            }
        }

        gravity.put(orientX);
        gravity.put(orientY);
        gravity.put(orientZ);
        orientationData.put(gravity);
        orientationData.put(new JSONArray()); // gyroscope (empty)
        root.put("orientation_data", orientationData);

        // Plate solve parameters from preferences
        SharedPreferences prefs = PreferenceManager.getDefaultSharedPreferences(this);
        JSONArray plateSolveParams = buildSolverParamsFromPrefs(prefs, latitude, longitude, dateTime);
        root.put("plate_solve_parameters", plateSolveParams);

        return root.toString();
    }

    private File getStargazerWorkspaceDir() {
        File dir = new File(getFilesDir(), "stargazer");
        dir.mkdirs();
        return dir;
    }

    private JSONArray buildSolverParamsFromPrefs(SharedPreferences prefs,
                                                 double latitude,
                                                 double longitude,
                                                 String isoTime) {
        JSONArray params = new JSONArray();

        // Always-on: write rdls (-r) and tweak (-J) -- not exposed as prefs.
        params.put("-r");
        params.put("-J");

        // Field width range + units.
        String unitsValue = prefs.getString(PreferenceKeys.SolverFieldUnitsKey, "arcminwidth");
        String minStr = prefs.getString(PreferenceKeys.SolverFieldMinKey, "30");
        String maxStr = prefs.getString(PreferenceKeys.SolverFieldMaxKey, "180");
        if (minStr != null && !minStr.trim().isEmpty()) {
            params.put("-L"); params.put(minStr.trim());
        }
        if (maxStr != null && !maxStr.trim().isEmpty()) {
            params.put("-H"); params.put(maxStr.trim());
        }
        if (unitsValue != null && !unitsValue.isEmpty()) {
            params.put("-u"); params.put(unitsValue);
        }

        // CPU time limit (engine-side rlimit; wall-clock is enforced in Python).
        String cpuStr = prefs.getString(PreferenceKeys.SolverCpuLimitKey, "60");
        if (cpuStr != null && !cpuStr.trim().isEmpty()) {
            params.put("-l"); params.put(cpuStr.trim());
        }

        // Python-side wall-clock kill timer. Recognized only by plate_solve.py.
        String wallStr = prefs.getString(PreferenceKeys.SolverWallTimeoutKey, "120");
        if (wallStr != null && !wallStr.trim().isEmpty()) {
            params.put("--stargazer-wall-timeout"); params.put(wallStr.trim());
        }

        // Max sources passed to the engine.
        String objsStr = prefs.getString(PreferenceKeys.SolverMaxObjectsKey, "100");
        if (objsStr != null && !objsStr.trim().isEmpty()) {
            params.put("--objs"); params.put(objsStr.trim());
        }

        // Source-extraction downsample.
        String downStr = prefs.getString(PreferenceKeys.SolverDownsampleKey, "2");
        if (downStr != null && !downStr.trim().isEmpty() && !"1".equals(downStr.trim())) {
            params.put("-z"); params.put(downStr.trim());
        }

        // Parity. Default "both" emits nothing; pos/neg map to solve-field's
        // -p flag with values 0/1 (positive/negative).
        String parityStr = prefs.getString(PreferenceKeys.SolverParityKey, "both");
        if ("pos".equals(parityStr)) {
            params.put("--parity"); params.put("pos");
        } else if ("neg".equals(parityStr)) {
            params.put("--parity"); params.put("neg");
        }

        // Positional hint: only when enabled, the user has a GPS fix, and a
        // sane time string is present (the engine itself does not need the
        // time, but a 0,0 GPS hint is almost always wrong).
        boolean hintEnabled = prefs.getBoolean(PreferenceKeys.SolverHintEnabledKey, false);
        boolean hasFix = (latitude != 0.0 || longitude != 0.0);
        if (hintEnabled && hasFix) {
            String radiusStr = prefs.getString(PreferenceKeys.SolverHintRadiusKey, "15");
            params.put("--stargazer-hint-from-gps");
            params.put(String.valueOf(latitude));
            params.put(String.valueOf(longitude));
            params.put(isoTime == null ? "" : isoTime);
            params.put(radiusStr == null ? "15" : radiusStr.trim());
        }

        return params;
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (pythonSolveFuture != null && !pythonSolveFuture.isDone()) {
            pythonSolveFuture.cancel(true);
        }
        solveExecutor.shutdown();
    }
}
