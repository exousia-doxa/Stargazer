package net.sourceforge.opencamera;

import android.content.Context;
import android.content.SharedPreferences;
import android.preference.PreferenceManager;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.util.HashMap;
import java.util.Map;

public class ConfigManager {
    private static final String PREFS_CONFIG = "stargazer_config";
    private static final String KEY_CORRECTION_MATRIX = "correction_matrix";
    private SharedPreferences prefs;
    private SharedPreferences appPrefs;

    public ConfigManager(Context context) {
        prefs = context.getSharedPreferences(PREFS_CONFIG, Context.MODE_PRIVATE);
        appPrefs = PreferenceManager.getDefaultSharedPreferences(context);
    }

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

            // Get degree step from app preferences
            String degreeStepStr = appPrefs.getString("preference_calibration_degree_step", "5.0");
            double degreeStep = Double.parseDouble(degreeStepStr);
            config.put("degree_step", degreeStep);
        } catch (JSONException | NumberFormatException e) {
            android.util.Log.e("ConfigManager", "Error building config", e);
        }
        return config;
    }

    public void saveConfig(JSONObject config) {
        try {
            SharedPreferences.Editor editor = prefs.edit();

            // Save correction matrix only (degree_step is managed by app preferences)
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

    public void clear() {
        prefs.edit().clear().apply();
    }
}
