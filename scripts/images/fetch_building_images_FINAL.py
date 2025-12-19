#!/usr/bin/env python3
"""
BUILDING IMAGE FETCHER - FINAL VERSION
=======================================
Fetches, validates, and uploads building images from multiple sources.

Features:
- 7 image sources: Google Street View, Mapillary, SerpAPI, Bing, Yelp, Flickr, TripAdvisor
- Dual AI validation: GPT-4o (exterior/building check) + Claude (commercial/address match)
- Resume capability (picks up where left off)
- AWS S3 upload with thumbnails
- Verbose logging with ETA

Usage:
    python scripts/images/fetch_building_images_FINAL.py
    python scripts/images/fetch_building_images_FINAL.py --max 100
    python scripts/images/fetch_building_images_FINAL.py --building-id SF_40160012024
    python scripts/images/fetch_building_images_FINAL.py --reset
    python scripts/images/fetch_building_images_FINAL.py --skip-upload
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
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple, Set
import argparse

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import BUILDING_DATA_PATH, IMAGES_DIR, AWS_BUCKET, AWS_REGION

try:
    from PIL import Image
except ImportError:
    print("ERROR: PIL not installed. Run: pip install Pillow")
    sys.exit(1)

try:
    import boto3
except ImportError:
    print("WARNING: boto3 not installed. S3 upload disabled.")
    boto3 = None

# =============================================================================
# PATHS
# =============================================================================
THUMBNAILS_DIR = Path(IMAGES_DIR).parent / "thumbnails"
STAGING_DIR = Path(__file__).parent.parent.parent / "staging" / "building_images"
CANDIDATES_DIR = STAGING_DIR / "candidates"
LOGS_DIR = STAGING_DIR / "logs"
STATE_FILE = STAGING_DIR / "pipeline_state.json"

# =============================================================================
# API KEYS (from environment)
# =============================================================================
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
YELP_API_KEY = os.environ.get("YELP_API_KEY", "")
FLICKR_KEY = os.environ.get("FLICKR_KEY", "")
TRIPADVISOR_KEY = os.environ.get("TRIPADVISOR_KEY", "")
MAPILLARY_TOKEN = os.environ.get("MAPILLARY_TOKEN", "")
BING_KEY = os.environ.get("BING_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# AWS
AWS_IMAGES_PREFIX = "images/"
AWS_THUMBNAILS_PREFIX = "thumbnails/"

# Validation thresholds
GPT4O_MIN_SCORE = 40
CLAUDE_MIN_SCORE = 40
FINAL_APPROVE_THRESHOLD = 50

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
    gpt4o_is_exterior: bool = False
    gpt4o_is_building: bool = False
    gpt4o_is_correct_building: bool = False
    gpt4o_reasoning: str = ""
    claude_score: int = 0
    claude_is_commercial: bool = False
    claude_is_real_photo: bool = False
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
    best_source: str = ""
    final_status: str = ""  # SUCCESS, NO_IMAGE, VALIDATION_FAILED
    error: str = ""

# =============================================================================
# STATE MANAGEMENT (for resume)
# =============================================================================
def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"processed": [], "success": [], "failed": [], "no_image": []}

def save_state(state: dict):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def reset_state():
    if STATE_FILE.exists():
        os.remove(STATE_FILE)
    print("State reset - starting fresh")

# =============================================================================
# LOGGING
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
        pct = (idx / total) * 100 if total > 0 else 0
        elapsed = (datetime.now() - self.start_time).total_seconds()
        rate = idx / elapsed if elapsed > 0 else 0
        eta_mins = ((total - idx) / rate / 60) if rate > 0 else 0

        print(f"\n[{idx}/{total}] ({pct:.1f}%) {building_id}")
        print(f"    Address: {address[:70]}")
        if idx > 1:
            print(f"    Rate: {rate*60:.1f}/hr | ETA: {eta_mins:.0f} min")

    def fetch(self, source: str, status: str, found: bool = False):
        icon = "+" if found else "-"
        print(f"    {icon} {source}: {status}")

    def validate(self, source: str, gpt_score: int, claude_score: int, final_score: int, approved: bool):
        icon = "OK" if approved else "NO"
        print(f"    [{icon}] {source}: GPT={gpt_score} Claude={claude_score} Final={final_score}")

    def success(self, filename: str, score: int, source: str):
        print(f"    >>> SUCCESS: {filename} (score={score}, source={source})")

    def fail(self, reason: str):
        print(f"    XXX FAILED: {reason}")

    def upload(self, filename: str, ok: bool):
        status = "uploaded" if ok else "FAILED"
        print(f"    S3: {filename} {status}")

log = Logger()

# =============================================================================
# IMAGE FETCHING - 7 SOURCES
# =============================================================================

def fetch_google_streetview(lat: float, lon: float, building_id: str) -> Optional[ImageCandidate]:
    """1. Google Street View - best for most buildings."""
    if not GOOGLE_API_KEY or pd.isna(lat) or pd.isna(lon):
        return None

    # Check if imagery exists
    meta_url = f"https://maps.googleapis.com/maps/api/streetview/metadata?location={lat},{lon}&key={GOOGLE_API_KEY}"
    try:
        resp = requests.get(meta_url, timeout=10)
        if resp.status_code != 200 or resp.json().get('status') != 'OK':
            return None
    except:
        return None

    url = f"https://maps.googleapis.com/maps/api/streetview?size=640x480&location={lat},{lon}&fov=90&pitch=10&key={GOOGLE_API_KEY}"
    return ImageCandidate(url=url, source="streetview")


def fetch_mapillary(lat: float, lon: float, building_id: str) -> Optional[ImageCandidate]:
    """2. Mapillary - crowdsourced street-level imagery."""
    if not MAPILLARY_TOKEN or pd.isna(lat) or pd.isna(lon):
        return None

    delta = 0.0005  # ~50m bounding box
    bbox = f"{lon-delta},{lat-delta},{lon+delta},{lat+delta}"
    params = {
        "access_token": MAPILLARY_TOKEN,
        "bbox": bbox,
        "fields": "id,thumb_1024_url",
        "limit": 5
    }

    try:
        resp = requests.get("https://graph.mapillary.com/images", params=params, timeout=15)
        if resp.status_code == 200:
            for img in resp.json().get("data", []):
                if img.get("thumb_1024_url"):
                    return ImageCandidate(url=img["thumb_1024_url"], source="Mapillary")
    except:
        pass
    return None


def fetch_serpapi(address: str, city: str, name: str, building_id: str) -> Optional[ImageCandidate]:
    """3. SerpAPI (Google Images) - good for named buildings."""
    if not SERPAPI_KEY:
        return None

    # Build search query - include name if available
    if name and name.strip():
        query = f"{name} {address} {city} building exterior"
    else:
        query = f"{address} {city} building exterior"

    params = {
        "engine": "google_images",
        "q": query,
        "api_key": SERPAPI_KEY,
        "num": 10
    }

    bad_keywords = ["interior", "inside", "room", "lobby", "floor plan", "map", "logo", "icon", "blueprint", "rendering"]

    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
        if resp.status_code == 200:
            for img in resp.json().get("images_results", []):
                title = img.get("title", "").lower()
                if any(kw in title for kw in bad_keywords):
                    continue
                img_url = img.get("original") or img.get("thumbnail")
                if img_url:
                    return ImageCandidate(url=img_url, source="SerpApi")
    except:
        pass
    return None


def fetch_bing(address: str, city: str, name: str, building_id: str) -> Optional[ImageCandidate]:
    """4. Bing Image Search - alternative to Google."""
    if not BING_KEY:
        return None

    if name and name.strip():
        query = f"{name} {address} {city} building exterior"
    else:
        query = f"{address} {city} building exterior"

    headers = {"Ocp-Apim-Subscription-Key": BING_KEY}
    params = {"q": query, "count": 10, "imageType": "Photo", "safeSearch": "Moderate"}

    bad_keywords = ["interior", "inside", "room", "floor", "plan", "map", "logo"]

    try:
        resp = requests.get("https://api.bing.microsoft.com/v7.0/images/search",
                           headers=headers, params=params, timeout=15)
        if resp.status_code == 200:
            for img in resp.json().get("value", []):
                name_check = img.get("name", "").lower()
                if any(kw in name_check for kw in bad_keywords):
                    continue
                if img.get("contentUrl"):
                    return ImageCandidate(url=img["contentUrl"], source="Bing")
    except:
        pass
    return None


def fetch_yelp(name: str, lat: float, lon: float, building_id: str) -> Optional[ImageCandidate]:
    """5. Yelp - good for retail/restaurant buildings."""
    if not YELP_API_KEY or not name or pd.isna(lat) or pd.isna(lon):
        return None

    headers = {"Authorization": f"Bearer {YELP_API_KEY}"}
    params = {"term": name, "latitude": lat, "longitude": lon, "radius": 200, "limit": 1}

    try:
        resp = requests.get("https://api.yelp.com/v3/businesses/search",
                           headers=headers, params=params, timeout=15)
        if resp.status_code == 200:
            businesses = resp.json().get("businesses", [])
            if businesses:
                biz_id = businesses[0].get("id")
                detail_resp = requests.get(f"https://api.yelp.com/v3/businesses/{biz_id}",
                                          headers=headers, timeout=15)
                if detail_resp.status_code == 200:
                    photos = detail_resp.json().get("photos", [])
                    if photos:
                        return ImageCandidate(url=photos[0], source="Yelp")
    except:
        pass
    return None


def fetch_flickr(address: str, city: str, lat: float, lon: float, building_id: str) -> Optional[ImageCandidate]:
    """6. Flickr - crowdsourced photos, good for landmarks."""
    if not FLICKR_KEY:
        return None

    # Try geo search first
    params = {
        "method": "flickr.photos.search",
        "api_key": FLICKR_KEY,
        "format": "json",
        "nojsoncallback": 1,
        "per_page": 10,
        "extras": "url_l,url_m",
        "content_type": 1,  # Photos only
        "media": "photos"
    }

    # Add location if available
    if pd.notna(lat) and pd.notna(lon):
        params["lat"] = lat
        params["lon"] = lon
        params["radius"] = 0.1  # km
    else:
        params["text"] = f"{address} {city} building"

    try:
        resp = requests.get("https://api.flickr.com/services/rest/", params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            photos = data.get("photos", {}).get("photo", [])
            for photo in photos:
                # Prefer large, fall back to medium
                url = photo.get("url_l") or photo.get("url_m")
                if url:
                    return ImageCandidate(url=url, source="Flickr")
    except:
        pass
    return None


def fetch_tripadvisor(name: str, address: str, lat: float, lon: float, building_id: str) -> Optional[ImageCandidate]:
    """7. TripAdvisor - good for hotels and tourist destinations."""
    if not TRIPADVISOR_KEY or not name:
        return None

    # Search for location
    headers = {"accept": "application/json"}
    params = {
        "key": TRIPADVISOR_KEY,
        "searchQuery": f"{name} {address}",
        "language": "en"
    }

    if pd.notna(lat) and pd.notna(lon):
        params["latLong"] = f"{lat},{lon}"

    try:
        resp = requests.get("https://api.content.tripadvisor.com/api/v1/location/search",
                           headers=headers, params=params, timeout=15)
        if resp.status_code == 200:
            locations = resp.json().get("data", [])
            if locations:
                location_id = locations[0].get("location_id")
                # Get photos for this location
                photo_params = {"key": TRIPADVISOR_KEY, "language": "en"}
                photo_resp = requests.get(
                    f"https://api.content.tripadvisor.com/api/v1/location/{location_id}/photos",
                    headers=headers, params=photo_params, timeout=15
                )
                if photo_resp.status_code == 200:
                    photos = photo_resp.json().get("data", [])
                    for photo in photos:
                        images = photo.get("images", {})
                        # Get largest available
                        for size in ["original", "large", "medium"]:
                            if size in images and images[size].get("url"):
                                return ImageCandidate(url=images[size]["url"], source="TripAdvisor")
    except:
        pass
    return None


def download_image(candidate: ImageCandidate, save_path: str) -> bool:
    """Download image to local path."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
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
# AI VALIDATION - GPT-4o + Claude
# =============================================================================

def encode_image_base64(image_path: str) -> str:
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def validate_with_gpt4o(image_path: str, address: str, city: str, building_name: str) -> dict:
    """
    GPT-4o validation - checks:
    1. Is this an EXTERIOR shot (not interior)?
    2. Does this show a real BUILDING (not logo, map, person)?
    3. Could this be the CORRECT building at the given address?
    """
    if not OPENAI_API_KEY:
        return {"score": 0, "is_exterior": False, "is_building": False,
                "is_correct": False, "reasoning": "No API key"}

    b64 = encode_image_base64(image_path)

    # Build context about the building
    building_context = f"Address: {address}, {city}"
    if building_name and building_name.strip():
        building_context = f"Building: {building_name}\n{building_context}"

    prompt = f"""Analyze this image for a commercial real estate database.

{building_context}

You must determine THREE things:

1. EXTERIOR: Is this an EXTERIOR photograph of a building?
   - YES if: outdoor shot showing building facade, entrance, or full structure
   - NO if: interior shot (lobby, hallway, office, room inside), aerial/satellite view only showing roof

2. BUILDING: Does this image show an actual BUILDING structure?
   - YES if: shows a real building (office, hotel, retail, warehouse, etc.)
   - NO if: logo, map, floor plan, sign only, person, landscape without building, construction rendering

3. CORRECT BUILDING: Could this plausibly be the building at {address}, {city}?
   - YES if: the building style/size matches what you'd expect at this address
   - UNCERTAIN if: can't tell from the image
   - NO if: clearly a different building (wrong city visible, residential home, etc.)

Respond ONLY with this exact JSON format:
{{
    "is_exterior": true or false,
    "is_building": true or false,
    "is_correct_building": true or false or "uncertain",
    "confidence": 0-100,
    "reasoning": "brief 1-sentence explanation"
}}"""

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}}
            ]
        }],
        "max_tokens": 300
    }

    try:
        resp = requests.post("https://api.openai.com/v1/chat/completions",
                            headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            # Parse JSON
            match = re.search(r'\{[^{}]+\}', content, re.DOTALL)
            if match:
                data = json.loads(match.group())
                is_correct = data.get("is_correct_building", False)
                if is_correct == "uncertain":
                    is_correct = True  # Give benefit of doubt
                return {
                    "score": data.get("confidence", 0),
                    "is_exterior": data.get("is_exterior", False),
                    "is_building": data.get("is_building", False),
                    "is_correct": is_correct if isinstance(is_correct, bool) else True,
                    "reasoning": data.get("reasoning", "")
                }
    except Exception as e:
        pass

    return {"score": 0, "is_exterior": False, "is_building": False,
            "is_correct": False, "reasoning": "API error"}


def validate_with_claude(image_path: str, address: str, city: str, building_type: str) -> dict:
    """
    Claude validation - checks:
    1. Is this a COMMERCIAL building (not residential)?
    2. Is this a real PHOTO (not rendering/illustration)?
    """
    if not ANTHROPIC_API_KEY:
        return {"score": 0, "is_commercial": False, "is_real_photo": False, "reasoning": "No API key"}

    b64 = encode_image_base64(image_path)

    prompt = f"""Verify this building image for a commercial real estate database.

Building Information:
- Address: {address}, {city}
- Expected Type: {building_type or 'Commercial'}

Determine:
1. Is this a COMMERCIAL building (office, retail, hotel, industrial, medical, etc.)?
   - NO if: single-family home, apartment building, residential condo

2. Is this a REAL PHOTOGRAPH?
   - NO if: 3D rendering, architectural illustration, sketch, stock graphic, satellite/map screenshot

Respond ONLY with this exact JSON:
{{
    "is_commercial": true or false,
    "is_real_photo": true or false,
    "confidence": 0-100,
    "reasoning": "brief explanation"
}}"""

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01"
    }
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 300,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                {"type": "text", "text": prompt}
            ]
        }]
    }

    try:
        resp = requests.post("https://api.anthropic.com/v1/messages",
                            headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            content = resp.json()["content"][0]["text"]
            match = re.search(r'\{[^{}]+\}', content, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return {
                    "score": data.get("confidence", 0),
                    "is_commercial": data.get("is_commercial", False),
                    "is_real_photo": data.get("is_real_photo", False),
                    "reasoning": data.get("reasoning", "")
                }
    except:
        pass

    return {"score": 0, "is_commercial": False, "is_real_photo": False, "reasoning": "API error"}


def validate_image(image_path: str, address: str, city: str,
                   building_name: str, building_type: str) -> ValidationResult:
    """Run full dual-AI validation pipeline."""
    result = ValidationResult()

    # Round 1: GPT-4o
    gpt = validate_with_gpt4o(image_path, address, city, building_name)
    result.gpt4o_score = gpt["score"]
    result.gpt4o_is_exterior = gpt["is_exterior"]
    result.gpt4o_is_building = gpt["is_building"]
    result.gpt4o_is_correct_building = gpt["is_correct"]
    result.gpt4o_reasoning = gpt["reasoning"]

    # Early reject if clearly wrong
    if not gpt["is_exterior"] or not gpt["is_building"]:
        result.final_score = min(gpt["score"], 30)
        result.approved = False
        return result

    # Round 2: Claude
    claude = validate_with_claude(image_path, address, city, building_type)
    result.claude_score = claude["score"]
    result.claude_is_commercial = claude["is_commercial"]
    result.claude_is_real_photo = claude["is_real_photo"]
    result.claude_reasoning = claude["reasoning"]

    # Calculate final score (weighted: GPT 40%, Claude 60%)
    result.final_score = int(gpt["score"] * 0.4 + claude["score"] * 0.6)

    # Approval criteria:
    # - Must be exterior shot of a building
    # - Must be commercial (or at least not clearly residential)
    # - Must be real photo
    # - Must have reasonable confidence
    result.approved = (
        result.final_score >= FINAL_APPROVE_THRESHOLD and
        gpt["is_exterior"] and
        gpt["is_building"] and
        (claude["is_commercial"] or claude["score"] >= 60) and  # Allow if high confidence
        claude["is_real_photo"]
    )

    return result


# =============================================================================
# THUMBNAIL & S3 UPLOAD
# =============================================================================

def create_thumbnail(image_path: str, thumbnail_path: str, size: tuple = (300, 200)) -> bool:
    try:
        img = Image.open(image_path)
        img.thumbnail(size, Image.Resampling.LANCZOS)
        # Convert to RGB if necessary (for PNG with transparency)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        img.save(thumbnail_path, "JPEG", quality=85)
        return True
    except Exception as e:
        print(f"      Thumbnail error: {e}")
        return False


def upload_to_s3(local_path: str, s3_key: str) -> bool:
    if not boto3:
        return False
    try:
        s3 = boto3.client('s3', region_name=AWS_REGION)
        s3.upload_file(local_path, AWS_BUCKET, s3_key,
                      ExtraArgs={'ContentType': 'image/jpeg', 'CacheControl': 'max-age=3600'})
        return True
    except Exception as e:
        return False


# =============================================================================
# MAIN PIPELINE
# =============================================================================

def get_buildings_with_images() -> Set[str]:
    """Get building IDs that already have images."""
    building_ids = set()
    if not os.path.exists(IMAGES_DIR):
        return building_ids
    for f in os.listdir(IMAGES_DIR):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            # Extract building_id (everything before last underscore)
            match = re.match(r'^(.+)_[^_]+\.\w+$', f)
            if match:
                building_ids.add(match.group(1))
    return building_ids


def get_buildings_missing_images(building_ids: Optional[List[str]] = None) -> pd.DataFrame:
    """Get commercial buildings missing images."""
    df = pd.read_csv(BUILDING_DATA_PATH, low_memory=False)

    if building_ids:
        return df[df['id_building'].isin(building_ids)]

    have_images = get_buildings_with_images()
    commercial = df[df['bldg_vertical'] == 'Commercial'].copy()
    missing = commercial[~commercial['id_building'].astype(str).isin(have_images)]

    # Sort by value (highest first)
    if 'savings_opex_avoided_annual_usd' in missing.columns:
        missing = missing.sort_values('savings_opex_avoided_annual_usd', ascending=False)

    return missing


def fetch_candidates(row: pd.Series) -> List[ImageCandidate]:
    """Fetch image candidates from all sources."""
    candidates = []

    building_id = str(row['id_building'])
    lat = row.get('loc_lat')
    lon = row.get('loc_lon')
    address = str(row.get('loc_address', ''))
    city = str(row.get('loc_city', ''))
    name = str(row.get('id_property_name', '')) if pd.notna(row.get('id_property_name')) else ''
    bldg_type = str(row.get('bldg_type', ''))

    # 1. Google Street View (most reliable for address matching)
    if pd.notna(lat) and pd.notna(lon):
        c = fetch_google_streetview(float(lat), float(lon), building_id)
        if c:
            candidates.append(c)
            log.fetch("Street View", "found", True)
        else:
            log.fetch("Street View", "no imagery")

    # 2. Mapillary (backup street-level)
    if len(candidates) < 3 and pd.notna(lat) and pd.notna(lon):
        c = fetch_mapillary(float(lat), float(lon), building_id)
        if c:
            candidates.append(c)
            log.fetch("Mapillary", "found", True)
        else:
            log.fetch("Mapillary", "no imagery")

    # 3. SerpAPI Google Images
    if len(candidates) < 3 and address:
        c = fetch_serpapi(address, city, name, building_id)
        if c:
            candidates.append(c)
            log.fetch("SerpAPI", "found", True)
        else:
            log.fetch("SerpAPI", "no results")

    # 4. Bing Images
    if len(candidates) < 3 and address:
        c = fetch_bing(address, city, name, building_id)
        if c:
            candidates.append(c)
            log.fetch("Bing", "found", True)
        else:
            log.fetch("Bing", "no results")

    # 5. Yelp (for retail/restaurant)
    if len(candidates) < 3 and name and pd.notna(lat) and pd.notna(lon):
        c = fetch_yelp(name, float(lat), float(lon), building_id)
        if c:
            candidates.append(c)
            log.fetch("Yelp", "found", True)
        else:
            log.fetch("Yelp", "no match")

    # 6. Flickr
    if len(candidates) < 3:
        lat_val = float(lat) if pd.notna(lat) else None
        lon_val = float(lon) if pd.notna(lon) else None
        c = fetch_flickr(address, city, lat_val, lon_val, building_id)
        if c:
            candidates.append(c)
            log.fetch("Flickr", "found", True)
        else:
            log.fetch("Flickr", "no results")

    # 7. TripAdvisor (for hotels/landmarks)
    if len(candidates) < 3 and name:
        lat_val = float(lat) if pd.notna(lat) else None
        lon_val = float(lon) if pd.notna(lon) else None
        c = fetch_tripadvisor(name, address, lat_val, lon_val, building_id)
        if c:
            candidates.append(c)
            log.fetch("TripAdvisor", "found", True)
        else:
            log.fetch("TripAdvisor", "no match")

    return candidates


def process_building(row: pd.Series, skip_upload: bool = False) -> BuildingResult:
    """Process a single building: fetch, validate, save, upload."""
    building_id = str(row['id_building'])
    address = str(row.get('loc_address', ''))
    city = str(row.get('loc_city', ''))
    name = str(row.get('id_property_name', '')) if pd.notna(row.get('id_property_name')) else ''
    bldg_type = str(row.get('bldg_type', 'Commercial'))

    result = BuildingResult(
        building_id=building_id,
        address=f"{address}, {city}",
        city=city
    )

    # Fetch candidates
    candidates = fetch_candidates(row)
    result.candidates_fetched = len(candidates)

    if not candidates:
        result.final_status = "NO_IMAGE"
        log.fail("No candidates from any source")
        return result

    # Validate each candidate
    best_candidate = None
    best_validation = None
    best_score = 0

    for candidate in candidates:
        temp_path = str(CANDIDATES_DIR / f"{building_id}_{candidate.source}_temp.jpg")

        if not download_image(candidate, temp_path):
            continue

        result.candidates_validated += 1

        # Full AI validation
        validation = validate_image(temp_path, address, city, name, bldg_type)

        log.validate(candidate.source, validation.gpt4o_score, validation.claude_score,
                    validation.final_score, validation.approved)

        if validation.approved and validation.final_score > best_score:
            # Clean up previous best
            if best_candidate and best_candidate.local_path and os.path.exists(best_candidate.local_path):
                try:
                    os.remove(best_candidate.local_path)
                except:
                    pass

            best_score = validation.final_score
            best_candidate = candidate
            best_candidate.local_path = temp_path
            best_validation = validation
        else:
            # Clean up rejected
            try:
                os.remove(temp_path)
            except:
                pass

        time.sleep(0.5)  # Rate limit

    # Save best image
    if best_candidate and best_validation and best_validation.approved:
        filename = f"{building_id}_{best_candidate.source}.jpg"
        final_path = str(IMAGES_DIR / filename)
        thumb_path = str(THUMBNAILS_DIR / filename)

        try:
            shutil.copy(best_candidate.local_path, final_path)
            create_thumbnail(final_path, thumb_path)
            os.remove(best_candidate.local_path)

            result.best_image = filename
            result.best_score = best_score
            result.best_source = best_candidate.source
            result.final_status = "SUCCESS"

            log.success(filename, best_score, best_candidate.source)

            # Upload to S3
            if not skip_upload:
                img_ok = upload_to_s3(final_path, f"{AWS_IMAGES_PREFIX}{filename}")
                log.upload(filename, img_ok)
                if os.path.exists(thumb_path):
                    thumb_ok = upload_to_s3(thumb_path, f"{AWS_THUMBNAILS_PREFIX}{filename}")
                    log.upload(f"thumb/{filename}", thumb_ok)

        except Exception as e:
            result.final_status = "SAVE_ERROR"
            result.error = str(e)
            log.fail(f"Save error: {e}")
    else:
        result.final_status = "VALIDATION_FAILED"
        log.fail("All candidates failed validation")

    return result


def main():
    parser = argparse.ArgumentParser(description="Fetch and validate building images")
    parser.add_argument("--max", type=int, help="Max buildings to process")
    parser.add_argument("--building-id", type=str, help="Process single building by ID")
    parser.add_argument("--building-ids", type=str, help="Comma-separated building IDs")
    parser.add_argument("--reset", action="store_true", help="Reset state, start fresh")
    parser.add_argument("--skip-upload", action="store_true", help="Skip S3 upload")
    args = parser.parse_args()

    # Setup directories
    for d in [STAGING_DIR, CANDIDATES_DIR, LOGS_DIR, THUMBNAILS_DIR, IMAGES_DIR]:
        Path(d).mkdir(parents=True, exist_ok=True)

    # Handle reset
    if args.reset:
        reset_state()

    # Load state
    state = load_state()
    processed_set = set(state["processed"])

    log.header("BUILDING IMAGE FETCHER - FINAL VERSION")
    print(f"    Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"    Previously processed: {len(processed_set)}")

    # Check API keys
    print("\n    API Keys:")
    print(f"      Google: {'OK' if GOOGLE_API_KEY else 'MISSING'}")
    print(f"      SerpAPI: {'OK' if SERPAPI_KEY else 'MISSING'}")
    print(f"      Bing: {'OK' if BING_KEY else 'MISSING'}")
    print(f"      Yelp: {'OK' if YELP_API_KEY else 'MISSING'}")
    print(f"      Flickr: {'OK' if FLICKR_KEY else 'MISSING'}")
    print(f"      TripAdvisor: {'OK' if TRIPADVISOR_KEY else 'MISSING'}")
    print(f"      Mapillary: {'OK' if MAPILLARY_TOKEN else 'MISSING'}")
    print(f"      OpenAI: {'OK' if OPENAI_API_KEY else 'MISSING'}")
    print(f"      Anthropic: {'OK' if ANTHROPIC_API_KEY else 'MISSING'}")

    # Get buildings to process
    log.section("LOADING DATA")

    if args.building_id:
        missing = get_buildings_missing_images([args.building_id])
        print(f"    Processing single building: {args.building_id}")
    elif args.building_ids:
        ids = [x.strip() for x in args.building_ids.split(",")]
        missing = get_buildings_missing_images(ids)
        print(f"    Processing {len(ids)} specified buildings")
    else:
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
            result = process_building(row, skip_upload=args.skip_upload)

            # Update state
            state["processed"].append(building_id)
            if result.final_status == "SUCCESS":
                state["success"].append(building_id)
                success_count += 1
            elif result.final_status == "NO_IMAGE":
                state["no_image"].append(building_id)
                no_image_count += 1
            else:
                state["failed"].append(building_id)
                failed_count += 1

            save_state(state)

        except Exception as e:
            log.fail(f"Exception: {e}")
            state["processed"].append(building_id)
            state["failed"].append(building_id)
            failed_count += 1
            save_state(state)

        time.sleep(1)  # Rate limit between buildings

    # Summary
    total = len(state["processed"])
    log.header("COMPLETE")
    print(f"    Total processed: {total}")
    print(f"    Success: {success_count} ({100*success_count/max(total,1):.1f}%)")
    print(f"    Failed validation: {failed_count}")
    print(f"    No image found: {no_image_count}")
    print(f"\n    State saved to: {STATE_FILE}")
    print(f"    Run again to continue from where you left off")
    print(f"    Use --reset to start fresh")


if __name__ == "__main__":
    main()
