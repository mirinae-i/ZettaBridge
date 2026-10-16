package com.zettabridge.launcher;
import java.io.*;import java.nio.file.*;import java.util.*;import java.util.zip.*;
public final class SaveStoreTest {
    static void check(boolean b,String why){if(!b)throw new AssertionError(why);}
    static void write(Path p,String v)throws Exception {Files.createDirectories(p.getParent());Files.writeString(p,v);}
    static Map<String,String> snapshot(Path root)throws Exception {
        Map<String,String> out=new TreeMap<>();if(Files.exists(root))try(var paths=Files.walk(root)){for(Path p:paths.filter(Files::isRegularFile).toList())out.put(root.relativize(p).toString(),Base64.getEncoder().encodeToString(Files.readAllBytes(p)));}return out;
    }
    static Process child(String...args)throws Exception {
        List<String> cmd=new ArrayList<>();cmd.add(System.getProperty("java.home")+"/bin/java");cmd.add("-cp");cmd.add(System.getProperty("java.class.path"));cmd.add(SaveStoreTest.class.getName());cmd.addAll(Arrays.asList(args));return new ProcessBuilder(cmd).inheritIO().redirectInput(ProcessBuilder.Redirect.PIPE).redirectOutput(ProcessBuilder.Redirect.PIPE).start();
    }
    public static void main(String[] args)throws Exception {
        if(args[0].equals("lock")){try(var l=SaveStore.lock(new File(args[1]),true)){System.out.println("locked");System.out.flush();System.in.read();}return;}
        if(args[0].equals("crash")){SaveStore s=new SaveStore(new File(args[1]));try(var l=SaveStore.lock(s.files.toFile(),false)){s.restore(Path.of(args[2]),i->{if(i==2)Runtime.getRuntime().halt(19);});}throw new AssertionError();}
        Path root=Path.of(args[0]);SaveStore.delete(root);Files.createDirectories(root);SaveStore s=new SaveStore(root.resolve("target/files").toFile());Files.createDirectories(s.files);
        SaveStore source=new SaveStore(root.resolve("source/files").toFile());
        String save="files/Library/Application Support/saves/world-123/world.db";
        write(source.data.resolve(save),"world A");write(source.data.resolve("files/.Keychain.plist"),"crystal keychain");
        write(source.data.resolve("files/Library/Preferences/game.plist"),"settings A");
        write(source.prefs.resolve(SaveStore.PREFIX+"lifecycle.xml"),"prefs A");
        Path backup=root.resolve("backup.zip");source.exportZip(backup);
        check(s.validate(backup,root.resolve("preview")).count==4,"all world/keychain/settings/prefs included");
        write(s.data.resolve(save),"world B");write(s.data.resolve("files/old-world"),"old");
        write(s.prefs.resolve(SaveStore.PREFIX+"lifecycle.xml"),"prefs B");write(s.prefs.resolve(SaveStore.PREFIX+"extra.xml"),"extra");
        write(s.prefs.resolve("unrelated.xml"),"do not modify");
        Map<String,String> old=snapshot(s.data),oldPrefs=snapshot(s.prefs);
        for(int fail=0;fail<6;fail++) {
            final int at=fail;boolean rejected=false;
            try {s.restore(backup,i->{if(i==at)throw new IOException("simulated move failure");});}catch(IOException e){rejected=true;}
            check(rejected && snapshot(s.data).equals(old) && snapshot(s.prefs).equals(oldPrefs),"rollback after step "+fail);
            check(!s.pendingRecovery(),"rollback cleared journal");
        }
        Process crash=child("crash",s.files.toString(),backup.toString());check(crash.waitFor()==19,"simulated process death");
        check(s.pendingRecovery(),"journal survives process death");new SaveStore(s.files.toFile()).recover();
        check(snapshot(s.data).equals(old)&&snapshot(s.prefs).equals(oldPrefs),"restart recovery restores originals");
        s.restore(backup,null);check(snapshot(s.data).equals(snapshot(source.data)),"restore exact data");
        check(Files.readString(s.prefs.resolve("unrelated.xml")).equals("do not modify"),"unrelated preferences preserved");
        check(!Files.exists(s.prefs.resolve(SaveStore.PREFIX+"extra.xml")),"stale game prefs removed");
        check(s.validate(s.previous,root.resolve("previous")).count==4,"previous snapshot retained");
        check(snapshot(root.resolve("previous/data")).equals(old),"previous backup is original data");
        Map<String,String> current=snapshot(s.data);
        Map<String,byte[]> entries=new LinkedHashMap<>();try(ZipFile z=new ZipFile(backup.toFile())){var en=z.entries();while(en.hasMoreElements()){ZipEntry e=en.nextElement();entries.put(e.getName(),z.getInputStream(e).readAllBytes());}}
        for(String variant:List.of("traversal","tamper","wrong-game","size","duplicate-manifest","collision")) {
            Map<String,byte[]> altered=new LinkedHashMap<>(entries);
            String manifest=new String(altered.get("manifest.txt"),java.nio.charset.StandardCharsets.UTF_8);
            switch(variant) {
                case "traversal":altered.put("data/../../escape",new byte[]{1});break;
                case "tamper":altered.put("data/"+save,"damaged".getBytes());break;
                case "wrong-game":altered.put("manifest.txt",manifest.replace(SaveStore.GAME,"wrong.game").getBytes());break;
                case "size":altered.put("manifest.txt",manifest.replace("F\t7\t","F\t3000000000\t").getBytes());break;
                case "duplicate-manifest":altered.put("manifest.txt",(manifest+"D\t0\t-\tdata\n").getBytes());break;
                case "collision":altered.put("data",new byte[]{1});break;
            }
            Path bad=root.resolve(variant+".zip");try(ZipOutputStream z=new ZipOutputStream(Files.newOutputStream(bad))){for(var e:altered.entrySet()){z.putNextEntry(new ZipEntry(e.getKey()));z.write(e.getValue());z.closeEntry();}}
            boolean rejected=false;try{s.restore(bad,null);}catch(IOException e){rejected=true;}
            check(rejected&&snapshot(s.data).equals(current),"reject "+variant+" before changing data");
        }
        Path truncated=root.resolve("truncated.zip");byte[] b=Files.readAllBytes(backup);Files.write(truncated,Arrays.copyOf(b,b.length/2));
        boolean rejected=false;try{s.restore(truncated,null);}catch(IOException e){rejected=true;}check(rejected&&snapshot(s.data).equals(current),"reject truncated archive");
        Path link=s.data.resolve("escape-link");Files.createSymbolicLink(link,root);rejected=false;try{s.exportZip(root.resolve("symlink.zip"));}catch(IOException e){rejected=true;}check(rejected,"reject symlink export");Files.delete(link);
        Process holder=child("lock",s.files.toString());check(new BufferedReader(new InputStreamReader(holder.getInputStream())).readLine().equals("locked"),"guest acquired gate");
        rejected=false;try(var lease=SaveStore.lock(s.files.toFile(),false)){}catch(IOException e){rejected=true;}
        check(rejected,"running guest blocks write");holder.getOutputStream().write(1);holder.getOutputStream().close();check(holder.waitFor()==0,"guest released gate");
        try(var lease=SaveStore.lock(s.files.toFile(),false)){check(lease.lock.isValid(),"exclusive gate after exit");}
        System.out.println("PASS: round trip; world/keychain/prefs; 6 rollback steps; process-death recovery; previous backup; 7 corrupt archives; symlink; cross-process gate");
    }
}
