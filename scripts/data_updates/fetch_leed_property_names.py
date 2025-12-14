#!/usr/bin/env python3
"""
Fetch property names from USGBC project pages for LEED buildings missing names.
Saves results to CSV for manual review before updating portfolio_data.csv
"""

import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# Output file
OUTPUT_FILE = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/leed_property_names.csv'

def extract_name_from_url(url):
    """Extract project name from URL slug as fallback"""
    if not url or pd.isna(url):
        return None
    # Extract slug from URL like https://www.usgbc.org/projects/cbre-philadelphia-downtown
    match = re.search(r'/projects/([^/]+)/?$', str(url))
    if match:
        slug = match.group(1)
        # Convert slug to title case
        name = slug.replace('-', ' ').title()
        return name
    return None

def fetch_name_from_page(url):
    """Fetch actual project name from USGBC page"""
    if not url or pd.isna(url) or str(url).lower() in ['nan', 'none', '']:
        return None, 'no_url'

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')

            # Try to find project name in h1 or title
            h1 = soup.find('h1')
            if h1:
                name = h1.get_text(strip=True)
                if name and len(name) > 2:
                    return name, 'fetched'

            # Try title tag
            title = soup.find('title')
            if title:
                name = title.get_text(strip=True)
                # Clean up title (often has " | USGBC" suffix)
                name = re.sub(r'\s*\|\s*USGBC.*$', '', name)
                if name and len(name) > 2:
                    return name, 'fetched'

            # Fallback to URL extraction
            return extract_name_from_url(url), 'from_url'
        else:
            return extract_name_from_url(url), f'http_{response.status_code}'

    except Exception as e:
        return extract_name_from_url(url), f'error_{str(e)[:30]}'

def process_building(row_data):
    """Process a single building"""
    idx, portfolio_idx, building_id, url, address = row_data
    name, status = fetch_name_from_page(url)
    return {
        'portfolio_idx': portfolio_idx,
        'id_building': building_id,
        'leed_project_url': url,
        'loc_address': address,
        'fetched_name': name,
        'fetch_status': status
    }

def main():
    print("Loading data...")
    portfolio = pd.read_csv('/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv', low_memory=False)
    leed = pd.read_csv('/Users/forrestmiller/Desktop/nationwide-prospector/data/source/leed_matches.csv')

    # Get LEED buildings missing property name
    leed_indices = set(leed['portfolio_idx'].tolist())
    leed_buildings = portfolio[portfolio.index.isin(leed_indices)].copy()

    missing_name = leed_buildings[
        (leed_buildings['id_property_name'].isna()) |
        (leed_buildings['id_property_name'] == '') |
        (leed_buildings['id_property_name'].astype(str).str.lower() == 'nan')
    ]

    print(f"Total LEED buildings: {len(leed_buildings)}")
    print(f"Missing property name: {len(missing_name)}")

    # Get URLs for missing buildings from leed_matches
    leed_urls = dict(zip(leed['portfolio_idx'], leed['leed_project_url']))

    # Prepare data for processing
    to_process = []
    for idx, row in missing_name.iterrows():
        url = leed_urls.get(idx)
        to_process.append((
            idx,
            idx,  # portfolio_idx
            row['id_building'],
            url,
            row.get('loc_address', '')
        ))

    print(f"\nFetching names for {len(to_process)} buildings...")
    print("This may take a few minutes...\n")

    results = []
    completed = 0

    # Use thread pool for parallel fetching
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process_building, data): data for data in to_process}

        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            completed += 1

            if completed % 50 == 0:
                print(f"  Processed {completed}/{len(to_process)} ({completed*100//len(to_process)}%)")

    # Create DataFrame and save
    df = pd.DataFrame(results)

    # Sort by portfolio_idx
    df = df.sort_values('portfolio_idx')

    # Save to CSV
    df.to_csv(OUTPUT_FILE, index=False)

    print(f"\n✓ Saved {len(df)} rows to {OUTPUT_FILE}")

    # Stats
    fetched = len(df[df['fetch_status'] == 'fetched'])
    from_url = len(df[df['fetch_status'] == 'from_url'])
    failed = len(df[df['fetched_name'].isna()])

    print(f"\nResults:")
    print(f"  Fetched from page: {fetched}")
    print(f"  Extracted from URL: {from_url}")
    print(f"  Failed/No name: {failed}")

    # Show sample
    print(f"\nSample results:")
    print(df[['id_building', 'fetched_name', 'fetch_status']].head(10).to_string())

if __name__ == '__main__':
    main()
