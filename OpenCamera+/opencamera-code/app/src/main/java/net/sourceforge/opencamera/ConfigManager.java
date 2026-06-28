package net.sourceforge.opencamera;

import android.content.Context;
import android.content.SharedPreferences;
import android.preference.PreferenceManager;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.io.File;
import java.util.HashMap;
import java.util.Map;

/**
 * Manages persistent configuration: correction matrix bins, IERS sync timestamps, solver parameters.
 * Uses SharedPreferences for storage (local) and app preferences for user-configurable settings.
 */
public class ConfigManager {
    private static final String PREFS_CONFIG = "stargazer_config";
    private static final String KEY_CORRECTION_MATRIX = "correction_matrix";
    private static final String KEY_IERS_LAST_SYNC = "iers_last_sync";
    private SharedPreferences prefs;
    private SharedPreferences appPrefs;
    private Context context;

    /**
     * Initialize ConfigManager with Android application context.
     */
    public ConfigManager(Context context) {
        this.context = context;
        prefs = context.getSharedPreferences(PREFS_CONFIG, Context.MODE_PRIVATE);
        appPrefs = PreferenceManager.getDefaultSharedPreferences(context);
    }

    /**
     * Load all configuration (correction matrices, degree step, IERS cache directory).
     * Returns JSONObject with keys: correction_matrix, degree_step, iers_cache_dir.
     */
    public JSONObject getConfig() {
        JSONObject config = new JSONObject();
        try {
            // Get correction matrix (stored as JSON array of [degree_range, matrix])
            String matrixJson = prefs.getString(KEY_CORRECTION_MATRIX, null);
            if (matrixJson != null && !matrixJson.isEmpty()) {
                JSONArray matrixArray = new JSONArray(matrixJson);
                config.put("correction_matrix", matrixArray);
            } else {
                config.put("correction_matrix", new JSONArray());
            }

            // Get degree step from app preferences with safe parsing
            String degreeStepStr = appPrefs.getString(PreferenceKeys.CalibrationDegreeStepKey, "5.0");
            double degreeStep = 5.0;
            if (degreeStepStr != null && !degreeStepStr.trim().isEmpty()) {
                try {
                    degreeStep = Double.parseDouble(degreeStepStr);
                } catch (NumberFormatException e) {
                    android.util.Log.w("ConfigManager", "Invalid degree_step value: " + degreeStepStr + ", using default 5.0", e);
                }
            }
            config.put("degree_step", degreeStep);

            // Include IERS cache dir so Python can load cached data during solve
            File iersCacheDir = new File(context.getCacheDir(), "iers");
            config.put("iers_cache_dir", iersCacheDir.getAbsolutePath());
        } catch (JSONException e) {
            android.util.Log.e("ConfigManager", "Error building config", e);
        }
        return config;
    }

    /**
     * Persist configuration to SharedPreferences (correction matrix only; degree_step via app preferences).
     */
    public void saveConfig(JSONObject config) {
        try {
            SharedPreferences.Editor editor = prefs.edit();

            JSONArray correctionMatrix = config.optJSONArray("correction_matrix");
            if (correctionMatrix != null) {
                editor.putString(KEY_CORRECTION_MATRIX, correctionMatrix.toString());
            }

            editor.apply();
            android.util.Log.d("ConfigManager", "Config saved to SharedPreferences");
        } catch (Exception e) {
            android.util.Log.e("ConfigManager", "Error saving config", e);
        }
    }

    /**
     * Get last IERS data synchronization timestamp (ISO 8601 format or null if never synced).
     */
    public String getIersLastSyncTimestamp() {
        return prefs.getString(KEY_IERS_LAST_SYNC, null);
    }

    /**
     * Record IERS data synchronization timestamp after successful sync.
     */
    public void setIersLastSyncTimestamp(String timestamp) {
        prefs.edit().putString(KEY_IERS_LAST_SYNC, timestamp).apply();
    }

    /**
     * Get IERS auto-sync interval in hours from app preferences (default 168 = 1 week).
     */
    public int getIersAutoSyncHours() {
        try {
            String val = appPrefs.getString(PreferenceKeys.IersAutoSyncHoursKey, "168");
            return Integer.parseInt(val);
        } catch (NumberFormatException e) {
            return 168;
        }
    }

    /**
     * Clear all stored configuration.
     */
    public void clear() {
        prefs.edit().clear().apply();
    }
}
