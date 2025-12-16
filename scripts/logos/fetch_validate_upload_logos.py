#!/usr/bin/env python3
"""
LOGO PIPELINE - Fetch, Validate, Remove BG, Resize, Upload to S3
=================================================================
Fetches logos for portfolio orgs missing them using SerpAPI,
validates with OpenAI Vision, removes background, resizes for web,
uploads to AWS S3, and updates CSV.

Usage:
    python scripts/logos/fetch_validate_upload_logos.py
    python scripts/logos/fetch_validate_upload_logos.py --max 50
    python scripts/logos/fetch_validate_upload_logos.py --reset
"""

import os
import sys
import re
import json
import time
import base64
import requests
import pandas as pd
import boto3
from pathlib import Path
from datetime import datetime
from typing import Optional, Set
from io import BytesIO
import argparse

try:
    from PIL import Image
except ImportError:
    print("ERROR: PIL not installed. Run: pip install Pillow")
    sys.exit(1)

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import LOGOS_DIR

# =============================================================================
# CONFIGURATION
# =============================================================================
PORTFOLIO_ORGS_CSV = Path(__file__).parent.parent.parent / "data" / "source" / "portfolio_organizations.csv"
STAGING_DIR = Path(__file__).parent.parent.parent / "staging" / "logos"
STATE_FILE = STAGING_DIR / "logo_pipeline_state.json"

# AWS
AWS_BUCKET = 'nationwide-odcv-images'
AWS_REGION = 'us-east-2'
AWS_LOGOS_PREFIX = 'logos/'

# API Keys (from environment variables)
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
REMOVEBG_API_KEY = os.environ.get("REMOVEBG_API_KEY", "")

# Logo optimization settings
MAX_LOGO_WIDTH = 400  # pixels
MAX_LOGO_HEIGHT = 200  # pixels
PNG_COMPRESSION = 6  # 0-9, higher = smaller file

# Thresholds
MIN_LOGO_SIZE = 2000  # bytes
MAX_LOGO_SIZE = 5000000  # 5MB
VALIDATION_THRESHOLD = 60

# =============================================================================
# STATE MANAGEMENT
# =============================================================================
def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"processed": [], "success": [], "failed": []}

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

    def org(self, idx: int, total: int, org_name: str):
        pct = (idx / total) * 100
        elapsed = (datetime.now() - self.start_time).total_seconds()
        rate = idx / elapsed if elapsed > 0 else 0
        print(f"\n[{idx}/{total}] ({pct:.1f}%) {org_name}")
        if rate > 0:
            eta = (total - idx) / rate / 60
            print(f"    Rate: {rate*60:.1f}/hr | ETA: {eta:.0f} min")

    def step(self, icon: str, msg: str):
        print(f"    {icon} {msg}")

    def success(self, filename: str):
        print(f"    ★ SUCCESS: {filename}")

    def fail(self, reason: str):
        print(f"    ✗ FAILED: {reason}")

log = Logger()

# =============================================================================
# SERPAPI SEARCH
# =============================================================================
def search_logo_serpapi(org_name: str) -> list:
    """Search for logo images using SerpAPI."""
    # Try different search queries
    queries = [
        f"{org_name} official logo",
        f"{org_name} company logo transparent",
        f"{org_name} logo"
    ]

    all_results = []
    seen_urls = set()

    for query in queries[:2]:  # Try first 2 queries
        params = {
            "engine": "google_images",
            "q": query,
            "api_key": SERPAPI_KEY,
            "num": 10,
            "safe": "active"
        }

        try:
            resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
            if resp.status_code == 200:
                for img in resp.json().get("images_results", []):
                    url = img.get("original") or img.get("thumbnail")
                    if url and url not in seen_urls:
                        # Skip stock photo sites
                        bad_sources = ['shutterstock', 'getty', 'istock', 'alamy', 'dreamstime', '123rf']
                        source = img.get("source", "").lower()
                        if not any(bad in source for bad in bad_sources):
                            seen_urls.add(url)
                            all_results.append({
                                "url": url,
                                "thumbnail": img.get("thumbnail"),
                                "title": img.get("title", ""),
                                "source": source
                            })
        except Exception as e:
            log.step("✗", f"SerpAPI error: {e}")

        time.sleep(0.3)

    log.step("🔍", f"SerpAPI found {len(all_results)} candidates")
    return all_results[:8]  # Return top 8

# =============================================================================
# OPENAI VALIDATION
# =============================================================================
def validate_logo_openai(image_path: str, org_name: str) -> dict:
    """Use OpenAI Vision to validate logo."""
    with open(image_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('utf-8')

    # Detect image type
    ext = image_path.lower().split('.')[-1]
    media_type = "image/png" if ext == "png" else "image/jpeg"

    prompt = f"""Analyze this image. I need the official LOGO for "{org_name}".

Check:
1. Is this a LOGO (graphic/vector design)? NOT a photo, building, or screenshot.
2. Does it appear to be for "{org_name}" or a similar company name?
3. Is it good quality (not blurry, no watermarks, reasonable resolution)?

Respond ONLY in JSON:
{{"is_logo": true/false, "matches_company": true/false, "good_quality": true/false, "confidence": 0-100, "reason": "brief explanation"}}"""

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}", "detail": "low"}}
            ]
        }],
        "max_tokens": 150
    }

    try:
        resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            match = re.search(r'\{[^{}]+\}', content, re.DOTALL)
            if match:
                data = json.loads(match.group())
                score = data.get("confidence", 0)
                is_logo = data.get("is_logo", False)
                matches = data.get("matches_company", False)
                quality = data.get("good_quality", False)

                approved = is_logo and matches and quality and score >= VALIDATION_THRESHOLD
                return {
                    "score": score,
                    "approved": approved,
                    "reason": data.get("reason", "")
                }
    except Exception as e:
        log.step("✗", f"OpenAI error: {e}")

    return {"score": 0, "approved": False, "reason": "API error"}

# =============================================================================
# DOWNLOAD & UPLOAD
# =============================================================================
def download_image(url: str, save_path: str) -> bool:
    """Download image to local path."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            content = resp.content
            if MIN_LOGO_SIZE <= len(content) <= MAX_LOGO_SIZE:
                with open(save_path, 'wb') as f:
                    f.write(content)
                return True
            else:
                log.step("✗", f"Size {len(content)} outside range")
    except Exception as e:
        pass
    return False

# =============================================================================
# BACKGROUND REMOVAL (remove.bg API)
# =============================================================================
def remove_background(image_path: str, output_path: str) -> bool:
    """Remove background using remove.bg API."""
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()

        response = requests.post(
            'https://api.remove.bg/v1.0/removebg',
            files={'image_file': image_data},
            data={'size': 'auto', 'format': 'png'},
            headers={'X-Api-Key': REMOVEBG_API_KEY},
            timeout=60
        )

        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response.content)
            log.step("✓", "Background removed")
            return True
        else:
            # Check for specific errors
            error_msg = response.json().get('errors', [{}])[0].get('title', 'Unknown error')
            log.step("⚠", f"remove.bg: {error_msg} - keeping original")
            return False
    except Exception as e:
        log.step("⚠", f"remove.bg error: {e} - keeping original")
        return False

def has_transparency(image_path: str) -> bool:
    """Check if image already has transparent background."""
    try:
        img = Image.open(image_path)
        if img.mode == 'RGBA':
            # Check if there are actually transparent pixels
            alpha = img.split()[-1]
            if alpha.getextrema()[0] < 255:  # Has some transparency
                return True
        return False
    except:
        return False

# =============================================================================
# RESIZE & OPTIMIZE
# =============================================================================
def resize_and_optimize(image_path: str, output_path: str) -> bool:
    """Resize logo to optimal web size and compress."""
    try:
        img = Image.open(image_path)

        # Get original size
        orig_w, orig_h = img.size
        orig_size = os.path.getsize(image_path)

        # Calculate new size maintaining aspect ratio
        ratio = min(MAX_LOGO_WIDTH / orig_w, MAX_LOGO_HEIGHT / orig_h)

        # Only resize if larger than max
        if ratio < 1:
            new_w = int(orig_w * ratio)
            new_h = int(orig_h * ratio)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            log.step("📐", f"Resized: {orig_w}x{orig_h} → {new_w}x{new_h}")

        # Ensure RGBA mode for PNG with transparency
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        # Save optimized PNG
        img.save(output_path, 'PNG', optimize=True, compress_level=PNG_COMPRESSION)

        new_size = os.path.getsize(output_path)
        reduction = (1 - new_size / orig_size) * 100 if orig_size > 0 else 0
        log.step("📦", f"Optimized: {orig_size//1024}KB → {new_size//1024}KB ({reduction:.0f}% smaller)")

        return True
    except Exception as e:
        log.step("✗", f"Resize error: {e}")
        return False

def upload_to_s3(local_path: str, s3_key: str) -> bool:
    """Upload file to S3."""
    try:
        s3 = boto3.client('s3', region_name=AWS_REGION)
        content_type = 'image/png' if local_path.endswith('.png') else 'image/jpeg'
        s3.upload_file(local_path, AWS_BUCKET, s3_key,
                       ExtraArgs={'ContentType': content_type, 'CacheControl': 'max-age=86400'})
        return True
    except Exception as e:
        log.step("✗", f"S3 upload error: {e}")
        return False

def get_s3_url(filename: str) -> str:
    """Get public S3 URL for logo."""
    return f"https://{AWS_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{AWS_LOGOS_PREFIX}{filename}"

# =============================================================================
# CSV UPDATE
# =============================================================================
def update_csv(org_name: str, logo_file: str, aws_url: str):
    """Update portfolio_organizations.csv with new logo info."""
    df = pd.read_csv(PORTFOLIO_ORGS_CSV, encoding='utf-8')

    mask = df['organization'] == org_name
    if mask.any():
        df.loc[mask, 'logo_file'] = logo_file
        df.loc[mask, 'aws_logo_url'] = aws_url
        df.to_csv(PORTFOLIO_ORGS_CSV, index=False)
        log.step("📝", f"Updated CSV: {logo_file}")

# =============================================================================
# MAIN PROCESSING
# =============================================================================
def org_to_filename(org_name: str) -> str:
    """Convert org name to logo filename."""
    clean = org_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
    clean = re.sub(r'[<>:"|?*]', '', clean)
    return f"{clean}.png"

def get_orgs_missing_logos() -> list:
    """Get orgs that don't have aws_logo_url set."""
    df = pd.read_csv(PORTFOLIO_ORGS_CSV, encoding='utf-8')

    # Missing = no aws_logo_url or empty
    missing = df[df['aws_logo_url'].isna() | (df['aws_logo_url'] == '')]

    # Sort by row_count descending (biggest portfolios first)
    if 'row_count' in missing.columns:
        missing = missing.sort_values('row_count', ascending=False)

    return missing['organization'].tolist()

def process_org(org_name: str) -> str:
    """Process single org. Returns SUCCESS or FAILED."""
    filename = org_to_filename(org_name)
    local_path = str(LOGOS_DIR / filename)
    temp_path = str(STAGING_DIR / f"temp_{filename}")
    nobg_path = str(STAGING_DIR / f"nobg_{filename}")
    final_path = str(STAGING_DIR / f"final_{filename}")

    # Check if logo already exists locally
    if os.path.exists(local_path):
        log.step("📁", "Logo exists locally, processing...")

        # Check if needs background removal
        if not has_transparency(local_path):
            log.step("🎨", "Removing background...")
            if remove_background(local_path, nobg_path):
                resize_and_optimize(nobg_path, local_path)
                os.remove(nobg_path)
            else:
                resize_and_optimize(local_path, local_path)
        else:
            log.step("✓", "Already has transparency")
            resize_and_optimize(local_path, local_path)

        # Upload to S3
        log.step("☁", "Uploading to S3...")
        s3_key = f"{AWS_LOGOS_PREFIX}{filename}"
        if upload_to_s3(local_path, s3_key):
            aws_url = get_s3_url(filename)
            update_csv(org_name, filename, aws_url)
            log.success(filename)
            return "SUCCESS"

    # Search for logo
    candidates = search_logo_serpapi(org_name)

    if not candidates:
        log.fail("No candidates found")
        return "FAILED"

    # Try each candidate
    for i, cand in enumerate(candidates, 1):
        url = cand["url"]
        source = cand.get("source", "")[:30]

        log.step("⬇", f"[{i}/{len(candidates)}] Downloading from {source}...")

        if not download_image(url, temp_path):
            continue

        # Validate with OpenAI
        log.step("🤖", "Validating with OpenAI...")
        result = validate_logo_openai(temp_path, org_name)

        if result["approved"]:
            log.step("✓", f"Approved (score={result['score']}): {result['reason'][:50]}")

            # Remove background if not transparent
            if not has_transparency(temp_path):
                log.step("🎨", "Removing background...")
                if remove_background(temp_path, nobg_path):
                    # Resize and optimize the no-bg version
                    resize_and_optimize(nobg_path, final_path)
                    os.remove(nobg_path)
                else:
                    # Just resize original if bg removal fails
                    resize_and_optimize(temp_path, final_path)
            else:
                log.step("✓", "Already has transparency")
                resize_and_optimize(temp_path, final_path)

            # Clean up temp
            if os.path.exists(temp_path):
                os.remove(temp_path)

            # Move final to logos dir
            if os.path.exists(final_path):
                os.rename(final_path, local_path)
            else:
                log.fail("Final image not created")
                return "FAILED"

            # Upload to S3
            log.step("☁", "Uploading to S3...")
            s3_key = f"{AWS_LOGOS_PREFIX}{filename}"
            if upload_to_s3(local_path, s3_key):
                aws_url = get_s3_url(filename)
                update_csv(org_name, filename, aws_url)
                log.success(filename)
                return "SUCCESS"
            else:
                log.fail("S3 upload failed")
                return "FAILED"
        else:
            log.step("✗", f"Rejected (score={result['score']}): {result['reason'][:50]}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

        time.sleep(0.5)

    log.fail("All candidates failed validation")
    return "FAILED"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, help="Max orgs to process")
    parser.add_argument("--reset", action="store_true", help="Reset state")
    args = parser.parse_args()

    # Setup
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    Path(LOGOS_DIR).mkdir(parents=True, exist_ok=True)

    if args.reset:
        reset_state()

    state = load_state()
    processed_set = set(state["processed"])

    log.header("LOGO PIPELINE - Fetch, Validate, Upload")
    print(f"    CSV: {PORTFOLIO_ORGS_CSV}")
    print(f"    Logos dir: {LOGOS_DIR}")
    print(f"    S3 bucket: {AWS_BUCKET}")
    print(f"    Previously processed: {len(processed_set)}")

    # API keys are hardcoded in script
    print(f"    API Keys: SerpAPI ✓ | OpenAI ✓ | RemoveBG ✓")

    # Get orgs to process
    missing = get_orgs_missing_logos()
    print(f"    Orgs missing logos: {len(missing)}")

    # Filter already processed
    missing = [org for org in missing if org not in processed_set]
    print(f"    Remaining to process: {len(missing)}")

    if args.max:
        missing = missing[:args.max]
        print(f"    Limited to: {args.max}")

    if not missing:
        print("\n    Nothing to process!")
        return

    print(f"\n{'='*70}")

    success = len(state["success"])
    failed = len(state["failed"])

    for idx, org_name in enumerate(missing, 1):
        log.org(idx, len(missing), org_name)

        try:
            status = process_org(org_name)

            state["processed"].append(org_name)
            if status == "SUCCESS":
                state["success"].append(org_name)
                success += 1
            else:
                state["failed"].append(org_name)
                failed += 1

            save_state(state)

        except Exception as e:
            log.fail(f"Exception: {e}")
            state["processed"].append(org_name)
            state["failed"].append(org_name)
            failed += 1
            save_state(state)

        time.sleep(1)

    # Summary
    print(f"\n{'='*70}")
    print(f"  COMPLETE")
    print(f"{'='*70}")
    print(f"    Success: {success}")
    print(f"    Failed: {failed}")
    print(f"    Total processed: {len(state['processed'])}")
    print(f"\n    State saved to: {STATE_FILE}")
    print(f"    Run again to continue")

if __name__ == "__main__":
    main()
