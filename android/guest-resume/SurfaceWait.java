package com.zettabridge.compat;

import com.apportable.MainThread;
import com.apportable.utils.RunLoop;
import java.lang.reflect.Method;

/** Keep Android window messages flowing while Apportable waits for a surface.
 * Called only from readySurface's slow path, outside the surface monitor.
 * The caller reacquires its monitor on the next state check. If dispatch throws,
 * no surface monitor is held while the exception propagates.
 */
public final class SurfaceWait {
    private static boolean announced;
    private SurfaceWait() { }

    public static boolean isOwner() {
        return Thread.currentThread() == MainThread.getThread();
    }

    public static void pump(Object lock) {
        if (!isOwner() || Thread.holdsLock(lock)) {
            throw new IllegalStateException("surface wait must pump on its owner outside mLock");
        }
        if (!announced) {
            announced = true;
            // The host report is useful even when Android filters guest logcat.
            // This optional diagnostic must not change the lifecycle behavior.
            try {
                Class<?> diagnostics = Class.forName("com.zettabridge.launcher.Diagnostics");
                Method stage = diagnostics.getDeclaredMethod("stage", String.class);
                stage.setAccessible(true);
                stage.invoke(null, "Guest3 resume fix: surface wait pumps owner messages");
            } catch (ReflectiveOperationException | RuntimeException ignored) { }
        }
        RunLoop.processMessages();
        synchronized (lock) {
            try {
                // A message alone cannot notify mLock. Bound the idle wait so
                // runWithScissors can complete even without a surface event.
                // A notify arriving just before this wait only costs 50 ms.
                lock.wait(50L);
            } catch (InterruptedException ignored) {
                // Same behavior as the original readySurface: recheck state.
                // Reinterrupting inside a wait loop would busy-spin on mLock.
            }
        }
    }
}
