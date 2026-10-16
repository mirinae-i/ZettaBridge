#pragma once
#include "zb/blockheads_crystals_code.h"
#include "zb/guest_memory.h"
#include <cstring>
#include <stdexcept>
#include <string>
#include <sys/mman.h>
namespace zb {
inline std::string prepare_blockheads_local_crystals(GuestMemory& m, std::uint32_t base) {
    auto ptr = [&](std::uint32_t off, std::size_t n) -> std::uint8_t* {
        if (std::uint64_t(base) + off + n > kGuestSpaceSize) return nullptr;
        return m.host_ptr(base + off, n, kPageRead);
    };
    auto word = [&](std::uint32_t off, std::uint32_t value) {
        std::uint32_t v=0; const auto* p=ptr(off,4); if(p) std::memcpy(&v,p,4); return p && v==value;
    };
    constexpr std::uint32_t id[]={0x3eaab781,0x8250b9d0,0x0afc8e85,0x1501717a,0xb9261c22};
    for(unsigned i=0;i<5;++i) if(!word(0x158+i*4,id[i])) return "skipped: unsupported build";
    const auto* started=ptr(0x10628c8,1);
    if(!started || *started) return "skipped: application already started";
    const auto* code=ptr(0xb60380,0xe28);
    if(!code) return "skipped: unreadable TCUI";
    std::uint64_t hash=14695981039346656037ULL;
    for(unsigned i=0;i<0xe28;++i) hash=(hash^code[i])*1099511628211ULL;
    if(hash!=kCrystalOriginalHash || !word(0xb5d19c,0xe12fff33) ||
       !word(0xb5d1ac,0xe24bd018) || !word(0xb5d1b0,0xe8bd8df0) ||
       !word(0x9f4f74,0xe92d4df0) || !word(0x9f4568,0xe92d4df0)) return "skipped: code guard mismatch";
    const std::uint32_t pages[]={page_round_down(base+0xb60380),page_round_down(base+0xb5d19c)};
    int prot[2];
    for(unsigned i=0;i<2;++i) {
        const auto f=m.page_flags(pages[i]);
        if((f&(kPageRead|kPageExec))!=(kPageRead|kPageExec)) return "skipped: non-executable page";
        prot[i]=PROT_READ|PROT_EXEC|((f&kPageWrite)?PROT_WRITE:0);
    }
    for(unsigned i=0;i<2;++i) if(!m.protect(pages[i],kPageSize,prot[i]|PROT_WRITE)) {
        for(unsigned j=0;j<i;++j) if(!m.protect(pages[j],kPageSize,prot[j])) throw std::runtime_error("crystal protection restore failed");
        return "skipped: protection failed";
    }
    std::memcpy(m.host_ptr(base+0xb60380,sizeof kCrystalCode,kPageWrite),kCrystalCode,sizeof kCrystalCode);
    const std::uint32_t nop=0xe320f000;
    const std::uint32_t branch=0xea000000u|(((0xb60394u-0xb5d1acu-8u)>>2)&0x00ffffffu);
    std::memcpy(m.host_ptr(base+0xb5d19c,4,kPageWrite),&nop,4); // Do not start a product query.
    std::memcpy(m.host_ptr(base+0xb5d1ac,4,kPageWrite),&branch,4); // Setup after original init.
    for(unsigned i=0;i<2;++i) if(!m.protect(pages[i],kPageSize,prot[i])) throw std::runtime_error("crystal protection restore failed");
    return "offline ADD buttons 200/1200/3000/10000; original local save path";
}
}
