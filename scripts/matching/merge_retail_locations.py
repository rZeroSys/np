#!/usr/bin/env python3
"""
Merge retail location CSVs from multiple sources with deduplication.
"""

import csv
import os
from datetime import datetime

# Source files
KAGGLE_FILE = "/Users/forrestmiller/Desktop/additional/kaggle_all_retailers.csv"
FANDOM_FILE = "/Users/forrestmiller/Desktop/additional/consolidated_retailer_locations_geocoded.csv"
GOOGLE_FILE = "/Users/forrestmiller/Desktop/additional/google_places_retailers.csv"
OUTPUT_FILE = "/Users/forrestmiller/Desktop/additional/all_retail_locations_merged.csv"

# Deduplication threshold (degrees, ~0.001 = ~100m)
COORD_THRESHOLD = 0.001

def normalize_retailer(name):
    """Standardize retailer names."""
    if not name:
        return name
    name_lower = name.lower().strip()

    mapping = {
        'the home depot': 'Home Depot',
        'home depot': 'Home Depot',
        "lowe's": 'Lowes',
        'lowes': 'Lowes',
        'jcpenney': 'JCPenney',
        'jc penney': 'JCPenney',
        'j.c. penney': 'JCPenney',
        'ross dress for less': 'Ross',
        'ross': 'Ross',
        'cvs pharmacy': 'CVS',
        'cvs': 'CVS',
        'whole foods market': 'Whole Foods',
        'whole foods': 'Whole Foods',
        'dollar general': 'Dollar General',
        'dollar tree': 'Dollar Tree',
        'harris teeter': 'Harris Teeter',
        "macy's": "Macy's",
        'macys': "Macy's",
        "kohl's": "Kohl's",
        'kohls': "Kohl's",
    }

    for key, val in mapping.items():
        if key in name_lower:
            return val

    return name.strip()

def is_duplicate(lat1, lon1, lat2, lon2, threshold=COORD_THRESHOLD):
    """Check if two coordinates are within threshold."""
    try:
        return abs(float(lat1) - float(lat2)) < threshold and abs(float(lon1) - float(lon2)) < threshold
    except (ValueError, TypeError):
        return False

def load_kaggle():
    """Load Kaggle CSV."""
    rows = []
    if not os.path.exists(KAGGLE_FILE):
        return rows
    with open(KAGGLE_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                'retailer': normalize_retailer(row.get('retailer', '')),
                'address': row.get('address', ''),
                'city': row.get('city', ''),
                'state': row.get('state', ''),
                'latitude': row.get('latitude', ''),
                'longitude': row.get('longitude', ''),
                'source': 'kaggle'
            })
    return rows

def load_fandom():
    """Load Fandom scraped CSV."""
    rows = []
    if not os.path.exists(FANDOM_FILE):
        return rows
    with open(FANDOM_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                'retailer': normalize_retailer(row.get('retailer', '')),
                'address': row.get('address', ''),
                'city': row.get('city', ''),
                'state': row.get('state_abbrev', row.get('state', '')),
                'latitude': row.get('latitude', ''),
                'longitude': row.get('longitude', ''),
                'source': 'fandom'
            })
    return rows

def load_google():
    """Load Google Places CSV."""
    rows = []
    if not os.path.exists(GOOGLE_FILE):
        return rows
    with open(GOOGLE_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                'retailer': normalize_retailer(row.get('retailer', '')),
                'address': row.get('address', ''),
                'city': row.get('city', ''),
                'state': row.get('state', ''),
                'latitude': row.get('latitude', ''),
                'longitude': row.get('longitude', ''),
                'source': 'google'
            })
    return rows

def main():
    print("=" * 70)
    print("MERGE RETAIL LOCATION DATA")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # Load all sources (priority order: Kaggle > Google > Fandom)
    print("\nLoading sources...")
    kaggle = load_kaggle()
    print(f"  Kaggle: {len(kaggle)} rows")

    google = load_google()
    print(f"  Google: {len(google)} rows")

    fandom = load_fandom()
    print(f"  Fandom: {len(fandom)} rows")

    total_input = len(kaggle) + len(google) + len(fandom)
    print(f"  TOTAL:  {total_input} rows")

    # Merge with deduplication
    print("\nDeduplicating by coordinates...")
    merged = []
    duplicates = 0

    # Process in priority order
    all_rows = kaggle + google + fandom

    for row in all_rows:
        lat = row.get('latitude', '')
        lon = row.get('longitude', '')
        retailer = row.get('retailer', '')

        if not lat or not lon:
            continue

        # Check if duplicate of existing
        is_dup = False
        for existing in merged:
            if existing['retailer'] == retailer and is_duplicate(lat, lon, existing['latitude'], existing['longitude']):
                is_dup = True
                duplicates += 1
                break

        if not is_dup:
            merged.append(row)

    print(f"  Duplicates removed: {duplicates}")
    print(f"  Unique locations:   {len(merged)}")

    # Count by retailer
    print("\nBy retailer:")
    retailer_counts = {}
    for row in merged:
        r = row['retailer']
        retailer_counts[r] = retailer_counts.get(r, 0) + 1

    for retailer in sorted(retailer_counts.keys(), key=lambda x: retailer_counts[x], reverse=True):
        print(f"  {retailer:20} {retailer_counts[retailer]:>5}")

    # Count by source
    print("\nBy source:")
    source_counts = {}
    for row in merged:
        s = row['source']
        source_counts[s] = source_counts.get(s, 0) + 1
    for source, count in sorted(source_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {source:20} {count:>5}")

    # Save
    print(f"\nSaving to {OUTPUT_FILE}...")
    fieldnames = ['retailer', 'address', 'city', 'state', 'latitude', 'longitude', 'source']
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged)

    print("\n" + "=" * 70)
    print(f"COMPLETE! {len(merged)} unique retail locations saved.")
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
