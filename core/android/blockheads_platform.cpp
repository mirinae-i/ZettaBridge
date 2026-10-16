#include "blockheads_platform.h"

#include <android/bitmap.h>
#include <EGL/egl.h>
#include <GLES/gl.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <bit>
#include <cstring>
#include <string>
#include "zb/guest_thread.h"
#include "zb/host_jni.h"
#include "zb/library_runtime.h"
#include "zb/runtime_report.h"

namespace zb {

void BlockheadsPlatform::free_guest(std::uint32_t address) {
    GuestCall call;
    call.regs = {address, 0, 0, 0};
    (void)runtime_.call_on_current(runtime_.service_api().free_fn, call);
}

int BlockheadsPlatform::lock_pixels(JNIEnv* env, jobject object, std::uint32_t output) {
    if (runtime_.memory().host_ptr(output, 4, kPageWrite) == nullptr) return ANDROID_BITMAP_RESULT_BAD_PARAMETER;
    AndroidBitmapInfo info{};
    int result = AndroidBitmap_getInfo(env, object, &info);
    if (result != ANDROID_BITMAP_RESULT_SUCCESS) return result;
    const std::uint64_t bytes = static_cast<std::uint64_t>(info.stride) * info.height;
    if (bytes == 0 || bytes > 64u * 1024u * 1024u) return ANDROID_BITMAP_RESULT_BAD_PARAMETER;
    void* pixels = nullptr;
    result = AndroidBitmap_lockPixels(env, object, &pixels);
    if (result != ANDROID_BITMAP_RESULT_SUCCESS) return result;
    if (pixels == nullptr) {
        AndroidBitmap_unlockPixels(env, object);
        return ANDROID_BITMAP_RESULT_BAD_PARAMETER;
    }
    GuestCall allocate;
    allocate.regs = {static_cast<std::uint32_t>(bytes), 0, 0, 0};
    const auto memory = runtime_.call_on_current(runtime_.service_api().malloc_fn, allocate);
    const std::uint32_t address = memory ? memory->r0 : 0;
    auto* destination = address ? runtime_.memory().host_ptr(address, bytes, kPageWrite) : nullptr;
    auto* out = runtime_.memory().host_ptr(output, 4, kPageWrite);
    jobject global = destination && out ? env->NewGlobalRef(object) : nullptr;
    if (global == nullptr) {
        AndroidBitmap_unlockPixels(env, object);
        if (address) free_guest(address);
        return env->ExceptionCheck() ? ANDROID_BITMAP_RESULT_JNI_EXCEPTION : ANDROID_BITMAP_RESULT_ALLOCATION_FAILED;
    }
    std::memcpy(destination, pixels, bytes);
    {
        std::lock_guard<std::mutex> lock(mutex_);
        locked_.push_back({global, pixels, address, static_cast<std::uint32_t>(bytes)});
    }
    std::memcpy(out, &address, 4);
    runtime_report().note_jni_detail("bitmap-bridge-last", "lock bytes=" + std::to_string(bytes), true);
    return ANDROID_BITMAP_RESULT_SUCCESS;
}

int BlockheadsPlatform::unlock_pixels(JNIEnv* env, jobject object) {
    LockedBitmap bitmap{};
    {
        std::lock_guard<std::mutex> lock(mutex_);
        for (auto it = locked_.begin(); it != locked_.end(); ++it) {
            if (env->IsSameObject(object, it->object)) {
                bitmap = *it;
                locked_.erase(it);
                break;
            }
        }
    }
    if (bitmap.object == nullptr) return ANDROID_BITMAP_RESULT_BAD_PARAMETER;
    const auto* source = runtime_.memory().host_ptr(bitmap.address, bitmap.size, kPageRead);
    if (source != nullptr) std::memcpy(bitmap.pixels, source, bitmap.size);
    const int result = AndroidBitmap_unlockPixels(env, bitmap.object);
    env->DeleteGlobalRef(bitmap.object);
    // Guest allocation/free may re-enter this dispatcher; never hold mutex_ here.
    free_guest(bitmap.address);
    runtime_report().note_jni_detail("bitmap-bridge-last", "unlock bytes=" + std::to_string(bitmap.size), true);
    return source != nullptr ? result : ANDROID_BITMAP_RESULT_BAD_PARAMETER;
}

bool BlockheadsPlatform::handle(std::uint32_t index, GuestThread& thread) {
    auto& r = thread.regs();
    // These indices are the unchanged generated Test4 stub ABI.
    if (index == 510 || index == 549) {
        float args[6];
        for (unsigned i = 0; i != 4; ++i) args[i] = std::bit_cast<float>(r[i]);
        const auto* stack = runtime_.memory().host_ptr(r[13], 8, kPageRead);
        if (stack == nullptr) {
            runtime_report().note_jni_detail("gles1-stack", "unreadable projection arguments", true);
            return true;
        }
        std::memcpy(args + 4, stack, 8);
        const char* name = index == 510 ? "glFrustumf" : "glOrthof";
        static thread_local const auto tid = static_cast<std::uint64_t>(::syscall(SYS_gettid));
        static thread_local bool context_observed = false;
        runtime_report().note_gl_call(name, tid);
        if (!context_observed) {
            context_observed = true;
            runtime_report().note_gl_egl_context(eglGetCurrentContext() != EGL_NO_CONTEXT);
        }
        if (index == 510) glFrustumf(args[0], args[1], args[2], args[3], args[4], args[5]);
        else glOrthof(args[0], args[1], args[2], args[3], args[4], args[5]);
        return true;
    }
    if (index < 217 || index > 219) return false;
    auto* env = reinterpret_cast<JNIEnv*>(static_cast<std::uintptr_t>(jni_.current_env()));
    int result = ANDROID_BITMAP_RESULT_BAD_PARAMETER;
    if (env != nullptr) {
        const auto real = jni_.resolve_ref(r[1], "AndroidBitmap");
        jobject object = real ? env->NewLocalRef(reinterpret_cast<jobject>(static_cast<std::uintptr_t>(real))) : nullptr;
        if (object != nullptr) {
            if (index == 217) {
                // Test4 disassembly also uses a 20-byte AndroidBitmapInfo.
                static_assert(sizeof(AndroidBitmapInfo) == 20);
                auto* out = runtime_.memory().host_ptr(r[2], sizeof(AndroidBitmapInfo), kPageWrite);
                if (out != nullptr) {
                    AndroidBitmapInfo info{};
                    result = AndroidBitmap_getInfo(env, object, &info);
                    if (result == ANDROID_BITMAP_RESULT_SUCCESS) std::memcpy(out, &info, sizeof info);
                }
            } else if (index == 218) result = lock_pixels(env, object, r[2]);
            else result = unlock_pixels(env, object);
            env->DeleteLocalRef(object);
        } else if (env->ExceptionCheck()) result = ANDROID_BITMAP_RESULT_JNI_EXCEPTION;
    }
    r[0] = static_cast<std::uint32_t>(result);
    return true;
}

}  // namespace zb
