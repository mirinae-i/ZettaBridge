#!/usr/bin/env python3
"""Host contracts for direct launch and existing switch policy; not an Android task test."""
import argparse
import os
from pathlib import Path
import subprocess

SOURCES = {
    'com/zettabridge/launcher/BlockheadsSavesActivity.java': 'package com.zettabridge.launcher; public class BlockheadsSavesActivity extends android.app.Activity {}',
    'android/content/Context.java': '''package android.content; public class Context {
        public static java.io.File root; public java.io.File getFilesDir(){return root;}
    }''',
    'android/content/Intent.java': '''package android.content; import android.net.Uri;
    public class Intent {
        public static final String ACTION_MAIN="android.intent.action.MAIN";
        public static final int FLAG_ACTIVITY_NEW_TASK=0x10000000, FLAG_ACTIVITY_CLEAR_TASK=0x8000,
            FLAG_ACTIVITY_CLEAR_TOP=0x04000000;
        public String action; public Class<?> target; public Uri data; public int flags;
        public java.util.Map<String,String> extras=new java.util.HashMap<>();
        public Intent(String a){action=a;} public Intent(Context c,Class<?> t){target=t;}
        public Intent setClass(Context c,Class<?> t){target=t;return this;}
        public Intent setData(Uri d){data=d;return this;}
        public Intent putExtra(String k,String v){extras.put(k,v);return this;}
        public String getStringExtra(String k){return extras.get(k);}
        public Intent addFlags(int f){flags|=f;return this;}
    }''',
    'android/net/Uri.java': '''package android.net; public class Uri {
        public String value; public static Uri parse(String s){Uri u=new Uri();u.value=s;return u;}
    }''',
    'android/os/Bundle.java': 'package android.os; public class Bundle {}',
    'android/os/Looper.java': 'package android.os; public class Looper {public static Looper getMainLooper(){return new Looper();}}',
    'android/os/Handler.java': '''package android.os; public class Handler {
        public Handler(Looper l){} public boolean postDelayed(Runnable r,long delay){r.run();return true;}
    }''',
    'android/app/Activity.java': '''package android.app; public class Activity extends android.content.Context {
        public android.content.Intent input=new android.content.Intent(android.content.Intent.ACTION_MAIN);
        public final java.util.List<android.content.Intent> started=new java.util.ArrayList<>();
        public boolean finished;
        protected void onCreate(android.os.Bundle b){}
        public android.content.Intent getIntent(){return input;}
        public void startActivity(android.content.Intent i){started.add(i);}
        public void finish(){finished=true;}
    }''',
    'android/widget/Toast.java': '''package android.widget; public class Toast {
        public static final int LENGTH_LONG=1,LENGTH_SHORT=0;public static int shown;
        public static Toast makeText(android.content.Context c,CharSequence s,int duration){return new Toast();}
        public void show(){shown++;}
    }''',
    'android/graphics/Bitmap.java': 'package android.graphics; public class Bitmap {}',
    'android/graphics/BitmapFactory.java': '''package android.graphics; public class BitmapFactory {
        public static Bitmap decodeFile(String s){return null;}
    }''',
    'com/zettabridge/launcher/Diagnostics.java': '''package com.zettabridge.launcher;
        class Diagnostics {static void stage(String s){System.out.println(s);}}''',
    'com/zettabridge/launcher/LibraryActivity.java': '''package com.zettabridge.launcher;
        public class LibraryActivity extends android.app.Activity {}''',
    'com/zettabridge/launcher/PluginStore.java': '''package com.zettabridge.launcher;
        class PluginStore {static PluginRecord find(android.content.Context c,String name){
            return PluginRecord.load(new java.io.File(c.getFilesDir(),"plugins/"+name));
        }}''',
    'com/zettabridge/launcher/ActivePlugin.java': '''package com.zettabridge.launcher;
        class ActivePlugin {static String active;static int kills;
            static String of(android.content.Context c){return active;}
            static boolean guestIsRunning(android.content.Context c){return active!=null;}
            static void endGuestProcess(android.content.Context c){kills++;active=null;}
        }''',
    'com/zettabridge/launcher/GuestLaunchActivity.java': '''package com.zettabridge.launcher;
        public class GuestLaunchActivity extends android.app.Activity {
            static boolean cleared;
            static android.content.Intent intent(android.content.Context c,String name,boolean clear){
                cleared=clear;return new android.content.Intent(c,GuestLaunchActivity.class).putExtra("game",name);
            }
        }''',
    'com/zettabridge/launcher/LaunchContractTest.java': '''package com.zettabridge.launcher;
    import android.content.*; import java.nio.file.*;
    public class LaunchContractTest {
        static void check(boolean value,String label){if(!value)throw new AssertionError(label);}
        static Intent launch(){
            BlockheadsLaunchActivity a=new BlockheadsLaunchActivity();
            a.input.putExtra("zb.package","some.other.game"); // external extras never choose the target
            a.onCreate(null);
            check(a.finished&&a.started.size()==1,"entry must finish after one destination");
            return a.started.get(0);
        }
        static void switchTo(Intent intent,String active,boolean clear,int kills){
            ActivePlugin.active=active; ActivePlugin.kills=0;
            PluginSwitchActivity s=new PluginSwitchActivity();s.input=intent;s.onCreate(null);
            check(s.finished&&s.started.size()==1,"existing switch must finish once");
            check(BlockheadsLaunchActivity.GAME.equals(s.started.get(0).getStringExtra("game")),"only Blockheads");
            check(ActivePlugin.kills==kills&&GuestLaunchActivity.cleared==clear,"preserve active guest / clear stale task policy");
        }
        public static void main(String[] args)throws Exception {
            Context.root=Path.of(args[0]).toFile();
            check(launch().target==LibraryActivity.class,"fresh install offers import");
            Path game=Context.root.toPath().resolve("plugins/"+BlockheadsLaunchActivity.GAME);
            Files.createDirectories(game.resolve("data"));
            Path save=game.resolve("data/keep.world"); Files.writeString(save,"existing world");
            PluginRecord record=new PluginRecord(game.toFile());
            record.packageName=BlockheadsLaunchActivity.GAME;record.label="The Blockheads";
            record.launcherActivity="com.apportable.activity.VerdeActivity";
            record.abis.add("armeabi-v7a"); record.save();
            Files.writeString(game.resolve("base.apk"),"fixture");
            check(launch().target==LibraryActivity.class,"incomplete import offers repair");
            record.selectedAbi="armeabi-v7a";record.save();
            Intent ready=launch();
            check(ready.target==PluginSwitchActivity.class,"reuse original switch, not guest bypass");
            check(ready.data.value.equals("zbplugin://"+BlockheadsLaunchActivity.GAME),"stable per-game task identity");
            check(ready.flags==(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TASK),"switch task flags");
            switchTo(ready,null,true,0);
            switchTo(launch(),BlockheadsLaunchActivity.GAME,false,0);
            switchTo(launch(),"some.other.game",true,1);
            Files.delete(game.resolve("base.apk"));
            check(launch().target==LibraryActivity.class,"missing archive never attempts a broken guest");
            check(Files.readString(save).equals("existing world"),"launch/fallback preserve save");
            System.out.println("PASS: fresh/incomplete/missing import; direct launch; cold/warm/other guest; saved data");
        }
    }''',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test12',action='store_true')
    for name in ('jdk', 'work'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    work, jdk = args.work.resolve(), args.jdk.resolve()
    sources = []
    for name, content in SOURCES.items():
        if args.test12 and name.endswith('/LaunchContractTest.java'):
            content = content.replace('Intent ready=launch();', '''
                Path journal=Context.root.toPath().resolve("zb-save-work/transaction/journal");
                Files.createDirectories(journal.getParent());Files.writeString(journal,"pending fixture");
                check(launch().target==BlockheadsSavesActivity.class,"unfinished restore must block game launch");
                check(Files.readString(save).equals("existing world"),"recovery route preserves data");
                Files.delete(journal);
                Intent ready=launch();''')
        path = work / 'src' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content + '\n')
        sources.append(path)
    sources.append(repo / ('android/test12/BlockheadsLaunchActivity.java' if args.test12 else 'android/test11/BlockheadsLaunchActivity.java'))
    if args.test12: sources.append(repo / 'android/test12/SaveStore.java')
    launcher = repo / 'android/launcher/app/src/main/java/com/zettabridge/launcher'
    sources += [launcher / n for n in ('PluginRecord.java', 'PluginSwitchActivity.java')]
    classes = work / 'classes'
    classes.mkdir(parents=True, exist_ok=True)
    env = os.environ | {'LD_LIBRARY_PATH': str(jdk / 'lib')}
    subprocess.run([str(jdk / 'bin/javac'), '-encoding', 'UTF-8', '-d', str(classes)] +
                   [str(p) for p in sources], env=env, check=True)
    # Each run gets a fresh fixture directory; never touch any real imported APK/data.
    import tempfile
    with tempfile.TemporaryDirectory(dir=work) as fixture:
        subprocess.run([str(jdk / 'bin/java'), '-cp', str(classes),
                        'com.zettabridge.launcher.LaunchContractTest', fixture], env=env, check=True)


if __name__ == '__main__':
    main()
