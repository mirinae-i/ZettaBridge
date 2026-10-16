#include <cstring>
#include <iostream>
#include <limits>
#include "check.h"
#include "zb/blockheads_display.h"

int main() {
    zb::GuestMemory memory;
    constexpr std::uint32_t base = 0x100000;
    auto put = [&](std::uint32_t offset, std::uint32_t value) {
        auto* p = memory.host_ptr(base + offset, 4, zb::kPageWrite);
        CHECK(p != nullptr); std::memcpy(p, &value, 4);
    };
    for (auto offset : {0u, 0x9c5000u, 0x496000u, 0x1062000u, 0x26d000u})
        CHECK(memory.map_anon(base + offset, 4096, PROT_READ | PROT_WRITE));
    constexpr std::uint32_t id[] = {0x3eaab781, 0x8250b9d0, 0x0afc8e85, 0x1501717a, 0xb9261c22};
    for (unsigned i = 0; i < 5; ++i) put(0x158 + 4 * i, id[i]);
    put(0x9c5234, 0xe92d4df0); put(0x496074, 0xe12fff30);
    put(0x26d804, 0xe92d4c10); put(0x26d824, 0xed9f0a36);
    put(0x26d85c, 0xee800a01); put(0x26d904, 0x44160000);
    CHECK(memory.protect(base + 0x26d000, 4096, PROT_READ | PROT_EXEC));
    put(0x9c5260, 0xe300500b); put(0x9c5264, 0x12345678);
    CHECK(memory.protect(base + 0x9c5000, 4096, PROT_READ | PROT_EXEC));
    auto instruction = [&] {
        std::uint32_t value; std::memcpy(&value, memory.host_ptr(base + 0x9c5260, 4, zb::kPageRead), 4);
        return value;
    };
    put(0x158, 0);
    CHECK(zb::prepare_blockheads_native_screen(memory, base).starts_with("skipped:"));
    CHECK(instruction() == 0xe300500b);
    put(0x158, id[0]); put(0x10628c8, 1);
    CHECK(zb::prepare_blockheads_native_screen(memory, base).starts_with("skipped:"));
    CHECK(instruction() == 0xe300500b);
    put(0x10628c8, 0);
    std::uint8_t before[4096], after[4096];
    std::memcpy(before, memory.host_ptr(base + 0x9c5000, 4096, zb::kPageRead), 4096);
    CHECK(zb::prepare_blockheads_native_screen(memory, base).starts_with("native mode 12; UI points=600"));
    CHECK(instruction() == 0xe300500c);
    CHECK(!memory.accessible(base + 0x9c5260, 4, zb::kPageWrite));
    CHECK(memory.accessible(base + 0x9c5260, 4, zb::kPageExec));
    std::memcpy(after, memory.host_ptr(base + 0x9c5000, 4096, zb::kPageRead), 4096);
    before[0x260] = 0x0c;
    CHECK(std::memcmp(before, after, 4096) == 0);
    CHECK(zb::prepare_blockheads_native_screen(memory, base) == "native mode 12 already prepared");
    // PPI policy changes just the mode literal; rendering pixels and adjacent
    // instructions are preserved. Repeat is idempotent, other literals refused.
    std::uint8_t scale_before[4096], scale_after[4096];
    std::memcpy(scale_before, memory.host_ptr(base + 0x26d000, 4096, zb::kPageRead), 4096);
    constexpr float points = 650.0f;
    CHECK(zb::prepare_blockheads_native_screen(memory, base, points).starts_with("native mode 12; UI points=650"));
    CHECK(!memory.accessible(base + 0x26d904, 4, zb::kPageWrite));
    CHECK(memory.accessible(base + 0x26d904, 4, zb::kPageExec));
    std::memcpy(scale_after, memory.host_ptr(base + 0x26d000, 4096, zb::kPageRead), 4096);
    std::memcpy(scale_before + 0x904, &points, sizeof points);
    CHECK(std::memcmp(scale_before, scale_after, 4096) == 0);
    CHECK(zb::prepare_blockheads_native_screen(memory, base, points) == "native mode 12 already prepared");
    CHECK(zb::prepare_blockheads_native_screen(memory, base, 670.0f).starts_with("skipped:"));
    CHECK(zb::prepare_blockheads_native_screen(memory, base, 0.0f).starts_with("skipped:"));
    CHECK(zb::prepare_blockheads_native_screen(memory, base, std::numeric_limits<float>::quiet_NaN()).starts_with("skipped:"));
    CHECK(zb::blockheads_ui_points("650.0") == points);
    for (const char* invalid : std::initializer_list<const char*>{nullptr, "", "nan", "inf", "0", "599", "683", "650garbage"})
        CHECK(zb::blockheads_ui_points(invalid) == 600.0f);
    CHECK(memory.protect(base + 0x9c5000, 4096, PROT_READ | PROT_WRITE | PROT_EXEC));
    put(0x9c5260, 0xdeadbeef);
    CHECK(memory.protect(base + 0x9c5000, 4096, PROT_READ | PROT_EXEC));
    CHECK(zb::prepare_blockheads_native_screen(memory, base).starts_with("skipped:"));
    CHECK(instruction() == 0xdeadbeef);
    CHECK(zb::prepare_blockheads_native_screen(memory, 0xfffffff0).starts_with("skipped:"));
    std::cout << "PASS: build/start guards, mode/scale literals, bounded PPI input, unchanged adjacent bytes, protections, idempotence\n";
}
