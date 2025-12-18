#!/usr/bin/env python3
"""
LEED Building Matcher
- Groups by normalized 5-digit ZIP
- Uses Google Distance Matrix API to find same buildings
- Saves progress every 50 ZIPs to Desktop
"""

import pandas as pd
import requests
import time
import re
import os
from datetime import datetime

# =============================================================================
# CONFIG
# =============================================================================
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
DISTANCE_THRESHOLD = 20  # meters - same building if < 20m
SAVE_EVERY = 50  # ZIPs

PORTFOLIO_PATH = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv'
LEED_PATH = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/leed_certified_buildings.csv'
OUTPUT_PATH = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/leed_matches.csv'
PROGRESS_PATH = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/leed_progress.csv'

# =============================================================================
# HELPERS
# =============================================================================
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def normalize_zip(z):
    """Normalize to exactly 5 digits"""
    if pd.isna(z):
        return None
    z = str(z).strip()
    z = re.sub(r'-\d{4}$', '', z)  # Remove +4
    z = re.sub(r'[^\d]', '', z)     # Only digits
    if len(z) == 0:
        return None
    if len(z) < 5:
        z = z.zfill(5)
    elif len(z) > 5:
        z = z[:5]
    return z

def get_distances(origins, destinations):
    """Call Distance Matrix API. Returns list of lists of distances in meters."""
    url = 'https://maps.googleapis.com/maps/api/distancematrix/json'
    params = {
        'origins': '|'.join(origins),
        'destinations': '|'.join(destinations),
        'key': GOOGLE_API_KEY,
        'mode': 'walking'
    }

    resp = requests.get(url, params=params, timeout=30)
    data = resp.json()

    if data['status'] != 'OK':
        log(f"  API ERROR: {data['status']} - {data.get('error_message', '')}")
        return None

    distances = []
    for row in data['rows']:
        row_dist = []
        for elem in row['elements']:
            if elem['status'] == 'OK':
                row_dist.append(elem['distance']['value'])
            else:
                row_dist.append(-1)
        distances.append(row_dist)
    return distances

def convert_timestamp(ts):
    """Convert unix timestamp to date string"""
    if pd.isna(ts):
        return None
    try:
        return datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d')
    except:
        return None

# =============================================================================
# MAIN
# =============================================================================
def main():
    log("=" * 60)
    log("LEED BUILDING MATCHER")
    log("=" * 60)

    # Load data
    log("Loading portfolio...")
    portfolio = pd.read_csv(PORTFOLIO_PATH, low_memory=False)
    log(f"  {len(portfolio)} buildings")

    log("Loading LEED...")
    leed = pd.read_csv(LEED_PATH)
    log(f"  {len(leed)} buildings")

    # Normalize ZIPs
    log("Normalizing ZIPs...")
    portfolio['zip_norm'] = portfolio['loc_zip'].apply(normalize_zip)
    leed['zip_norm'] = leed['geo_postal_code'].apply(normalize_zip)

    p_valid = portfolio['zip_norm'].notna().sum()
    l_valid = leed['zip_norm'].notna().sum()
    log(f"  Portfolio valid ZIPs: {p_valid}")
    log(f"  LEED valid ZIPs: {l_valid}")

    # Find shared ZIPs
    shared_zips = sorted(set(portfolio['zip_norm'].dropna()) & set(leed['zip_norm'].dropna()))
    log(f"  Shared ZIPs: {len(shared_zips)}")

    # Check for existing progress
    matches = []
    matched_portfolio_idx = set()
    matched_leed_idx = set()
    start_zip_idx = 0

    try:
        progress = pd.read_csv(PROGRESS_PATH)
        matches = progress.to_dict('records')
        matched_portfolio_idx = set(progress['portfolio_idx'].tolist())
        matched_leed_idx = set(progress['leed_idx'].tolist())
        start_zip_idx = int(progress['zip_idx'].max()) + 1
        log(f"RESUMING from ZIP #{start_zip_idx} with {len(matches)} existing matches")
    except:
        log("Starting fresh (no progress file)")

    api_calls = 0

    # Process each ZIP
    log("")
    log("=" * 60)
    log("PROCESSING ZIPS")
    log("=" * 60)

    for zip_idx, zip_code in enumerate(shared_zips):
        if zip_idx < start_zip_idx:
            continue

        # Get buildings in this ZIP
        p_in_zip = portfolio[(portfolio['zip_norm'] == zip_code) & (~portfolio.index.isin(matched_portfolio_idx))]
        l_in_zip = leed[(leed['zip_norm'] == zip_code) & (~leed.index.isin(matched_leed_idx))]

        if len(p_in_zip) == 0 or len(l_in_zip) == 0:
            log(f"ZIP {zip_code} [{zip_idx+1}/{len(shared_zips)}]: SKIP (0 candidates)")
            continue

        log(f"ZIP {zip_code} [{zip_idx+1}/{len(shared_zips)}]: {len(p_in_zip)} portfolio x {len(l_in_zip)} LEED")

        # Build address lists
        p_data = [(idx, row['loc_address']) for idx, row in p_in_zip.iterrows()]
        l_data = [(idx, f"{row['address_line1']}, {row['city']}, {row['geo_state_abbrv']} {row['geo_postal_code']}")
                  for idx, row in l_in_zip.iterrows()]

        # Process in 10x10 batches (API limit: 100 elements)
        for p_start in range(0, len(p_data), 10):
            p_batch = p_data[p_start:p_start+10]

            for l_start in range(0, len(l_data), 10):
                l_batch = l_data[l_start:l_start+10]

                # Filter out already matched
                p_batch = [(i, a) for i, a in p_batch if i not in matched_portfolio_idx]
                l_batch = [(i, a) for i, a in l_batch if i not in matched_leed_idx]

                if not p_batch or not l_batch:
                    continue

                p_origins = [a for _, a in p_batch]
                l_dests = [a for _, a in l_batch]

                log(f"  API call: {len(p_origins)} origins x {len(l_dests)} destinations")

                distances = get_distances(p_origins, l_dests)
                api_calls += 1

                if distances is None:
                    log(f"  FAILED - skipping batch")
                    time.sleep(2)
                    continue

                # Find matches
                for p_i, (p_idx, p_addr) in enumerate(p_batch):
                    if p_idx in matched_portfolio_idx:
                        continue

                    for l_i, (l_idx, l_addr) in enumerate(l_batch):
                        if l_idx in matched_leed_idx:
                            continue

                        dist = distances[p_i][l_i]

                        if 0 <= dist < DISTANCE_THRESHOLD:
                            leed_row = leed.loc[l_idx]

                            match = {
                                'zip_idx': zip_idx,
                                'portfolio_idx': p_idx,
                                'leed_idx': l_idx,
                                'portfolio_address': p_addr,
                                'leed_address': l_addr,
                                'distance_m': dist,
                                'leed_certification_level': leed_row['certification_level'],
                                'leed_certification_date': convert_timestamp(leed_row['certification_date']),
                                'leed_rating_system': leed_row['rating_system'],
                                'leed_project_url': f"https://www.usgbc.org{leed_row['url']}" if pd.notna(leed_row['url']) else None,
                                'leed_project_id': leed_row['prjt_id']
                            }
                            matches.append(match)
                            matched_portfolio_idx.add(p_idx)
                            matched_leed_idx.add(l_idx)

                            log(f"  MATCH! {dist}m: {p_addr[:40]}... = {leed_row['certification_level']}")
                            break

                time.sleep(0.1)

        # Save progress
        if (zip_idx + 1) % SAVE_EVERY == 0:
            log(f"SAVING PROGRESS: {len(matches)} matches after {zip_idx+1} ZIPs")
            pd.DataFrame(matches).to_csv(PROGRESS_PATH, index=False)

    # Final save
    log("")
    log("=" * 60)
    log("COMPLETE")
    log("=" * 60)
    log(f"Total matches: {len(matches)}")
    log(f"API calls: {api_calls}")

    if matches:
        df = pd.DataFrame(matches)
        df.to_csv(OUTPUT_PATH, index=False)
        df.to_csv(PROGRESS_PATH, index=False)
        log(f"Saved to: {OUTPUT_PATH}")

        log("")
        log("By certification level:")
        print(df['leed_certification_level'].value_counts())

if __name__ == '__main__':
    main()
