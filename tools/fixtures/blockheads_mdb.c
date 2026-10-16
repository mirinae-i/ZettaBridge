#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
int main(int argc,char**argv){
 int logfile=dup(2); setbuf(stderr,0);
 void *a=dlopen("libdl_android.so",RTLD_NOW);
 void (*sdk)(unsigned)=dlsym(a,"android_set_application_target_sdk_version");sdk(27);
 void* v=dlopen("libv.so",RTLD_NOW);
 dprintf(logfile,"libv=%p err=%s\n",v,v?"none":dlerror());
 if(!v)return 1;
 void (*init)(void*,void*)=dlsym(v,"libv_init");
 dprintf(logfile,"libv_init=%p begin\n",init);init(0,0);dprintf(logfile,"libv init returned\n");
 void* app=dlopen("libApplication.so",RTLD_NOW);
 int (*create)(void**) = dlsym(app,"mdb_env_create");
 int (*maxdbs)(void*,unsigned) = dlsym(app,"mdb_env_set_maxdbs");
 int (*mapsize)(void*,unsigned) = dlsym(app,"mdb_env_set_mapsize");
 int (*openenv)(void*,const char*,unsigned,int) = dlsym(app,"mdb_env_open");
 int (*begin)(void*,void*,unsigned,void**) = dlsym(app,"mdb_txn_begin");
 int (*dbiopen)(void*,const char*,unsigned,unsigned*) = dlsym(app,"mdb_dbi_open");
 typedef struct { unsigned size; void* data; } Val;
 int (*put)(void*,unsigned,Val*,Val*,unsigned)=dlsym(app,"mdb_put");
 int (*get)(void*,unsigned,Val*,Val*)=dlsym(app,"mdb_get");
 void (*closeenv)(void*)=dlsym(app,"mdb_env_close");
 void (*aborttxn)(void*)=dlsym(app,"mdb_txn_abort");
 int (*commit)(void*) = dlsym(app,"mdb_txn_commit");
 const char* (*err)(int) = dlsym(app,"mdb_strerror");
 void *env=0,*txn=0;unsigned dbi=0;int rc;
 #define CHECK(call) do { rc=(call); dprintf(logfile,#call " => %d %s\n",rc,err(rc)); if(rc) _exit(3); } while(0)
 CHECK(create(&env)); CHECK(maxdbs(env,16)); CHECK(mapsize(env,16*1024*1024));
 CHECK(openenv(env,getenv("DBPATH"),0,0600)); CHECK(begin(env,0,0,&txn));
 CHECK(dbiopen(txn,"app",0x40000,&dbi));
 Val key={8,"test-key"},value={11,"saved-value"};
 CHECK(put(txn,dbi,&key,&value,0)); CHECK(commit(txn));
 closeenv(env);env=0;txn=0;
 CHECK(create(&env));CHECK(maxdbs(env,16));CHECK(mapsize(env,16*1024*1024));
 CHECK(openenv(env,getenv("DBPATH"),0,0600));CHECK(begin(env,0,0x20000,&txn));
 CHECK(dbiopen(txn,"app",0,&dbi));value=(Val){0,0};CHECK(get(txn,dbi,&key,&value));
 if(value.size!=11 || memcmp(value.data,"saved-value",11)) { dprintf(logfile,"DATA MISMATCH\n"); _exit(4); }
 dprintf(logfile,"PERSISTENT VALUE VERIFIED after close/reopen\n");aborttxn(txn);closeenv(env);
 dprintf(logfile,"LMDB PROBE PASSED\n");_exit(0);
}
