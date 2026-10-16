#pragma once

#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <sys/mman.h>

#include "zb/guest_memory.h"

namespace zb {

// Test10 opt-in for the exact Blockheads 1.7.6 build. Run immediately after the
// library load returns, before Java can start MainThread.nativeRun. The original
// APK and extracted library on disk are never modified. main() has not executed,
// so its screen-mode instruction cannot have a cached translation yet.
inline std::string prepare_blockheads_native_screen(GuestMemory& memory, std::uint32_t base) {
    auto word = [&](std::uint32_t offset, std::uint32_t expected) {
        const std::uint64_t address = static_cast<std::uint64_t>(base) + offset;
        if (address + 4 > kGuestSpaceSize) return false;
        const auto* p = memory.host_ptr(static_cast<std::uint32_t>(address), 4, kPageRead);
        std::uint32_t actual = 0;
        if (p) std::memcpy(&actual, p, 4);
        return p && actual == expected;
    };
    constexpr std::uint32_t id[] = {0x3eaab781, 0x8250b9d0, 0x0afc8e85, 0x1501717a, 0xb9261c22};
    for (unsigned i = 0; i < 5; ++i)
        if (!word(0x158 + i * 4, id[i])) return "skipped: unsupported build id";
    const std::uint64_t started_address = static_cast<std::uint64_t>(base) + 0x10628c8;
    const auto* started = started_address < kGuestSpaceSize
        ? memory.host_ptr(static_cast<std::uint32_t>(started_address), 1, kPageRead) : nullptr;
    if (!word(0x9c5234, 0xe92d4df0) || !word(0x496074, 0xe12fff30) || !started || *started)
        return "skipped: unsupported or already started application";
    // main: r5 supplies the argument to +[UIScreenMode emulatedMode:].
    // 11 chooses the closest preset; 12 selects UINativeScreenMode, whose size
    // comes from Android real display metrics. Use the game's existing mode path.
    constexpr std::uint32_t offset = 0x9c5260;
    if (word(offset, 0xe300500c)) return "native mode 12 already prepared";
    if (!word(offset, 0xe300500b)) return "skipped: screen-mode instruction mismatch";
    const auto address = base + offset;
    const auto flags = memory.page_flags(address);
    if ((flags & (kPageRead | kPageExec)) != (kPageRead | kPageExec))
        return "skipped: screen-mode page is not executable";
    const int prot = PROT_READ | PROT_EXEC | ((flags & kPageWrite) ? PROT_WRITE : 0);
    const auto page = page_round_down(address);
    if (!memory.protect(page, kPageSize, prot | PROT_WRITE)) return "skipped: cannot write screen-mode page";
    constexpr std::uint32_t replacement = 0xe300500c;
    std::memcpy(memory.host_ptr(address, 4, kPageWrite), &replacement, 4);
    if (!memory.protect(page, kPageSize, prot))
        throw std::runtime_error("cannot restore screen-mode page protection");
    return "preset mode 11 -> native mode 12 (before application start)";
}

}  // namespace zb
