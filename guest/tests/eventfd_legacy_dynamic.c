/* ARM EABI eventfd predates eventfd2 and takes only an initial counter.
 * Exercise descriptor semantics and a real cross-thread epoll wakeup. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/epoll.h>
#include <sys/eventfd.h>
#include <sys/syscall.h>
#include <unistd.h>

#define REQUIRE(c) do { if (!(c)) { \
    fprintf(stderr, "FAIL line=%d errno=%d: %s\n", __LINE__, errno, #c); return 1; \
} } while (0)

static void* writer(void* arg) {
    const int fd = *(const int*)arg;
    const uint64_t increment = UINT64_C(0x100000009);
    usleep(50000);
    return (void*)(uintptr_t)(write(fd, &increment, sizeof increment) != sizeof increment);
}

int main(void) {
    /* The extra register must be ignored: eventfd has no flags argument. */
    const int fd = syscall(__NR_eventfd, UINT32_MAX, 0xdeadbeef);
    REQUIRE(fd >= 0);
    REQUIRE(fcntl(fd, F_GETFD) == 0);
    const int flags = fcntl(fd, F_GETFL);
    REQUIRE(flags >= 0 && !(flags & O_NONBLOCK));
    uint64_t value = 0;
    REQUIRE(read(fd, &value, sizeof value) == sizeof value && value == UINT32_MAX);
    REQUIRE(fcntl(fd, F_SETFL, flags | O_NONBLOCK) == 0);
    errno = 0;
    REQUIRE(read(fd, &value, sizeof value) == -1 && errno == EAGAIN);

    const int ep = epoll_create1(EPOLL_CLOEXEC);
    REQUIRE(ep >= 0);
    struct epoll_event event = {0}, received = {0};
    event.events = EPOLLIN;
    event.data.u64 = UINT64_C(0x1122334455667788);
    REQUIRE(epoll_ctl(ep, EPOLL_CTL_ADD, fd, &event) == 0);
    REQUIRE(epoll_wait(ep, &received, 1, 0) == 0);
    pthread_t thread;
    REQUIRE(pthread_create(&thread, NULL, writer, (void*)&fd) == 0);
    REQUIRE(epoll_wait(ep, &received, 1, 3000) == 1);
    REQUIRE(received.events & EPOLLIN);
    REQUIRE(received.data.u64 == event.data.u64);
    REQUIRE(read(fd, &value, sizeof value) == sizeof value && value == UINT64_C(0x100000009));
    void* result = NULL;
    REQUIRE(pthread_join(thread, &result) == 0 && result == NULL);
    REQUIRE(epoll_wait(ep, &received, 1, 0) == 0);
    REQUIRE(close(ep) == 0 && close(fd) == 0);

    /* eventfd2 must retain its independent flag semantics. */
    const int modern = eventfd(2, EFD_CLOEXEC | EFD_NONBLOCK | EFD_SEMAPHORE);
    REQUIRE(modern >= 0);
    REQUIRE(fcntl(modern, F_GETFD) & FD_CLOEXEC);
    REQUIRE(fcntl(modern, F_GETFL) & O_NONBLOCK);
    REQUIRE(read(modern, &value, sizeof value) == sizeof value && value == 1);
    REQUIRE(read(modern, &value, sizeof value) == sizeof value && value == 1);
    errno = 0;
    REQUIRE(read(modern, &value, sizeof value) == -1 && errno == EAGAIN);
    REQUIRE(close(modern) == 0);
    puts("legacy_eventfd=PASS epoll_wakeup=PASS eventfd2_flags=PASS");
    return 0;
}
