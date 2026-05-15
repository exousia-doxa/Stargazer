package net.sourceforge.opencamera;

import android.os.Bundle;
import android.preference.PreferenceFragment;
import android.util.Log;

public class SolverPreferenceFragment extends PreferenceFragment {
    private static final String TAG = "SolverPreferenceFragment";

    @Override
    public void onCreate(Bundle savedInstanceState) {
        if (MyDebug.LOG)
            Log.d(TAG, "onCreate");

        super.onCreate(savedInstanceState);

        // Load solver-only preferences
        addPreferencesFromResource(R.xml.preferences_solver);

        if (MyDebug.LOG)
            Log.d(TAG, "onCreate done");
    }
}

