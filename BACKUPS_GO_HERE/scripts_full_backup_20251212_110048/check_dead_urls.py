#!/usr/bin/env python3
"""
Check portfolio organization URLs for dead/parked/for-sale domains.
Massively parallel, verbose output, saves results as it goes.
"""

import csv
import asyncio
import aiohttp
import time
import sys
from pathlib import Path
from datetime import datetime

# Config
INPUT_CSV = Path(__file__).parent.parent / "data/source/portfolio_organizations.csv"
OUTPUT_CSV = Path(__file__).parent.parent / "data/source/dead_urls.csv"
MAX_CONCURRENT = 100  # High parallelism
TIMEOUT = 10  # seconds per request

# Patterns indicating domain for sale / parked
SALE_PATTERNS = [
    'domain for sale', 'buy this domain', 'domain is for sale',
    'this domain is for sale', 'purchase this domain', 'domain may be for sale',
    'acquire this domain', 'make an offer', 'domain available',
    'parked free', 'parked domain', 'sedoparking', 'parking-lander',
    'godaddy', 'dan.com', 'afternic', 'sedo.com', 'hugedomains',
    'undeveloped.com', 'domainmarket', 'brandbucket', 'squadhelp',
    'is for sale', 'for sale at', 'domain has expired', 'expired domain',
    'this site is under construction', 'coming soon', 'website coming soon',
    'page not found', 'this page is parked', 'parked by',
    'buy now for', 'domain broker', 'premium domain',
]

# HTTP errors that indicate dead domain
DEAD_STATUSES = [404, 410, 502, 503, 504, 521, 522, 523, 524]

results_lock = asyncio.Lock()
checked = 0
total = 0
start_time = None

async def write_result(writer, row):
    """Write result to CSV file (thread-safe)."""
    async with results_lock:
        writer.writerow(row)

async def check_url(session, org, url, writer, semaphore):
    """Check a single URL for sale/parked status."""
    global checked

    async with semaphore:
        result = {
            'organization': org,
            'url': url,
            'status': 'OK',
            'status_code': None,
            'issue': None,
            'match': None
        }

        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT),
                                   allow_redirects=True, ssl=False) as resp:
                result['status_code'] = resp.status

                # Check for dead status codes
                if resp.status in DEAD_STATUSES:
                    result['status'] = 'DEAD'
                    result['issue'] = f'HTTP {resp.status}'
                else:
                    # Check page content for sale patterns
                    try:
                        text = await resp.text()
                        text_lower = text.lower()

                        for pattern in SALE_PATTERNS:
                            if pattern in text_lower:
                                result['status'] = 'FOR_SALE'
                                result['issue'] = 'Domain appears parked/for sale'
                                result['match'] = pattern
                                break
                    except:
                        pass  # Can't read body, assume OK

        except asyncio.TimeoutError:
            result['status'] = 'TIMEOUT'
            result['issue'] = f'Timeout after {TIMEOUT}s'
        except aiohttp.ClientConnectorError as e:
            result['status'] = 'DEAD'
            result['issue'] = f'Connection failed: {str(e)[:50]}'
        except aiohttp.ClientError as e:
            result['status'] = 'ERROR'
            result['issue'] = f'Client error: {str(e)[:50]}'
        except Exception as e:
            result['status'] = 'ERROR'
            result['issue'] = f'Error: {str(e)[:50]}'

        checked += 1
        elapsed = time.time() - start_time
        rate = checked / elapsed if elapsed > 0 else 0
        eta = (total - checked) / rate if rate > 0 else 0

        # Verbose output
        status_icon = {
            'OK': '\033[92m✓\033[0m',
            'FOR_SALE': '\033[91m$\033[0m',
            'DEAD': '\033[91m✗\033[0m',
            'TIMEOUT': '\033[93m⏱\033[0m',
            'ERROR': '\033[93m!\033[0m'
        }.get(result['status'], '?')

        print(f"[{checked:4d}/{total}] {status_icon} {org[:40]:<40} | {result['status']:<8} | ETA: {eta:.0f}s")

        if result['status'] != 'OK':
            print(f"           └─ {url}")
            if result['issue']:
                print(f"           └─ {result['issue']}")
            if result['match']:
                print(f"           └─ Matched: '{result['match']}'")

        # Write bad results immediately
        if result['status'] != 'OK':
            await write_result(writer, result)

        return result

async def main():
    global total, start_time

    # Load URLs
    print(f"Loading URLs from {INPUT_CSV}...")
    urls_to_check = []
    with open(INPUT_CSV, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = (row.get('org_url') or '').strip()
            if url:
                urls_to_check.append((row['organization'], url))

    total = len(urls_to_check)
    print(f"Found {total} URLs to check")
    print(f"Max concurrent: {MAX_CONCURRENT}")
    print(f"Timeout: {TIMEOUT}s per request")
    print(f"Output: {OUTPUT_CSV}")
    print("=" * 80)

    # Open output CSV
    with open(OUTPUT_CSV, 'w', newline='') as outfile:
        fieldnames = ['organization', 'url', 'status', 'status_code', 'issue', 'match']
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        # Create async CSV writer wrapper
        class AsyncWriter:
            def __init__(self, writer, file):
                self.writer = writer
                self.file = file
            def writerow(self, row):
                self.writer.writerow(row)
                self.file.flush()  # Flush immediately

        async_writer = AsyncWriter(writer, outfile)

        # Run checks
        start_time = time.time()
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, limit_per_host=5)
        async with aiohttp.ClientSession(connector=connector,
                                         headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}) as session:
            tasks = [check_url(session, org, url, async_writer, semaphore)
                     for org, url in urls_to_check]
            results = await asyncio.gather(*tasks)

    # Summary
    elapsed = time.time() - start_time
    print("=" * 80)
    print(f"DONE in {elapsed:.1f}s ({total/elapsed:.1f} URLs/sec)")

    bad = [r for r in results if r['status'] != 'OK']
    for_sale = [r for r in results if r['status'] == 'FOR_SALE']
    dead = [r for r in results if r['status'] == 'DEAD']
    timeout = [r for r in results if r['status'] == 'TIMEOUT']
    errors = [r for r in results if r['status'] == 'ERROR']

    print(f"\nResults:")
    print(f"  OK:       {len(results) - len(bad)}")
    print(f"  FOR_SALE: {len(for_sale)}")
    print(f"  DEAD:     {len(dead)}")
    print(f"  TIMEOUT:  {len(timeout)}")
    print(f"  ERROR:    {len(errors)}")
    print(f"\nBad URLs saved to: {OUTPUT_CSV}")

if __name__ == '__main__':
    asyncio.run(main())
