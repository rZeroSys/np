#!/usr/bin/env python3
"""
Fetch images for buildings missing images in portfolios ranked 20-40 by OpEx.
Uses Google Street View Static API and SerpAPI as fallback.
"""

import os
import sys
import requests
import pandas as pd
import time
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import BUILDING_DATA_PATH, IMAGES_DIR, MISSING_IMAGES_DIR

# API Keys
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")

# Paths - from centralized config
BUILDING_DATA = str(BUILDING_DATA_PATH)
GOOD_IMAGES_DIR = str(IMAGES_DIR)
OUTPUT_DIR = str(MISSING_IMAGES_DIR)

def get_buildings_with_images():
    """Get set of building IDs that have images."""
    image_files = os.listdir(GOOD_IMAGES_DIR)
    building_ids = set()
    for img in image_files:
        if img.endswith('.jpg') or img.endswith('.png'):
            parts = img.split('_')
            if len(parts) >= 2:
                bid = f"{parts[0]}_{parts[1]}"
                building_ids.add(bid)
    return building_ids

def get_portfolio_20_40_missing_images():
    """Get buildings in portfolios ranked 20-40 that are missing images."""
    df = pd.read_csv(BUILDING_DATA, low_memory=False)

    # Get buildings with images (including newly fetched ones in missing_images folder)
    have_images = get_buildings_with_images()

    # Also check missing_images folder
    if os.path.exists(OUTPUT_DIR):
        for img in os.listdir(OUTPUT_DIR):
            if img.endswith('.jpg') or img.endswith('.png'):
                parts = img.split('_')
                if len(parts) >= 2:
                    bid = f"{parts[0]}_{parts[1]}"
                    have_images.add(bid)

    # Mark which have images
    df['has_image'] = df['building_id'].astype(str).isin(have_images)

    # Get portfolios ranked by OpEx
    portfolio_opex = df.groupby('building_owner')['total_annual_opex_avoidance'].sum()
    ranked_portfolios = portfolio_opex.nlargest(40).index.tolist()

    # Get portfolios 20-40 (indices 20-39)
    portfolios_20_40 = ranked_portfolios[20:40]

    print("Portfolios 20-40 by OpEx:")
    for i, p in enumerate(portfolios_20_40, 21):
        opex = portfolio_opex[p]
        print(f"  {i}. {p[:50]} - ${opex:,.0f}")

    # Filter to portfolios 20-40 without images
    missing = df[
        (df['building_owner'].isin(portfolios_20_40)) &
        (~df['has_image'])
    ].copy()

    return missing

def fetch_streetview(lat, lon, building_id):
    """Fetch image from Google Street View Static API."""
    url = "https://maps.googleapis.com/maps/api/streetview"
    params = {
        "size": "640x480",
        "location": f"{lat},{lon}",
        "fov": "90",
        "pitch": "10",
        "key": GOOGLE_API_KEY
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            if 'image' in content_type and len(response.content) > 5000:
                return response.content
    except Exception as e:
        print(f"    Street View error: {e}")

    return None

def fetch_serpapi(address, building_id):
    """Fetch image using SerpAPI Google Images search."""
    url = "https://serpapi.com/search"
    params = {
        "engine": "google_images",
        "q": f"{address} building exterior",
        "api_key": SERPAPI_KEY,
        "num": 5
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 200:
            data = response.json()
            images = data.get("images_results", [])
            for img in images[:5]:
                img_url = img.get("original") or img.get("thumbnail")
                if img_url:
                    try:
                        img_response = requests.get(img_url, timeout=15, headers={
                            'User-Agent': 'Mozilla/5.0'
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
    print("FETCH MISSING BUILDING IMAGES - PORTFOLIOS 20-40")
    print("=" * 60)

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Get buildings missing images
    print("\nLoading data...")
    missing = get_portfolio_20_40_missing_images()
    print(f"\nBuildings missing images in portfolios 20-40: {len(missing)}")

    if len(missing) == 0:
        print("No missing images!")
        return

    # Process each building
    print("\n" + "-" * 60)
    success_count = 0
    fail_count = 0

    for idx, row in missing.iterrows():
        building_id = row['building_id']
        lat = row.get('latitude')
        lon = row.get('longitude')
        address = row.get('address', '')
        owner = row.get('building_owner', 'Unknown')

        print(f"\n[{success_count + fail_count + 1}/{len(missing)}] {building_id}")
        print(f"    Owner: {str(owner)[:40]}")
        print(f"    Address: {str(address)[:50]}")

        image_data = None
        source = None

        # Try Street View first
        if pd.notna(lat) and pd.notna(lon):
            print(f"    Trying Street View ({lat}, {lon})...", end=" ", flush=True)
            image_data = fetch_streetview(lat, lon, building_id)
            if image_data:
                source = "streetview"
                print("OK!")

        # Fallback to SerpAPI
        if not image_data and address:
            print(f"    Trying SerpAPI...", end=" ", flush=True)
            image_data = fetch_serpapi(address, building_id)
            if image_data:
                source = "serpapi"
                print("OK!")

        # Save image
        if image_data:
            filename = f"{building_id}_{source}.jpg"
            filepath = os.path.join(OUTPUT_DIR, filename)
            with open(filepath, 'wb') as f:
                f.write(image_data)
            print(f"    Saved: {filename}")
            success_count += 1
        else:
            print("    FAILED - no image found")
            fail_count += 1

        # Rate limit
        time.sleep(0.5)

    print("\n" + "=" * 60)
    print("COMPLETE!")
    print(f"  Success: {success_count}")
    print(f"  Failed: {fail_count}")
    print(f"  Output: {OUTPUT_DIR}")
    print("=" * 60)

if __name__ == "__main__":
    main()
