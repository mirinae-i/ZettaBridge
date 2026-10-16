#pragma once

#include <charconv>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <sys/mman.h>

#include "zb/guest_memory.h"

namespace zb {

// Invalid or absent policy retains Test10's 600-point content width. Bound the
// environment input independently of Java; never allow a zero/NaN scale.
inline float blockheads_ui_points(const char* text) {
    if (!text) return 600.0f;
    float value = 0;
    const auto end = text + std::strlen(text);
    const auto parsed = std::from_chars(text, end, value);
    return parsed.ec == std::errc{} && parsed.ptr == end && std::isfinite(value) &&
        value >= 600.0f && value <= 682.0f ? value : 600.0f;
}

// Test11 opt-in for the exact Blockheads 1.7.6 build. Run immediately after the
// library load returns, before Java can start MainThread.nativeRun. The original
// APK and extracted library on disk are never modified. main() has not executed,
// so its screen-mode instruction cannot have a cached translation yet.
inline std::string prepare_blockheads_native_screen(GuestMemory& memory, std::uint32_t base,
                                                    float ui_points = 600.0f) {
    if (!std::isfinite(ui_points) || ui_points < 600.0f || ui_points > 682.0f)
        return "skipped: invalid UI points";
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
    constexpr std::uint32_t mode_offset = 0x9c5260;
    constexpr std::uint32_t points_offset = 0x26d904;
    // +[UINativeScreenMode nativeMode:] computes VerdePluginNativeWidth / 600.
    // Change its private float literal, not display pixels, projection, or views.
    // This method has not executed before main; no translated code is invalidated.
    if (!word(0x26d804, 0xe92d4c10) || !word(0x26d824, 0xed9f0a36) ||
        !word(0x26d85c, 0xee800a01)) return "skipped: native-scale code mismatch";
    std::uint32_t points_bits;
    std::memcpy(&points_bits, &ui_points, sizeof points_bits);
    const bool native = word(mode_offset, 0xe300500c);
    if (!native && !word(mode_offset, 0xe300500b)) return "skipped: screen-mode instruction mismatch";
    if (!word(points_offset, 0x44160000) && !word(points_offset, points_bits))
        return "skipped: native-scale literal mismatch";
    if (native && word(points_offset, points_bits)) return "native mode 12 already prepared";
    const std::uint32_t addresses[] = {base + mode_offset, base + points_offset};
    int protections[2];
    for (unsigned i = 0; i < 2; ++i) {
        const auto flags = memory.page_flags(addresses[i]);
        if ((flags & (kPageRead | kPageExec)) != (kPageRead | kPageExec))
            return "skipped: screen-mode page is not executable";
        protections[i] = PROT_READ | PROT_EXEC | ((flags & kPageWrite) ? PROT_WRITE : 0);
    }
    // Make both pages writable before touching either. A refusal leaves all
    // bytes unchanged, including when only the second page cannot be protected.
    for (unsigned i = 0; i < 2; ++i) {
        if (!memory.protect(page_round_down(addresses[i]), kPageSize, protections[i] | PROT_WRITE)) {
            for (unsigned j = 0; j < i; ++j)
                if (!memory.protect(page_round_down(addresses[j]), kPageSize, protections[j]))
                    throw std::runtime_error("cannot restore screen-mode page protection");
            return "skipped: cannot write screen-mode page";
        }
    }
    constexpr std::uint32_t replacement = 0xe300500c;
    std::memcpy(memory.host_ptr(addresses[0], 4, kPageWrite), &replacement, 4);
    std::memcpy(memory.host_ptr(addresses[1], 4, kPageWrite), &points_bits, 4);
    bool restored = true;
    for (unsigned i = 0; i < 2; ++i)
        if (!memory.protect(page_round_down(addresses[i]), kPageSize, protections[i])) restored = false;
    if (!restored) throw std::runtime_error("cannot restore screen-mode page protection");
    return "native mode 12; UI points=" + std::to_string(ui_points) +
        " sizeRatio=" + std::to_string(600.0f / ui_points) + " (before application start)";
}

}  // namespace zb
