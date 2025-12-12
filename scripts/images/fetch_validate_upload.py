#!/usr/bin/env python3
"""
BUILDING IMAGE PIPELINE v2
==========================
Fetches, validates, creates thumbnails, and uploads to AWS S3.
- Verbose output
- Resume capability (picks up where left off)
- Correct naming convention
- Uploads to AWS automatically

Usage:
    python scripts/images/fetch_validate_upload.py
    python scripts/images/fetch_validate_upload.py --max 100
    python scripts/images/fetch_validate_upload.py --reset  # Start fresh
"""

import os
import sys
import re
import json
import time
import base64
import shutil
import requests
import pandas as pd
import boto3
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import BUILDING_DATA_PATH, IMAGES_DIR, AWS_BUCKET, AWS_REGION

try:
    from PIL import Image
except ImportError:
    print("ERROR: PIL not installed. Run: pip install Pillow")
    sys.exit(1)

# =============================================================================
# PATHS
# =============================================================================
THUMBNAILS_DIR = Path(IMAGES_DIR).parent / "thumbnails"
STAGING_DIR = Path(__file__).parent.parent.parent / "staging" / "building_images"
CANDIDATES_DIR = STAGING_DIR / "candidates"
LOGS_DIR = STAGING_DIR / "logs"
STATE_FILE = STAGING_DIR / "pipeline_state.json"

# =============================================================================
# API KEYS
# =============================================================================
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
YELP_API_KEY = os.environ.get("YELP_API_KEY", "")
MAPILLARY_TOKEN = os.environ.get("MAPILLARY_TOKEN", "")
BING_KEY = os.environ.get("BING_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# AWS
AWS_IMAGES_PREFIX = "images/"
AWS_THUMBNAILS_PREFIX = "thumbnails/"

# Validation thresholds
FINAL_APPROVE_THRESHOLD = 45

# =============================================================================
# STATE MANAGEMENT (for resume)
# =============================================================================
def load_state() -> dict:
    """Load pipeline state from file."""
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"processed": [], "success": [], "failed": [], "no_image": []}

def save_state(state: dict):
    """Save pipeline state to file."""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def reset_state():
    """Reset pipeline state."""
    if STATE_FILE.exists():
        os.remove(STATE_FILE)
    print("State reset - will start from beginning")

# =============================================================================
# VERBOSE LOGGING
# =============================================================================
class Logger:
    def __init__(self):
        self.start_time = datetime.now()

    def header(self, text: str):
        print(f"\n{'='*70}")
        print(f"  {text}")
        print(f"{'='*70}")

    def section(self, text: str):
        print(f"\n{'-'*70}")
        print(f"  {text}")
        print(f"{'-'*70}")

    def building(self, idx: int, total: int, building_id: str, address: str):
        pct = (idx / total) * 100
        elapsed = (datetime.now() - self.start_time).total_seconds()
        rate = idx / elapsed if elapsed > 0 else 0
        eta_mins = ((total - idx) / rate / 60) if rate > 0 else 0

        print(f"\n[{idx}/{total}] ({pct:.1f}%) {building_id}")
        print(f"    Address: {address[:60]}")
        print(f"    Rate: {rate:.1f}/min | ETA: {eta_mins:.0f} min remaining")

    def fetch(self, source: str, status: str):
        icon = "✓" if status == "found" else "✗"
        print(f"    {icon} {source}: {status}")

    def validate(self, source: str, score: int, approved: bool, reasoning: str = ""):
        icon = "✓" if approved else "✗"
        status = "APPROVED" if approved else "rejected"
        print(f"    {icon} Validate {source}: score={score} {status}")
        if reasoning:
            print(f"      └─ {reasoning[:80]}")

    def success(self, filename: str, score: int):
        print(f"    ★ SUCCESS: {filename} (score={score})")

    def fail(self, reason: str):
        print(f"    ✗ FAILED: {reason}")

    def upload(self, filename: str, status: str):
        icon = "↑" if status == "ok" else "✗"
        print(f"    {icon} Upload: {filename} {status}")

    def stats(self, success: int, failed: int, no_image: int, total: int):
        print(f"\n{'='*70}")
        print(f"  STATISTICS")
        print(f"{'='*70}")
        print(f"    Total processed:  {total}")
        print(f"    Success:          {success} ({100*success/max(total,1):.1f}%)")
        print(f"    Failed:           {failed}")
        print(f"    No image found:   {no_image}")
        elapsed = (datetime.now() - self.start_time).total_seconds() / 60
        print(f"    Time elapsed:     {elapsed:.1f} minutes")

log = Logger()

# =============================================================================
# IMAGE FETCHING
# =============================================================================
def fetch_google_streetview(lat: float, lon: float) -> Optional[str]:
    """Fetch from Google Street View. Returns URL if available."""
    meta_url = f"https://maps.googleapis.com/maps/api/streetview/metadata?location={lat},{lon}&key={GOOGLE_API_KEY}"
    try:
        resp = requests.get(meta_url, timeout=10)
        if resp.status_code == 200 and resp.json().get('status') == 'OK':
            return f"https://maps.googleapis.com/maps/api/streetview?size=640x480&location={lat},{lon}&fov=90&pitch=10&key={GOOGLE_API_KEY}"
    except:
        pass
    return None

def fetch_serpapi(address: str, city: str) -> Optional[str]:
    """Fetch from SerpAPI Google Images."""
    query = f"{address} {city} building exterior"
    params = {"engine": "google_images", "q": query, "api_key": SERPAPI_KEY, "num": 5}
    bad_keywords = ["interior", "inside", "room", "lobby", "floor plan", "map", "logo"]

    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
        if resp.status_code == 200:
            for img in resp.json().get("images_results", []):
                title = img.get("title", "").lower()
                if not any(kw in title for kw in bad_keywords):
                    return img.get("original") or img.get("thumbnail")
    except:
        pass
    return None

def fetch_mapillary(lat: float, lon: float) -> Optional[str]:
    """Fetch from Mapillary."""
    delta = 0.0005
    bbox = f"{lon-delta},{lat-delta},{lon+delta},{lat+delta}"
    params = {"access_token": MAPILLARY_TOKEN, "bbox": bbox, "fields": "id,thumb_1024_url", "limit": 3}

    try:
        resp = requests.get("https://graph.mapillary.com/images", params=params, timeout=15)
        if resp.status_code == 200:
            for img in resp.json().get("data", []):
                if img.get("thumb_1024_url"):
                    return img["thumb_1024_url"]
    except:
        pass
    return None

def fetch_bing(address: str, city: str) -> Optional[str]:
    """Fetch from Bing Image Search."""
    query = f"{address} {city} building exterior"
    headers = {"Ocp-Apim-Subscription-Key": BING_KEY}
    params = {"q": query, "count": 5, "imageType": "Photo", "safeSearch": "Moderate"}
    bad_keywords = ["interior", "inside", "room", "floor", "plan", "map"]

    try:
        resp = requests.get("https://api.bing.microsoft.com/v7.0/images/search", headers=headers, params=params, timeout=15)
        if resp.status_code == 200:
            for img in resp.json().get("value", []):
                name = img.get("name", "").lower()
                if not any(kw in name for kw in bad_keywords):
                    return img.get("contentUrl")
    except:
        pass
    return None

def download_image(url: str, save_path: str) -> bool:
    """Download image to local path."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200 and len(resp.content) > 5000:
            with open(save_path, 'wb') as f:
                f.write(resp.content)
            return True
    except:
        pass
    return False

# =============================================================================
# AI VALIDATION
# =============================================================================
def encode_image_base64(image_path: str) -> str:
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')

def validate_gpt4o(image_path: str) -> dict:
    """GPT-4o validation."""
    b64 = encode_image_base64(image_path)
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

    payload = {
        "model": "gpt-4o",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": """Analyze this image. Answer:
1. EXTERIOR: Is this an EXTERIOR shot of a building? (YES/NO/UNCERTAIN)
2. BUILDING: Does this show an actual BUILDING? (YES/NO/UNCERTAIN)
3. QUALITY: Is image quality acceptable? (YES/NO)

Respond ONLY in JSON: {"exterior": "YES/NO/UNCERTAIN", "building": "YES/NO/UNCERTAIN", "quality": "YES/NO", "confidence": 0-100, "reasoning": "brief"}"""},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}}
            ]
        }],
        "max_tokens": 200
    }

    try:
        resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            match = re.search(r'\{[^{}]+\}', content, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return {"score": data.get("confidence", 0), "exterior": data.get("exterior", "NO"),
                        "building": data.get("building", "NO"), "reasoning": data.get("reasoning", "")}
    except Exception as e:
        pass
    return {"score": 0, "exterior": "NO", "building": "NO", "reasoning": "API error"}

def validate_claude(image_path: str, address: str, bldg_type: str) -> dict:
    """Claude validation."""
    b64 = encode_image_base64(image_path)
    headers = {"x-api-key": ANTHROPIC_API_KEY, "Content-Type": "application/json", "anthropic-version": "2023-06-01"}

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 300,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                {"type": "text", "text": f"""Verify this building image.
Address: {address}
Type: {bldg_type}

Check: 1) Is this a COMMERCIAL building? 2) Is this a real photo? 3) Could this be the building at this address?

Respond ONLY in JSON: {{"is_commercial": true/false, "is_real_photo": true/false, "confidence": 0-100, "reasoning": "brief"}}"""}
            ]
        }]
    }

    try:
        resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            content = resp.json()["content"][0]["text"]
            match = re.search(r'\{[^{}]+\}', content, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return {"score": data.get("confidence", 0), "commercial": data.get("is_commercial", False),
                        "reasoning": data.get("reasoning", "")}
    except:
        pass
    return {"score": 0, "commercial": False, "reasoning": "API error"}

# =============================================================================
# THUMBNAIL
# =============================================================================
def create_thumbnail(image_path: str, thumbnail_path: str, size: tuple = (300, 200)) -> bool:
    try:
        img = Image.open(image_path)
        img.thumbnail(size, Image.Resampling.LANCZOS)
        img.save(thumbnail_path, "JPEG", quality=85)
        return True
    except:
        return False

# =============================================================================
# AWS S3 UPLOAD
# =============================================================================
def upload_to_s3(local_path: str, s3_key: str) -> bool:
    """Upload file to S3."""
    try:
        s3 = boto3.client('s3', region_name=AWS_REGION)
        s3.upload_file(local_path, AWS_BUCKET, s3_key,
                       ExtraArgs={'ContentType': 'image/jpeg', 'CacheControl': 'max-age=3600'})
        return True
    except Exception as e:
        return False

def upload_image_and_thumbnail(building_id: str, filename: str):
    """Upload both full image and thumbnail to S3."""
    image_path = str(IMAGES_DIR / filename)
    thumb_path = str(THUMBNAILS_DIR / filename)

    # Upload full image
    s3_image_key = f"{AWS_IMAGES_PREFIX}{filename}"
    img_ok = upload_to_s3(image_path, s3_image_key)
    log.upload(filename, "ok" if img_ok else "FAILED")

    # Upload thumbnail
    if os.path.exists(thumb_path):
        s3_thumb_key = f"{AWS_THUMBNAILS_PREFIX}{filename}"
        thumb_ok = upload_to_s3(thumb_path, s3_thumb_key)
        log.upload(f"thumb/{filename}", "ok" if thumb_ok else "FAILED")

# =============================================================================
# MAIN PROCESSING
# =============================================================================
def get_buildings_with_images() -> Set[str]:
    """Get building IDs that already have images."""
    building_ids = set()
    for f in os.listdir(IMAGES_DIR):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            match = re.match(r'^(.+)_[^_]+\.\w+$', f)
            if match:
                building_ids.add(match.group(1))
    return building_ids

def get_buildings_missing_images() -> pd.DataFrame:
    """Get commercial buildings missing images."""
    df = pd.read_csv(BUILDING_DATA_PATH, low_memory=False)
    have_images = get_buildings_with_images()
    commercial = df[df['bldg_vertical'] == 'Commercial'].copy()
    missing = commercial[~commercial['id_building'].astype(str).isin(have_images)]
    if 'savings_opex_avoided_annual_usd' in missing.columns:
        missing = missing.sort_values('savings_opex_avoided_annual_usd', ascending=False)
    return missing

def process_building(row: pd.Series, state: dict) -> str:
    """Process single building. Returns status: SUCCESS, FAILED, NO_IMAGE"""
    building_id = str(row['id_building'])
    lat = row.get('loc_lat')
    lon = row.get('loc_lon')
    address = str(row.get('loc_address', ''))
    city = str(row.get('loc_city', ''))
    bldg_type = str(row.get('bldg_type', 'Commercial'))
    full_address = f"{address}, {city}"

    # Fetch candidates from multiple sources
    candidates = []

    # 1. Google Street View
    if pd.notna(lat) and pd.notna(lon):
        url = fetch_google_streetview(float(lat), float(lon))
        if url:
            candidates.append(("streetview", url))
            log.fetch("Google Street View", "found")
        else:
            log.fetch("Google Street View", "no imagery")

    # 2. Mapillary
    if pd.notna(lat) and pd.notna(lon) and len(candidates) < 3:
        url = fetch_mapillary(float(lat), float(lon))
        if url:
            candidates.append(("Mapillary", url))
            log.fetch("Mapillary", "found")
        else:
            log.fetch("Mapillary", "no imagery")

    # 3. SerpAPI
    if address and len(candidates) < 3:
        url = fetch_serpapi(address, city)
        if url:
            candidates.append(("Serpapi", url))
            log.fetch("SerpAPI", "found")
        else:
            log.fetch("SerpAPI", "no results")

    # 4. Bing
    if address and len(candidates) < 2:
        url = fetch_bing(address, city)
        if url:
            candidates.append(("Bing", url))
            log.fetch("Bing", "found")
        else:
            log.fetch("Bing", "no results")

    if not candidates:
        log.fail("No candidates from any source")
        return "NO_IMAGE"

    # Validate each candidate
    best_source = None
    best_score = 0
    best_path = None

    for source, url in candidates:
        temp_path = str(CANDIDATES_DIR / f"{building_id}_{source}_temp.jpg")

        if not download_image(url, temp_path):
            log.validate(source, 0, False, "download failed")
            continue

        # GPT-4o validation
        gpt = validate_gpt4o(temp_path)

        # Early reject
        if gpt["exterior"] == "NO" or gpt["building"] == "NO":
            log.validate(source, gpt["score"], False, f"GPT4o: {gpt['reasoning'][:50]}")
            os.remove(temp_path)
            continue

        # Claude validation
        claude = validate_claude(temp_path, full_address, bldg_type)

        # Final score
        final_score = int(gpt["score"] * 0.4 + claude["score"] * 0.6)
        approved = final_score >= FINAL_APPROVE_THRESHOLD and gpt["exterior"] != "NO" and gpt["building"] != "NO"

        log.validate(source, final_score, approved, f"GPT:{gpt['score']} Claude:{claude['score']}")

        if approved and final_score > best_score:
            if best_path and os.path.exists(best_path):
                os.remove(best_path)
            best_source = source
            best_score = final_score
            best_path = temp_path
        else:
            os.remove(temp_path)

        time.sleep(0.5)

    # Save best image
    if best_source and best_path:
        filename = f"{building_id}_{best_source}.jpg"
        final_path = str(IMAGES_DIR / filename)
        thumb_path = str(THUMBNAILS_DIR / filename)

        shutil.copy(best_path, final_path)
        create_thumbnail(final_path, thumb_path)
        os.remove(best_path)

        log.success(filename, best_score)

        # Upload to S3
        upload_image_and_thumbnail(building_id, filename)

        return "SUCCESS"
    else:
        log.fail("All candidates failed validation")
        return "FAILED"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, help="Max buildings to process")
    parser.add_argument("--reset", action="store_true", help="Reset state, start fresh")
    args = parser.parse_args()

    # Setup directories
    for d in [STAGING_DIR, CANDIDATES_DIR, LOGS_DIR, THUMBNAILS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # Handle reset
    if args.reset:
        reset_state()

    # Load state
    state = load_state()
    processed_set = set(state["processed"])

    log.header("BUILDING IMAGE PIPELINE v2")
    print(f"    Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"    Previously processed: {len(processed_set)}")

    # Get buildings to process
    log.section("LOADING DATA")
    missing = get_buildings_missing_images()
    print(f"    Commercial buildings missing images: {len(missing)}")

    # Filter out already processed
    missing = missing[~missing['id_building'].astype(str).isin(processed_set)]
    print(f"    Remaining to process: {len(missing)}")

    if args.max:
        missing = missing.head(args.max)
        print(f"    Limited to: {args.max}")

    if len(missing) == 0:
        print("\n    Nothing to process!")
        return

    log.section("PROCESSING BUILDINGS")

    success_count = len(state["success"])
    failed_count = len(state["failed"])
    no_image_count = len(state["no_image"])

    for idx, (_, row) in enumerate(missing.iterrows(), 1):
        building_id = str(row['id_building'])
        address = str(row.get('loc_address', ''))
        city = str(row.get('loc_city', ''))

        log.building(idx, len(missing), building_id, f"{address}, {city}")

        try:
            status = process_building(row, state)

            # Update state
            state["processed"].append(building_id)
            if status == "SUCCESS":
                state["success"].append(building_id)
                success_count += 1
            elif status == "FAILED":
                state["failed"].append(building_id)
                failed_count += 1
            else:
                state["no_image"].append(building_id)
                no_image_count += 1

            # Save state after each building
            save_state(state)

        except Exception as e:
            log.fail(f"Exception: {e}")
            state["processed"].append(building_id)
            state["failed"].append(building_id)
            failed_count += 1
            save_state(state)

        time.sleep(1)

    # Final stats
    log.stats(success_count, failed_count, no_image_count, len(state["processed"]))
    print(f"\n    State saved to: {STATE_FILE}")
    print(f"    Run again to continue from where you left off")

if __name__ == "__main__":
    main()
