package net.sourceforge.opencamera;

import android.app.FragmentTransaction;
import android.os.Build;
import android.os.Bundle;
import android.preference.PreferenceFragment;
import android.preference.PreferenceManager;
import androidx.appcompat.app.AppCompatActivity;

public class SettingsActivity extends AppCompatActivity implements PreferenceFragment.OnPreferenceStartFragmentCallback {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_settings);

        PreferenceManager.setDefaultValues(this, R.xml.preferences, false);

        if (savedInstanceState == null) {
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

            FragmentTransaction transaction = getFragmentManager().beginTransaction();
            MyPreferenceFragment fragment = new MyPreferenceFragment();
            fragment.setArguments(bundle);
            transaction.replace(R.id.fragment_container, fragment, "PREFERENCE_FRAGMENT");
            transaction.commit();
        }
    }

    @Override
    public boolean onPreferenceStartFragment(PreferenceFragment caller, android.preference.Preference pref) {
        return false;
    }
}
