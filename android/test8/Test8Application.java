package com.zettabridge.launcher;

import android.app.Activity;
import android.app.Application;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.system.Os;
import android.util.DisplayMetrics;
import android.view.WindowManager;
import android.view.SurfaceView;
import android.view.View;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import javax.microedition.khronos.egl.EGL10;
import javax.microedition.khronos.egl.EGL11;

/** Test11 retains this class name for the pinned launcher/JNI ABI. */
public final class Test8Application extends ZbApplication {
    private final Handler main = new Handler(Looper.getMainLooper());
    private final AtomicLong swaps = new AtomicLong();
    private final AtomicLong goodSwaps = new AtomicLong();
    private volatile Activity game;
    private Object observedEgl;
    private String eglState = "not observed";
    private long started, discoveryStarted;
    private int reportStep;
    private boolean samplePending, inspectionWarning;
    private static final long[] REPORT_SECONDS = {0, 5, 15, 30, 60};
    private static native String inspectNative();

    @Override public void onCreate() {
        try {
            Os.setenv("ZB_LOAD_TRACE", "0", true);
            Os.setenv("ZB_BLOCKHEADS_NATIVE_SCREEN", "1", true);
        }
        catch (Exception e) { Diagnostics.stage("Test11 tracing unavailable: " + e); }
        super.onCreate();
        if (Build.VERSION.SDK_INT >= 28 && !Application.getProcessName().endsWith(":guest")) return;
        try { prepareUiDensity(); }
        catch (android.system.ErrnoException e) { Diagnostics.stage("Test11 UI density environment unavailable: " + e); }
        installConfigurationDispatch();
        discoveryStarted = SystemClock.uptimeMillis();
        main.postDelayed(this::discoverGame, 250);
    }

    // Match the native mode's real-display coordinate space. Do not use the
    // screenshot's dimensions or a model-specific PPI. This is a launch-time
    // choice: like Test10, changing panels while running requires a relaunch.
    @SuppressWarnings("deprecation")
    private void prepareUiDensity() throws android.system.ErrnoException {
        Os.setenv("ZB_BLOCKHEADS_UI_POINTS", "600.0", true);
        try {
            WindowManager wm = (WindowManager) getSystemService(WINDOW_SERVICE);
            if (wm == null || wm.getDefaultDisplay() == null) return;
            DisplayMetrics metrics = new DisplayMetrics();
            wm.getDefaultDisplay().getRealMetrics(metrics);
            UiDensity policy = UiDensity.choose(metrics.widthPixels, metrics.heightPixels,
                    metrics.xdpi, metrics.ydpi, metrics.densityDpi);
            Os.setenv("ZB_BLOCKHEADS_UI_POINTS", Float.toString(policy.points), true);
            Diagnostics.stage("Test11 UI density width=" + metrics.widthPixels + " height=" + metrics.heightPixels +
                    " xdpi=" + metrics.xdpi + " ydpi=" + metrics.ydpi + " densityDpi=" + metrics.densityDpi +
                    " source=" + policy.source + " points=" + policy.points + " sizeRatio=" + 600f / policy.points);
        } catch (RuntimeException e) {
            Diagnostics.stage("Test11 UI density unavailable; retain Test10 scale: " + e);
        }
    }

    static final class UiDensity {
        final float points;
        final String source;
        private UiDensity(float width, String why) { points = width; source = why; }
        static UiDensity choose(int width, int height, float xdpi, float ydpi, int densityDpi) {
            int shorter = Math.min(width, height), longer = Math.max(width, height);
            // Only near-square panels. A narrow cover screen keeps its Test10 UI.
            if (shorter <= 0 || (double) longer / shorter > 1.35)
                return new UiDensity(600f, "unchanged-aspect");
            float dpi;
            String source;
            if (Float.isFinite(xdpi) && Float.isFinite(ydpi) && xdpi >= 72f && ydpi >= 72f &&
                    xdpi <= 1000f && ydpi <= 1000f && Math.max(xdpi, ydpi) / Math.min(xdpi, ydpi) <= 1.2f) {
                dpi = (float) Math.sqrt((double) xdpi * ydpi);
                source = "physical-ppi";
            } else if (densityDpi >= 72 && densityDpi <= 1000) {
                dpi = densityDpi;
                source = "logical-dpi-fallback";
            } else return new UiDensity(600f, "unchanged-invalid-density");
            // Target one game point per Android baseline dp (1/160 inch with
            // physical PPI). Limit this first adjustment to 12 percent smaller.
            // Both axes share one scale, and native surface pixels stay intact.
            float nativeScale = width / 600f;
            float scale = Math.max(nativeScale * 0.88f, Math.min(nativeScale, dpi / 160f));
            return new UiDensity(Math.max(600f, Math.min(600f / 0.88f, width / scale)), source);
        }
    }

    private static Field field(Class<?> type, String name) throws NoSuchFieldException {
        for (Class<?> c = type; c != null; c = c.getSuperclass()) {
            try { Field f = c.getDeclaredField(name); f.setAccessible(true); return f; }
            catch (NoSuchFieldException ignored) { }
        }
        throw new NoSuchFieldException(type.getName() + "." + name);
    }
    private static Object get(Object object, String name) throws ReflectiveOperationException {
        return object == null ? null : field(object.getClass(), name).get(object);
    }
    private static Object call(Object object, String name) throws ReflectiveOperationException {
        Method m = object.getClass().getMethod(name); m.setAccessible(true); return m.invoke(object);
    }
    private static Object activityThread() throws ReflectiveOperationException {
        Method m = Class.forName("android.app.ActivityThread").getDeclaredMethod("currentActivityThread");
        m.setAccessible(true); return m.invoke(null);
    }
    private static String value(Object object, String name) {
        try { return String.valueOf(get(object, name)); }
        catch (ReflectiveOperationException | RuntimeException e) { return "unavailable(" + name + ")"; }
    }
    private static Throwable cause(Throwable t) {
        return t instanceof InvocationTargetException && t.getCause() != null ? t.getCause() : t;
    }

    // Plugin instrumentation replaces Activity.mApplication. Host Application callbacks
    // therefore cannot discover this activity. Inspect the live framework records on main.
    private void discoverGame() {
        try {
            Object records = get(activityThread(), "mActivities");
            if (records instanceof Map) for (Object record : ((Map<?, ?>) records).values()) {
                Object a = get(record, "activity");
                if (a instanceof Activity && a.getClass().getName().equals("com.apportable.activity.VerdeActivity")
                        && !((Activity) a).isDestroyed()) {
                    game = (Activity) a; started = SystemClock.uptimeMillis(); reportStep = 0;
                    Diagnostics.stage("Test11 display diagnostics attached application=" + game.getApplication().getClass().getName());
                    sample(); return;
                }
            }
        } catch (ReflectiveOperationException | RuntimeException e) {
            if (!inspectionWarning) {
                inspectionWarning = true; Diagnostics.stage("Test11 activity discovery unavailable: " + cause(e));
            }
        }
        if (SystemClock.uptimeMillis() - discoveryStarted < 60000) main.postDelayed(this::discoverGame, 250);
        else Diagnostics.stage("Test11 activity discovery timed out");
    }

    private void installConfigurationDispatch() {
        try {
            Object thread = activityThread();
            Handler h = (Handler) get(thread, "mH");
            Field callbackField = field(Handler.class, "mCallback");
            Handler.Callback previous = (Handler.Callback) callbackField.get(h);
            int execute = field(h.getClass(), "EXECUTE_TRANSACTION").getInt(null);
            callbackField.set(h, (Handler.Callback) message -> {
                List<PendingRoot> roots = new ArrayList<>();
                if (message.what == execute && message.obj != null) {
                    try { roots = collectConfigurationRoots(thread, message.obj); }
                    catch (ReflectiveOperationException | RuntimeException e) {
                        roots.clear();
                        if (!inspectionWarning) {
                            inspectionWarning = true;
                            Diagnostics.stage("Test11 configuration inspection unavailable: " + cause(e));
                        }
                    }
                }
                if (roots.isEmpty()) return previous != null && previous.handleMessage(message);
                List<PendingRoot> detached = new ArrayList<>();
                try {
                    for (PendingRoot root : roots) {
                        if (root.decorField.get(root.activity) == root.decor) {
                            root.decorField.set(root.activity, null); detached.add(root);
                        }
                    }
                    if (previous == null || !previous.handleMessage(message)) h.handleMessage(message);
                    return true;
                } catch (IllegalAccessException e) {
                    throw new IllegalStateException("Test11 cannot defer foreign decor", e);
                } finally {
                    for (PendingRoot root : detached) root.restoreAndDispatch();
                }
            });
            Diagnostics.stage("Test11 configuration owner-thread dispatch installed");
        } catch (ReflectiveOperationException | RuntimeException e) {
            Diagnostics.stage("Test11 configuration dispatch unavailable: " + cause(e));
        }
    }

    private static List<PendingRoot> collectConfigurationRoots(Object thread, Object transaction)
            throws ReflectiveOperationException {
        List<PendingRoot> result = new ArrayList<>();
        Object rawItems = call(transaction, "getTransactionItems");
        if (!(rawItems instanceof List)) return result;
        List<?> items = (List<?>) rawItems;
        // Lifecycle, relaunch and display-migration transactions retain their normal path.
        for (Object item : items) if (!item.getClass().getName().equals(
                "android.app.servertransaction.ActivityConfigurationChangeItem")) return result;
        Map<?, ?> records = (Map<?, ?>) get(thread, "mActivities");
        for (Object item : items) {
            Object record = records.get(call(item, "getActivityToken"));
            Object rawActivity = get(record, "activity");
            if (!(rawActivity instanceof Activity) || !rawActivity.getClass().getName().equals(
                    "com.apportable.activity.VerdeActivity")) continue;
            Activity activity = (Activity) rawActivity;
            Field decorField = field(Activity.class, "mDecor");
            View decor = (View) decorField.get(activity);
            if (decor == null || decor.getHandler() == null || decor.getDisplay() == null) continue;
            Handler owner = decor.getHandler();
            if (owner.getLooper().getThread() == Thread.currentThread()) continue;
            Object root = decor.getParent();
            if (root == null || !root.getClass().getName().equals("android.view.ViewRootImpl")) continue;
            Method update = root.getClass().getMethod("updateConfiguration", int.class); update.setAccessible(true);
            boolean duplicate = false;
            for (PendingRoot old : result) if (old.activity == activity) duplicate = true;
            if (!duplicate) result.add(new PendingRoot(activity, decorField, decor, root, owner, update,
                    decor.getDisplay().getDisplayId()));
        }
        return result;
    }

    private static final class PendingRoot {
        final Activity activity;
        final Field decorField;
        final View decor;
        final Object root;
        final Handler owner;
        final Method update;
        final int displayId;
        PendingRoot(Activity a, Field f, View d, Object r, Handler h, Method u, int display) {
            activity = a; decorField = f; decor = d; root = r; owner = h; update = u; displayId = display;
        }
        void restoreAndDispatch() {
            try { if (decorField.get(activity) == null) decorField.set(activity, decor); }
            catch (IllegalAccessException e) { throw new IllegalStateException("Test11 cannot restore decor", e); }
            boolean posted = owner.post(() -> {
                if (activity.isDestroyed() || !decor.isAttachedToWindow() || decor.getParent() != root) return;
                try {
                    update.invoke(root, displayId);
                    Diagnostics.stage("Test11 configuration delivered owner=" + Thread.currentThread().getName());
                } catch (ReflectiveOperationException e) {
                    Diagnostics.stage("Test11 configuration delivery failed: " + cause(e));
                    throw new IllegalStateException("Test11 configuration delivery failed", cause(e));
                }
            });
            Diagnostics.stage("Test11 configuration routed owner=" + owner.getLooper().getThread().getName() + " posted=" + posted);
        }
    }

    private void sample() {
        Activity a = game;
        if (a == null || a.isDestroyed()) return;
        long seconds = (SystemClock.uptimeMillis() - started) / 1000;
        boolean report = reportStep < REPORT_SECONDS.length && seconds >= REPORT_SECONDS[reportStep];
        if (report) while (reportStep < REPORT_SECONDS.length && seconds >= REPORT_SECONDS[reportStep]) reportStep++;
        try {
            if (report) {
                View decor = (View) get(a, "mDecor");
                Object loader = get(a, "mLibraryLoader");
                Diagnostics.stage("Test11 activity +" + seconds + "s decorOwner=" +
                        (decor != null && decor.getHandler() != null ? decor.getHandler().getLooper().getThread().getName() : "none") +
                        " loadFinished=" + value(loader, "mLoadFinished") + " pausedNotLoaded=" + value(loader, "mPausedNotLoaded") +
                        " error=" + value(loader, "mLoadError") + " finishing=" + a.isFinishing());
            }
            Class<?> type = a.getClassLoader().loadClass("com.apportable.MainThread");
            Handler owner = (Handler) type.getMethod("getHandler").invoke(null);
            if (owner != null && !samplePending) {
                samplePending = true;
                if (!owner.post(() -> {
                    try { sampleGame(a, seconds, report); }
                    finally { main.post(() -> samplePending = false); }
                })) samplePending = false;
            } else if (report) Diagnostics.stage("Test11 owner sample pending=" + samplePending + " handlerPresent=" + (owner != null));
        } catch (ReflectiveOperationException | RuntimeException | LinkageError e) {
            if (report) Diagnostics.stage("Test11 owner sample unavailable: " + cause(e));
        }
        if (seconds < 60) main.postDelayed(this::sample, 1000);
    }

    private void sampleGame(Activity a, long seconds, boolean report) {
        if (game != a || a.isDestroyed()) return;
        try {
            // getSurface() creates a view, so diagnostics must read the existing field instead.
            Object surface = get(a.getApplication(), "mGLView");
            if (surface != null) {
                try { instrumentEgl(surface); }
                catch (ReflectiveOperationException | RuntimeException e) {
                    if (report) Diagnostics.stage("Test11 Java EGL hook unavailable: " + cause(e));
                }
            }
            if (report) {
                String state = surface == null ? "absent" : surface.getClass().getName();
                if (surface instanceof SurfaceView) {
                    SurfaceView v = (SurfaceView) surface;
                    state += " width=" + v.getWidth() + " height=" + v.getHeight() + " attached=" + v.isAttachedToWindow() +
                            " shown=" + v.isShown() + " valid=" + v.getHolder().getSurface().isValid();
                }
                if (surface != null) for (String name : new String[]{"mHasSurface", "mHaveEglContext", "mHaveEglSurface", "mSizeChanged", "mWidth", "mHeight"})
                    state += " " + name + "=" + value(surface, name);
                Diagnostics.stage("Test11 surface +" + seconds + "s " + state + " javaSwaps=" + swaps.get() +
                        " javaGoodSwaps=" + goodSwaps.get() + " egl=" + eglState);
            }
        } catch (ReflectiveOperationException | RuntimeException | LinkageError e) {
            if (report) Diagnostics.stage("Test11 surface unavailable: " + cause(e));
        }
        // Keep native inspection independent of Java view/field compatibility.
        if (report) try { Diagnostics.stage("Test11 native display +" + seconds + "s " + inspectNative()); }
        catch (RuntimeException | LinkageError e) { Diagnostics.stage("Test11 native display unavailable: " + e); }
    }

    private void instrumentEgl(Object surface) throws ReflectiveOperationException {
        Object helper = get(surface, "mEglHelper");
        if (helper == null) return;
        Field f = field(helper.getClass(), "mEgl");
        Object target = f.get(helper);
        if (target == null || target == observedEgl) return;
        if (!(target instanceof EGL10)) return;
        Class<?>[] interfaces = target instanceof EGL11 ? new Class<?>[]{EGL11.class} : new Class<?>[]{EGL10.class};
        Object proxy = Proxy.newProxyInstance(EGL10.class.getClassLoader(), interfaces, (p, method, args) -> {
            if (method.getName().equals("equals") && method.getParameterCount() == 1) return p == args[0];
            if (method.getName().equals("hashCode") && method.getParameterCount() == 0) return System.identityHashCode(p);
            Object result;
            try { result = method.invoke(target, args); }
            catch (InvocationTargetException e) { throw e.getCause(); }
            if (method.getName().equals("eglSwapBuffers")) {
                swaps.incrementAndGet(); if (Boolean.TRUE.equals(result)) goodSwaps.incrementAndGet();
            } else if (method.getName().equals("eglMakeCurrent")) {
                eglState = "makeCurrent=" + result + " thread=" + Thread.currentThread().getName();
            } else if (method.getName().equals("eglGetError") && result instanceof Integer && (Integer) result != EGL10.EGL_SUCCESS) {
                // Observe only the game's own error query. Never consume an extra EGL error.
                eglState = "gameObservedError=0x" + Integer.toHexString((Integer) result);
            }
            return result;
        });
        f.set(helper, proxy); observedEgl = proxy;
        Diagnostics.stage("Test11 Java EGL counters attached owner=" + Thread.currentThread().getName());
    }
}
