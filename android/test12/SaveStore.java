package com.zettabridge.launcher;

import java.io.*;
import java.nio.channels.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.zip.*;

/** Offline, private-storage snapshots. Call only while holding the exclusive gate. */
final class SaveStore {
    static final String GAME = "com.noodlecake.blockheads";
    static final String PREFIX = GAME + "__";
    static final long MAX_BYTES = 2L * 1024 * 1024 * 1024;
    static final int MAX_ENTRIES = 50000;
    static final String HEADER = "zettabridge-save-v1\n" + GAME + "\n";
    final Path files, data, prefs, work, transaction, previous;
    SaveStore(File filesDir) {
        files = filesDir.toPath();
        data = files.resolve("plugins/" + GAME + "/data");
        prefs = files.getParent().resolve("shared_prefs");
        work = files.resolve("zb-save-work");
        transaction = work.resolve("transaction");
        previous = files.resolve("zb-save-backups/before-restore.zip");
    }
    static final class Lease implements AutoCloseable {
        final FileChannel channel; final FileLock lock;
        Lease(FileChannel c, FileLock l) { channel=c; lock=l; }
        public void close() throws IOException { try { lock.release(); } finally { channel.close(); } }
    }
    static Lease lock(File files, boolean shared) throws IOException {
        FileChannel c = FileChannel.open(new File(files,"zb-save-lock").toPath(),
                StandardOpenOption.CREATE, StandardOpenOption.READ, StandardOpenOption.WRITE);
        try {
            FileLock l=c.tryLock(0,Long.MAX_VALUE,shared);
            if(l==null) throw new IOException("Exit the game before managing saves.");
            return new Lease(c,l);
        } catch(IOException|RuntimeException e) { c.close(); throw e; }
    }
    boolean pendingRecovery() { return Files.exists(transaction.resolve("journal")); }
    private static void safeName(String n) throws IOException {
        if(n.isEmpty() || n.length()>1024 || n.startsWith("/") || n.contains("\\") || n.contains(":"))
            throw new IOException("Invalid archive path");
        for(char c:n.toCharArray()) if(c<32 || c==127) throw new IOException("Invalid archive path");
        for(String part:n.split("/",-1)) if(part.isEmpty() || part.equals(".") || part.equals(".."))
            throw new IOException("Invalid archive path");
        if(!n.equals("data") && !n.startsWith("data/") && !n.equals("prefs") &&
                !(n.startsWith("prefs/"+PREFIX) && n.indexOf('/',6)==-1))
            throw new IOException("Unsupported archive content");
    }
    private static MessageDigest digest() {
        try { return MessageDigest.getInstance("SHA-256"); }
        catch(NoSuchAlgorithmException e) { throw new AssertionError(e); }
    }
    private static String hex(byte[] b) {
        StringBuilder s=new StringBuilder(); for(byte v:b) s.append(String.format(Locale.ROOT,"%02x",v&255)); return s.toString();
    }
    static void delete(Path p) throws IOException {
        if(!Files.exists(p,LinkOption.NOFOLLOW_LINKS)) return;
        if(Files.isDirectory(p,LinkOption.NOFOLLOW_LINKS)) {
            try(DirectoryStream<Path> ds=Files.newDirectoryStream(p)) { for(Path child:ds) delete(child); }
        }
        Files.delete(p);
    }
    private static void ordinary(Path p) throws IOException {
        for(Path q=p;q!=null;q=q.getParent()) if(Files.isSymbolicLink(q)) throw new IOException("Symbolic links are not supported");
    }
    static void copyBounded(InputStream in, OutputStream out) throws IOException {
        if(in==null || out==null) throw new IOException("Document could not be opened");
        byte[] b=new byte[65536];long size=0;int n;
        while((n=in.read(b))!=-1) { size+=n;if(size>MAX_BYTES) throw new IOException("Archive exceeds 2 GiB");out.write(b,0,n); }
    }
    private static final class Item {
        final String name, hash; final long size; final boolean dir;
        Item(String n,long s,String h,boolean d) {name=n;size=s;hash=h;dir=d;}
    }
    private static List<Path> children(Path p) throws IOException {
        List<Path> out=new ArrayList<>(); if(Files.isDirectory(p))
            try(DirectoryStream<Path> ds=Files.newDirectoryStream(p)) { for(Path x:ds) out.add(x); }
        out.sort(Comparator.comparing(x->x.getFileName().toString()));return out;
    }
    private static void writeTree(ZipOutputStream zip,Path p,String name,List<Item> list,long[] bytes) throws IOException {
        ordinary(p);safeName(name);
        if(list.size()>=MAX_ENTRIES) throw new IOException("Too many save files");
        boolean dir=Files.isDirectory(p,LinkOption.NOFOLLOW_LINKS);
        if(!dir && !Files.isRegularFile(p,LinkOption.NOFOLLOW_LINKS)) throw new IOException("Unsupported save file: "+name);
        ZipEntry e=new ZipEntry(name+(dir?"/":"")); e.setTime(Files.getLastModifiedTime(p).toMillis());zip.putNextEntry(e);
        MessageDigest hash=digest();long count=0;
        if(!dir) try(InputStream in=Files.newInputStream(p)) {
            byte[] buf=new byte[65536];int n;
            while((n=in.read(buf))!=-1) {count+=n;bytes[0]+=n;if(bytes[0]>MAX_BYTES) throw new IOException("Save exceeds 2 GiB");hash.update(buf,0,n);zip.write(buf,0,n);}
        }
        zip.closeEntry();list.add(new Item(name,count,dir?"-":hex(hash.digest()),dir));
        if(dir) for(Path child:children(p)) writeTree(zip,child,name+"/"+child.getFileName(),list,bytes);
    }
    void exportZip(Path destination) throws IOException {
        if(!Files.isDirectory(data)) throw new IOException("No imported game save data found");
        ordinary(data);ordinary(prefs);Files.createDirectories(destination.getParent());
        List<Item> list=new ArrayList<>();long[] bytes={0};
        try(FileOutputStream file=new FileOutputStream(destination.toFile());ZipOutputStream zip=new ZipOutputStream(file)) {
            writeTree(zip,data,"data",list,bytes);
            for(Path p:children(prefs)) if(p.getFileName().toString().startsWith(PREFIX))
                writeTree(zip,p,"prefs/"+p.getFileName(),list,bytes);
            zip.putNextEntry(new ZipEntry("manifest.txt"));
            StringBuilder manifest=new StringBuilder(HEADER);
            for(Item i:list) manifest.append(i.dir?'D':'F').append('\t').append(i.size).append('\t').append(i.hash).append('\t').append(i.name).append('\n');
            zip.write(manifest.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));zip.closeEntry();
            zip.finish();zip.flush();file.getFD().sync();
        }
    }
    static final class Summary {
        final int count; final long bytes;
        Summary(int c,long b) {count=c;bytes=b;}
        public String toString() {return count+" files, "+String.format(Locale.ROOT,"%.1f MiB",bytes/1048576.0);}
    }
    Summary validate(Path archive,Path stage) throws IOException {
        delete(stage);Files.createDirectories(stage);
        try(ZipFile zip=new ZipFile(archive.toFile())) {
            ZipEntry manifest=zip.getEntry("manifest.txt");
            if(manifest==null || manifest.getSize()<0 || manifest.getSize()>16*1024*1024) throw new IOException("Not a ZettaBridge save backup");
            String text;
            try(InputStream in=zip.getInputStream(manifest)) {text=new String(readLimited(in,16*1024*1024),java.nio.charset.StandardCharsets.UTF_8);}
            if(!text.startsWith(HEADER)) throw new IOException("Wrong game or backup version");
            Map<String,Item> expected=new LinkedHashMap<>();
            for(String line:text.substring(HEADER.length()).split("\n")) {
                if(line.isEmpty()) continue;String[] s=line.split("\t",-1);
                if(s.length!=4 || !(s[0].equals("D")||s[0].equals("F"))) throw new IOException("Invalid backup manifest");
                safeName(s[3]);long n;
                try {n=Long.parseLong(s[1]);}catch(NumberFormatException e){throw new IOException("Invalid file size",e);}
                boolean dir=s[0].equals("D");
                if(n<0 || n>MAX_BYTES || (dir && (n!=0 || !s[2].equals("-"))) || (!dir && !s[2].matches("[0-9a-f]{64}"))) throw new IOException("Invalid backup entry");
                if(expected.put(s[3],new Item(s[3],n,s[2],dir))!=null || expected.size()>MAX_ENTRIES) throw new IOException("Duplicate or excessive entries");
            }
            if(!expected.containsKey("data") || !expected.get("data").dir) throw new IOException("Backup has no game data root");
            Set<String> seen=new HashSet<>();long total=0;int count=0,entries=0;
            Enumeration<? extends ZipEntry> en=zip.entries();
            while(en.hasMoreElements()) {
                ZipEntry e=en.nextElement(); if(++entries>MAX_ENTRIES+1) throw new IOException("Too many ZIP entries");
                if(e.getName().equals("manifest.txt")) {if(!seen.add("manifest.txt"))throw new IOException("Duplicate manifest");continue;}
                String name=e.isDirectory()?e.getName().substring(0,e.getName().length()-1):e.getName();safeName(name);
                Item i=expected.get(name);
                if(i==null || !seen.add(name) || i.dir!=e.isDirectory() || e.getSize()!=i.size) throw new IOException("Archive differs from manifest");
                Path target=stage.resolve(name);ordinary(target);
                if(i.dir) {Files.createDirectories(target);continue;}
                Files.createDirectories(target.getParent());MessageDigest hash=digest();long size=0;
                try(InputStream in=zip.getInputStream(e);FileOutputStream out=new FileOutputStream(target.toFile())) {
                    byte[] b=new byte[65536];int n;
                    while((n=in.read(b))!=-1) {size+=n;total+=n;if(size>i.size || total>MAX_BYTES)throw new IOException("Expanded archive too large");hash.update(b,0,n);out.write(b,0,n);}
                    out.getFD().sync();
                }
                if(size!=i.size || !hex(hash.digest()).equals(i.hash)) throw new IOException("Damaged save file: "+name);
                count++;
            }
            if(seen.size()!=expected.size()+1 || count==0) throw new IOException("Incomplete or empty backup");
            return new Summary(count,total);
        } catch(IOException|RuntimeException e) {delete(stage);throw e;}
    }
    private static byte[] readLimited(InputStream in,int max) throws IOException {
        ByteArrayOutputStream out=new ByteArrayOutputStream();byte[] b=new byte[8192];int n;
        while((n=in.read(b))!=-1) {if(out.size()+n>max)throw new IOException("Manifest too large");out.write(b,0,n);}return out.toByteArray();
    }
    private static void move(Path a,Path b) throws IOException {
        Files.createDirectories(b.getParent());Files.move(a,b,StandardCopyOption.ATOMIC_MOVE);
    }
    private Path target(String name) throws IOException {
        safeName(name);
        if(name.equals("data")) return data;
        if(name.startsWith("prefs/"+PREFIX) && name.indexOf('/',6)==-1) return prefs.resolve(name.substring(6));
        throw new IOException("Invalid restore destination");
    }
    private void journal(Properties p) throws IOException {
        Path tmp=transaction.resolve("journal.tmp");
        try(FileOutputStream out=new FileOutputStream(tmp.toFile())) {p.store(out,"ZettaBridge restore journal");out.getFD().sync();}
        move(tmp,transaction.resolve("journal"));
    }
    void recover() throws IOException {
        Path journal=transaction.resolve("journal");if(!Files.exists(journal)) {delete(transaction);return;}
        if(Files.exists(transaction.resolve("COMMITTED"))) {delete(transaction);return;}
        Properties p=new Properties();
        try(InputStream in=Files.newInputStream(journal)) {p.load(new ByteArrayInputStream(readLimited(in,16*1024*1024)));}
        int n;
        try {n=Integer.parseInt(p.getProperty("count"));}catch(RuntimeException e){throw new IOException("Invalid restore journal",e);}
        if(n<1 || n>MAX_ENTRIES) throw new IOException("Invalid restore count");
        for(int i=n-1;i>=0;--i) {
            Path t=target(p.getProperty(i+".name","")),old=transaction.resolve("old/"+i);ordinary(t);
            String existed=p.getProperty(i+".existed");
            if(!"true".equals(existed)&&!"false".equals(existed))throw new IOException("Invalid recovery state");
            if(Files.exists(old,LinkOption.NOFOLLOW_LINKS)) {delete(t);move(old,t);}
            else if("false".equals(existed)) delete(t);
            else if(!Files.exists(t,LinkOption.NOFOLLOW_LINKS)) throw new IOException("Recovery requires original data");
        }
        delete(transaction);
    }
    // Hook only for fault-injection tests; production passes null.
    interface Step {void after(int index) throws IOException;}
    Summary restore(Path archive,Step step) throws IOException {
        recover();Files.createDirectories(transaction);
        Path stage=transaction.resolve("stage");Summary summary=validate(archive,stage);
        try {
            if(Files.isDirectory(data)) {
                Path temp=previous.resolveSibling("before-restore.tmp");exportZip(temp);
                Files.move(temp,previous,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
            }
            SortedSet<String> names=new TreeSet<>();names.add("data");
            for(Path p:children(prefs)) if(p.getFileName().toString().startsWith(PREFIX)) names.add("prefs/"+p.getFileName());
            for(Path p:children(stage.resolve("prefs"))) names.add("prefs/"+p.getFileName());
            Properties j=new Properties();j.setProperty("count",Integer.toString(names.size()));int index=0;
            for(String name:names) {
                Path t=target(name);ordinary(t);
                j.setProperty(index+".name",name);j.setProperty(index+".existed",Boolean.toString(Files.exists(t,LinkOption.NOFOLLOW_LINKS)));index++;
            }
            journal(j);index=0;
            for(String name:names) {
                Path t=target(name),replacement=stage.resolve(name);
                if(Files.exists(t,LinkOption.NOFOLLOW_LINKS)) move(t,transaction.resolve("old/"+index));
                if(step!=null)step.after(index*2);
                if(Files.exists(replacement,LinkOption.NOFOLLOW_LINKS))move(replacement,t);
                if(step!=null)step.after(index*2+1);index++;
            }
            try(FileOutputStream out=new FileOutputStream(transaction.resolve("COMMITTED").toFile())) {out.write(1);out.getFD().sync();}
            delete(transaction);return summary;
        } catch(IOException|RuntimeException e) {
            try {recover();}catch(IOException recovery) {e.addSuppressed(recovery);}throw e;
        }
    }
}
