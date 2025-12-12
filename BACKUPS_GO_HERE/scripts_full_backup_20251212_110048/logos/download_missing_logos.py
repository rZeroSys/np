#!/usr/bin/env python3
"""
Download missing logos for portfolio organizations.
Uses SerpAPI for Google Image search and OpenAI Vision to select best logo.
"""

import os
import sys
import time
import requests
import pandas as pd

# API Keys - set these as environment variables
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")

# Paths
LOGO_DIR = "/Users/forrestmiller/Desktop/Final real/Logos"
PORTFOLIO_CSV = "/Users/forrestmiller/Desktop/Final real/portfolio_organizations.csv"

def search_logo_images(org_name):
    """Search for logo images using SerpAPI."""
    params = {
        "engine": "google_images",
        "q": f"{org_name} logo",
        "api_key": SERPAPI_KEY,
        "num": 8,
        "safe": "active"
    }

    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        images = []
        for img in data.get("images_results", [])[:8]:
            if img.get("thumbnail"):
                images.append({
                    "url": img.get("original"),
                    "thumbnail": img.get("thumbnail"),
                    "title": img.get("title", ""),
                })
        return images
    except Exception as e:
        print(f"Search error: {e}")
        return []

def select_best_logo_with_vision(org_name, images):
    """Use OpenAI Vision to look at thumbnails and pick best logo."""
    if not images:
        return None

    # Build message with image thumbnails
    content = [
        {
            "type": "text",
            "text": f"I need the official logo for \"{org_name}\". Look at these {len(images)} images and tell me which number (1-{len(images)}) is the best logo. Reply with ONLY the number."
        }
    ]

    # Add each thumbnail image
    for i, img in enumerate(images):
        content.append({
            "type": "text",
            "text": f"\nImage {i+1}:"
        })
        content.append({
            "type": "image_url",
            "image_url": {"url": img["thumbnail"], "detail": "low"}
        })

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": content}],
                "max_tokens": 10,
                "temperature": 0
            },
            timeout=60
        )
        resp.raise_for_status()

        answer = resp.json()["choices"][0]["message"]["content"].strip()

        # Parse the number
        import re
        nums = re.findall(r'\d+', answer)
        if nums:
            idx = int(nums[0]) - 1
            if 0 <= idx < len(images):
                return images[idx]

        # Default to first if parsing fails
        return images[0]

    except Exception as e:
        print(f"Vision API error: {e}")
        return images[0] if images else None

def download_image(url, save_path):
    """Download image from URL."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=30, stream=True)
        resp.raise_for_status()

        with open(save_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"Download error: {e}")
        return False

def get_missing_orgs():
    """Get list of orgs missing logos from CSV."""
    df = pd.read_csv(PORTFOLIO_CSV)
    missing = df[df['logo_file'].isna()]['organization'].tolist()
    return missing

def main():
    print("=" * 60)
    print("  LOGO DOWNLOADER")
    print("  Using OpenAI Vision to find best logos")
    print("=" * 60)
    print()

    missing_orgs = get_missing_orgs()
    total = len(missing_orgs)

    print(f"Found {total} organizations missing logos\n")

    success = 0
    failed = 0

    for i, org in enumerate(missing_orgs, 1):
        # Filename = exact org name with spaces -> underscores
        filename = org.replace(' ', '_').replace('/', '_') + '.png'
        save_path = os.path.join(LOGO_DIR, filename)

        # Skip if already exists
        if os.path.exists(save_path):
            print(f"[{i}/{total}] {org} - Already exists, skipping")
            continue

        print(f"[{i}/{total}] {org}")
        print(f"  Searching...", end=" ", flush=True)

        # Search for images
        images = search_logo_images(org)

        if not images:
            print("No images found")
            failed += 1
            continue

        print(f"Found {len(images)} images")
        print(f"  Analyzing with Vision AI...", end=" ", flush=True)

        # Use vision to pick best
        best = select_best_logo_with_vision(org, images)

        if not best:
            print("Failed")
            failed += 1
            continue

        print("Selected")
        print(f"  Downloading...", end=" ", flush=True)

        # Download the full resolution image
        if download_image(best["url"], save_path):
            print(f"✓ Saved: {filename}")
            success += 1
        else:
            # Try thumbnail as fallback
            if download_image(best["thumbnail"], save_path):
                print(f"✓ Saved (thumbnail): {filename}")
                success += 1
            else:
                print("Failed")
                failed += 1

        # Rate limiting
        time.sleep(1)

    print()
    print("=" * 60)
    print(f"  COMPLETE")
    print(f"  Success: {success}")
    print(f"  Failed:  {failed}")
    print("=" * 60)

if __name__ == "__main__":
    main()
