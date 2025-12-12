#!/usr/bin/env python3
"""
Fetch images for notable buildings (those with names) from the nationwide prospector.
Uses AI (GPT-4o) to validate that images show the correct building.

Usage:
    python3 scripts/images/fetch_notable_images.py
    python3 scripts/images/fetch_notable_images.py --max 100
    python3 scripts/images/fetch_notable_images.py --skip-existing
    python3 scripts/images/fetch_notable_images.py --building ATL_8
"""

import os
import sys
import json
import time
import base64
import argparse
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import PORTFOLIO_DATA_PATH

# =============================================================================
# CONFIGURATION
# =============================================================================
DATA_PATH = str(PORTFOLIO_DATA_PATH)
# Output is external to project - intentionally hardcoded
OUTPUT_DIR = Path("/Users/forrestmiller/Desktop/notable_building_images")

# API Keys
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
BING_KEY = os.environ.get("BING_KEY", "")
YELP_API_KEY = os.environ.get("YELP_API_KEY", "")
MAPILLARY_TOKEN = os.environ.get("MAPILLARY_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Validation threshold
AI_ACCEPT_THRESHOLD = 50

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def log(msg, indent=0):
    """Print verbose log message."""
    prefix = "  " * indent
    print(f"{prefix}{msg}")


def load_notable_buildings():
    """Load buildings with names from CSV."""
    df = pd.read_csv(DATA_PATH, low_memory=False)

    # Filter to buildings with names
    df = df[df['id_property_name'].notna() & (df['id_property_name'].str.strip() != '')]

    # Select relevant columns
    cols = ['id_building', 'id_property_name', 'loc_address', 'loc_city', 'loc_state', 'loc_lat', 'loc_lon']
    available_cols = [c for c in cols if c in df.columns]
    df = df[available_cols].copy()

    return df


def get_existing_images():
    """Get set of building IDs that already have images."""
    existing = set()
    if OUTPUT_DIR.exists():
        for f in OUTPUT_DIR.iterdir():
            if f.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                # Extract building ID from filename (e.g., ATL_8_streetview.jpg -> ATL_8)
                parts = f.stem.rsplit('_', 1)
                if len(parts) >= 1:
                    existing.add(parts[0])
    return existing


# =============================================================================
# IMAGE FETCHING FUNCTIONS
# =============================================================================

def fetch_google_streetview(lat, lon):
    """Fetch from Google Street View Static API."""
    if pd.isna(lat) or pd.isna(lon):
        return None, "NO COORDINATES"

    # Check if imagery exists
    meta_url = f"https://maps.googleapis.com/maps/api/streetview/metadata?location={lat},{lon}&key={GOOGLE_API_KEY}"
    try:
        meta_resp = requests.get(meta_url, timeout=10)
        if meta_resp.status_code != 200:
            return None, f"META ERROR {meta_resp.status_code}"
        meta_data = meta_resp.json()
        if meta_data.get('status') != 'OK':
            return None, f"NO IMAGERY ({meta_data.get('status')})"
    except Exception as e:
        return None, f"META ERROR: {str(e)[:30]}"

    # Fetch image
    url = f"https://maps.googleapis.com/maps/api/streetview?size=640x480&location={lat},{lon}&fov=90&pitch=10&key={GOOGLE_API_KEY}"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200 and len(resp.content) > 5000:
            return resp.content, f"DOWNLOADED ({len(resp.content)//1024}KB)"
        return None, f"SMALL IMAGE ({len(resp.content)} bytes)"
    except Exception as e:
        return None, f"ERROR: {str(e)[:30]}"


def fetch_serpapi(name, address, city):
    """Fetch from SerpAPI Google Images."""
    query = f"{name} {address} {city} building exterior"
    url = "https://serpapi.com/search"
    params = {
        "engine": "google_images",
        "q": query,
        "api_key": SERPAPI_KEY,
        "num": 5
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            return None, f"API ERROR {resp.status_code}"

        data = resp.json()
        images = data.get("images_results", [])

        # Filter out bad images
        bad_keywords = ["interior", "inside", "room", "lobby", "floor plan", "map", "logo", "icon"]
        for img in images:
            title = img.get("title", "").lower()
            if any(kw in title for kw in bad_keywords):
                continue
            img_url = img.get("original") or img.get("thumbnail")
            if img_url:
                # Download the image
                try:
                    img_resp = requests.get(img_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
                    if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                        return img_resp.content, f"DOWNLOADED ({len(img_resp.content)//1024}KB)"
                except:
                    continue
        return None, "NO SUITABLE IMAGES"
    except Exception as e:
        return None, f"ERROR: {str(e)[:30]}"


def fetch_bing(name, address, city):
    """Fetch from Bing Image Search."""
    query = f"{name} {address} {city} building"
    url = "https://api.bing.microsoft.com/v7.0/images/search"
    headers = {"Ocp-Apim-Subscription-Key": BING_KEY}
    params = {
        "q": query,
        "count": 5,
        "imageType": "Photo",
        "safeSearch": "Moderate"
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code != 200:
            return None, f"API ERROR {resp.status_code}"

        data = resp.json()
        images = data.get("value", [])

        for img in images:
            img_url = img.get("contentUrl")
            if img_url:
                try:
                    img_resp = requests.get(img_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
                    if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                        return img_resp.content, f"DOWNLOADED ({len(img_resp.content)//1024}KB)"
                except:
                    continue
        return None, "NO IMAGES FOUND"
    except Exception as e:
        return None, f"ERROR: {str(e)[:30]}"


def fetch_yelp(name, lat, lon):
    """Fetch from Yelp Business Photos."""
    if pd.isna(lat) or pd.isna(lon):
        return None, "NO COORDINATES"

    headers = {"Authorization": f"Bearer {YELP_API_KEY}"}
    search_url = "https://api.yelp.com/v3/businesses/search"
    params = {
        "term": name,
        "latitude": lat,
        "longitude": lon,
        "radius": 200,
        "limit": 1
    }

    try:
        resp = requests.get(search_url, headers=headers, params=params, timeout=15)
        if resp.status_code != 200:
            return None, f"API ERROR {resp.status_code}"

        businesses = resp.json().get("businesses", [])
        if not businesses:
            return None, "NO BUSINESS FOUND"

        # Get business details for photos
        biz_id = businesses[0].get("id")
        detail_url = f"https://api.yelp.com/v3/businesses/{biz_id}"
        detail_resp = requests.get(detail_url, headers=headers, timeout=15)

        if detail_resp.status_code == 200:
            photos = detail_resp.json().get("photos", [])
            if photos:
                try:
                    img_resp = requests.get(photos[0], timeout=30)
                    if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                        return img_resp.content, f"DOWNLOADED ({len(img_resp.content)//1024}KB)"
                except:
                    pass
        return None, "NO PHOTOS"
    except Exception as e:
        return None, f"ERROR: {str(e)[:30]}"


def fetch_mapillary(lat, lon):
    """Fetch from Mapillary street-level imagery."""
    if pd.isna(lat) or pd.isna(lon):
        return None, "NO COORDINATES"

    # Bounding box ~50m around point
    delta = 0.0005
    bbox = f"{lon - delta},{lat - delta},{lon + delta},{lat + delta}"

    url = "https://graph.mapillary.com/images"
    params = {
        "access_token": MAPILLARY_TOKEN,
        "bbox": bbox,
        "fields": "id,thumb_1024_url",
        "limit": 5
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            return None, f"API ERROR {resp.status_code}"

        images = resp.json().get("data", [])
        for img in images:
            img_url = img.get("thumb_1024_url")
            if img_url:
                try:
                    img_resp = requests.get(img_url, timeout=30)
                    if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                        return img_resp.content, f"DOWNLOADED ({len(img_resp.content)//1024}KB)"
                except:
                    continue
        return None, "NO IMAGES"
    except Exception as e:
        return None, f"ERROR: {str(e)[:30]}"


# =============================================================================
# AI VALIDATION
# =============================================================================

def validate_with_ai(image_bytes, building_name, address, city):
    """Use GPT-4o to validate if image shows the correct building."""

    # Encode image as base64
    b64_image = base64.b64encode(image_bytes).decode('utf-8')

    # Determine image type
    if image_bytes[:3] == b'\xff\xd8\xff':
        media_type = "image/jpeg"
    elif image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        media_type = "image/png"
    else:
        media_type = "image/jpeg"  # Default

    prompt = f"""Analyze this image and determine if it shows the exterior of a building.

Building Name: {building_name}
Address: {address}, {city}

Evaluate:
1. Is this an EXTERIOR photo of a building (not interior, logo, map, or person)?
2. Does this appear to be a commercial/institutional building?
3. Could this plausibly be the building at the given address?

Respond with ONLY a JSON object:
{{
    "is_exterior": true/false,
    "is_building": true/false,
    "confidence_score": 0-100,
    "rejection_reason": "reason if score < 50, otherwise null"
}}"""

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{b64_image}",
                            "detail": "low"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 200
    }

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )

        if resp.status_code != 200:
            return 0, f"API ERROR {resp.status_code}"

        content = resp.json()["choices"][0]["message"]["content"]

        # Parse JSON from response
        # Handle markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        result = json.loads(content.strip())
        score = result.get("confidence_score", 0)
        reason = result.get("rejection_reason")

        if score >= AI_ACCEPT_THRESHOLD:
            return score, "ACCEPTED"
        else:
            return score, f"REJECTED ({reason or 'low confidence'})"

    except json.JSONDecodeError as e:
        return 0, f"JSON PARSE ERROR"
    except Exception as e:
        return 0, f"ERROR: {str(e)[:30]}"


# =============================================================================
# MAIN PIPELINE
# =============================================================================

def process_building(row, index, total):
    """Process a single building - fetch and validate image."""
    building_id = row['id_building']
    name = row.get('id_property_name', 'Unknown')
    address = row.get('loc_address', '')
    city = row.get('loc_city', '')
    state = row.get('loc_state', '')
    lat = row.get('loc_lat')
    lon = row.get('loc_lon')

    print(f"\n[{index}/{total}] {building_id} - {name}")
    log(f"Address: {address}, {city}, {state}", 1)

    # Sources to try in order
    sources = [
        ("Google Street View", lambda: fetch_google_streetview(lat, lon)),
        ("SerpAPI", lambda: fetch_serpapi(name, address, city)),
        ("Bing", lambda: fetch_bing(name, address, city)),
        ("Yelp", lambda: fetch_yelp(name, lat, lon)),
        ("Mapillary", lambda: fetch_mapillary(lat, lon)),
    ]

    for source_name, fetch_func in sources:
        log(f"Trying {source_name}...", 1)

        image_bytes, status = fetch_func()
        log(status, 2)

        if image_bytes is None:
            continue

        # Validate with AI
        log("AI Validation...", 1)
        score, validation_status = validate_with_ai(image_bytes, name, address, city)
        log(f"Score {score}/100 - {validation_status}", 2)

        if score >= AI_ACCEPT_THRESHOLD:
            # Save the image
            source_slug = source_name.lower().replace(" ", "_")
            filename = f"{building_id}_{source_slug}.jpg"
            filepath = OUTPUT_DIR / filename

            with open(filepath, 'wb') as f:
                f.write(image_bytes)

            log(f"Saved: {filename}", 1)
            return True, source_name, score

        # Small delay before trying next source
        time.sleep(0.5)

    log("NO VALID IMAGE FOUND", 1)
    return False, None, 0


def main():
    parser = argparse.ArgumentParser(description="Fetch images for notable buildings")
    parser.add_argument("--max", type=int, help="Maximum number of buildings to process")
    parser.add_argument("--skip-existing", action="store_true", help="Skip buildings with existing images")
    parser.add_argument("--building", type=str, help="Process single building by ID")
    args = parser.parse_args()

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("NOTABLE BUILDING IMAGE FETCHER")
    print("=" * 60)

    # Load buildings
    print("\nLoading notable buildings...")
    df = load_notable_buildings()
    print(f"Found {len(df)} buildings with names")

    # Filter to single building if specified
    if args.building:
        df = df[df['id_building'] == args.building]
        if len(df) == 0:
            print(f"ERROR: Building '{args.building}' not found")
            return
        print(f"Processing single building: {args.building}")

    # Skip existing if requested
    if args.skip_existing:
        existing = get_existing_images()
        before = len(df)
        df = df[~df['id_building'].isin(existing)]
        print(f"Skipping {before - len(df)} buildings with existing images")

    # Limit if specified
    if args.max:
        df = df.head(args.max)
        print(f"Limited to {args.max} buildings")

    print(f"\nProcessing {len(df)} buildings...")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 60)

    # Process buildings
    success_count = 0
    fail_count = 0

    start_time = datetime.now()

    for idx, row in df.iterrows():
        current = success_count + fail_count + 1
        success, source, score = process_building(row, current, len(df))

        if success:
            success_count += 1
        else:
            fail_count += 1

        # Rate limiting
        time.sleep(0.3)

    # Summary
    elapsed = datetime.now() - start_time
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total processed: {success_count + fail_count}")
    print(f"Success: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Success rate: {success_count/(success_count+fail_count)*100:.1f}%")
    print(f"Time elapsed: {elapsed}")
    print(f"Images saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
