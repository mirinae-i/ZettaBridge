#include <sys/mman.h>
#include <cstdlib>
#include <cstring>
#include <dynarmic/interface/exclusive_monitor.h>
#include "check.h"
#include "zb/guest_memory.h"
#include "zb/guest_thread.h"

void exercise(bool tracing) {
    CHECK(setenv("ZB_LOAD_TRACE", tracing ? "1" : "0", 1) == 0);
    zb::GuestMemory memory;
    CHECK(memory.ok());
    CHECK(memory.map_anon(0x10000, 4096, PROT_READ | PROT_WRITE));
    // mov r0,0; add r0,1; subs r1,1; bne add; svc host-return
    const std::uint32_t words[] = {0xe3a00000, 0xe2800001, 0xe2511001, 0x1afffffc, 0xef5affff};
    std::memcpy(memory.base() + 0x10000, words, sizeof words);
    CHECK(memory.protect(0x10000, 4096, PROT_READ | PROT_EXEC));
    Dynarmic::ExclusiveMonitor monitor(1);
    zb::GuestThread thread(memory, &monitor, 0);
    thread.set_cpsr(0x10);
    thread.regs()[1] = 2000000;
    thread.regs()[15] = 0x10000;
    std::uint64_t samples = 0, last_ticks = 0;
    thread.progress_observer = [&](zb::GuestThread& current, std::uint64_t sample, std::uint64_t ticks) {
        CHECK(&current == &thread);
        CHECK(sample == ++samples);
        CHECK(ticks > last_ticks);
        last_ticks = ticks;
        CHECK(current.regs()[15] >= 0x10000 && current.regs()[15] <= 0x10014);
    };
    const auto stop = thread.run();
    CHECK(stop.kind == zb::StopKind::Svc && stop.swi == zb::kHostReturnSwi);
    CHECK(thread.regs()[0] == 2000000 && thread.regs()[1] == 0);
    CHECK(tracing ? samples > 0 : samples == 0);
}
int main() {
    exercise(false);
    exercise(true);
    std::puts("trace_guest_thread_test PASS: ARM loop identical with trace off/on (host JIT backend)");
}
