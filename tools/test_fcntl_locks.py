#!/usr/bin/env python3
"""Drive the ARM32 lock probe against real conflicting locks held by this process."""
import argparse
import fcntl
import os
from pathlib import Path
import selectors
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runner', 'sysroot', 'guest', 'work'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--emulator', type=Path, help='Optional development-only ARM64 runner')
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    lock_path = (args.work / 'locks.data').resolve()
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    os.ftruncate(fd, 1024)
    fcntl.lockf(fd, fcntl.LOCK_EX, 1, 0)
    fcntl.lockf(fd, fcntl.LOCK_EX, 17, 5 << 30)
    command = [str(args.runner.resolve()), '--sysroot', str(args.sysroot.resolve()),
               str(args.guest.resolve()), str(lock_path), str(os.getpid())]
    if args.emulator:
        command.insert(0, str(args.emulator.resolve()))
    log_path = args.work / 'stderr.log'
    process = None
    with log_path.open('wb') as log, selectors.DefaultSelector() as selector:
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log, bufsize=0)
            selector.register(process.stdout, selectors.EVENT_READ)
            pending = b''
            output = bytearray()
            releases = {}
            released = set()
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                now = time.monotonic()
                for kind, due in list(releases.items()):
                    if now >= due:
                        assert process.poll() is None, 'Guest exited while waiting for a lock'
                        length, offset = (1, 0) if kind == 'classic' else (17, 5 << 30)
                        fcntl.lockf(fd, fcntl.LOCK_UN, length, offset)
                        released.add(kind)
                        del releases[kind]
                if not selector.select(0.025):
                    continue
                data = os.read(process.stdout.fileno(), 4096)
                if not data:
                    break
                output.extend(data)
                pending += data
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    text = line.decode('utf-8', errors='replace')
                    print(text, flush=True)
                    for kind in ('classic', 'wide'):
                        if text == 'WAIT ' + kind:
                            assert kind not in released and kind not in releases
                            # Keep the real conflict for another 250 ms. A fake success
                            # or nonblocking implementation must not pass the next line.
                            releases[kind] = time.monotonic() + 0.25
                        if text.startswith('PASS ' + kind + ' blocking'):
                            assert kind in released, 'Blocking lock returned before release'
            process.wait(timeout=2)
            assert process.returncode == 0, 'Guest failed; see ' + str(log_path)
            assert b'FCNTL LOCKS PASS\n' in output, 'Missing completion marker'
            assert released == {'classic', 'wide'}
            print('HOST LOCK DRIVER PASS (both blocking locks held for 250 ms)')
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            os.close(fd)


if __name__ == '__main__':
    main()
