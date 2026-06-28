package net.sourceforge.opencamera;

import android.app.Activity;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.preference.Preference;
import android.preference.PreferenceFragment;
import android.preference.PreferenceManager;
import android.util.Log;
import android.widget.Toast;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import org.json.JSONObject;

import java.io.File;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Preferences UI for plate solver configuration: IERS sync, calibration parameters, solver options.
 * Handles manual IERS synchronization via background thread and Python interop.
 */
public class SolverPreferenceFragment extends PreferenceFragment implements SharedPreferences.OnSharedPreferenceChangeListener {
    private static final String TAG = "SolverPreferenceFragment";
    private ConfigManager configManager;
    private ExecutorService executor = Executors.newSingleThreadExecutor();
    private Handler mainHandler = new Handler(Looper.getMainLooper());

    @Override
    public void onCreate(Bundle savedInstanceState) {
        if (MyDebug.LOG)
            Log.d(TAG, "onCreate");

        super.onCreate(savedInstanceState);

        addPreferencesFromResource(R.xml.preferences_solver);
        configManager = new ConfigManager(getActivity());

        Preference syncButton = findPreference("preference_iers_sync_button");
        if (syncButton != null) {
            syncButton.setOnPreferenceClickListener(preference -> {
                handleIersSyncClick();
                return true;
            });
        }

        updateLastSyncDisplay();

        if (MyDebug.LOG)
            Log.d(TAG, "onCreate done");
    }

    /**
     * Update preference display with last successful IERS sync timestamp.
     */
    private void updateLastSyncDisplay() {
        Preference lastSyncPref = findPreference("preference_iers_last_sync");
        String timestamp = configManager.getIersLastSyncTimestamp();
        if (lastSyncPref != null) {
            if (timestamp != null && !timestamp.isEmpty()) {
                lastSyncPref.setSummary("Last synced: " + timestamp);
            } else {
                lastSyncPref.setSummary(getString(R.string.preference_iers_last_sync_default));
            }
        }
    }

    /**
     * Handle IERS sync button click: invoke Python tools.sync_iers_data() on background thread.
     * Updates UI on main thread with success/failure result.
     */
    private void handleIersSyncClick() {
        Log.d(TAG, "IERS sync button clicked");

        Preference syncButton = findPreference("preference_iers_sync_button");
        if (syncButton != null) {
            syncButton.setTitle(getString(R.string.preference_iers_sync_button) + " (syncing...)");
            syncButton.setEnabled(false);
        }

        executor.execute(() -> {
            try {
                Log.d(TAG, "[IERS] Starting manual sync");

                // Check fragment lifecycle before accessing context (fix for Bug #2)
                Activity activity = getActivity();
                if (activity == null) {
                    Log.w(TAG, "[IERS] Fragment detached, sync cancelled");
                    return;
                }

                if (!Python.isStarted()) {
                    Log.d(TAG, "[IERS] Starting Python runtime");
                    try {
                        Python.start(new AndroidPlatform(activity));
                    } catch (Exception e) {
                        Log.e(TAG, "[IERS] Failed to start Python: " + e.getMessage());
                        mainHandler.post(() -> showSyncResult(false, "Failed to start Python: " + e.getMessage()));
                        return;
                    }
                }

                Python py = Python.getInstance();

                File cacheDir = activity.getCacheDir();
                File iersCacheDir = new File(cacheDir, "iers");

                Log.d(TAG, "[IERS] Cache dir: " + iersCacheDir);

                PyObject tools = py.getModule("tools");
                if (tools == null) {
                    mainHandler.post(() -> showSyncResult(false, "Failed to load tools module"));
                    return;
                }

                PyObject syncResult = tools.callAttr("sync_iers_data", iersCacheDir.getAbsolutePath());
                if (syncResult == null) {
                    mainHandler.post(() -> showSyncResult(false, "Sync function returned null"));
                    return;
                }

                PyObject successObj = syncResult.callAttr("get", "success");
                PyObject messageObj = syncResult.callAttr("get", "message");
                PyObject timestampObj = syncResult.callAttr("get", "timestamp");

                boolean success = successObj != null && successObj.toBoolean();
                String message = messageObj != null ? messageObj.toString() : "Unknown error";
                String timestamp = timestampObj != null ? timestampObj.toString() : null;

                if (success && timestamp != null && !timestamp.equals("None")) {
                    configManager.setIersLastSyncTimestamp(timestamp);
                    Log.d(TAG, "[IERS] Sync success, timestamp=" + timestamp);
                    mainHandler.post(() -> showSyncResult(true, "IERS data synced successfully"));
                } else {
                    Log.w(TAG, "[IERS] Sync failed: " + message);
                    mainHandler.post(() -> showSyncResult(false, message));
                }
            } catch (Exception e) {
                Log.e(TAG, "[IERS] Exception: " + e.getMessage(), e);
                mainHandler.post(() -> showSyncResult(false, "Sync error: " + e.getMessage()));
            } finally {
                mainHandler.post(this::updateLastSyncDisplay);
                mainHandler.post(() -> {
                    Preference syncBtn = findPreference("preference_iers_sync_button");
                    if (syncBtn != null) {
                        syncBtn.setTitle(getString(R.string.preference_iers_sync_button));
                        syncBtn.setEnabled(true);
                    }
                });
            }
        });
    }

    /**
     * Display sync result (success or error message) as toast notification.
     */
    private void showSyncResult(boolean success, String message) {
        String text = (success ? "✓ " : "✗ ") + message;
        Activity activity = getActivity();
        if (activity != null) {
            Toast.makeText(activity, text, Toast.LENGTH_LONG).show();
        }
        Log.d(TAG, "[IERS] " + text);
    }

    @Override
    public void onResume() {
        super.onResume();
        SharedPreferences sharedPreferences = getPreferenceScreen().getSharedPreferences();
        sharedPreferences.registerOnSharedPreferenceChangeListener(this);
        updateLastSyncDisplay();
    }

    @Override
    public void onPause() {
        super.onPause();
        getPreferenceScreen().getSharedPreferences().unregisterOnSharedPreferenceChangeListener(this);
    }

    @Override
    public void onSharedPreferenceChanged(SharedPreferences sharedPreferences, String key) {
        // Refresh last sync display if external preference changes occur
        if (key.equals(PreferenceKeys.IersAutoSyncHoursKey)) {
            updateLastSyncDisplay();
        }
    }

    @Override
    public void onDestroy() {
        executor.shutdown();
        super.onDestroy();
    }
}

