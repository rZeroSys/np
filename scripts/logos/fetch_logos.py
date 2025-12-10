#!/usr/bin/env python3
"""
Logo Fetcher - Simple approach:
1. Ask OpenAI what the company is and best search query
2. SerpAPI image search with that query
3. Download and validate
"""

import csv
import os
import time
import base64
import requests
import pandas as pd
from openai import OpenAI

# =============================================================================
# CONFIGURATION
# =============================================================================

PORTFOLIO_ORGS_CSV = "/Users/forrestmiller/Desktop/Final real/portfolio_orgs.csv"
LOGOS_DIR = "/Users/forrestmiller/Desktop/Final real/Logos"
PROGRESS_CSV = "/Users/forrestmiller/Desktop/Final real/Logos/logo_fetch_progress.csv"

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")

MIN_LOGO_SIZE = 3000
MAX_LOGO_SIZE = 2000000
REQUEST_TIMEOUT = 15
MAX_ATTEMPTS = 8

client = OpenAI(api_key=OPENAI_KEY)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}

# =============================================================================
# FUNCTIONS
# =============================================================================

def to_logo_filename(company_name):
    return f"{company_name.strip().replace(' ', '_')}.png"

def save_progress(org_name, status, source='', attempts=0, error=''):
    file_exists = os.path.exists(PROGRESS_CSV)
    with open(PROGRESS_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['org_name', 'status', 'source', 'attempts', 'error'])
        writer.writerow([org_name, status, source, attempts, error])

def get_portfolio_orgs_without_logos():
    df = pd.read_csv(PORTFOLIO_ORGS_CSV)
    no_logo = df[df['logo_file'].isna() | (df['logo_file'] == '')]
    return no_logo.sort_values('total_count', ascending=False)['organization_name'].tolist()

def ask_openai_for_search_query(org_name):
    """Ask OpenAI what search query to use to find this company's logo."""
    prompt = f"""I need to find the official logo for: "{org_name}"

This is a company/organization that owns, manages, or occupies commercial real estate buildings.

Tell me:
1. What is this company? (1 sentence)
2. What is their official/full company name?
3. What Google Image search query should I use to find their official logo?

Respond in this exact format:
DESCRIPTION: [what the company is]
FULL_NAME: [official company name]
SEARCH: [the search query to use]"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200
        )
        text = response.choices[0].message.content.strip()

        # Parse response
        lines = text.split('\n')
        search_query = None
        full_name = None
        description = None

        for line in lines:
            if line.startswith('SEARCH:'):
                search_query = line.replace('SEARCH:', '').strip()
            elif line.startswith('FULL_NAME:'):
                full_name = line.replace('FULL_NAME:', '').strip()
            elif line.startswith('DESCRIPTION:'):
                description = line.replace('DESCRIPTION:', '').strip()

        return search_query, full_name, description
    except Exception as e:
        print(f"    OpenAI error: {e}")
        return None, None, None

def search_and_download_logo(search_query):
    """Use SerpAPI to search for logo images and download them."""
    params = {
        'engine': 'google_images',
        'q': search_query,
        'api_key': SERPAPI_KEY,
        'num': 20,
        'safe': 'active'
    }

    try:
        resp = requests.get('https://serpapi.com/search', params=params, timeout=REQUEST_TIMEOUT)
        data = resp.json()
        results = data.get('images_results', [])

        candidates = []
        for r in results:
            url = r.get('original', '')
            source = r.get('source', '')
            title = r.get('title', '')

            if not url:
                continue

            # Skip obviously bad sources
            bad_sources = ['getty', 'shutterstock', 'istock', 'alamy', 'dreamstime']
            if any(bad in source.lower() for bad in bad_sources):
                continue

            # Try to download
            try:
                img_resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=HEADERS)
                if img_resp.status_code == 200:
                    content = img_resp.content
                    content_type = img_resp.headers.get('Content-Type', '')

                    # Check it's an image
                    if 'image' in content_type or url.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
                        if MIN_LOGO_SIZE <= len(content) <= MAX_LOGO_SIZE:
                            candidates.append({
                                'bytes': content,
                                'source': source,
                                'url': url,
                                'title': title
                            })

                            if len(candidates) >= MAX_ATTEMPTS:
                                break
            except:
                continue

        return candidates
    except Exception as e:
        print(f"    SerpAPI error: {e}")
        return []

def validate_logo(image_bytes, org_name, full_name=None):
    """Use OpenAI Vision to validate logo."""
    b64_image = base64.standard_b64encode(image_bytes).decode('utf-8')

    check_name = full_name or org_name

    prompt = f"""Is this the official LOGO for "{check_name}"?

Rules:
- Must be a LOGO (graphic/vector design), NOT a photo, screenshot, or building image
- Must be for this specific company (name/brand visible or clearly matches)
- Reject if it's a different company's logo
- Reject if it's low quality or has watermarks

Answer ONLY: GOOD or BAD"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}", "detail": "low"}}
                ]
            }],
            max_tokens=10
        )
        result = response.choices[0].message.content.strip().upper()
        return "GOOD" in result
    except Exception as e:
        print(f"    Validation error: {e}")
        return False

def process_org(org_name, index, total):
    """Process a single organization."""
    print(f"\n{'='*60}")
    print(f"[{index}/{total}] {org_name}")
    print(f"{'='*60}")

    # Step 1: Ask OpenAI what to search for
    print(f"  🤖 Asking OpenAI about this company...")
    search_query, full_name, description = ask_openai_for_search_query(org_name)

    if not search_query:
        print(f"  ❌ OpenAI couldn't identify company")
        save_progress(org_name, 'FAILED', '', 0, 'OpenAI failed to identify')
        return False

    print(f"  📝 {description}")
    print(f"  🔍 Search: {search_query}")

    # Step 2: Search and download candidates
    print(f"  🌐 Searching SerpAPI...")
    candidates = search_and_download_logo(search_query)

    if not candidates:
        print(f"  ❌ No logo candidates found")
        save_progress(org_name, 'FAILED', '', 0, 'No candidates')
        return False

    print(f"  ✓ Found {len(candidates)} candidates")

    # Step 3: Validate each candidate
    for i, cand in enumerate(candidates, 1):
        source = cand['source'][:30]
        size = len(cand['bytes'])
        print(f"\n  [{i}/{len(candidates)}] {source}... ({size:,} bytes)")
        print(f"  🤖 Validating...", end=' ', flush=True)

        if validate_logo(cand['bytes'], org_name, full_name):
            print("✅ APPROVED!")

            filename = to_logo_filename(org_name)
            filepath = os.path.join(LOGOS_DIR, filename)
            with open(filepath, 'wb') as f:
                f.write(cand['bytes'])

            print(f"  💾 Saved: {filename}")
            save_progress(org_name, 'SUCCESS', cand['source'], i)
            return True
        else:
            print("❌ REJECTED")

    print(f"\n  ❌ All {len(candidates)} candidates failed")
    save_progress(org_name, 'FAILED', '', len(candidates), 'All failed validation')
    return False

def main():
    print("=" * 60)
    print("🖼️  LOGO FETCHER")
    print("=" * 60)

    os.makedirs(LOGOS_DIR, exist_ok=True)

    orgs = get_portfolio_orgs_without_logos()
    total = len(orgs)
    print(f"\n🎯 {total} orgs need logos\n")

    if total == 0:
        print("✅ All done!")
        return

    for i, org in enumerate(orgs[:10], 1):
        print(f"   {i}. {org}")
    if total > 10:
        print(f"   ... and {total-10} more")

    print("\n" + "=" * 60)

    success = fail = 0
    start = time.time()

    for i, org in enumerate(orgs, 1):
        try:
            if process_org(org, i, total):
                success += 1
            else:
                fail += 1
        except KeyboardInterrupt:
            print("\n\n⚠️ STOPPED")
            break
        except Exception as e:
            print(f"  ❌ Error: {e}")
            fail += 1

        if i % 10 == 0:
            elapsed = time.time() - start
            print(f"\n{'='*60}")
            print(f"📊 {i}/{total} | ✅ {success} | ❌ {fail} | {i/elapsed*60:.0f}/hr")
            print(f"{'='*60}")

    print(f"\n🏁 Done: ✅ {success} | ❌ {fail}")

if __name__ == "__main__":
    main()
