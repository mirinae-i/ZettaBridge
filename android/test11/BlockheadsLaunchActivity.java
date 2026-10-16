package com.zettabridge.launcher;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.widget.Toast;

/** Home-screen entry; preserve the existing plugin switch/task/process policy. */
public final class BlockheadsLaunchActivity extends Activity {
    static final String GAME = "com.noodlecake.blockheads";

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        PluginRecord game = PluginStore.find(this, GAME);
        if (game != null && game.isLaunchable() && game.apk().isFile()) {
            Diagnostics.stage("Test11 direct launch " + GAME);
            startActivity(PluginSwitchActivity.intent(this, GAME));
        } else {
            // A fresh install still imports the user's original APK through the
            // existing transactional importer. Never bundle or rewrite the game.
            Diagnostics.stage("Test11 direct launch needs game import");
            Toast.makeText(this, "Import The Blockheads APK once to enable direct launch.",
                    Toast.LENGTH_LONG).show();
            startActivity(new Intent(this, LibraryActivity.class)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP));
        }
        finish();
    }
}
