/* Developer-only integration probe. Requires the user's original libv/libSystem,
 * with ordinary ELF import fixups and all constructors retained. No game code is
 * bundled. Main-queue draining happens ONLY after a Mach notification, as in a
 * run loop, rather than polling the queue (which hides a broken eventfd wakeup).
 */
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>

static int output;
static int immediate_count, delayed_count;
static uint64_t scheduled_ns, fired_ns;
static void* queue;
static uint64_t (*dispatch_time_fn)(uint64_t, int64_t);
static void (*dispatch_after_fn)(uint64_t, void*, void*, void (*)(void*));

static uint64_t now_ns(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}
static void delayed(void* ignored) {
    (void)ignored;
    fired_ns = now_ns();
    ++delayed_count;
    dprintf(output, "CALLBACK delayed elapsed_ms=%llu\n",
            (unsigned long long)((fired_ns - scheduled_ns) / 1000000));
}
static void immediate(void* ignored) {
    (void)ignored;
    ++immediate_count;
    scheduled_ns = now_ns();
    dispatch_after_fn(dispatch_time_fn(0, 200000000), queue, NULL, delayed);
    dprintf(output, "CALLBACK immediate: queued 200ms activation-style delay\n");
}
#define LOOKUP(h, name, variable) do { \
    *(void**)(&(variable)) = dlsym(h, name); \
    if (!(variable)) { dprintf(output, "missing %s: %s\n", name, dlerror()); return 2; } \
} while (0)

int main(void) {
    output = dup(2); /* libv changes the standard output descriptors. */
    void* android = dlopen("libdl_android.so", RTLD_NOW);
    void (*set_target)(unsigned) = NULL;
    LOOKUP(android, "android_set_application_target_sdk_version", set_target);
    set_target(27);
    void* v = dlopen("libv.so", RTLD_NOW);
    if (!v) { dprintf(output, "libv: %s\n", dlerror()); return 2; }
    void (*init)(void*, void*) = NULL;
    LOOKUP(v, "libv_init", init);
    init(NULL, NULL);
    void* system = dlopen("libSystem.so", RTLD_NOW);
    if (!system) { dprintf(output, "libSystem: %s\n", dlerror()); return 2; }
    void (*async_fn)(void*, void*, void (*)(void*)) = NULL;
    void (*drain)(void*) = NULL;
    unsigned (*get_port)(void) = NULL;
    int (*receive)(void*, unsigned, unsigned, unsigned, unsigned, unsigned, unsigned) = NULL;
    LOOKUP(system, "dispatch_time", dispatch_time_fn);
    LOOKUP(system, "dispatch_after_f", dispatch_after_fn);
    LOOKUP(system, "dispatch_async_f", async_fn);
    LOOKUP(system, "_dispatch_main_queue_callback_4CF", drain);
    LOOKUP(system, "_dispatch_get_main_queue_port_4CF", get_port);
    LOOKUP(system, "mach_msg", receive);
    queue = dlsym(system, "_dispatch_main_q");
    if (!queue) return 2;
    const unsigned port = get_port();
    dprintf(output, "dispatch main port=%u\n", port);
    async_fn(queue, NULL, immediate);
    const uint64_t deadline = now_ns() + UINT64_C(6000000000);
    unsigned wakes = 0;
    while (!delayed_count && now_ns() < deadline) {
        uint32_t message[256] = {0};
        /* MACH_RCV_MSG | MACH_RCV_TIMEOUT, one second, no send operation. */
        const int result = receive(message, 0x102, 0, sizeof message, port, 1000, 0);
        dprintf(output, "receive=0x%x\n", result);
        if (result == 0) { ++wakes; drain(NULL); }
    }
    const int ok = immediate_count == 1 && delayed_count == 1 &&
                   fired_ns - scheduled_ns >= UINT64_C(200000000);
    dprintf(output, "RESULT immediate=%d delayed=%d wakes=%u %s\n",
            immediate_count, delayed_count, wakes, ok ? "PASS" : "FAIL");
    _exit(ok ? 0 : 1);
}
