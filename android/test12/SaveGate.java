package com.zettabridge.launcher;
import android.content.Context;
import android.os.Process;
import android.widget.Toast;
import java.io.IOException;
final class SaveGate {
    private static SaveStore.Lease guestLease;
    static boolean isGuest(Context context) {
        if (android.os.Build.VERSION.SDK_INT >= 28)
            return android.app.Application.getProcessName().endsWith(":guest");
        android.app.ActivityManager am = (android.app.ActivityManager)context.getSystemService(Context.ACTIVITY_SERVICE);
        java.util.List<android.app.ActivityManager.RunningAppProcessInfo> processes = am != null ? am.getRunningAppProcesses() : null;
        if (processes != null) for (android.app.ActivityManager.RunningAppProcessInfo p : processes)
            if (p.pid == Process.myPid()) return p.processName.endsWith(":guest");
        throw new IllegalStateException("Cannot identify process for save protection");
    }
    static boolean enterGuest(Context context) {
        try {
            guestLease=SaveStore.lock(context.getFilesDir(),true);
            if(new SaveStore(context.getFilesDir()).pendingRecovery()) throw new IOException("Restore recovery required");
            return true;
        } catch(IOException|RuntimeException e) {
            Toast.makeText(context,"Save management is active. Open the Saves shortcut before launching the game.",Toast.LENGTH_LONG).show();
            Process.killProcess(Process.myPid());return false;
        }
    }
}
