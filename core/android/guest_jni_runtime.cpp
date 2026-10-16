#include "guest_jni_runtime.h"
#include "blockheads_platform.h"

#include <atomic>
#include <cstdint>
#include <cstring>
#include <mutex>

namespace zb {

namespace {

JNIEnv* E(JniBackend::Env env) {
    return reinterpret_cast<JNIEnv*>(static_cast<std::uintptr_t>(env));
}

std::once_flag g_once;
std::atomic<GuestJniRuntime*> g_instance{nullptr};

}  // namespace

GuestJniRuntime& GuestJniRuntime::get(JNIEnv* env) {
    std::call_once(g_once, [env] {
        JavaVM* vm = nullptr;
        if (env->GetJavaVM(&vm) != JNI_OK || vm == nullptr) env->FatalError("ZettaBridge: GetJavaVM failed");
        // Process-lifetime by design: never deleted (see the class comment).
        g_instance.store(new GuestJniRuntime(vm));
    });
    return *g_instance.load();
}

GuestJniRuntime* GuestJniRuntime::peek() {
    return g_instance.load();
}

GuestJniRuntime::GuestJniRuntime(JavaVM* vm)
    : backend_(vm),
      engine_(backend_, gl_backend_, asset_backend_, egl_backend_, window_backend_, looper_backend_,
              input_backend_, configuration_backend_),
      native_activity_glue_(*engine_.host_native_activity(), engine_.host_native_window(), engine_.host_input()),
      proxies_(engine_) {
    engine_.set_native_activity_platform(&native_activity_glue_);
    auto* platform = new BlockheadsPlatform(engine_.runtime(), engine_.host_jni());
    engine_.set_platform_host_call_handler([platform](std::uint32_t index, GuestThread& thread) {
        return platform->handle(index, thread);
    });
}

std::string GuestJniRuntime::inspect_blockheads_display() {
    auto& runtime = engine_.runtime();
    std::uint64_t base = 0;
    for (const auto& path : runtime.mapped_file_paths()) {
        if (path.find("/com.noodlecake.blockheads/") != std::string::npos && path.ends_with("/libApplication.so")) {
            auto address = runtime.mapped_file_address(path, 0);
            if (address) base = *address;
        }
    }
    if (!base) return "application library not mapped";
    auto& memory = runtime.memory();
    bool valid = true;
    auto read = [&](std::uint64_t address, void* out, std::size_t size) {
        if (address >= kGuestSpaceSize || size > kGuestSpaceSize - address) { valid = false; return; }
        auto* src = memory.host_ptr(static_cast<std::uint32_t>(address), size, kPageRead);
        if (!src) { valid = false; return; }
        std::memcpy(out, src, size);
    };
    auto word = [&](std::uint64_t address) { std::uint32_t v = 0; read(address, &v, sizeof v); return v; };
    constexpr std::uint32_t build_id[] = {0x3eaab781, 0x8250b9d0, 0x0afc8e85, 0x1501717a, 0xb9261c22};
    for (std::size_t i = 0; i < 5; ++i)
        if (word(base + 0x158 + 4 * i) != build_id[i]) return "unsupported application build id";
    if (!valid || word(base + 0x240c68) != 0xe92d4c10 || word(base + 0x7816e8) != 0xe92d4df0 ||
        word(base + 0x781a44) != 0xe92d4df0) return "unsupported application code layout";
    auto field_address = [&](std::uint32_t object, std::uint32_t offset_variable) -> std::uint64_t {
        const auto offset = word(base + offset_variable);
        if (!object || offset > 65535) { valid = false; return kGuestSpaceSize; }
        return static_cast<std::uint64_t>(object) + offset;
    };
    auto field = [&](std::uint32_t o, std::uint32_t v) { return word(field_address(o, v)); };
    auto byte_field = [&](std::uint32_t o, std::uint32_t v) {
        std::uint8_t b = 0; read(field_address(o, v), &b, 1); return b;
    };
    const auto app = word(base + 0x106055c);
    if (!app) return "application singleton not initialized";
    if (word(app) != base + 0xe8e500) return "unsupported application class";
    const auto delegate = field(app, 0xf3135c);
    if (!delegate) return "application delegate not initialized";
    if (word(delegate) != base + 0xe92218) return "unsupported delegate class";
    const auto controller = field(delegate, 0xf358a0);
    if (!controller) return "view controller not initialized";
    if (word(controller) != base + 0xe90f80) return "unsupported controller class";
    std::string out;
    auto add = [&](const char* name, auto value) {
        if (!out.empty()) out += ' ';
        out += name; out += '='; out += std::to_string(value);
    };
    add("appState", field(app, 0xf31358));
    add("active", byte_field(controller, 0xf3387c));
    add("animating", byte_field(controller, 0xf3386c));
    add("gdprComplete", byte_field(controller, 0xf33874));
    add("gameViewPresent", field(controller, 0xf33864) != 0);
    add("contextPresent", field(controller, 0xf33868) != 0);
    add("glInitialized", byte_field(controller, 0xf33888));
    add("frameDrawn", byte_field(controller, 0xf33880));
    add("frameInterval", field(controller, 0xf33870));
    const auto link = field(controller, 0xf33890);
    add("displayLinkPresent", link != 0);
    if (link && word(link) == base + 0xe8df38) {
        add("linkPaused", byte_field(link, 0xf30ffc));
        add("linkSuspended", byte_field(link, 0xf3101c));
        add("timerPresent", field(link, 0xf31020) != 0);
        add("linkFrameIndex", field(link, 0xf31028));
        add("linkInterval", field(link, 0xf31010));
        double timestamp = 0; read(field_address(link, 0xf31004), &timestamp, sizeof timestamp);
        add("linkTimestamp", timestamp);
    } else if (link) out += " displayLinkClass=unsupported";
    if (!valid) out += " partial=unreadable";
    return out;
}

bool GuestJniRuntime::Engine::bind_class_loader(JniBackend::Env env, JniBackend::Ref loader, std::string& error) {
    JNIEnv* e = E(env);
    if (jni_backend_.set_class_loader(e, reinterpret_cast<jobject>(static_cast<std::uintptr_t>(loader)))) {
        return true;
    }
    const std::string pending = take_pending_exception(env);
    error = "the object is not a ClassLoader, or a different plugin class loader is already bound";
    if (!pending.empty()) error += " (" + pending + ")";
    return false;
}

// Throwable.toString() of the pending exception, which is cleared. ART clears it anyway after a
// failed JNI_OnLoad, so its text only survives inside ZettaBridge's own error message.
std::string GuestJniRuntime::Engine::take_pending_exception(JniBackend::Env env) {
    JNIEnv* e = E(env);
    if (e->ExceptionCheck() == JNI_FALSE) return {};
    jthrowable pending = e->ExceptionOccurred();
    e->ExceptionClear();
    std::string text = "a Java exception was pending";
    if (pending == nullptr || e->PushLocalFrame(4) != JNI_OK) {
        e->ExceptionClear();
        if (pending != nullptr) e->DeleteLocalRef(pending);
        return text;
    }
    jclass throwable = e->FindClass("java/lang/Throwable");
    jmethodID to_string =
        throwable != nullptr ? e->GetMethodID(throwable, "toString", "()Ljava/lang/String;") : nullptr;
    auto description = to_string != nullptr ? static_cast<jstring>(e->CallObjectMethod(pending, to_string)) : nullptr;
    if (e->ExceptionCheck() == JNI_FALSE && description != nullptr) {
        const char* chars = e->GetStringUTFChars(description, nullptr);
        if (chars != nullptr) {
            text = chars;
            e->ReleaseStringUTFChars(description, chars);
        }
    }
    e->ExceptionClear();
    e->PopLocalFrame(nullptr);
    e->DeleteLocalRef(pending);
    return text;
}

}  // namespace zb
