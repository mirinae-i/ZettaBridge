#include <cstring>
#include <fstream>
#include <iostream>
#include <vector>
#include "check.h"
#include "zb/blockheads_crystals.h"
int main(int argc,char** argv) {
    CHECK(argc==2);std::ifstream f(argv[1],std::ios::binary);
    std::vector<unsigned char> raw((std::istreambuf_iterator<char>(f)),{});CHECK(raw.size()>0xb611a8);
    zb::GuestMemory m;constexpr std::uint32_t base=0x100000;
    auto put=[&](std::uint32_t off,std::uint32_t val){auto*p=m.host_ptr(base+off,4,zb::kPageWrite);CHECK(p);std::memcpy(p,&val,4);};
    for(auto off:{0u,0xb60000u,0xb61000u,0xb5d000u,0x9f4000u,0x1062000u}) {
        CHECK(m.map_anon(base+off,4096,PROT_READ|PROT_WRITE));
        if(off+4096<raw.size())std::memcpy(m.host_ptr(base+off,4096,zb::kPageWrite),raw.data()+off,4096);
    }
    put(0x10628c8,0);
    for(auto off:{0xb60000u,0xb5d000u})CHECK(m.protect(base+off,4096,PROT_READ|PROT_EXEC));
    const auto pristine=[&]{return std::memcmp(m.host_ptr(base+0xb60380,0xe28,zb::kPageRead),raw.data()+0xb60380,0xe28)==0;};
    put(0x158,0);CHECK(zb::prepare_blockheads_local_crystals(m,base).starts_with("skipped:"));CHECK(pristine());
    put(0x158,0x3eaab781);put(0x10628c8,1);CHECK(zb::prepare_blockheads_local_crystals(m,base).starts_with("skipped:"));CHECK(pristine());
    put(0x10628c8,0);put(0xb61190,0);CHECK(zb::prepare_blockheads_local_crystals(m,base).starts_with("skipped:"));
    std::uint32_t original;std::memcpy(&original,raw.data()+0xb61190,4);put(0xb61190,original);CHECK(pristine());
    CHECK(m.protect(base+0xb5d000,4096,PROT_READ));CHECK(zb::prepare_blockheads_local_crystals(m,base).starts_with("skipped:"));CHECK(pristine());
    CHECK(m.protect(base+0xb5d000,4096,PROT_READ|PROT_EXEC));
    CHECK(zb::prepare_blockheads_local_crystals(m,base).starts_with("offline ADD"));
    CHECK(std::memcmp(m.host_ptr(base+0xb60380,sizeof zb::kCrystalCode,zb::kPageRead),zb::kCrystalCode,sizeof zb::kCrystalCode)==0);
    CHECK(std::memcmp(m.host_ptr(base+0xb60380+sizeof zb::kCrystalCode,0xe28-sizeof zb::kCrystalCode,zb::kPageRead),raw.data()+0xb60380+sizeof zb::kCrystalCode,0xe28-sizeof zb::kCrystalCode)==0);
    CHECK(!m.accessible(base+0xb60380,4,zb::kPageWrite)&&!m.accessible(base+0xb5d19c,4,zb::kPageWrite));
    CHECK(zb::prepare_blockheads_local_crystals(m,base).starts_with("skipped:"));
    CHECK(zb::prepare_blockheads_local_crystals(m,0xfffffff0).starts_with("skipped:"));
    std::cout<<"PASS: original-build hash; startup guard; executable pages; scoped edits; restored permissions; no late reapplication\n";
}
