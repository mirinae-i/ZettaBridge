#!/usr/bin/env python3
"""Check Test12's scoped changes against the pinned, signed Test11 base."""
import argparse
import json
from pathlib import Path
from build_blockheads_test12 import BASE_SHA256
from verify_blockheads_test10 import verify

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'apk', 'native', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.base, args.apk, args.native, base_sha=BASE_SHA256,
                    base_report=b'zettabridge-diagnostic-report11', revision=12,
                    suffix='offline-saves', direct_launch=True, save_tools=True)
    result['addon_scope'] = 'Test11 display/launch policy retained; offline crystal opt-in; process-gated save ZIP and recovery'
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
