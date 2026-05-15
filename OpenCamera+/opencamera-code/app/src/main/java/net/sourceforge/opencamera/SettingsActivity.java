package net.sourceforge.opencamera;

import android.app.Fragment;
import android.app.FragmentTransaction;
import android.os.Build;
import android.os.Bundle;
import android.preference.Preference;
import android.preference.PreferenceFragment;
import android.preference.PreferenceManager;
import android.util.Log;
import androidx.appcompat.app.AppCompatActivity;

public class SettingsActivity extends AppCompatActivity implements PreferenceFragment.OnPreferenceStartFragmentCallback {
    private static final String TAG = "SettingsActivity";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_settings);

        boolean from_stargazer = getIntent().getBooleanExtra("from_stargazer", false);
        int prefs_xml = from_stargazer ? R.xml.preferences_solver : R.xml.preferences;

        PreferenceManager.setDefaultValues(this, prefs_xml, false);

        if (savedInstanceState == null) {
            Bundle bundle = createDefaultBundle();

            // Check if bundle was passed via Intent (from MainActivity)
            Bundle intentBundle = getIntent().getBundleExtra("preferences_bundle");
            if (intentBundle != null) {
                bundle.putAll(intentBundle);
            }

            FragmentTransaction transaction = getFragmentManager().beginTransaction();
            PreferenceFragment fragment;
            if (from_stargazer) {
                fragment = new SolverPreferenceFragment();
            } else {
                fragment = new MyPreferenceFragment();
            }
            fragment.setArguments(bundle);
            transaction.replace(R.id.fragment_container, fragment, "PREFERENCE_FRAGMENT");
            transaction.commit();
        }
    }

    private Bundle createDefaultBundle() {
        Bundle bundle = new Bundle();
        bundle.putBoolean("edge_to_edge_mode", Build.VERSION.SDK_INT >= Build.VERSION_CODES.VANILLA_ICE_CREAM);
        bundle.putInt("cameraId", 0);
        bundle.putString("cameraIdSPhysical", "");
        bundle.putInt("nCameras", 0);
        bundle.putBoolean("camera_open", false);
        bundle.putString("camera_api", "");
        bundle.putBoolean("using_android_l", false);
        bundle.putString("photo_mode_string", "");
        bundle.putBoolean("supports_auto_stabilise", false);
        bundle.putBoolean("supports_flash", false);
        bundle.putBoolean("supports_force_video_4k", false);
        bundle.putBoolean("supports_camera2", false);
        bundle.putBoolean("supports_face_detection", false);
        bundle.putBoolean("supports_jpeg_r", false);
        bundle.putBoolean("supports_raw", false);
        bundle.putBoolean("supports_burst_raw", false);
        bundle.putBoolean("supports_optimise_focus_latency", false);
        bundle.putBoolean("supports_preshots", false);
        bundle.putBoolean("supports_hdr", false);
        bundle.putBoolean("supports_nr", false);
        bundle.putBoolean("supports_panorama", false);
        bundle.putBoolean("has_gyro_sensors", false);
        bundle.putBoolean("supports_expo_bracketing", false);
        bundle.putBoolean("supports_preview_bitmaps", false);
        bundle.putInt("max_expo_bracketing_n_images", 0);
        bundle.putBoolean("supports_exposure_compensation", false);
        bundle.putInt("exposure_compensation_min", 0);
        bundle.putInt("exposure_compensation_max", 0);
        bundle.putBoolean("supports_iso_range", false);
        bundle.putInt("iso_range_min", 0);
        bundle.putInt("iso_range_max", 0);
        bundle.putBoolean("supports_exposure_time", false);
        bundle.putBoolean("supports_exposure_lock", false);
        bundle.putBoolean("supports_white_balance_lock", false);
        bundle.putLong("exposure_time_min", 0);
        bundle.putLong("exposure_time_max", 0);
        bundle.putBoolean("supports_white_balance_temperature", false);
        bundle.putInt("white_balance_temperature_min", 0);
        bundle.putInt("white_balance_temperature_max", 0);
        bundle.putBoolean("is_multi_cam", false);
        bundle.putBoolean("has_physical_cameras", false);
        bundle.putBoolean("supports_optical_stabilization", false);
        bundle.putBoolean("optical_stabilization_enabled", false);
        bundle.putBoolean("supports_video_stabilization", false);
        bundle.putBoolean("video_stabilization_enabled", false);
        bundle.putBoolean("can_disable_shutter_sound", false);
        bundle.putInt("tonemap_max_curve_points", 0);
        bundle.putBoolean("supports_tonemap_curve", false);
        bundle.putBoolean("supports_photo_video_recording", false);
        bundle.putFloat("camera_view_angle_x", 0);
        bundle.putFloat("camera_view_angle_y", 0);
        bundle.putFloat("min_zoom_factor", 1.0f);
        bundle.putFloat("max_zoom_factor", 1.0f);
        bundle.putInt("magnetic_accuracy", 0);
        bundle.putString("iso_key", "");
        bundle.putInt("preview_width", 0);
        bundle.putInt("preview_height", 0);
        return bundle;
    }

    @Override
    public boolean onPreferenceStartFragment(PreferenceFragment caller, Preference pref) {
        if (MyDebug.LOG) {
            Log.d(TAG, "onPreferenceStartFragment");
            Log.d(TAG, "pref: " + pref.getFragment());
        }

        final Bundle args = new Bundle(caller.getArguments());
        final Fragment fragment = Fragment.instantiate(this, pref.getFragment(), args);
        fragment.setTargetFragment(caller, 0);
        if (MyDebug.LOG) {
            Log.d(TAG, "replace fragment");
        }
        getFragmentManager().beginTransaction().add(android.R.id.content, fragment, "PREFERENCE_FRAGMENT_" + pref.getFragment()).addToBackStack(null).commitAllowingStateLoss();

        return true;
    }
}
