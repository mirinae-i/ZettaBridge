// No JNI, guest syscalls or guest signal delivery are exercised in this harness.
#include <csignal>
#include <cstdint>
#include <string>
namespace zb {
int host_interrupt_signal() { return SIGUSR2; }
const char* syscall_name(std::uint32_t) { return "test-syscall"; }
std::string jni_recent_calls() { return "test-jni"; }
}
