#!/usr/bin/env python3
"""
Fix dead/parked URLs found by check_dead_urls.py
Reads dead_urls.csv, searches for correct URLs, saves recommendations.
DOES NOT modify source files - outputs to Desktop for review.
"""

import csv
import asyncio
import aiohttp
import time
import os
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime

# ============ CONFIG ============
DEAD_URLS_CSV = Path(__file__).parent.parent / "data/source/dead_urls.csv"

# Output to Desktop, NOT project directory
OUTPUT_DIR = Path.home() / "Desktop"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
PROGRESS_CSV = OUTPUT_DIR / f"url_fix_progress_{TIMESTAMP}.csv"
FINAL_CSV = OUTPUT_DIR / f"url_fix_recommendations_{TIMESTAMP}.csv"

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
TIMEOUT = 10

# Only match REAL parked domain indicators (not generic text)
PARKED_PATTERNS = [
    'sedoparking', 'parking-lander', 'godaddy.com/forsale', 'dan.com',
    'afternic', 'hugedomains', 'buy this domain', 'domain is for sale',
    'this domain is for sale', 'domain for sale', 'domainmarket',
]

# ============ SEARCH ============
async def search_correct_url(session, org_name, old_url, semaphore):
    """Use SerpAPI to find correct official website. Skips old dead domain."""
    async with semaphore:
        # Get old domain to skip
        old_domain = urlparse(old_url).netloc.lower().replace('www.', '')

        query = f"{org_name} official website"
        url = f"https://serpapi.com/search.json?q={query}&api_key={SERPAPI_KEY}&num=10"

        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return None, f"HTTP {resp.status}"

                data = await resp.json()
                results = data.get('organic_results', [])

                if not results:
                    return None, "No results"

                # Skip social/directories AND the old dead domain
                skip_domains = ['facebook.com', 'linkedin.com', 'twitter.com', 'instagram.com',
                                'youtube.com', 'yelp.com', 'wikipedia.org', 'bloomberg.com',
                                'crunchbase.com', 'zoominfo.com', 'glassdoor.com', 'indeed.com',
                                'yellowpages.com', 'bbb.org', 'mapquest.com', old_domain]

                candidates = []
                for r in results[:10]:
                    link = r.get('link', '')
                    if not link:
                        continue

                    parsed = urlparse(link)
                    domain = parsed.netloc.lower().replace('www.', '')

                    if any(skip in domain for skip in skip_domains):
                        continue

                    # Score by org name in domain
                    score = 0
                    for word in org_name.lower().split():
                        if len(word) > 3 and word in domain:
                            score += 10

                    if r == results[0]:
                        score += 3

                    homepage = f"{parsed.scheme}://{parsed.netloc}"
                    candidates.append((homepage, score, domain))

                if not candidates:
                    return None, f"No alternatives (only found {old_domain})"

                candidates.sort(key=lambda x: -x[1])
                return candidates[0][0], None

        except Exception as e:
            return None, str(e)[:30]

# ============ VALIDATE ============
async def validate_url(session, url, semaphore):
    """Check new URL is actually good."""
    async with semaphore:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT),
                                   allow_redirects=True, ssl=False) as resp:
                if resp.status >= 400:
                    return False, f"HTTP {resp.status}"

                text = await resp.text()
                text_lower = text.lower()
                for pattern in PARKED_PATTERNS:
                    if pattern in text_lower:
                        return False, f"Matched: {pattern}"
                return True, "OK"
        except Exception as e:
            return False, str(e)[:30]

# ============ MAIN ============
async def main():
    print("=" * 80)
    print("FIX DEAD URLs")
    print("=" * 80)
    print(f"Reading:  {DEAD_URLS_CSV}")
    print(f"Progress: {PROGRESS_CSV}")
    print(f"Final:    {FINAL_CSV}")
    print("=" * 80)

    # Load dead URLs
    print(f"\n[1/3] Loading dead URLs...")
    if not DEAD_URLS_CSV.exists():
        print(f"\n\033[91mERROR: {DEAD_URLS_CSV} not found!")
        print("Run check_dead_urls.py first!\033[0m")
        return

    dead_urls = []
    with open(DEAD_URLS_CSV, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Filter to only REAL dead URLs (not false positives like Costco)
            status = row.get('status', '')
            match = row.get('match', '').lower()
            issue = row.get('issue', '').lower()

            is_real_dead = (
                status == 'DEAD' or
                status == 'TIMEOUT' or
                status == 'ERROR' or
                any(p in match for p in PARKED_PATTERNS) or
                any(p in issue for p in PARKED_PATTERNS)
            )

            if is_real_dead:
                dead_urls.append(row)

    print(f"      Found {len(dead_urls)} genuinely dead/parked URLs (filtered false positives)")

    if not dead_urls:
        print("\n[DONE] No dead URLs to fix!")
        return

    # Open progress CSV
    progress_file = open(PROGRESS_CSV, 'w', newline='')
    progress_writer = csv.DictWriter(progress_file,
        fieldnames=['organization', 'old_url', 'status', 'new_url', 'validated', 'validation_reason'])
    progress_writer.writeheader()
    progress_file.flush()

    # Search for replacements
    print(f"\n[2/3] Searching for correct URLs via SerpAPI...")
    print("-" * 80)
    start = time.time()

    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(
        connector=connector,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    ) as session:

        search_sem = asyncio.Semaphore(5)  # Rate limit SerpAPI
        validate_sem = asyncio.Semaphore(30)

        results = []
        for i, dead in enumerate(dead_urls):
            org = dead['organization']
            old_url = dead['url']
            old_status = dead.get('status', '')

            print(f"\n[{i+1}/{len(dead_urls)}] {org}")
            print(f"      Old URL: {old_url} ({old_status})")

            # Search (pass old_url so we skip the dead domain)
            new_url, err = await search_correct_url(session, org, old_url, search_sem)

            result = {
                'organization': org,
                'old_url': old_url,
                'status': old_status,
                'new_url': '',
                'validated': False,
                'validation_reason': ''
            }

            if new_url:
                print(f"      Found:   {new_url}")

                # Validate
                is_valid, reason = await validate_url(session, new_url, validate_sem)
                result['new_url'] = new_url
                result['validated'] = is_valid
                result['validation_reason'] = reason

                if is_valid:
                    print(f"      \033[92m✓ VALID\033[0m")
                else:
                    print(f"      \033[91m✗ INVALID: {reason}\033[0m")
            else:
                print(f"      \033[93m? No replacement found: {err}\033[0m")
                result['validation_reason'] = err or 'No replacement found'

            results.append(result)

            # Save progress immediately
            progress_writer.writerow(result)
            progress_file.flush()

            await asyncio.sleep(0.3)  # Be nice to SerpAPI

    progress_file.close()

    # Write final recommendations
    print(f"\n[3/3] Writing final recommendations...")
    with open(FINAL_CSV, 'w', newline='') as f:
        writer = csv.DictWriter(f,
            fieldnames=['organization', 'old_url', 'new_url', 'validated', 'action'])
        writer.writeheader()
        for r in results:
            action = 'REPLACE' if r['validated'] else ('MANUAL_CHECK' if r['new_url'] else 'NEEDS_RESEARCH')
            writer.writerow({
                'organization': r['organization'],
                'old_url': r['old_url'],
                'new_url': r['new_url'],
                'validated': r['validated'],
                'action': action
            })

    # Summary
    elapsed = time.time() - start
    valid = [r for r in results if r['validated']]
    found = [r for r in results if r['new_url']]

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Time:               {elapsed:.1f}s")
    print(f"Dead URLs:          {len(dead_urls)}")
    print(f"Replacements found: {len(found)}")
    print(f"Validated:          {len(valid)}")
    print(f"Needs research:     {len(dead_urls) - len(found)}")
    print()
    print(f"Progress saved to:  {PROGRESS_CSV}")
    print(f"Final saved to:     {FINAL_CSV}")
    print()
    print("\033[93mREVIEW THE CSV BEFORE APPLYING CHANGES!\033[0m")

if __name__ == '__main__':
    asyncio.run(main())
