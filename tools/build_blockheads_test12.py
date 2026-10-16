#!/usr/bin/env python3
"""Build offline crystals and save tools over the signed Test11 base."""
from build_blockheads_test10 import main
BASE_SHA256='31115550c72bae1ccca250ccd576e95de72ca81e0a31d3553df8264f7123dcbf'
if __name__=='__main__':
    main(base_sha=BASE_SHA256,base_report=b'zettabridge-diagnostic-report11',
         revision=12,suffix='offline-saves',direct_launch=True,save_tools=True)
