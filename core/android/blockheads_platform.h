#pragma once

#include <cstdint>
#include <mutex>
#include <vector>
#include <jni.h>

namespace zb {
class GuestThread;
class LibraryRuntime;
class HostJni;

// Reconstructed equivalents of Test4's five Android graphics adapters.
// This object has the same process lifetime as GuestJniRuntime.
class BlockheadsPlatform {
public:
    BlockheadsPlatform(LibraryRuntime& runtime, HostJni& jni) : runtime_(runtime), jni_(jni) {}
    bool handle(std::uint32_t index, GuestThread& thread);
private:
    struct LockedBitmap { jobject object; void* pixels; std::uint32_t address; std::uint32_t size; };
    int lock_pixels(JNIEnv* env, jobject object, std::uint32_t output);
    int unlock_pixels(JNIEnv* env, jobject object);
    void free_guest(std::uint32_t address);
    LibraryRuntime& runtime_;
    HostJni& jni_;
    std::mutex mutex_;
    std::vector<LockedBitmap> locked_;
};
}  // namespace zb
