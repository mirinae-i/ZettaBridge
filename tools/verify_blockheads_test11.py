#!/usr/bin/env python3
"""Verify the scoped Test10 -> Test11 update. This does not execute Android."""
import argparse
import json
from pathlib import Path
from build_blockheads_test11 import BASE_SHA256
from verify_blockheads_test10 import verify

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'apk', 'native', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.base, args.apk, args.native, base_sha=BASE_SHA256,
                    base_report=b'zettabridge-diagnostic-report10', revision=11, suffix='ppi-ui')
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
