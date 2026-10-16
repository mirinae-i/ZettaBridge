#!/usr/bin/env python3
"""Exercise Test8 dispatch/EGL contracts on a host JVM. This is not an Android UI test."""
import argparse
import os
from pathlib import Path
import subprocess
import textwrap

SOURCES = {
'android/os/Build.java': 'package android.os;public class Build {public static class VERSION {public static final int SDK_INT=37;}}',
'android/app/Application.java': '''package android.app; public class Application {
 public void onCreate() {} public static String getProcessName(){return "test:guest";}
}''',
'android/app/Activity.java': '''package android.app; public class Activity {
 public android.view.View mDecor; public Application app = new Application();
 public boolean isDestroyed(){return false;} public boolean isFinishing(){return false;}
 public Application getApplication(){return app;} public ClassLoader getClassLoader(){return getClass().getClassLoader();}
}''',
'android/os/Looper.java': '''package android.os;
public class Looper {
 private static final Looper MAIN=new Looper(Thread.currentThread());
 private final Thread thread;
 public Looper(Thread t){thread=t;} public Thread getThread(){return thread;}
 public static Looper getMainLooper(){return MAIN;}
}''',
'android/os/Message.java': '''package android.os; public class Message {public int what;public Object obj;}''',
'android/os/Handler.java': '''package android.os; import java.util.ArrayDeque;
public class Handler {
 public interface Callback {boolean handleMessage(Message m);}
 public Callback mCallback; private final Looper looper;
 public final ArrayDeque<Runnable> queue=new ArrayDeque<>();
 public Handler(Looper l){looper=l;} public Looper getLooper(){return looper;}
 public boolean post(Runnable r){queue.add(r);return true;}
 public boolean postDelayed(Runnable r,long d){return post(r);}
 public void handleMessage(Message m){}
 public void dispatchMessage(Message m){if(mCallback==null||!mCallback.handleMessage(m))handleMessage(m);}
}''',
'android/os/SystemClock.java': '''package android.os;public class SystemClock {public static long uptimeMillis(){return 1000;}}''',
'android/system/Os.java': '''package android.system;public class Os {public static void setenv(String n,String v,boolean b){}}''',
'android/view/Display.java': '''package android.view;public class Display {public int getDisplayId(){return 0;}}''',
'android/view/ViewParent.java': '''package android.view;public interface ViewParent {}''',
'android/view/View.java': '''package android.view;public class View {
 public android.os.Handler handler;public ViewParent parent;
 public android.os.Handler getHandler(){return handler;}public ViewParent getParent(){return parent;}
 public Display getDisplay(){return new Display();}public boolean isAttachedToWindow(){return true;}
 public int getWidth(){return 100;}public int getHeight(){return 200;}public boolean isShown(){return true;}
}''',
'android/view/Surface.java': '''package android.view;public class Surface {public boolean isValid(){return true;}}''',
'android/view/SurfaceHolder.java': '''package android.view;public interface SurfaceHolder {Surface getSurface();}''',
'android/view/SurfaceView.java': '''package android.view;public class SurfaceView extends View {
 public SurfaceHolder getHolder(){return ()->new Surface();}
}''',
'android/view/ViewRootImpl.java': '''package android.view;public class ViewRootImpl implements ViewParent {
 public final Thread owner;public int updates;
 public ViewRootImpl(Thread t){owner=t;}
 public void updateConfiguration(int display){if(Thread.currentThread()!=owner)throw new IllegalStateException("wrong owner");updates++;}
}''',
'android/app/ActivityThread.java': '''package android.app;import java.util.*;import android.os.*;import android.view.*;
public class ActivityThread {
 public static ActivityThread CURRENT=new ActivityThread();
 public static ActivityThread currentActivityThread(){return CURRENT;}
 public final Map<Object,Record> mActivities=new HashMap<>(); public final H mH=new H();
 public int calls;public boolean throwInFramework;public Thread executing;
 public static class Record {public Activity activity;public Record(Activity a){activity=a;}}
 public class H extends Handler {
  public static final int EXECUTE_TRANSACTION=159;
  public H(){super(Looper.getMainLooper());}
  @Override public void handleMessage(Message msg){
   calls++;executing=Thread.currentThread();
   if(throwInFramework)throw new IllegalArgumentException("framework failure");
   for(Record r:mActivities.values())if(r.activity.mDecor!=null)
    ((ViewRootImpl)r.activity.mDecor.getParent()).updateConfiguration(0);
  }
 }
}''',
'android/app/servertransaction/ActivityConfigurationChangeItem.java': '''package android.app.servertransaction;
public class ActivityConfigurationChangeItem {private Object token;public ActivityConfigurationChangeItem(Object t){token=t;} public Object getActivityToken(){return token;}}''',
'android/app/servertransaction/ClientTransaction.java': '''package android.app.servertransaction;import java.util.*;
public class ClientTransaction {public List<Object> items;public ClientTransaction(Object... i){items=Arrays.asList(i);}public List<Object> getTransactionItems(){return items;}}''',
'com/apportable/activity/VerdeActivity.java': '''package com.apportable.activity;
public class VerdeActivity extends android.app.Activity {public Object mLibraryLoader;}
''',
'com/apportable/MainThread.java': '''package com.apportable;public class MainThread {
 public static android.os.Handler handler;public static android.os.Handler getHandler(){return handler;}
}''',
'com/zettabridge/launcher/ZbApplication.java': '''package com.zettabridge.launcher;public class ZbApplication extends android.app.Application {}''',
'com/zettabridge/launcher/Diagnostics.java': '''package com.zettabridge.launcher;public class Diagnostics {public static void stage(String s){System.out.println(s);}}''',
'com/zettabridge/launcher/DisplayContractTest.java': r'''package com.zettabridge.launcher;
import android.app.*;import android.app.servertransaction.*;import android.os.*;import android.view.*;
import com.apportable.activity.VerdeActivity;
import java.lang.reflect.*;import java.util.concurrent.*;import java.util.concurrent.atomic.*;
import javax.microedition.khronos.egl.*;
public class DisplayContractTest {
 static void check(boolean b,String label){if(!b)throw new AssertionError(label);}
 static Object privateCall(Object o,String name,Class<?> parameter,Object arg)throws Exception{
  Method m=o.getClass().getDeclaredMethod(name,parameter);m.setAccessible(true);return m.invoke(o,arg);
 }
 static Object field(Object o,String name)throws Exception{Field f=o.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(o);}
 public static class Helper {public EGL10 mEgl;}
 public static class Surface {public Helper mEglHelper=new Helper();}
 static final Object TOKEN=new Object();
 static Message message(Object... items){Message m=new Message();m.what=159;m.obj=new ClientTransaction(items);return m;}
 static void attach(ActivityThread t,VerdeActivity a,Thread owner,Handler handler){
  View decor=new View();decor.handler=handler;decor.parent=new ViewRootImpl(owner);a.mDecor=decor;
  t.mActivities.put(TOKEN,new ActivityThread.Record(a));
 }
 static Test8Application install(ActivityThread t){ActivityThread.CURRENT=t;Test8Application app=new Test8Application();app.onCreate();return app;}
 public static void main(String[] args)throws Exception{
  // Initialize main looper here before creating the owner executor.
  Thread main=Looper.getMainLooper().getThread();
  ExecutorService worker=Executors.newSingleThreadExecutor(r->new Thread(r,"MainThread"));
  try{
   Thread owner=worker.submit(()->Thread.currentThread()).get();
   Handler h=new Handler(new Looper(owner));
   ActivityThread t=new ActivityThread();VerdeActivity a=new VerdeActivity();attach(t,a,owner,h);
   Message config=message(new ActivityConfigurationChangeItem(TOKEN));
   boolean rejected=false;try{t.mH.dispatchMessage(config);}catch(IllegalStateException e){rejected=true;}
   check(rejected,"unadapted path must reject foreign root");t.calls=0;
   AtomicInteger chained=new AtomicInteger();t.mH.mCallback=m->{chained.incrementAndGet();return false;};
   Test8Application app=install(t);View original=a.mDecor;ViewRootImpl root=(ViewRootImpl)original.parent;
   t.mH.dispatchMessage(config);
   check(t.calls==1&&chained.get()==1&&t.executing==main,"framework stays on main and chained once");
   check(a.mDecor==original&&root.updates==0&&h.queue.size()==1,"decor restored, update deferred");
   worker.submit(h.queue.remove()).get();check(root.updates==1,"owner receives update exactly once");
   t.throwInFramework=true;boolean propagated=false;
   try{t.mH.dispatchMessage(config);}catch(IllegalArgumentException e){propagated=true;}
   check(propagated&&a.mDecor==original,"framework error propagates with decor restored");
   worker.submit(h.queue.remove()).get();t.throwInFramework=false;
   Handler mainHandler=new Handler(Looper.getMainLooper());attach(t,a,main,mainHandler);
   int before=t.calls;t.mH.dispatchMessage(config);
   check(t.calls==before+1&&((ViewRootImpl)a.mDecor.parent).updates==1&&mainHandler.queue.isEmpty(),"main owner unchanged");
   attach(t,a,owner,h);boolean mixedRejected=false;
   try{t.mH.dispatchMessage(message(new ActivityConfigurationChangeItem(TOKEN),new Object()));}
   catch(IllegalStateException e){mixedRejected=true;}
   check(mixedRejected&&h.queue.isEmpty(),"mixed transactions untouched");
   // Activity discovery must use framework records, despite a foreign Application.
   com.apportable.MainThread.handler=h;
   Method discover=Test8Application.class.getDeclaredMethod("discoverGame");discover.setAccessible(true);discover.invoke(app);
   check(field(app,"game")==a,"plugin activity discovered without host lifecycle callbacks");
   h.queue.clear();
   Surface surface=new Surface();AtomicInteger calls=new AtomicInteger(),errors=new AtomicInteger();
   RuntimeException driverFailure=new IllegalStateException("driver failure");
   surface.mEglHelper.mEgl=(EGL10)Proxy.newProxyInstance(EGL10.class.getClassLoader(),new Class<?>[]{EGL11.class},(p,m,v)->{
    if(m.getName().equals("eglSwapBuffers")){int n=calls.incrementAndGet();if(n==3)throw driverFailure;return n==1;}
    if(m.getName().equals("eglGetError")){errors.incrementAndGet();return EGL10.EGL_BAD_SURFACE;}
    if(m.getReturnType()==boolean.class)return true;
    if(m.getReturnType()==int.class)return 0;return null;
   });
   privateCall(app,"instrumentEgl",Object.class,surface);EGL10 proxy=surface.mEglHelper.mEgl;
   check(proxy instanceof EGL11&&proxy.equals(proxy)&&!proxy.equals(new Object()),"EGL11/identity preserved");
   check(proxy.eglSwapBuffers(null,null),"true result preserved");
   check(!proxy.eglSwapBuffers(null,null),"false result preserved");
   check(errors.get()==0,"no extra EGL error queries");
   check(proxy.eglGetError()==EGL10.EGL_BAD_SURFACE&&errors.get()==1,"game error query forwarded once");
   boolean originalException=false;try{proxy.eglSwapBuffers(null,null);}catch(RuntimeException e){originalException=e==driverFailure;}
   check(originalException&&calls.get()==3,"driver exception unwrapped and no duplicated call");
   check(((AtomicLong)field(app,"swaps")).get()==2&&((AtomicLong)field(app,"goodSwaps")).get()==1,"exact swap counters");
   privateCall(app,"instrumentEgl",Object.class,surface);check(proxy==surface.mEglHelper.mEgl,"no recursive wrapping");
   System.out.println("PASS: dispatch, restoration, exception, chaining, discovery, EGL forwarding contracts; Android device not tested");
  }finally{worker.shutdownNow();}
 }
}
'''
}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('jdk','android','work'):p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();a.jdk=a.jdk.resolve();a.android=a.android.resolve();a.work=a.work.resolve()
 src=a.work/'src';classes=a.work/'classes';classes.mkdir(parents=True,exist_ok=True)
 for name,text in SOURCES.items():
  f=src/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(textwrap.dedent(text))
 repo=Path(__file__).resolve().parents[1]
 env=os.environ.copy();env['LD_LIBRARY_PATH']=str(a.jdk/'lib');env['TMPDIR']=str(a.work)
 subprocess.run([str(a.jdk/'bin/javac'),'-source','17','-target','17','-classpath',str(a.android),'-d',str(classes),*[str(f) for f in src.rglob('*.java')],str(repo/'android/test8/Test8Application.java')],env=env,check=True)
 subprocess.run([str(a.jdk/'bin/java'),'-cp',str(classes)+os.pathsep+str(a.android),'com.zettabridge.launcher.DisplayContractTest'],env=env,check=True)
if __name__=='__main__':main()
