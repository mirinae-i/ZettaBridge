#!/usr/bin/env python3
"""Run a lifecycle deadlock regression against the production surface methods.

Original methods and patched callbacks are decompiled from the APKs. The patched
readySurface uses its production Java source, with its compiled DEX method
checked against the delivered APK (JADX cannot reconstruct that method).
EGL/native rendering and the Android message queue are host fakes. This does not
replace ART or target-device validation.
"""
import argparse
from pathlib import Path
import re
import subprocess
from build_blockheads_resume import TARGET, method_text


def extract(source, name):
    m = re.search(r'    public void ' + name + r'\(\)[^{]*\{', source)
    assert m, name
    start = m.start(); pos = m.end(); depth = 1
    while depth:
        depth += (source[pos] == '{') - (source[pos] == '}')
        pos += 1
    method = source[start:pos]
    assert 'UnsupportedOperationException' not in method
    return method


SURFACE = '''package com.apportable.gl;
import com.zettabridge.compat.SurfaceWait;
public class GLSurfaceView {
    final Object mLock = new Object();
    boolean mHasSurface=true, mWaitingForSurface, mHaveEglSurface, mHaveEglContext;
    boolean mExited, mSizeChanged=true;
    int mWidth=1080, mHeight=2520;
    GL10 mGL;
    EglHelper mEglHelper = new EglHelper();
    Renderer mRenderer = new Renderer();
    Object getHolder() { return this; }
    int destroys;
    public void stopEglSurfaceLocked() {
        if (!SurfaceWait.isOwner() || !Thread.holdsLock(mLock)) throw new AssertionError("EGL owner/lock");
        if (mHaveEglSurface) { mHaveEglSurface=false; destroys++; }
    }
    static class GL10 {}
    static class EglHelper {
        Object mEglConfig;
        int starts, creates;
        void start() { starts++; }
        Object createSurface(Object holder) { creates++; return new GL10(); }
    }
    static class Renderer {
        int created, changed;
        void onSurfaceCreated(GL10 gl,Object cfg) { created++; }
        void onSurfaceChanged(GL10 gl,int w,int h) { changed++; }
    }
    // Actual APK methods or the source whose compiled method matches the APK.
%s
}
'''

MAIN = '''package com.apportable;
public class MainThread {
    public static volatile Thread owner;
    public static Thread getThread() { return owner; }
}
'''

LOOP = '''package com.apportable.utils;
import java.util.concurrent.*;
public class RunLoop {
    static final ConcurrentLinkedQueue<Runnable> queue = new ConcurrentLinkedQueue<>();
    public static void post(Runnable task) { queue.add(task); }
    public static void clear() { queue.clear(); }
    public static void processMessages() {
        int count=queue.size();
        for(int i=0;i<count;i++) { Runnable r=queue.poll(); if(r!=null) r.run(); }
    }
    public static void scissors(Runnable r) throws Exception {
        FutureTask<Void> f=new FutureTask<>(r,null); post(f); f.get(2,TimeUnit.SECONDS);
    }
}
'''

TEST = '''package com.apportable.gl;
import com.apportable.MainThread;
import com.apportable.utils.RunLoop;
import com.zettabridge.compat.SurfaceWait;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.function.BooleanSupplier;
public class ResumeTest {
    static void check(boolean ok,String msg) { if(!ok) throw new AssertionError(msg); }
    static void until(BooleanSupplier done) throws Exception {
        long end=System.nanoTime()+TimeUnit.SECONDS.toNanos(3);
        while(!done.getAsBoolean()) { if(System.nanoTime()>end) throw new AssertionError("timeout"); Thread.sleep(1); }
    }
    static class Fixture implements AutoCloseable {
        final GLSurfaceView view=new GLSurfaceView();
        final AtomicInteger frames=new AtomicInteger();
        final AtomicReference<Throwable> failure=new AtomicReference<>();
        volatile boolean quit;
        final Thread owner=new Thread(()->{
            MainThread.owner=Thread.currentThread();
            try {
                while(!quit) { view.readySurface(); if(quit) break; frames.incrementAndGet(); RunLoop.processMessages(); Thread.sleep(1); }
            } catch(Throwable t) { failure.set(t); }
        },"render-owner");
        Fixture() throws Exception { RunLoop.clear(); owner.setDaemon(true); owner.start(); until(()->frames.get()>2); }
        boolean hasSurface() { synchronized(view.mLock) { return view.mHasSurface; } }
        boolean waiting() { synchronized(view.mLock) { return view.mWaitingForSurface; } }
        void restore() { synchronized(view.mLock) { view.mHasSurface=true; view.mLock.notifyAll(); } }
        public void close() throws Exception { quit=true; restore(); owner.join(3000); check(!owner.isAlive(),"owner cleanup"); }
    }
    static void regression(boolean legacy) throws Exception {
        try(Fixture f=new Fixture()) {
            CountDownLatch destroyed=new CountDownLatch(1);
            AtomicBoolean callback=new AtomicBoolean();
            FutureTask<Void> stopped=new FutureTask<>(()->{
                f.view.surfaceDestroyed(); destroyed.countDown();
                // WindowManagerGlobal synchronously waits for a foreign root's handler.
                RunLoop.scissors(()->{check(!Thread.holdsLock(f.view.mLock),"callback under lock"); callback.set(true);});
                return null;
            });
            Thread ui=new Thread(stopped,"android-main"); ui.setDaemon(true); ui.start();
            check(destroyed.await(2,TimeUnit.SECONDS),"destroy acknowledgement");
            if(legacy) {
                Thread.sleep(250); check(!callback.get() && !stopped.isDone(),"legacy deadlock was not reproduced");
                f.restore(); stopped.get(2,TimeUnit.SECONDS);
                System.out.println("RED confirmed: original owner queue stalls until an impossible future surface");
            } else {
                stopped.get(2,TimeUnit.SECONDS); check(callback.get(),"stop handler not serviced");
                int frame=f.frames.get(); Thread.sleep(120);
                check(f.frames.get()==frame,"rendered while surface absent");
                f.view.surfaceCreated(); until(()->f.frames.get()>frame);
                check(f.view.mEglHelper.starts==1,"context recreated unnecessarily");
                System.out.println("PASS stop handler completes without a surface; rendering resumes after recreation");
            }
            check(f.failure.get()==null,"render failure: "+f.failure.get());
        }
    }
    static void cycles() throws Exception {
        try(Fixture f=new Fixture()) {
            for(int i=0;i<30;i++) {
                if(i%2==0) f.view.surfaceDestroyed();
                else RunLoop.scissors(f.view::surfaceDestroyed);
                until(f::waiting);
                check(!f.view.mHaveEglSurface,"destroy returned before EGL release");
                RunLoop.scissors(()->check(!Thread.holdsLock(f.view.mLock),"pump owns surface lock"));
                int frame=f.frames.get();
                if(i%2==0) f.view.surfaceCreated();
                else RunLoop.scissors(f.view::surfaceCreated);
                until(()->f.frames.get()>frame);
            }
            check(f.view.destroys==30,"destroy count");
            check(f.view.mEglHelper.starts==1 && f.view.mRenderer.created==1,"lost preserved context");
            check(f.failure.get()==null,"render failure: "+f.failure.get());
            System.out.println("PASS 30 pause/return cycles, including callbacks on the render owner");
        }
    }
    static void interruptedCallback(boolean creating) throws Exception {
        GLSurfaceView v=new GLSurfaceView();
        v.mHasSurface=creating; v.mWaitingForSurface=creating;
        AtomicBoolean restored=new AtomicBoolean();
        Thread callback=new Thread(()->{
            if(creating) v.surfaceCreated(); else v.surfaceDestroyed();
            restored.set(Thread.currentThread().isInterrupted());
        },"interrupted-ui");
        callback.setDaemon(true); callback.start();
        until(()->callback.getState()==Thread.State.WAITING);
        callback.interrupt();
        // The original reinterrupt-inside-wait loop prevents this acknowledgement.
        synchronized(v.mLock) { v.mWaitingForSurface=!creating; v.mLock.notifyAll(); }
        callback.join(2000); check(!callback.isAlive() && restored.get(),"interrupt acknowledgement/status");
    }
    static void pumpFailure() throws Exception {
        try(Fixture f=new Fixture()) {
            f.view.surfaceDestroyed();
            RunLoop.post(()->{throw new IllegalStateException("injected-handler-failure");});
            until(()->f.failure.get()!=null);
            check(f.failure.get() instanceof IllegalStateException,"exception was swallowed");
            AtomicBoolean acquired=new AtomicBoolean();
            Thread other=new Thread(()->{synchronized(f.view.mLock){acquired.set(true);}});
            other.setDaemon(true); other.start(); other.join(1000);
            check(acquired.get(),"surface monitor leaked on pump failure");
            System.out.println("PASS exception propagation releases monitor; interrupted callbacks acknowledge before reinterrupting");
        }
    }
    public static void main(String[] args) throws Exception {
        boolean legacy=args[0].equals("legacy"); regression(legacy);
        if(!legacy) { cycles(); interruptedCallback(true); interruptedCallback(false); pumpFailure(); }
    }
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('java', 'original-source', 'fixed-source', 'build-work', 'work'):
        p.add_argument('--' + n, type=Path, required=True)
    a = p.parse_args()
    repo = Path(__file__).resolve().parents[1]
    ready_source = (repo / 'android/guest-resume/GLSurfaceView.java.in').read_text()
    assert ready_source == (a.build_work / 'method-source/GLSurfaceView.java').read_text()
    compiled = (a.build_work / 'method-decoded/smali' / TARGET).read_text()
    delivered = (a.build_work / 'checked/smali' / TARGET).read_text()
    assert method_text(compiled, 'readySurface') == method_text(delivered, 'readySurface')
    for label, input_file in [('legacy', a.original_source), ('fixed', a.fixed_source)]:
        work = a.work.resolve() / label; work.mkdir(parents=True, exist_ok=True)
        src = input_file.read_text()
        content = SURFACE % '\n'.join(extract(ready_source if label == 'fixed' and n == 'readySurface' else src, n)
                                       for n in ('readySurface', 'surfaceCreated', 'surfaceDestroyed'))
        files = {'GLSurfaceView.java': content, 'MainThread.java': MAIN, 'RunLoop.java': LOOP, 'ResumeTest.java': TEST}
        for n, text in files.items(): (work / n).write_text(text)
        java = [str(a.java.resolve()), '-Djava.io.tmpdir=' + str(work)]
        subprocess.run(java + ['com.sun.tools.javac.Main', '-d', str(work)] +
                       [str(work / n) for n in files] + [str(repo / 'android/guest-resume/SurfaceWait.java')], check=True)
        subprocess.run(java + ['-cp', str(work), 'com.apportable.gl.ResumeTest', label], check=True, timeout=30)


if __name__ == '__main__':
    main()
