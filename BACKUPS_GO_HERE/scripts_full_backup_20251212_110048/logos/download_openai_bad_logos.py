#!/usr/bin/env python3
"""
Download correct logos for ones OpenAI flagged as bad.
Reads from bad_logos.csv, saves with exact same filename.
"""

import os
import csv
import requests
import time

OUTPUT_DIR = "/Users/forrestmiller/Desktop/new logos"
BAD_LOGOS_CSV = "/Users/forrestmiller/Desktop/new logos/bad_logos.csv"

# Map company names to domains
DOMAIN_MAP = {
    "24 Hour Fitness": "24hourfitness.com",
    "99 Ranch Market": "99ranch.com",
    "AT T": "att.com",
    "Academy Of Art University": "academyart.edu",
    "Adobe": "adobe.com",
    "Aerotek": "aerotek.com",
    "Afscme": "afscme.org",
    "Ahold Delhaize": "aholddelhaize.com",
    "Allstate": "allstate.com",
    "Altera Corp": "altera.com",
    "American National Red Cross": "redcross.org",
    "Applied Materials": "appliedmaterials.com",
    "Ashley HomeStore": "ashleyfurniture.com",
    "BJ s Wholesale Club": "bjs.com",
    "Bank of America": "bankofamerica.com",
    "Berklee College Of Music": "berklee.edu",
    "Beth Israel Deaconess Medical Center": "bidmc.org",
    "Boston Children s Hospital": "childrenshospital.org",
    "Boys Girls Clubs of America": "bgca.org",
    "Budget Car Rental": "budget.com",
    "Burger King": "burgerking.com",
    "Burlington Stores": "burlington.com",
    "CalSTRS": "calstrs.com",
    "California Department of Motor Vehicles DMV": "dmv.ca.gov",
    "California State University": "calstate.edu",
    # Add more as needed - script will try to guess domain if not found
}

def guess_domain(company_name):
    """Try to guess domain from company name."""
    # Clean up name
    name = company_name.lower()
    name = name.replace(" ", "").replace("_", "").replace("-", "")
    name = name.replace("'", "").replace(".", "")

    # Common suffixes to try
    suffixes = [".com", ".org", ".edu", ".net", ".gov"]

    # Return first guess
    return name[:20] + ".com"

def download_logo(domain, output_path):
    """Try multiple sources to download logo."""
    sources = [
        f"https://unavatar.io/{domain}?fallback=false",
        f"https://logo.clearbit.com/{domain}",
        f"https://www.google.com/s2/favicons?domain={domain}&sz=256",
    ]

    for url in sources:
        try:
            r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200 and len(r.content) > 1000:
                with open(output_path, 'wb') as f:
                    f.write(r.content)
                return True, len(r.content)
        except:
            pass
    return False, 0

def main():
    print("=" * 70)
    print("DOWNLOAD CORRECT LOGOS FOR OPENAI BAD LIST")
    print("=" * 70)

    if not os.path.exists(BAD_LOGOS_CSV):
        print(f"ERROR: {BAD_LOGOS_CSV} not found!")
        return

    # Read bad logos
    bad_logos = []
    with open(BAD_LOGOS_CSV, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            bad_logos.append({
                'filename': row['filename'],
                'company': row['company'],
                'issue': row.get('issue', '')
            })

    print(f"\nBad logos to fix: {len(bad_logos)}")
    print(f"Output: {OUTPUT_DIR}\n")

    success = 0
    failed = []

    for item in bad_logos:
        filename = item['filename']
        company = item['company']

        # Skip if already downloaded
        output_path = os.path.join(OUTPUT_DIR, filename)
        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            if size > 5000:  # Already have a decent file
                print(f"[SKIP] {filename} - already exists ({size:,} bytes)")
                success += 1
                continue

        # Get domain
        domain = DOMAIN_MAP.get(company, guess_domain(company))

        print(f"[{filename}]")
        print(f"    Company: {company}")
        print(f"    Domain: {domain}")

        ok, size = download_logo(domain, output_path)

        if ok:
            print(f"    ✅ Downloaded ({size:,} bytes)")
            success += 1
        else:
            print(f"    ❌ FAILED")
            failed.append(filename)

        time.sleep(0.3)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"✅ Success: {success}/{len(bad_logos)}")

    if failed:
        print(f"\n❌ Failed ({len(failed)}):")
        for f in failed:
            print(f"   - {f}")

if __name__ == "__main__":
    main()
