package net.sourceforge.opencamera;

import net.sourceforge.opencamera.ui.FolderChooserDialog;
import net.sourceforge.opencamera.ui.MyEditTextPreference;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.DialogFragment;
import android.app.Fragment;
import android.app.FragmentManager;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.DialogInterface;
//import android.content.Intent;
import android.content.SharedPreferences;
import android.content.SharedPreferences.OnSharedPreferenceChangeListener;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager.NameNotFoundException;
import android.content.res.TypedArray;
import android.graphics.Color;
import android.graphics.Insets;
import android.graphics.Point;
//import android.net.Uri;
import android.graphics.Rect;
import android.os.Build;
import android.os.Bundle;
import android.preference.EditTextPreference;
import android.preference.ListPreference;
import android.preference.Preference;
import android.preference.Preference.OnPreferenceChangeListener;
import android.preference.Preference.OnPreferenceClickListener;
import android.preference.PreferenceFragment;
import android.preference.PreferenceGroup;
import android.preference.PreferenceManager;
import android.preference.TwoStatePreference;
import android.text.Html;
import android.text.SpannableString;
import android.text.Spanned;
import android.text.method.LinkMovementMethod;
import android.util.Log;
import android.view.Display;
import android.view.LayoutInflater;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowMetrics;
import android.widget.ScrollView;
import android.widget.TextView;

import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;

/** Fragment to handle the Settings UI. Note that originally this was a
 *  PreferenceActivity rather than a PreferenceFragment which required all
 *  communication to be via the bundle (since this replaced the MainActivity,
 *  meaning we couldn't access data from that class. This no longer applies due
 *  to now using a PreferenceFragment, but I've still kept with transferring
 *  information via the bundle (for the most part, at least).
 *  Also note that passing via a bundle may be necessary to avoid accessing the
 *  preview, which can be null - see note about video resolutions below.
 *  Also see https://stackoverflow.com/questions/14093438/after-the-rotate-oncreate-fragment-is-called-before-oncreate-fragmentactivi .
 *  If the application is destroyed when in background when the user is viewing
 *  the settings, then the application and its fragments will be recreated -
 *  so reading from the bundle means the state is restored, where as trying
 *  to read camera settings won't be possible as the camera won't yet be
 *  reopened.
 */
public class MyPreferenceFragment extends PreferenceFragment implements OnSharedPreferenceChangeListener {
    private static final String TAG = "MyPreferenceFragment";

    private boolean edge_to_edge_mode = false;

    private int cameraId;

    /* Any AlertDialogs we create should be added to dialogs, and removed when dismissed. Any dialogs still
     * opened when onDestroy() is called are closed.
     * Normally this shouldn't be needed - the settings is usually only closed by the user pressing Back,
     * which can only be done once any opened dialogs are also closed. But this is required if we want to
     * programmatically close the settings - this is done in MainActivity.onNewIntent(), so that if Open Camera
     * is launched from the homescreen again when the settings was opened, we close the settings.
     * UPDATE: At the time of writing, we don't set android:launchMode="singleTask", so onNewIntent() is not called,
     * so this code isn't necessary - but there shouldn't be harm to leave it here for future use.
     */
    private final HashSet<AlertDialog> dialogs = new HashSet<>();

    @Override
    public void onCreate(Bundle savedInstanceState) {
        if( MyDebug.LOG )
            Log.d(TAG, "onCreate");
        super.onCreate(savedInstanceState);
        addPreferencesFromResource(R.xml.preferences);

        final Bundle bundle = getArguments();
        this.edge_to_edge_mode = bundle.getBoolean("edge_to_edge_mode");
        this.cameraId = bundle.getInt("cameraId");
        if( MyDebug.LOG )
            Log.d(TAG, "cameraId: " + cameraId);
        final int nCameras = bundle.getInt("nCameras");
        if( MyDebug.LOG )
            Log.d(TAG, "nCameras: " + nCameras);

        final boolean camera_open = bundle.getBoolean("camera_open");
        if( MyDebug.LOG )
            Log.d(TAG, "camera_open: " + camera_open);

        final String camera_api = bundle.getString("camera_api");

        final String photo_mode_string = bundle.getString("photo_mode_string");

        final boolean using_android_l = bundle.getBoolean("using_android_l");
        if( MyDebug.LOG )
            Log.d(TAG, "using_android_l: " + using_android_l);

        final int camera_orientation = bundle.getInt("camera_orientation");
        if( MyDebug.LOG )
            Log.d(TAG, "camera_orientation: " + camera_orientation);

        final float min_zoom_factor = bundle.getFloat("min_zoom_factor");
        final float max_zoom_factor = bundle.getFloat("max_zoom_factor");

        final SharedPreferences sharedPreferences = PreferenceManager.getDefaultSharedPreferences(this.getActivity());

        final boolean supports_auto_stabilise = bundle.getBoolean("supports_auto_stabilise");
        if( MyDebug.LOG )
            Log.d(TAG, "supports_auto_stabilise: " + supports_auto_stabilise);

		/*if( !supports_auto_stabilise ) {
			Preference pref = findPreference("preference_auto_stabilise");
			PreferenceGroup pg = (PreferenceGroup)this.findPreference("preference_category_camera_effects");
        	pg.removePreference(pref);
		}*/

        //readFromBundle(bundle, "color_effects", Preview.getColorEffectPreferenceKey(), Camera.Parameters.EFFECT_NONE, "preference_category_camera_effects");
        //readFromBundle(bundle, "scene_modes", Preview.getSceneModePreferenceKey(), Camera.Parameters.SCENE_MODE_AUTO, "preference_category_camera_effects");
        //readFromBundle(bundle, "white_balances", Preview.getWhiteBalancePreferenceKey(), Camera.Parameters.WHITE_BALANCE_AUTO, "preference_category_camera_effects");
        //readFromBundle(bundle, "isos", Preview.getISOPreferenceKey(), "auto", "preference_category_camera_effects");
        //readFromBundle(bundle, "exposures", "preference_exposure", "0", "preference_category_camera_effects");

        final boolean supports_face_detection = bundle.getBoolean("supports_face_detection");
        if( MyDebug.LOG )
            Log.d(TAG, "supports_face_detection: " + supports_face_detection);

        if( !supports_face_detection  && ( camera_open || sharedPreferences.getBoolean(PreferenceKeys.FaceDetectionPreferenceKey, false) == false ) ) {
            // if camera not open, we'll think this setting isn't supported - but should only remove
            // this preference if it's set to the default (otherwise if user sets to a non-default
            // value that causes camera to not open, user won't be able to put it back to the
            // default!)
            Preference pref = findPreference(PreferenceKeys.FaceDetectionPreferenceKey);
            PreferenceGroup pg = (PreferenceGroup)this.findPreference("preference_category_camera_controls");
            pg.removePreference(pref);
        }

        final int preview_width = bundle.getInt("preview_width");
        final int preview_height = bundle.getInt("preview_height");
        final int [] preview_widths = bundle.getIntArray("preview_widths");
        final int [] preview_heights = bundle.getIntArray("preview_heights");
        final int [] video_widths = bundle.getIntArray("video_widths");
        final int [] video_heights = bundle.getIntArray("video_heights");

        final int resolution_width = bundle.getInt("resolution_width");
        final int resolution_height = bundle.getInt("resolution_height");
        final int [] widths = bundle.getIntArray("resolution_widths");
        final int [] heights = bundle.getIntArray("resolution_heights");
        final boolean [] supports_burst = bundle.getBooleanArray("resolution_supports_burst");

        final boolean supports_raw = bundle.getBoolean("supports_raw");
        if( MyDebug.LOG )
            Log.d(TAG, "supports_raw: " + supports_raw);

        final boolean supports_hdr = bundle.getBoolean("supports_hdr");
        if( MyDebug.LOG )
            Log.d(TAG, "supports_hdr: " + supports_hdr);

        final boolean supports_panorama = bundle.getBoolean("supports_panorama");
        if( MyDebug.LOG )
            Log.d(TAG, "supports_panorama: " + supports_panorama);

        final boolean has_gyro_sensors = bundle.getBoolean("has_gyro_sensors");
        if( MyDebug.LOG )
            Log.d(TAG, "has_gyro_sensors: " + has_gyro_sensors);

        final boolean supports_expo_bracketing = bundle.getBoolean("supports_expo_bracketing");
        if( MyDebug.LOG )
            Log.d(TAG, "supports_expo_bracketing: " + supports_expo_bracketing);

        final boolean supports_exposure_compensation = bundle.getBoolean("supports_exposure_compensation");
        final int exposure_compensation_min = bundle.getInt("exposure_compensation_min");
        final int exposure_compensation_max = bundle.getInt("exposure_compensation_max");
        if( MyDebug.LOG ) {
            Log.d(TAG, "supports_exposure_compensation: " + supports_exposure_compensation);
            Log.d(TAG, "exposure_compensation_min: " + exposure_compensation_min);
            Log.d(TAG, "exposure_compensation_max: " + exposure_compensation_max);
        }

        final boolean supports_iso_range = bundle.getBoolean("supports_iso_range");
        final int iso_range_min = bundle.getInt("iso_range_min");
        final int iso_range_max = bundle.getInt("iso_range_max");
        if( MyDebug.LOG ) {
            Log.d(TAG, "supports_iso_range: " + supports_iso_range);
            Log.d(TAG, "iso_range_min: " + iso_range_min);
            Log.d(TAG, "iso_range_max: " + iso_range_max);
        }

        final boolean supports_exposure_time = bundle.getBoolean("supports_exposure_time");
        final long exposure_time_min = bundle.getLong("exposure_time_min");
        final long exposure_time_max = bundle.getLong("exposure_time_max");
        if( MyDebug.LOG ) {
            Log.d(TAG, "supports_exposure_time: " + supports_exposure_time);
            Log.d(TAG, "exposure_time_min: " + exposure_time_min);
            Log.d(TAG, "exposure_time_max: " + exposure_time_max);
        }

        final boolean supports_white_balance_temperature = bundle.getBoolean("supports_white_balance_temperature");
        final int white_balance_temperature_min = bundle.getInt("white_balance_temperature_min");
        final int white_balance_temperature_max = bundle.getInt("white_balance_temperature_max");
        if( MyDebug.LOG ) {
            Log.d(TAG, "supports_white_balance_temperature: " + supports_white_balance_temperature);
            Log.d(TAG, "white_balance_temperature_min: " + white_balance_temperature_min);
            Log.d(TAG, "white_balance_temperature_max: " + white_balance_temperature_max);
        }

        final boolean is_multi_cam = bundle.getBoolean("is_multi_cam");
        if( MyDebug.LOG )
            Log.d(TAG, "is_multi_cam: " + is_multi_cam);

        final String [] video_quality = bundle.getStringArray("video_quality");

        final String current_video_quality = bundle.getString("current_video_quality");
        final int video_frame_width = bundle.getInt("video_frame_width");
        final int video_frame_height = bundle.getInt("video_frame_height");
        final int video_bit_rate = bundle.getInt("video_bit_rate");
        final int video_frame_rate = bundle.getInt("video_frame_rate");
        final double video_capture_rate = bundle.getDouble("video_capture_rate");
        final boolean video_high_speed = bundle.getBoolean("video_high_speed");
        final float video_capture_rate_factor = bundle.getFloat("video_capture_rate_factor");

        final boolean supports_optical_stabilization = bundle.getBoolean("supports_optical_stabilization");
        final boolean optical_stabilization_enabled = bundle.getBoolean("optical_stabilization_enabled");

        final boolean supports_video_stabilization = bundle.getBoolean("supports_video_stabilization");
        if( MyDebug.LOG )
            Log.d(TAG, "supports_video_stabilization: " + supports_video_stabilization);

        final boolean video_stabilization_enabled = bundle.getBoolean("video_stabilization_enabled");

        final boolean can_disable_shutter_sound = bundle.getBoolean("can_disable_shutter_sound");
        if( MyDebug.LOG )
            Log.d(TAG, "can_disable_shutter_sound: " + can_disable_shutter_sound);

        final int tonemap_max_curve_points = bundle.getInt("tonemap_max_curve_points");
        final boolean supports_tonemap_curve = bundle.getBoolean("supports_tonemap_curve");
        if( MyDebug.LOG ) {
            Log.d(TAG, "tonemap_max_curve_points: " + tonemap_max_curve_points);
            Log.d(TAG, "supports_tonemap_curve: " + supports_tonemap_curve);
        }

        final float camera_view_angle_x = bundle.getFloat("camera_view_angle_x");
        final float camera_view_angle_y = bundle.getFloat("camera_view_angle_y");
        if( MyDebug.LOG ) {
            Log.d(TAG, "camera_view_angle_x: " + camera_view_angle_x);
            Log.d(TAG, "camera_view_angle_y: " + camera_view_angle_y);
        }

        {
            List<String> camera_api_values = new ArrayList<>();
            List<String> camera_api_entries = new ArrayList<>();

            // all devices support old api
            camera_api_values.add("preference_camera_api_old");
            camera_api_entries.add(getActivity().getResources().getString(R.string.preference_camera_api_old));

            final boolean supports_camera2 = bundle.getBoolean("supports_camera2");
            if( MyDebug.LOG )
                Log.d(TAG, "supports_camera2: " + supports_camera2);
            if( supports_camera2 ) {
                camera_api_values.add("preference_camera_api_camera2");
                camera_api_entries.add(getActivity().getResources().getString(R.string.preference_camera_api_camera2));
            }

            if( camera_api_values.size() == 1 ) {
                // if only supports 1 API, no point showing the preference
                camera_api_values.clear();
                camera_api_entries.clear();
            }

            readFromBundle(camera_api_values.toArray(new String[0]), camera_api_entries.toArray(new String[0]), "preference_camera_api", PreferenceKeys.CameraAPIPreferenceDefault, "preference_category_online");

            if( camera_api_values.size() >= 2 ) {
                final Preference pref = findPreference("preference_camera_api");
                pref.setOnPreferenceChangeListener(new OnPreferenceChangeListener() {
                    @Override
                    public boolean onPreferenceChange(Preference arg0, Object newValue) {
                        if( pref.getKey().equals("preference_camera_api") ) {
                            ListPreference list_pref = (ListPreference)pref;
                            if( list_pref.getValue().equals(newValue) ) {
                                if( MyDebug.LOG )
                                    Log.d(TAG, "user selected same camera API");
                            }
                            else {
                                if( MyDebug.LOG )
                                    Log.d(TAG, "user changed camera API - need to restart");
                                MainActivity main_activity = (MainActivity)MyPreferenceFragment.this.getActivity();
                                main_activity.restartOpenCamera();
                            }
                        }
                        return true;
                    }
                });
            }
        }
        /*final boolean supports_camera2 = bundle.getBoolean("supports_camera2");
        if( MyDebug.LOG )
            Log.d(TAG, "supports_camera2: " + supports_camera2);
        if( supports_camera2 ) {
            final Preference pref = findPreference("preference_use_camera2");
            pref.setOnPreferenceClickListener(new OnPreferenceClickListener() {
                @Override
                public boolean onPreferenceClick(Preference arg0) {
                    if( pref.getKey().equals("preference_use_camera2") ) {
                        if( MyDebug.LOG )
                            Log.d(TAG, "user clicked camera2 API - need to restart");
                        MainActivity main_activity = (MainActivity)MyPreferenceFragment.this.getActivity();
                        main_activity.restartOpenCamera();
                        return false;
                    }
                    return false;
                }
            });
        }
        else {
            Preference pref = findPreference("preference_use_camera2");
            PreferenceGroup pg = (PreferenceGroup)this.findPreference("preference_category_online");
            pg.removePreference(pref);
        }*/

        setupDependencies();
    }

    @Override
    public void onViewCreated(View view, Bundle savedInstanceState) {
        super.onViewCreated(view, savedInstanceState);

        if( edge_to_edge_mode ) {
            handleEdgeToEdge(view);
        }
    }

    static void handleEdgeToEdge(View view) {
        ViewCompat.setOnApplyWindowInsetsListener(view, (v, windowInsets) -> {
            //androidx.core.graphics.Insets insets = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout());
            // don't need to avoid WindowInsetsCompat.Type.displayCutout(), as we already do this for the entire activity (see MainActivity's setOnApplyWindowInsetsListener)
            androidx.core.graphics.Insets insets = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars());
            v.setPadding(insets.left, insets.top, insets.right, insets.bottom);
            return WindowInsetsCompat.CONSUMED;
        });
        view.requestApplyInsets();
    }

    /** Adds a TextView to an AlertDialog builder, placing it inside a scrollview and adding appropriate padding.
     */
    private void addTextViewForAlertDialog(AlertDialog.Builder alertDialog, TextView textView) {
        final float scale = getActivity().getResources().getDisplayMetrics().density;
        ScrollView scrollView = new ScrollView(getActivity());
        scrollView.addView(textView);
        // padding values from /sdk/platforms/android-18/data/res/layout/alert_dialog.xml
        textView.setPadding((int)(5*scale+0.5f), (int)(5*scale+0.5f), (int)(5*scale+0.5f), (int)(5*scale+0.5f));
        scrollView.setPadding((int)(14*scale+0.5f), (int)(2*scale+0.5f), (int)(10*scale+0.5f), (int)(12*scale+0.5f));
        alertDialog.setView(scrollView);
    }

    /** Programmatically set up dependencies for preference types (e.g., ListPreference) that don't
     *  support this in xml (such as SwitchPreference and CheckBoxPreference), or where this depends
     *  on the device (e.g., Android version).
     */
    private void setupDependencies() {
    }

    /** Removes an entry and value pair from a ListPreference, if it exists.
     * @param pref The ListPreference to remove the supplied entry/value.
     * @param filter_value The value to remove from the list.
     */
    static void filterArrayEntry(ListPreference pref, String filter_value) {
        {
            CharSequence [] orig_entries = pref.getEntries();
            CharSequence [] orig_values = pref.getEntryValues();
            List<CharSequence> new_entries = new ArrayList<>();
            List<CharSequence> new_values = new ArrayList<>();
            for(int i=0;i<orig_entries.length;i++) {
                CharSequence value = orig_values[i];
                if( !value.equals(filter_value) ) {
                    new_entries.add(orig_entries[i]);
                    new_values.add(value);
                }
            }
            CharSequence [] new_entries_arr = new CharSequence[new_entries.size()];
            new_entries.toArray(new_entries_arr);
            CharSequence [] new_values_arr = new CharSequence[new_values.size()];
            new_values.toArray(new_values_arr);
            pref.setEntries(new_entries_arr);
            pref.setEntryValues(new_values_arr);
        }
    }

    public static class SaveFolderChooserDialog extends FolderChooserDialog {
        @Override
        public void onDismiss(DialogInterface dialog) {
            if( MyDebug.LOG )
                Log.d(TAG, "FolderChooserDialog dismissed");
            // n.b., fragments have to be static (as they might be inserted into a new Activity - see http://stackoverflow.com/questions/15571010/fragment-inner-class-should-be-static),
            // so we access the MainActivity via the fragment's getActivity().
            MainActivity main_activity = (MainActivity)this.getActivity();
            if( main_activity != null ) { // main_activity may be null if this is being closed via MainActivity.onNewIntent()
                String new_save_location = this.getChosenFolder();
                main_activity.updateSaveFolder(new_save_location);
            }
            super.onDismiss(dialog);
        }
    }

    private void readFromBundle(String [] values, String [] entries, String preference_key, String default_value, String preference_category_key) {
        readFromBundle(this, values, entries, preference_key, default_value, preference_category_key);
    }

    static void readFromBundle(PreferenceFragment preference_fragment, String [] values, String [] entries, String preference_key, String default_value, String preference_category_key) {
        if( MyDebug.LOG ) {
            Log.d(TAG, "readFromBundle");
        }
        if( values != null && values.length > 0 ) {
            if( MyDebug.LOG ) {
                Log.d(TAG, "values:");
                for(String value : values) {
                    Log.d(TAG, value);
                }
            }
            ListPreference lp = (ListPreference)preference_fragment.findPreference(preference_key);
            lp.setEntries(entries);
            lp.setEntryValues(values);
            SharedPreferences sharedPreferences = PreferenceManager.getDefaultSharedPreferences(preference_fragment.getActivity());
            String value = sharedPreferences.getString(preference_key, default_value);
            if( MyDebug.LOG )
                Log.d(TAG, "    value: " + Arrays.toString(values));
            lp.setValue(value);
        }
        else {
            if( MyDebug.LOG )
                Log.d(TAG, "remove preference " + preference_key + " from category " + preference_category_key);
            Preference pref = preference_fragment.findPreference(preference_key);
            PreferenceGroup pg = (PreferenceGroup)preference_fragment.findPreference(preference_category_key);
            pg.removePreference(pref);
        }
    }

    static void setBackground(Fragment fragment) {
        // prevent fragment being transparent
        // note, setting color here only seems to affect the "main" preference fragment screen, and not sub-screens
        // note, on Galaxy Nexus Android 4.3 this sets to black rather than the dark grey that the background theme should be (and what the sub-screens use); works okay on Nexus 7 Android 5
        // we used to use a light theme for the PreferenceFragment, but mixing themes in same activity seems to cause problems (e.g., for EditTextPreference colors)
        TypedArray array = fragment.getActivity().getTheme().obtainStyledAttributes(new int[] {
                android.R.attr.colorBackground
        });
        int backgroundColor = array.getColor(0, Color.BLACK);
		/*if( MyDebug.LOG ) {
			int r = (backgroundColor >> 16) & 0xFF;
			int g = (backgroundColor >> 8) & 0xFF;
			int b = (backgroundColor >> 0) & 0xFF;
			Log.d(TAG, "backgroundColor: " + r + " , " + g + " , " + b);
		}*/
        fragment.getView().setBackgroundColor(backgroundColor);
        array.recycle();
    }

    @Override
    public void onResume() {
        super.onResume();
        SharedPreferences sharedPreferences = getPreferenceScreen().getSharedPreferences();
        sharedPreferences.registerOnSharedPreferenceChangeListener(this);
        // Initialize summaries of all preferences
        initSummaries(getPreferenceScreen());
    }

    @Override
    public void onPause() {
        super.onPause();
        getPreferenceScreen().getSharedPreferences().unregisterOnSharedPreferenceChangeListener(this);
    }

    @Override
    public void onDestroy() {
        if( MyDebug.LOG )
            Log.d(TAG, "onDestroy");
        super.onDestroy();

        if( MyDebug.LOG )
            Log.d(TAG, "isRemoving?: " + isRemoving());

        if( isRemoving() ) {
            // if isRemoving()==true, then it means the fragment is being removed and we are returning to the activity
            // if isRemoving()==false, then it may be that the activity is being destroyed
            ((MainActivity)getActivity()).settingsClosing();
        }

        dismissDialogs(getFragmentManager(), dialogs);
    }

    static void dismissDialogs(FragmentManager fragment_manager, HashSet<AlertDialog> dialogs) {
        // dismiss open dialogs - see comment for dialogs for why we do this
        for(AlertDialog dialog : dialogs) {
            if( MyDebug.LOG )
                Log.d(TAG, "dismiss dialog: " + dialog);
            dialog.dismiss();
        }
        // similarly dimiss any dialog fragments still opened
        Fragment folder_fragment = fragment_manager.findFragmentByTag("FOLDER_FRAGMENT");
        if( folder_fragment != null ) {
            DialogFragment dialogFragment = (DialogFragment)folder_fragment;
            if( MyDebug.LOG )
                Log.d(TAG, "dismiss dialogFragment: " + dialogFragment);
            dialogFragment.dismissAllowingStateLoss();
        }
    }

    /* So that manual changes to the checkbox/switch preferences, while the preferences are showing, show up;
     * in particular, needed for preference_using_saf, when the user cancels the SAF dialog (see
     * MainActivity.onActivityResult).
     * Also programmatically sets summary (see setSummary).
     */
    @Override
    public void onSharedPreferenceChanged(SharedPreferences sharedPreferences, String key) {
        if( MyDebug.LOG )
            Log.d(TAG, "onSharedPreferenceChanged: " + key);
        updatePreference(findPreference(key));

        // Stargazer specific preferences update
        switch (key) {
            case PreferenceKeys.MatrixWidthPreferenceKey:
            case PreferenceKeys.MatrixHeightPreferenceKey:
            case PreferenceKeys.FocalLengthPreferenceKey:
            case PreferenceKeys.SolverFieldMinKey:
            case PreferenceKeys.SolverFieldMaxKey:
            case PreferenceKeys.SolverCpuLimitKey:
            case PreferenceKeys.SolverWallTimeoutKey:
            case PreferenceKeys.SolverMaxObjectsKey:
            case PreferenceKeys.SolverHintRadiusKey:
                EditTextPreference editTextPref = (EditTextPreference)findPreference(key);
                if (editTextPref != null) {
                    String value = editTextPref.getText();
                    if (value == null || value.trim().isEmpty()) {
                        value = "0"; // Default value if empty
                    }
                    // Update summary to show the current value
                    editTextPref.setSummary(value);
                }
                break;
        }
    }

    // Helper method to initialize summaries on startup
    private void initSummaries(Preference p) {
        if (p instanceof PreferenceGroup) {
            PreferenceGroup pGrp = (PreferenceGroup) p;
            for (int i = 0; i < pGrp.getPreferenceCount(); i++) {
                initSummaries(pGrp.getPreference(i));
            }
        } else {
            updatePreference(p);
        }
    }

    // Updated updatePreference method to handle Stargazer prefs
    private void updatePreference(Preference p) {
        if (p == null) {
            return;
        }
        if (p instanceof ListPreference) {
            ListPreference listp = (ListPreference) p;
            p.setSummary(listp.getEntry());
        } else if (p instanceof EditTextPreference) {
            EditTextPreference editTextPref = (EditTextPreference) p;
            String key = editTextPref.getKey();

            switch (key) {
                case PreferenceKeys.MatrixWidthPreferenceKey:
                case PreferenceKeys.MatrixHeightPreferenceKey:
                case PreferenceKeys.FocalLengthPreferenceKey:
                case PreferenceKeys.SolverFieldMinKey:
                case PreferenceKeys.SolverFieldMaxKey:
                case PreferenceKeys.SolverCpuLimitKey:
                case PreferenceKeys.SolverWallTimeoutKey:
                case PreferenceKeys.SolverMaxObjectsKey:
                case PreferenceKeys.SolverHintRadiusKey:
                    String value = editTextPref.getText();
                    if (value == null || value.trim().isEmpty()) {
                        value = "0"; // Default value
                    }
                    editTextPref.setSummary(value);
                    break;
                default:
                    // For other EditTextPreferences if any
                    p.setSummary(editTextPref.getText());
                    break;
            }
        }
    }

    static void handleOnSharedPreferenceChanged(SharedPreferences prefs, String key, Preference pref) {
        if( MyDebug.LOG )
            Log.d(TAG, "handleOnSharedPreferenceChanged: " + key);

        if( pref == null ) {
            // this can happen if the shared preference that changed is for a sub-screen i.e. a different fragment
            if( MyDebug.LOG )
                Log.d(TAG, "handleOnSharedPreferenceChanged: preference doesn't belong to this fragment");
            return;
        }

        if( pref instanceof TwoStatePreference ) {
            TwoStatePreference twoStatePref = (TwoStatePreference)pref;
            twoStatePref.setChecked(prefs.getBoolean(key, true));
        }
        else if( pref instanceof  ListPreference ) {
            ListPreference listPref = (ListPreference)pref;
            listPref.setValue(prefs.getString(key, ""));
        }
        setSummary(pref);
    }

    /** Programmatically sets summaries as required.
     *  Remember to call setSummary() from the constructor for any keys we set, to initialise the
     *  summary.
     */
    static void setSummary(Preference pref) {
        if( pref instanceof EditTextPreference ) {
            /* We have a runtime check for using EditTextPreference - we don't want these due to importance of
             * supporting the Google Play emoji policy (see comment in MyEditTextPreference.java) - and this
             * helps guard against the risk of accidentally adding more EditTextPreferences in future.
             * Once we've switched to using Android X Preference library, and hence safe to use EditTextPreference
             * again, this code can be removed.
             */
            throw new RuntimeException("detected an EditTextPreference: " + pref.getKey() + " pref: " + pref);
        }

        if( pref.getKey().equals("preference_save_location") ) {
            // can't use %s (as only supported for ListPreference), so handle this directly
            MainActivity main_activity = (MainActivity)pref.getContext();
            String folder_name;
            if( main_activity.getStorageUtils().isUsingSAF() ) {
                folder_name = main_activity.getStorageUtils().getSaveLocationSAF();
            }
            else {
                folder_name = main_activity.getStorageUtils().getSaveLocation();
            }
            folder_name = main_activity.getHumanReadableSaveFolder(folder_name);
            String summary = main_activity.getResources().getString(R.string.preference_save_location_summary);
            if( !folder_name.isEmpty() ) {
                summary += "\n" + folder_name;
            }
            pref.setSummary(summary);
        }
        else if( pref instanceof EditTextPreference || pref instanceof MyEditTextPreference ) {
            // %s only supported for ListPreference
            // we also display the usual summary if no preference value is set
            if( pref.getKey().equals("preference_exif_artist") ||
                    pref.getKey().equals("preference_exif_copyright") ||
                    pref.getKey().equals("preference_save_photo_prefix") ||
                    pref.getKey().equals("preference_save_video_prefix") ||
                    pref.getKey().equals("preference_textstamp")
            ) {
                String default_value = "";
                if( pref.getKey().equals("preference_save_photo_prefix") )
                    default_value = "IMG_";
                else if( pref.getKey().equals("preference_save_video_prefix") )
                    default_value = "VID_";

                String current_value;
                if( pref instanceof EditTextPreference ) {
                    EditTextPreference editTextPref = (EditTextPreference)pref;
                    current_value = editTextPref.getText();
                }
                else {
                    MyEditTextPreference editTextPref = (MyEditTextPreference)pref;
                    current_value = editTextPref.getText();
                }

                if( current_value.equals(default_value) ) {
                    switch (pref.getKey()) {
                        case "preference_exif_artist":
                            pref.setSummary(R.string.preference_exif_artist_summary);
                            break;
                        case "preference_exif_copyright":
                            pref.setSummary(R.string.preference_exif_copyright_summary);
                            break;
                        case "preference_save_photo_prefix":
                            pref.setSummary(R.string.preference_save_photo_prefix_summary);
                            break;
                        case "preference_save_video_prefix":
                            pref.setSummary(R.string.preference_save_video_prefix_summary);
                            break;
                        case "preference_textstamp":
                            pref.setSummary(R.string.preference_textstamp_summary);
                            break;
                    }
                }
                else {
                    // non-default value, so display the current value
                    pref.setSummary(current_value);
                }
            }
        }
    }
}
