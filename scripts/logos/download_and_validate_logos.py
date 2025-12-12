#!/usr/bin/env python3
"""
Download all logo images from AWS and validate them.
Saves working logos to a folder and outputs broken_logos.csv as it runs.
"""

import csv
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import PORTFOLIO_ORGS_PATH

# Config
CSV_PATH = str(PORTFOLIO_ORGS_PATH)
# Output folders are external to project - intentionally hardcoded
OUTPUT_FOLDER = '/Users/forrestmiller/Desktop/downloaded_logos'
BROKEN_CSV = '/Users/forrestmiller/Desktop/broken_logos.csv'

PNG_HEADER = b'\x89PNG\r\n\x1a\n'

def main():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # Read orgs
    with open(CSV_PATH, 'r') as f:
        reader = csv.DictReader(f)
        orgs = list(reader)

    total = len(orgs)
    print(f"Found {total} organizations")
    print(f"Saving logos to: {OUTPUT_FOLDER}")
    print(f"Broken logos CSV: {BROKEN_CSV}")
    print("=" * 70)
    sys.stdout.flush()

    # Open broken CSV for writing (append as we go)
    with open(BROKEN_CSV, 'w', newline='') as broken_file:
        broken_writer = csv.writer(broken_file)
        broken_writer.writerow(['organization', 'aws_logo_url', 'error_reason'])
        broken_file.flush()

        broken_count = 0
        success_count = 0

        for i, org in enumerate(orgs):
            org_name = org.get('organization', 'Unknown')
            url = org.get('aws_logo_url', '').strip()

            if not url:
                print(f"[{i+1:4d}/{total}] ❌ NO URL        | {org_name}")
                sys.stdout.flush()
                broken_writer.writerow([org_name, '', 'NO_URL'])
                broken_file.flush()
                broken_count += 1
                continue

            filename = url.split('/')[-1]
            save_path = os.path.join(OUTPUT_FOLDER, filename)

            try:
                req = urllib.request.Request(url)
                req.add_header('User-Agent', 'Mozilla/5.0')
                resp = urllib.request.urlopen(req, timeout=15)
                data = resp.read()

                # Check if valid PNG
                if not data.startswith(PNG_HEADER):
                    print(f"[{i+1:4d}/{total}] ❌ INVALID PNG   | {org_name}")
                    sys.stdout.flush()
                    broken_writer.writerow([org_name, url, 'INVALID_PNG_HEADER'])
                    broken_file.flush()
                    broken_count += 1
                    continue

                # Check minimum size (< 500 bytes is suspicious)
                if len(data) < 500:
                    print(f"[{i+1:4d}/{total}] ❌ TOO SMALL     | {org_name} ({len(data)} bytes)")
                    sys.stdout.flush()
                    broken_writer.writerow([org_name, url, f'TOO_SMALL_{len(data)}_BYTES'])
                    broken_file.flush()
                    broken_count += 1
                    continue

                # Save the file
                with open(save_path, 'wb') as img_file:
                    img_file.write(data)

                print(f"[{i+1:4d}/{total}] ✅ OK {len(data):>8} B | {org_name}")
                sys.stdout.flush()
                success_count += 1

            except urllib.error.HTTPError as e:
                print(f"[{i+1:4d}/{total}] ❌ HTTP {e.code}      | {org_name}")
                sys.stdout.flush()
                broken_writer.writerow([org_name, url, f'HTTP_{e.code}'])
                broken_file.flush()
                broken_count += 1

            except Exception as e:
                print(f"[{i+1:4d}/{total}] ❌ ERROR         | {org_name} - {str(e)[:40]}")
                sys.stdout.flush()
                broken_writer.writerow([org_name, url, str(e)[:100]])
                broken_file.flush()
                broken_count += 1

    print("=" * 70)
    print(f"DONE!")
    print(f"✅ Success: {success_count}")
    print(f"❌ Broken:  {broken_count}")
    print(f"\nLogos saved to: {OUTPUT_FOLDER}")
    print(f"Broken list:    {BROKEN_CSV}")
    sys.stdout.flush()

if __name__ == '__main__':
    main()
