package com.zettabridge.launcher;

import android.app.Application;
import android.os.Build;
import android.system.Os;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;

// The original Test4 application and instrumentation stay in classes.dex.
public final class Test7Application extends ZbApplication {
    @Override public void onCreate() {
        String setup = "enabled";
        try { Os.setenv("ZB_LOAD_TRACE", "1", true); }
        catch (Exception failure) { setup = "unavailable: " + failure; }
        super.onCreate();
        if (Build.VERSION.SDK_INT >= 28 && !Application.getProcessName().endsWith(":guest")) return;
        Diagnostics.stage("Test7 native load tracing " + setup);
        try {
            Runtime.getRuntime().addShutdownHook(new Thread(() -> {
                Diagnostics.stage("Test7 Java VM shutdown hook reached");
                capture(-1);
            }, "zb-test7-shutdown"));
        } catch (Throwable failure) {
            Diagnostics.stage("Test7 shutdown hook unavailable: " + failure);
        }
        Thread sampler = new Thread(() -> {
            int previous = 0;
            for (int seconds : new int[] {5, 20, 45}) {
                try { Thread.sleep((seconds - previous) * 1000L); }
                catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); return; }
                capture(seconds);
                previous = seconds;
            }
        }, "zb-test7-stacks");
        sampler.setDaemon(true);
        sampler.start();
    }

    private static void capture(int seconds) {
        try {
            List<Map.Entry<Thread, StackTraceElement[]>> entries =
                new ArrayList<>(Thread.getAllStackTraces().entrySet());
            entries.sort(Comparator.comparing(entry -> entry.getKey().getName()));
            int shown = 0;
            for (Map.Entry<Thread, StackTraceElement[]> entry : entries) {
                Thread thread = entry.getKey();
                if (thread == Thread.currentThread()) continue;
                boolean relevant = thread.getName().equals("main") || thread.getName().contains("MainThread");
                for (StackTraceElement frame : entry.getValue()) {
                    String owner = frame.getClassName();
                    if (owner.startsWith("com.apportable.") || owner.startsWith("com.zettabridge.")) relevant = true;
                }
                if (!relevant || shown >= 6) continue;
                StringBuilder text = new StringBuilder("Test7 stack +").append(seconds).append("s name=")
                    .append(thread.getName()).append(" javaId=").append(thread.getId())
                    .append(" state=").append(thread.getState());
                StackTraceElement[] frames = entry.getValue();
                for (int i = 0; i < frames.length && i < 10; i++) text.append("\n  at ").append(frames[i]);
                Diagnostics.stage(text.toString());
                shown++;
            }
            Diagnostics.stage("Test7 stack sample +" + seconds + "s complete threads=" + shown);
        } catch (Throwable failure) {
            Diagnostics.stage("Test7 stack sample +" + seconds + "s unavailable: " + failure);
        }
    }
}
