#!/usr/bin/env python3
"""
Re-fetch bad building images using SerpAPI Google Images search.
"""

import os
import sys
import requests
import pandas as pd
import time
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import BUILDING_DATA_PATH, MISSING_IMAGES_DIR

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")

# Paths - from centralized config
BUILDING_DATA = str(BUILDING_DATA_PATH)
OUTPUT_DIR = str(MISSING_IMAGES_DIR)

# Bad images that need re-fetching
BAD_BUILDING_IDS = [
    "BOS_101337",
    "BOS_103535",
    "BOS_103539",
    "BOS_103569",
    "BOS_103575",
    "CAM_1073",
    "CAM_1165",
    "CAM_1197",
    "CHI_103602",
    "CA_6262690",
    "CA_6263960",
    "CA_6799015",
    "CA_6874055",
    "CA_17806265",
    "DC_5473622",
    "DC_5473628",
    "DC_5473698",
    "DC_5476692",
    "NYC_2032470070",
    "NYC_2048230001",
    "NYC_3085910980",
    "SD_188",
    "SF_37210822024",
    "SF_02290032024",
]

def get_building_info(building_id):
    """Get building info from CSV."""
    df = pd.read_csv(BUILDING_DATA, low_memory=False)
    row = df[df['building_id'] == building_id]
    if len(row) == 0:
        return None
    return row.iloc[0]

def fetch_serpapi_image(query):
    """Fetch image using SerpAPI Google Images search."""
    url = "https://serpapi.com/search"
    params = {
        "engine": "google_images",
        "q": query,
        "api_key": SERPAPI_KEY,
        "num": 5,
        "safe": "active"
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 200:
            data = response.json()
            images = data.get("images_results", [])

            # Try each image result until we get one that works
            for img in images[:5]:
                img_url = img.get("original") or img.get("thumbnail")
                if img_url:
                    try:
                        img_response = requests.get(img_url, timeout=15, headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                        })
                        if img_response.status_code == 200 and len(img_response.content) > 5000:
                            return img_response.content
                    except:
                        continue
    except Exception as e:
        print(f"    SerpAPI error: {e}")

    return None

def main():
    print("=" * 60)
    print("RE-FETCH BAD BUILDING IMAGES VIA SERPAPI")
    print("=" * 60)

    df = pd.read_csv(BUILDING_DATA, low_memory=False)

    success_count = 0
    fail_count = 0

    for i, building_id in enumerate(BAD_BUILDING_IDS):
        row = df[df['building_id'] == building_id]
        if len(row) == 0:
            print(f"\n[{i+1}/{len(BAD_BUILDING_IDS)}] {building_id} - NOT FOUND IN CSV")
            fail_count += 1
            continue

        row = row.iloc[0]
        address = row.get('address', '')
        owner = row.get('building_owner', 'Unknown')

        print(f"\n[{i+1}/{len(BAD_BUILDING_IDS)}] {building_id}")
        print(f"    Owner: {str(owner)[:40]}")
        print(f"    Address: {str(address)[:50]}")

        # Remove old bad image
        old_file = os.path.join(OUTPUT_DIR, f"{building_id}_streetview.jpg")
        if os.path.exists(old_file):
            os.remove(old_file)
            print(f"    Removed old image")

        # Try different search queries
        queries = [
            f"{address} building exterior",
            f"{address} building",
            f"{owner} {address.split(',')[0] if ',' in str(address) else address}",
        ]

        image_data = None
        for query in queries:
            print(f"    Searching: {query[:50]}...", end=" ", flush=True)
            image_data = fetch_serpapi_image(query)
            if image_data:
                print("OK!")
                break
            else:
                print("no result")

        if image_data:
            filename = f"{building_id}_serpapi.jpg"
            filepath = os.path.join(OUTPUT_DIR, filename)
            with open(filepath, 'wb') as f:
                f.write(image_data)
            print(f"    Saved: {filename}")
            success_count += 1
        else:
            print("    FAILED - no image found")
            fail_count += 1

        # Rate limit
        time.sleep(1)

    print("\n" + "=" * 60)
    print("COMPLETE!")
    print(f"  Success: {success_count}")
    print(f"  Failed: {fail_count}")
    print("=" * 60)

if __name__ == "__main__":
    main()
