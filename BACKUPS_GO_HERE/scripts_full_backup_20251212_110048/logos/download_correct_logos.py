#!/usr/bin/env python3
"""
Download correct logos using Logo APIs.
"""

import os
import requests
import time

OUTPUT_DIR = "/Users/forrestmiller/Desktop/new logos"

# Bad logos with their domains for API lookup
BAD_LOGOS = {
    "Hilton.png": "hilton.com",
    "Adobe.png": "adobe.com",
    "Allstate.png": "allstate.com",
    "Bank_of_America.png": "bankofamerica.com",
    "Ascension_Health.png": "ascension.org",
    "Google.png": "google.com",
    "Microsoft.png": "microsoft.com",
    "Kaiser_Permanente.png": "kaiserpermanente.org",
    "Walmart.png": "walmart.com",
    "Wyndham.png": "wyndhamhotels.com",
    "Prologis.png": "prologis.com",
    "Hines.png": "hines.com",
    "Deloitte.png": "deloitte.com",
    "KPMG.png": "kpmg.com",
    "Accenture.png": "accenture.com",
    "Intel.png": "intel.com",
    "VMware.png": "vmware.com",
    "Cushman_Wakefield.png": "cushmanwakefield.com",
    "T_Mobile.png": "t-mobile.com",
    "Kroger.png": "kroger.com",
    "Walgreens.png": "walgreens.com",
    "JCPenney.png": "jcpenney.com",
}

def download_from_clearbit(domain, output_path):
    """Clearbit - 128x128 but reliable."""
    url = f"https://logo.clearbit.com/{domain}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and len(r.content) > 1000:
            with open(output_path, 'wb') as f:
                f.write(r.content)
            return True, "clearbit"
    except:
        pass
    return False, None

def download_from_logo_dev(domain, output_path):
    """Logo.dev - higher quality, needs token for best results."""
    # Public endpoint (no token needed for basic)
    url = f"https://img.logo.dev/{domain}?format=png"
    try:
        r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code == 200 and len(r.content) > 1000:
            with open(output_path, 'wb') as f:
                f.write(r.content)
            return True, "logo.dev"
    except:
        pass
    return False, None

def download_from_brandfetch(domain, output_path):
    """Brandfetch - try public CDN."""
    # Try common CDN patterns
    urls = [
        f"https://asset.brandfetch.io/id{domain}/logo.png",
        f"https://cdn.brandfetch.io/{domain}/logo",
    ]
    for url in urls:
        try:
            r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200 and len(r.content) > 1000:
                with open(output_path, 'wb') as f:
                    f.write(r.content)
                return True, "brandfetch"
        except:
            pass
    return False, None

def download_from_google_favicon(domain, output_path):
    """Google's high-res favicon service."""
    url = f"https://www.google.com/s2/favicons?domain={domain}&sz=256"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200 and len(r.content) > 1000:
            with open(output_path, 'wb') as f:
                f.write(r.content)
            return True, "google-favicon"
    except:
        pass
    return False, None

def download_from_unavatar(domain, output_path):
    """Unavatar - aggregates multiple sources."""
    url = f"https://unavatar.io/{domain}?fallback=false"
    try:
        r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code == 200 and len(r.content) > 1000:
            with open(output_path, 'wb') as f:
                f.write(r.content)
            return True, "unavatar"
    except:
        pass
    return False, None

def main():
    print("=" * 70)
    print("DOWNLOAD CORRECT LOGOS")
    print("=" * 70)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"\nOutput: {OUTPUT_DIR}")
    print(f"Logos to download: {len(BAD_LOGOS)}")
    print()

    success = 0
    failed = []

    for filename, domain in BAD_LOGOS.items():
        output_path = os.path.join(OUTPUT_DIR, filename)
        print(f"[{filename}] -> {domain}")

        # Try each source in order of quality
        sources = [
            ("Logo.dev", download_from_logo_dev),
            ("Unavatar", download_from_unavatar),
            ("Clearbit", download_from_clearbit),
            ("Google Favicon", download_from_google_favicon),
        ]

        downloaded = False
        for source_name, download_func in sources:
            ok, source = download_func(domain, output_path)
            if ok:
                size = os.path.getsize(output_path)
                print(f"    ✅ Downloaded from {source_name} ({size:,} bytes)")
                success += 1
                downloaded = True
                break
            else:
                print(f"    ❌ {source_name} failed")

        if not downloaded:
            print(f"    ⚠️  ALL SOURCES FAILED")
            failed.append(filename)

        time.sleep(0.5)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"✅ Downloaded: {success}/{len(BAD_LOGOS)}")

    if failed:
        print(f"\n❌ Failed ({len(failed)}):")
        for f in failed:
            print(f"   - {f}")

    print(f"\nLogos saved to: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
