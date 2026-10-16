package com.zettabridge.launcher;

import android.app.*;
import android.content.*;
import android.net.Uri;
import android.os.Bundle;
import android.widget.*;
import java.io.*;
import java.nio.file.*;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.concurrent.*;

/** User-selected ZIP backup/restore through Android's document picker. */
public final class BlockheadsSavesActivity extends Activity {
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private SaveStore store;
    private TextView status;
    private final List<Button> actions=new ArrayList<>();
    private volatile boolean destroyed;
    private boolean busy;
    private static final int EXPORT=12, IMPORT=13, PREVIOUS=14;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);setTitle("\uc138\uc774\ube0c \uad00\ub9ac");store=new SaveStore(getFilesDir());
        ScrollView scroll=new ScrollView(this);LinearLayout content=new LinearLayout(this);content.setOrientation(LinearLayout.VERTICAL);
        int pad=(int)(24*getResources().getDisplayMetrics().density);content.setPadding(pad,pad,pad,pad);scroll.addView(content);setContentView(scroll);
        TextView help=new TextView(this);help.setText("\uc6d4\ub4dc \uc800\uc7a5\uc740 \uac8c\uc784\uc758 \uae30\uc874 \uc790\ub3d9 \uc800\uc7a5\uc744 \uc0ac\uc6a9\ud569\ub2c8\ub2e4.\n\n\ub0b4\ubcf4\ub0b4\uae30\u00b7\ubd88\ub7ec\uc624\uae30 \uc804\uc5d0\ub294 \uac8c\uc784 \uc548\uc5d0\uc11c \uc6d4\ub4dc\ub97c \uc800\uc7a5\ud558\uace0 \uc571\uc744 \uc644\uc804\ud788 \uc885\ub8cc\ud574 \uc8fc\uc138\uc694. \ubc31\uc5c5\uc5d0\ub294 \ubaa8\ub4e0 \uc6d4\ub4dc, \ud06c\ub9ac\uc2a4\ud0c8 \uc794\uc561\uacfc \uac8c\uc784 \uc124\uc815\uc774 \ub4e4\uc5b4\uac11\ub2c8\ub2e4. \ubd88\ub7ec\uc624\uae30\ub294 \ud604\uc7ac \uc800\uc7a5 \uc804\uccb4\ub97c \uad50\uccb4\ud569\ub2c8\ub2e4.");content.addView(help);
        add(content,"\uc138\uc774\ube0c ZIP \ub0b4\ubcf4\ub0b4\uae30",()->choose(EXPORT));
        add(content,"\uc138\uc774\ube0c ZIP \ubd88\ub7ec\uc624\uae30",()->choose(IMPORT));
        add(content,"\ubcf5\uc6d0 \uc9c1\uc804 \ubc31\uc5c5 \ub0b4\ubcf4\ub0b4\uae30",()->choose(PREVIOUS));
        add(content,"\uc911\ub2e8\ub41c \ubcf5\uc6d0 \ubcf5\uad6c",()->run(()->{try(SaveStore.Lease l=SaveStore.lock(getFilesDir(),false)){store.recover();}return "\ubcf5\uad6c \ud655\uc778 \uc644\ub8cc. \uac8c\uc784\uc744 \uc2e4\ud589\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.";}));
        add(content,"\uac8c\uc784 \uc2e4\ud589",()->{if(store.pendingRecovery()){message("\uba3c\uc800 \uc911\ub2e8\ub41c \ubcf5\uc6d0\uc744 \ubcf5\uad6c\ud574 \uc8fc\uc138\uc694.");return;}startActivity(new Intent(this,BlockheadsLaunchActivity.class));finish();});
        add(content,"\uac8c\uc784\u00b7\uc9c4\ub2e8 \uad00\ub9ac",()->startActivity(new Intent(this,LibraryActivity.class)));
        status=new TextView(this);status.setPadding(0,pad,0,0);status.setText("\uc800\uc7a5 \ud3f4\ub354\n"+store.data+"\n\n\uc571 \uc0ad\uc81c \uc2dc \ub0b4\ubd80 \uc800\uc7a5\ub3c4 \uc0ad\uc81c\ub429\ub2c8\ub2e4. \uba3c\uc800 ZIP\uc744 \ub0b4\ubcf4\ub0b4 \uc8fc\uc138\uc694.");content.addView(status);
        if(store.pendingRecovery()) message("\uc911\ub2e8\ub41c \ubcf5\uc6d0\uc774 \uc788\uc2b5\ub2c8\ub2e4. '\uc911\ub2e8\ub41c \ubcf5\uc6d0 \ubcf5\uad6c'\ub97c \ub20c\ub7ec \uc6d0\ub798 \uc800\uc7a5\uc73c\ub85c \ub418\ub3cc\ub824 \uc8fc\uc138\uc694.");
    }
    private void add(LinearLayout group,String title,Runnable click) {
        Button b=new Button(this);b.setText(title);b.setOnClickListener(v->{if(!busy)click.run();});group.addView(b);actions.add(b);
    }
    private void busy(boolean value) {busy=value;for(Button b:actions)b.setEnabled(!value);}
    private void message(String text) {if(!destroyed)status.setText(text);}
    private boolean idle() {
        try(SaveStore.Lease l=SaveStore.lock(getFilesDir(),false)) {if(store.pendingRecovery())throw new IOException("\uc911\ub2e8\ub41c \ubcf5\uc6d0\uc744 \uba3c\uc800 \ubcf5\uad6c\ud574 \uc8fc\uc138\uc694.");return true;}
        catch(IOException|RuntimeException e) {message("\uac8c\uc784\uc744 \uc644\uc804\ud788 \uc885\ub8cc\ud55c \ub4a4 \ub2e4\uc2dc \uc2dc\ub3c4\ud574 \uc8fc\uc138\uc694.\n"+e.getMessage());return false;}
    }
    private void choose(int request) {
        if(!idle()) return;
        if(request==PREVIOUS && !Files.isRegularFile(store.previous)) {message("\ubcf5\uc6d0 \uc9c1\uc804 \ubc31\uc5c5\uc774 \uc544\uc9c1 \uc5c6\uc2b5\ub2c8\ub2e4.");return;}
        Intent intent=new Intent(request==IMPORT?Intent.ACTION_OPEN_DOCUMENT:Intent.ACTION_CREATE_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE).setType("application/zip").putExtra(Intent.EXTRA_LOCAL_ONLY,true);
        if(request!=IMPORT)intent.putExtra(Intent.EXTRA_TITLE,request==PREVIOUS?"Blockheads-before-restore.zip":"Blockheads-save-"+new SimpleDateFormat("yyyyMMdd-HHmmss",Locale.ROOT).format(new Date())+".zip");
        try {startActivityForResult(intent,request);}catch(ActivityNotFoundException e){message("\ud30c\uc77c \uc120\ud0dd \uc571\uc744 \uc5f4 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.");}
    }
    private interface Task {String call() throws Exception;}
    private void run(Task task) {
        busy(true);message("\ucc98\ub9ac \uc911\u2026 \uc571\uc744 \ub2eb\uc9c0 \ub9d0\uc544 \uc8fc\uc138\uc694.");
        worker.execute(()->{
            String result;
            try {result=task.call();}catch(Exception e) {result="\uc644\ub8cc\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4: "+e.getMessage();if(store.pendingRecovery())result+="\n\uc911\ub2e8\ub41c \ubcf5\uc6d0 \ubcf5\uad6c\ub97c \uc2e4\ud589\ud574 \uc8fc\uc138\uc694.";}
            final String text=result;runOnUiThread(()->{if(!destroyed){busy(false);message(text);}});
        });
    }
    @Override protected void onActivityResult(int request,int result,Intent intent) {
        super.onActivityResult(request,result,intent);
        if(result!=RESULT_OK || intent==null || intent.getData()==null)return;
        Uri uri=intent.getData();
        if(request==EXPORT || request==PREVIOUS) run(()->{
            try(SaveStore.Lease l=SaveStore.lock(getFilesDir(),false)) {
                store.recover();Files.createDirectories(store.work);
                Path path=request==PREVIOUS?store.previous:store.work.resolve("export.zip");
                if(request==EXPORT) store.exportZip(path);
                try(InputStream in=Files.newInputStream(path);OutputStream out=getContentResolver().openOutputStream(uri,"wt")) {SaveStore.copyBounded(in,out);}
                if(request==EXPORT)Files.deleteIfExists(path);
                return "\ub0b4\ubcf4\ub0b4\uae30 \uc644\ub8cc. \uc120\ud0dd\ud55c \uc704\uce58\uc5d0 \uc138\uc774\ube0c ZIP\uc744 \uc800\uc7a5\ud588\uc2b5\ub2c8\ub2e4.";
            }
        });
        else if(request==IMPORT) {
            busy(true);message("\ubc31\uc5c5\uc744 \uac80\uc0ac\ud558\uace0 \uc788\uc2b5\ub2c8\ub2e4\u2026");
            worker.execute(()->{
                try(SaveStore.Lease l=SaveStore.lock(getFilesDir(),false)) {
                    store.recover();Files.createDirectories(store.work);Path zip=store.work.resolve("incoming.zip");
                    try(InputStream in=getContentResolver().openInputStream(uri);OutputStream out=Files.newOutputStream(zip)) {SaveStore.copyBounded(in,out);}
                    SaveStore.Summary summary=store.validate(zip,store.work.resolve("preview"));SaveStore.delete(store.work.resolve("preview"));
                    runOnUiThread(()->{if(destroyed)return;busy(false);
                        new AlertDialog.Builder(this).setTitle("\uc138\uc774\ube0c \uc804\uccb4\ub97c \ubd88\ub7ec\uc62c\uae4c\uc694?")
                            .setMessage(summary+"\n\n\ud604\uc7ac \uc6d4\ub4dc\u00b7\ud06c\ub9ac\uc2a4\ud0c8\u00b7\uc124\uc815\uc774 \uc774 \ubc31\uc5c5 \ub0b4\uc6a9\uc73c\ub85c \uad50\uccb4\ub429\ub2c8\ub2e4. \ud604\uc7ac \ub370\uc774\ud130\ub294 \ubcf5\uc6d0 \uc9c1\uc804 \ubc31\uc5c5\uc73c\ub85c \ub0a8\uae41\ub2c8\ub2e4.")
                            .setNegativeButton("\ucde8\uc18c",(d,w)->message("\ubd88\ub7ec\uc624\uae30\ub97c \ucde8\uc18c\ud588\uc2b5\ub2c8\ub2e4. \ud604\uc7ac \uc800\uc7a5\uc740 \uadf8\ub300\ub85c\uc785\ub2c8\ub2e4."))
                            .setPositiveButton("\ubc31\uc5c5 \ud6c4 \ubd88\ub7ec\uc624\uae30",(d,w)->run(()->{
                                try(SaveStore.Lease lease=SaveStore.lock(getFilesDir(),false)) {store.restore(zip,null);Files.deleteIfExists(zip);}
                                return "\ubd88\ub7ec\uc624\uae30 \uc644\ub8cc. \uac8c\uc784\uc744 \uc2e4\ud589\ud558\uba74 \ubcf5\uc6d0\ud55c \uc6d4\ub4dc\uc640 \uc794\uc561\uc744 \uc0ac\uc6a9\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4. \uc774\uc804 \ub370\uc774\ud130\ub294 '\ubcf5\uc6d0 \uc9c1\uc804 \ubc31\uc5c5 \ub0b4\ubcf4\ub0b4\uae30'\ub85c \ubcf4\uad00\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.";
                            })).show();
                    });
                } catch(Exception e) {runOnUiThread(()->{if(!destroyed){busy(false);message("\ubc31\uc5c5\uc744 \uc5f4 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4. \ud604\uc7ac \uc800\uc7a5\uc740 \ubcc0\uacbd\ud558\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.\n"+e.getMessage());}});}
            });
        }
    }
    @Override protected void onDestroy() {destroyed=true;worker.shutdown();super.onDestroy();}
}
