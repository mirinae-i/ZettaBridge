/* ARM EABI record-lock regression. The Python driver holds conflicting host locks. */
#define _LARGEFILE64_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <unistd.h>

#define REQUIRE(test) do { if (!(test)) { fprintf(stderr, "FAIL line %d: %s errno=%d\n", __LINE__, #test, errno); exit(1); } } while (0)
static int ctl(int fd, int command, void* lock) { return syscall(__NR_fcntl64, fd, command, lock); }
int main(int argc, char** argv) {
    REQUIRE(argc == 3);
    setbuf(stdout, NULL);
    const int owner = atoi(argv[2]);
    const int fd = open(argv[1], O_RDWR);
    REQUIRE(fd >= 0);
    struct { uint32_t before; struct flock lock; uint32_t after; } small = {
        .before=0x13572468, .lock={.l_type=F_WRLCK, .l_whence=SEEK_SET, .l_start=0, .l_len=1}, .after=0xabcdef12};
    REQUIRE(ctl(fd, 5, &small.lock) == 0);
    REQUIRE(small.lock.l_type == F_WRLCK && small.lock.l_pid == owner && small.lock.l_start == 0 && small.lock.l_len == 1);
    REQUIRE(small.before == 0x13572468 && small.after == 0xabcdef12);
    REQUIRE(ctl(fd, 6, &small.lock) == -1 && (errno == EAGAIN || errno == EACCES));
    small.lock.l_start = 8;
    REQUIRE(ctl(fd, 6, &small.lock) == 0);
    small.lock.l_type = F_UNLCK;
    REQUIRE(ctl(fd, 6, &small.lock) == 0);
    /* NR_fcntl must use the same ARM32 layout for the classic command numbers. */
    small.lock.l_type = F_WRLCK;
    small.lock.l_start = 0;
    REQUIRE(syscall(__NR_fcntl, fd, 5, &small.lock) == 0 && small.lock.l_pid == owner);
    puts("PASS classic F_GETLK/F_SETLK/NR_fcntl");

    struct { uint64_t before; struct flock64 lock; uint64_t after; } large = {
        .before=0x123456789abcdef0ULL, .lock={.l_type=F_WRLCK, .l_whence=SEEK_SET, .l_start=5LL<<30, .l_len=17}, .after=0x9876543210abcdefULL};
    REQUIRE(ctl(fd, 12, &large.lock) == 0);
    REQUIRE(large.lock.l_type == F_WRLCK && large.lock.l_pid == owner && large.lock.l_start == (5LL<<30) && large.lock.l_len == 17);
    REQUIRE(large.before == 0x123456789abcdef0ULL && large.after == 0x9876543210abcdefULL);
    REQUIRE(ctl(fd, 13, &large.lock) == -1 && (errno == EAGAIN || errno == EACCES));
    large.lock.l_start += 32;
    REQUIRE(ctl(fd, 13, &large.lock) == 0);
    large.lock.l_type = F_UNLCK;
    REQUIRE(ctl(fd, 13, &large.lock) == 0);
    REQUIRE(syscall(__NR_fcntl, fd, 12, &large.lock) == -1 && errno == EINVAL);
    puts("PASS 64-bit locks above 4 GiB");

    REQUIRE(ctl(fd, 5, (void*)1) == -1 && errno == EFAULT);
    struct flock* ro = mmap(NULL, 4096, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS, -1, 0);
    REQUIRE(ro != MAP_FAILED);
    *ro = (struct flock){.l_type=F_WRLCK, .l_whence=SEEK_SET, .l_start=64, .l_len=1};
    REQUIRE(mprotect(ro, 4096, PROT_READ) == 0);
    REQUIRE(ctl(fd, 6, ro) == 0); /* Input-only call may read a read-only structure. */
    REQUIRE(ctl(fd, 5, ro) == -1 && errno == EFAULT);
    REQUIRE(munmap(ro,4096) == 0);
    puts("PASS guest pointer permissions");

    small.lock = (struct flock){.l_type=F_WRLCK, .l_whence=SEEK_SET, .l_start=0, .l_len=1};
    puts("WAIT classic");
    REQUIRE(ctl(fd, 7, &small.lock) == 0);
    small.lock.l_type = F_UNLCK;
    REQUIRE(ctl(fd, 6, &small.lock) == 0);
    /* With the low lock gone, the first conflict for an unbounded query is > INT32_MAX. */
    small.lock = (struct flock){.l_type=F_WRLCK, .l_whence=SEEK_SET, .l_start=0, .l_len=0};
    REQUIRE(ctl(fd, 5, &small.lock) == -1 && errno == EOVERFLOW);
    REQUIRE(small.lock.l_type == F_WRLCK && small.lock.l_start == 0 && small.lock.l_len == 0);
    puts("PASS classic blocking lock and overflow");
    large.lock = (struct flock64){.l_type=F_WRLCK, .l_whence=SEEK_SET, .l_start=5LL<<30, .l_len=17};
    puts("WAIT wide");
    REQUIRE(ctl(fd, 14, &large.lock) == 0);
    large.lock.l_type = F_UNLCK;
    REQUIRE(ctl(fd, 13, &large.lock) == 0);
    puts("PASS wide blocking lock");
    close(fd);
    puts("FCNTL LOCKS PASS");
    return 0;
}
