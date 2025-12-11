#!/usr/bin/env python3
"""
Fetch and validate images for commercial buildings missing images.
Fully automated - uses GPT-4o + Claude for validation, no human review.

Usage:
    python scripts/images/fetch_and_validate_missing.py
    python scripts/images/fetch_and_validate_missing.py --max 50
    python scripts/images/fetch_and_validate_missing.py --dry-run
"""

import os
import sys
import re
import json
import time
import base64
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple
import argparse

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import BUILDING_DATA_PATH, IMAGES_DIR

# =============================================================================
# API KEYS (from environment variables)
# =============================================================================
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
YELP_API_KEY = os.environ.get("YELP_API_KEY", "")
TRIPADVISOR_KEY = os.environ.get("TRIPADVISOR_KEY", "")
FLICKR_KEY = os.environ.get("FLICKR_KEY", "")
MAPILLARY_TOKEN = os.environ.get("MAPILLARY_TOKEN", "")
BING_KEY = os.environ.get("BING_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# =============================================================================
# CONFIGURATION
# =============================================================================
STAGING_DIR = Path(__file__).parent.parent.parent / "staging" / "building_images"
CANDIDATES_DIR = STAGING_DIR / "candidates"
APPROVED_DIR = STAGING_DIR / "approved"
REJECTED_DIR = STAGING_DIR / "rejected"
LOGS_DIR = STAGING_DIR / "logs"

# Validation thresholds (pragmatic - AI scores tend to be conservative)
GPT4O_PASS_THRESHOLD = 40
CLAUDE_PASS_THRESHOLD = 40
FINAL_APPROVE_THRESHOLD = 45

# =============================================================================
# DATA CLASSES
# =============================================================================
@dataclass
class ImageCandidate:
    url: str
    source: str
    local_path: str = ""
    file_size: int = 0

@dataclass
class ValidationResult:
    gpt4o_score: int = 0
    gpt4o_exterior: str = ""
    gpt4o_building: str = ""
    gpt4o_reasoning: str = ""
    claude_score: int = 0
    claude_commercial: bool = False
    claude_reasoning: str = ""
    final_score: int = 0
    approved: bool = False

@dataclass
class BuildingResult:
    building_id: str
    address: str
    city: str
    candidates_fetched: int = 0
    candidates_validated: int = 0
    best_image: str = ""
    best_score: int = 0
    final_status: str = ""  # SUCCESS, NO_IMAGE, VALIDATION_FAILED
    error: str = ""

# =============================================================================
# IMAGE FETCHING FUNCTIONS
# =============================================================================

def fetch_google_streetview(lat: float, lon: float, building_id: str) -> Optional[ImageCandidate]:
    """Fetch from Google Street View Static API."""
    # First check if imagery exists
    meta_url = f"https://maps.googleapis.com/maps/api/streetview/metadata?location={lat},{lon}&key={GOOGLE_API_KEY}"
    try:
        meta_resp = requests.get(meta_url, timeout=10)
        if meta_resp.status_code != 200 or meta_resp.json().get('status') != 'OK':
            return None
    except:
        return None

    # Fetch image
    url = f"https://maps.googleapis.com/maps/api/streetview?size=640x480&location={lat},{lon}&fov=90&pitch=10&key={GOOGLE_API_KEY}"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200 and len(resp.content) > 5000:
            return ImageCandidate(url=url, source="streetview")
    except:
        pass
    return None


def fetch_serpapi(address: str, city: str, building_id: str) -> Optional[ImageCandidate]:
    """Fetch from SerpAPI Google Images."""
    query = f"{address} {city} building exterior"
    url = "https://serpapi.com/search"
    params = {
        "engine": "google_images",
        "q": query,
        "api_key": SERPAPI_KEY,
        "num": 5
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            images = data.get("images_results", [])

            # Filter out interior/bad images by title
            bad_keywords = ["interior", "inside", "room", "lobby", "floor plan", "map", "logo"]
            for img in images:
                title = img.get("title", "").lower()
                if any(kw in title for kw in bad_keywords):
                    continue
                img_url = img.get("original") or img.get("thumbnail")
                if img_url:
                    return ImageCandidate(url=img_url, source="serpapi")
    except:
        pass
    return None


def fetch_yelp(name: str, lat: float, lon: float, building_id: str) -> Optional[ImageCandidate]:
    """Fetch from Yelp Business Photos."""
    headers = {"Authorization": f"Bearer {YELP_API_KEY}"}

    # Search for business
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
        if resp.status_code == 200:
            businesses = resp.json().get("businesses", [])
            if businesses:
                # Get business details for photos
                biz_id = businesses[0].get("id")
                detail_url = f"https://api.yelp.com/v3/businesses/{biz_id}"
                detail_resp = requests.get(detail_url, headers=headers, timeout=15)
                if detail_resp.status_code == 200:
                    photos = detail_resp.json().get("photos", [])
                    if photos:
                        return ImageCandidate(url=photos[0], source="yelp")
    except:
        pass
    return None


def fetch_mapillary(lat: float, lon: float, building_id: str) -> Optional[ImageCandidate]:
    """Fetch from Mapillary street-level imagery."""
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
        if resp.status_code == 200:
            images = resp.json().get("data", [])
            for img in images:
                thumb_url = img.get("thumb_1024_url")
                if thumb_url:
                    return ImageCandidate(url=thumb_url, source="mapillary")
    except:
        pass
    return None


def fetch_bing_images(address: str, city: str, building_id: str) -> Optional[ImageCandidate]:
    """Fetch from Bing Image Search."""
    query = f"{address} {city} building exterior"
    url = "https://api.bing.microsoft.com/v7.0/images/search"
    headers = {"Ocp-Apim-Subscription-Key": BING_KEY}
    params = {
        "q": query,
        "count": 5,
        "imageType": "Photo",
        "safeSearch": "Moderate"
    }

    bad_keywords = ["interior", "inside", "room", "floor", "plan", "map"]

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code == 200:
            images = resp.json().get("value", [])
            for img in images:
                name = img.get("name", "").lower()
                if any(kw in name for kw in bad_keywords):
                    continue
                img_url = img.get("contentUrl")
                if img_url:
                    return ImageCandidate(url=img_url, source="bing")
    except:
        pass
    return None


def download_image(candidate: ImageCandidate, save_path: str) -> bool:
    """Download image to local path."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(candidate.url, headers=headers, timeout=30)
        if resp.status_code == 200 and len(resp.content) > 5000:
            with open(save_path, 'wb') as f:
                f.write(resp.content)
            candidate.local_path = save_path
            candidate.file_size = len(resp.content)
            return True
    except:
        pass
    return False


# =============================================================================
# AI VALIDATION FUNCTIONS
# =============================================================================

def encode_image_base64(image_path: str) -> str:
    """Encode image to base64."""
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def validate_with_gpt4o(image_path: str) -> dict:
    """
    Round 1: GPT-4o validates exterior/building/quality.
    Returns dict with score and details.
    """
    base64_img = encode_image_base64(image_path)

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
                    {
                        "type": "text",
                        "text": """Analyze this image for a commercial building database.

Answer these questions:
1. EXTERIOR: Is this an EXTERIOR shot of a building? (YES/NO/UNCERTAIN)
   - NO if: interior, lobby, hallway, room inside
2. BUILDING: Does this show an actual BUILDING? (YES/NO/UNCERTAIN)
   - NO if: sign only, map, logo, person, landscape without building
3. QUALITY: Is image quality acceptable? (YES/NO)
   - NO if: extremely blurry, tiny, mostly black/white

Respond ONLY in this JSON format:
{
  "exterior": "YES or NO or UNCERTAIN",
  "building": "YES or NO or UNCERTAIN",
  "quality": "YES or NO",
  "confidence": 0-100,
  "reasoning": "brief explanation"
}"""
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_img}",
                            "detail": "low"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 200
    }

    try:
        resp = requests.post("https://api.openai.com/v1/chat/completions",
                            headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            # Parse JSON from response
            json_match = re.search(r'\{[^{}]+\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "score": data.get("confidence", 0),
                    "exterior": data.get("exterior", "UNCERTAIN"),
                    "building": data.get("building", "UNCERTAIN"),
                    "quality": data.get("quality", "NO"),
                    "reasoning": data.get("reasoning", "")
                }
    except Exception as e:
        print(f"      GPT-4o error: {e}")

    return {"score": 0, "exterior": "UNCERTAIN", "building": "UNCERTAIN", "quality": "NO", "reasoning": "API error"}


def validate_with_claude(image_path: str, address: str, building_type: str) -> dict:
    """
    Round 2: Claude validates commercial type and address context.
    Returns dict with score and details.
    """
    base64_img = encode_image_base64(image_path)

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01"
    }

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 300,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": base64_img
                        }
                    },
                    {
                        "type": "text",
                        "text": f"""Verify this building image for a commercial real estate database.

Context:
- Address: {address}
- Building Type: {building_type}

Check:
1. Is this a COMMERCIAL building (office, retail, hotel, industrial)? NOT a residential home.
2. Does this look like a real photograph (not a rendering, stock illustration, or map screenshot)?
3. Could this plausibly be the building at the given address?

Respond ONLY in JSON:
{{
  "is_commercial": true or false,
  "is_real_photo": true or false,
  "plausible_match": true or false,
  "confidence": 0-100,
  "reasoning": "brief explanation"
}}"""
                    }
                ]
            }
        ]
    }

    try:
        resp = requests.post("https://api.anthropic.com/v1/messages",
                            headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            content = resp.json()["content"][0]["text"]
            json_match = re.search(r'\{[^{}]+\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "score": data.get("confidence", 0),
                    "is_commercial": data.get("is_commercial", False),
                    "is_real_photo": data.get("is_real_photo", False),
                    "plausible_match": data.get("plausible_match", False),
                    "reasoning": data.get("reasoning", "")
                }
    except Exception as e:
        print(f"      Claude error: {e}")

    return {"score": 0, "is_commercial": False, "is_real_photo": False, "plausible_match": False, "reasoning": "API error"}


def validate_image(image_path: str, address: str, building_type: str) -> ValidationResult:
    """Run full validation pipeline on an image."""
    result = ValidationResult()

    # Round 1: GPT-4o
    gpt_result = validate_with_gpt4o(image_path)
    result.gpt4o_score = gpt_result["score"]
    result.gpt4o_exterior = gpt_result["exterior"]
    result.gpt4o_building = gpt_result["building"]
    result.gpt4o_reasoning = gpt_result["reasoning"]

    # Early reject if clearly not exterior/building
    if gpt_result["exterior"] == "NO" or gpt_result["building"] == "NO":
        result.final_score = min(result.gpt4o_score, 30)
        result.approved = False
        return result

    # Round 2: Claude
    claude_result = validate_with_claude(image_path, address, building_type)
    result.claude_score = claude_result["score"]
    result.claude_commercial = claude_result["is_commercial"]
    result.claude_reasoning = claude_result["reasoning"]

    # Final score: weighted average
    result.final_score = int(result.gpt4o_score * 0.4 + result.claude_score * 0.6)

    # Approve if passes thresholds (score-based, lenient on booleans)
    result.approved = (
        result.final_score >= FINAL_APPROVE_THRESHOLD and
        result.gpt4o_exterior != "NO" and  # Allow YES or UNCERTAIN
        result.gpt4o_building != "NO"      # Allow YES or UNCERTAIN
    )

    return result


# =============================================================================
# MAIN PIPELINE
# =============================================================================

def get_buildings_with_images() -> set:
    """Get set of building IDs that already have images."""
    images_dir = str(IMAGES_DIR)
    building_ids = set()

    for f in os.listdir(images_dir):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            # Extract building_id (everything before last underscore)
            match = re.match(r'^(.+)_[^_]+\.\w+$', f)
            if match:
                building_ids.add(match.group(1))

    return building_ids


def get_commercial_buildings_missing_images() -> pd.DataFrame:
    """Get commercial buildings that don't have images."""
    df = pd.read_csv(BUILDING_DATA_PATH, low_memory=False)

    # Get buildings with images
    have_images = get_buildings_with_images()

    # Filter to commercial buildings without images
    commercial = df[df['bldg_vertical'] == 'Commercial'].copy()
    missing = commercial[~commercial['id_building'].astype(str).isin(have_images)]

    # Sort by portfolio OpEx (highest value first)
    if 'savings_opex_avoided_annual_usd' in missing.columns:
        missing = missing.sort_values('savings_opex_avoided_annual_usd', ascending=False)

    return missing


def fetch_candidates_for_building(row: pd.Series) -> List[ImageCandidate]:
    """Fetch image candidates from multiple sources for a building."""
    candidates = []

    building_id = str(row['id_building'])
    lat = row.get('loc_lat')
    lon = row.get('loc_lon')
    address = str(row.get('loc_address', ''))
    city = str(row.get('loc_city', ''))
    name = str(row.get('id_property_name', ''))
    bldg_type = str(row.get('bldg_type', ''))

    # 1. Google Street View (best for most buildings)
    if pd.notna(lat) and pd.notna(lon):
        candidate = fetch_google_streetview(float(lat), float(lon), building_id)
        if candidate:
            candidates.append(candidate)

    # 2. Mapillary (street-level alternative)
    if len(candidates) < 3 and pd.notna(lat) and pd.notna(lon):
        candidate = fetch_mapillary(float(lat), float(lon), building_id)
        if candidate:
            candidates.append(candidate)

    # 3. Yelp (good for retail/restaurants)
    if len(candidates) < 3 and name and pd.notna(lat) and pd.notna(lon):
        if any(t in bldg_type.lower() for t in ['retail', 'restaurant', 'store', 'shop']):
            candidate = fetch_yelp(name, float(lat), float(lon), building_id)
            if candidate:
                candidates.append(candidate)

    # 4. SerpAPI (fallback)
    if len(candidates) < 3 and address:
        candidate = fetch_serpapi(address, city, building_id)
        if candidate:
            candidates.append(candidate)

    # 5. Bing Images (fallback)
    if len(candidates) < 2 and address:
        candidate = fetch_bing_images(address, city, building_id)
        if candidate:
            candidates.append(candidate)

    return candidates


def process_building(row: pd.Series, dry_run: bool = False) -> BuildingResult:
    """Process a single building: fetch candidates, validate, select best."""
    building_id = str(row['id_building'])
    address = str(row.get('loc_address', ''))
    city = str(row.get('loc_city', ''))
    bldg_type = str(row.get('bldg_type', 'Commercial'))

    result = BuildingResult(
        building_id=building_id,
        address=f"{address}, {city}",
        city=city
    )

    # Fetch candidates
    print(f"    Fetching candidates...", end=" ", flush=True)
    candidates = fetch_candidates_for_building(row)
    result.candidates_fetched = len(candidates)
    print(f"found {len(candidates)}")

    if not candidates:
        result.final_status = "NO_IMAGE"
        return result

    if dry_run:
        result.final_status = "DRY_RUN"
        return result

    # Download and validate each candidate
    best_candidate = None
    best_validation = None
    best_score = 0

    for i, candidate in enumerate(candidates):
        print(f"    Validating candidate {i+1}/{len(candidates)} ({candidate.source})...", end=" ", flush=True)

        # Download to temp location
        temp_path = str(CANDIDATES_DIR / f"{building_id}_{candidate.source}_temp.jpg")
        if not download_image(candidate, temp_path):
            print("download failed")
            continue

        result.candidates_validated += 1

        # Validate with AI
        validation = validate_image(temp_path, f"{address}, {city}", bldg_type)
        print(f"score={validation.final_score} {'APPROVED' if validation.approved else 'rejected'}")

        if validation.approved and validation.final_score > best_score:
            best_score = validation.final_score
            best_candidate = candidate
            best_validation = validation

        # Clean up temp file if not best
        if not (validation.approved and validation.final_score >= best_score):
            try:
                os.remove(temp_path)
            except:
                pass

        time.sleep(0.5)  # Rate limit between validations

    # Handle result
    if best_candidate and best_validation and best_validation.approved:
        # Move best image to approved folder and final location
        temp_path = str(CANDIDATES_DIR / f"{building_id}_{best_candidate.source}_temp.jpg")
        final_filename = f"{building_id}_{best_candidate.source}.jpg"
        final_path = str(IMAGES_DIR / final_filename)

        try:
            # Copy to assets/images/
            import shutil
            shutil.copy(temp_path, final_path)
            os.remove(temp_path)

            result.best_image = final_filename
            result.best_score = best_score
            result.final_status = "SUCCESS"
        except Exception as e:
            result.final_status = "SAVE_ERROR"
            result.error = str(e)
    else:
        result.final_status = "VALIDATION_FAILED"

    return result


def main():
    parser = argparse.ArgumentParser(description="Fetch and validate missing building images")
    parser.add_argument("--max", type=int, default=None, help="Max buildings to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't download/validate, just show what would be done")
    parser.add_argument("--building-id", type=str, help="Process single building by ID")
    args = parser.parse_args()

    # Setup directories
    for d in [STAGING_DIR, CANDIDATES_DIR, APPROVED_DIR, REJECTED_DIR, LOGS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("BUILDING IMAGE FETCH & VALIDATE PIPELINE")
    print("=" * 70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Dry run: {args.dry_run}")
    print()

    # Get buildings to process
    print("Loading buildings missing images...")
    if args.building_id:
        df = pd.read_csv(BUILDING_DATA_PATH, low_memory=False)
        missing = df[df['id_building'] == args.building_id]
    else:
        missing = get_commercial_buildings_missing_images()

    print(f"  Commercial buildings missing images: {len(missing)}")

    if args.max:
        missing = missing.head(args.max)
        print(f"  Processing first {args.max}")

    print()
    print("-" * 70)

    # Process each building
    results = []
    success_count = 0
    fail_count = 0
    no_image_count = 0

    for idx, (_, row) in enumerate(missing.iterrows()):
        building_id = row['id_building']
        address = row.get('loc_address', '')

        print(f"\n[{idx+1}/{len(missing)}] {building_id}")
        print(f"    Address: {address}")

        result = process_building(row, dry_run=args.dry_run)
        results.append(result)

        if result.final_status == "SUCCESS":
            success_count += 1
            print(f"    SUCCESS: {result.best_image} (score={result.best_score})")
        elif result.final_status == "NO_IMAGE":
            no_image_count += 1
            print(f"    NO IMAGE: No candidates found from any source")
        elif result.final_status == "DRY_RUN":
            print(f"    DRY RUN: Would validate {result.candidates_fetched} candidates")
        else:
            fail_count += 1
            print(f"    FAILED: {result.final_status}")

        # Rate limit between buildings
        time.sleep(1)

    # Save results log
    log_file = LOGS_DIR / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(log_file, 'w') as f:
        json.dump([asdict(r) for r in results], f, indent=2)

    # Summary
    print()
    print("=" * 70)
    print("COMPLETE!")
    print("=" * 70)
    print(f"  Total processed: {len(results)}")
    print(f"  Success: {success_count}")
    print(f"  Failed validation: {fail_count}")
    print(f"  No image found: {no_image_count}")
    print(f"  Log saved: {log_file}")
    print()


if __name__ == "__main__":
    main()
