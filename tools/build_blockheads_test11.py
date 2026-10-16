#!/usr/bin/env python3
"""Build the PPI-aware Test11 update using the exact previously shipped Test10 APK."""
from build_blockheads_test10 import main

BASE_SHA256 = 'e2fa636c94c554db4977fb42b5b5f5cd44acc99dd9588daad3aab8ac261418fa'

if __name__ == '__main__':
    main(base_sha=BASE_SHA256, base_report=b'zettabridge-diagnostic-report10',
         revision=11, suffix='ppi-ui', direct_launch=True)
