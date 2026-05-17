package net.sourceforge.opencamera;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.preference.Preference;
import android.preference.PreferenceFragment;
import android.util.Log;
import android.widget.Toast;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import org.json.JSONObject;

import java.io.File;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class SolverPreferenceFragment extends PreferenceFragment {
    private static final String TAG = "SolverPreferenceFragment";
    private ConfigManager configManager;
    private ExecutorService executor = Executors.newSingleThreadExecutor();
    private Handler mainHandler = new Handler(Looper.getMainLooper());

    @Override
    public void onCreate(Bundle savedInstanceState) {
        if (MyDebug.LOG)
            Log.d(TAG, "onCreate");

        super.onCreate(savedInstanceState);

        // Load solver-only preferences
        addPreferencesFromResource(R.xml.preferences_solver);
        configManager = new ConfigManager(getActivity());

        // Setup IERS sync button
        Preference syncButton = findPreference("preference_iers_sync_button");
        if (syncButton != null) {
            syncButton.setOnPreferenceClickListener(preference -> {
                handleIersSyncClick();
                return true;
            });
        }

        // Update last sync display
        updateLastSyncDisplay();

        if (MyDebug.LOG)
            Log.d(TAG, "onCreate done");
    }

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

    private void handleIersSyncClick() {
        Log.d(TAG, "IERS sync button clicked");

        Preference syncButton = findPreference("preference_iers_sync_button");
        if (syncButton != null) {
            syncButton.setTitle(getString(R.string.preference_iers_sync_button) + " (syncing...)");
            syncButton.setEnabled(false);
        }

        // Run sync on background thread
        executor.execute(() -> {
            try {
                Log.d(TAG, "[IERS] Starting manual sync");

                // Initialize Python if needed
                if (!Python.isStarted()) {
                    Log.d(TAG, "[IERS] Starting Python runtime");
                    try {
                        Python.start(new AndroidPlatform(getActivity()));
                    } catch (Exception e) {
                        Log.e(TAG, "[IERS] Failed to start Python: " + e.getMessage());
                        mainHandler.post(() -> showSyncResult(false, "Failed to start Python: " + e.getMessage()));
                        return;
                    }
                }

                Python py = Python.getInstance();

                // Get cache directory
                File cacheDir = getActivity().getCacheDir();
                File iersCacheDir = new File(cacheDir, "iers");

                Log.d(TAG, "[IERS] Cache dir: " + iersCacheDir);

                // Call Python sync function
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

    private void showSyncResult(boolean success, String message) {
        String text = (success ? "✓ " : "✗ ") + message;
        Toast.makeText(getActivity(), text, Toast.LENGTH_LONG).show();
        Log.d(TAG, "[IERS] " + text);
    }

    @Override
    public void onDestroy() {
        executor.shutdown();
        super.onDestroy();
    }
}

