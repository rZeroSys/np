#!/usr/bin/env python3
import os
import csv
import base64
import time
import subprocess
from openai import OpenAI

# Config
IMAGE_DIR = '/Users/forrestmiller/Desktop/Final real/good images'
MASTER_CSV = '/Users/forrestmiller/Desktop/Final real/merged_property_matches_updated.csv'
PREVIOUS_REVIEWS = '/Users/forrestmiller/Desktop/final images/identified_tenants.csv'
OUTPUT_CSV = '/Users/forrestmiller/Desktop/Final real/good images/identified_tenants.csv'
API_KEY = os.environ.get('OPENAI_API_KEY', '')

client = OpenAI(api_key=API_KEY)

def get_buildings_missing_tenant():
    """Get building IDs that have empty tenant field in master CSV"""
    missing = set()
    with open(MASTER_CSV, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            tenant = row.get('tenant', '').strip()
            if not tenant:
                missing.add(row['building_id'])
    return missing

def get_already_reviewed():
    """Get building IDs already reviewed from previous and current output"""
    reviewed = set()
    for csv_path in [PREVIOUS_REVIEWS, OUTPUT_CSV]:
        if os.path.exists(csv_path):
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    reviewed.add(row['building_id'])
    return reviewed

# Cache directory listing for speed
_IMAGE_CACHE = None

def get_image_cache():
    """Build cache of building_id -> image_path"""
    global _IMAGE_CACHE
    if _IMAGE_CACHE is None:
        print("  Building image cache (one-time)...", flush=True)
        _IMAGE_CACHE = {}
        for f in os.listdir(IMAGE_DIR):
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                # Extract building_id (everything before last underscore)
                parts = f.rsplit('_', 1)
                if len(parts) >= 1:
                    bid = parts[0]
                    if bid not in _IMAGE_CACHE:
                        _IMAGE_CACHE[bid] = os.path.join(IMAGE_DIR, f)
        print(f"  Cached {len(_IMAGE_CACHE)} images", flush=True)
    return _IMAGE_CACHE

def find_image_for_building(building_id):
    """Find image file for a building ID using cache"""
    cache = get_image_cache()
    return cache.get(building_id)

def has_text_ocr(image_path):
    """Use tesseract OCR to check if image has any text"""
    try:
        result = subprocess.run(
            ['tesseract', image_path, 'stdout', '-l', 'eng', '--psm', '11'],
            capture_output=True,
            text=True,
            timeout=30
        )
        text = result.stdout.strip()
        # Filter out noise - require at least 3 alphanumeric chars
        alphanumeric = ''.join(c for c in text if c.isalnum())
        return len(alphanumeric) >= 3
    except Exception as e:
        print(f"    OCR error: {e}")
        return True  # If OCR fails, send to API anyway

def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def identify_tenant(image_path):
    """Use OpenAI API to identify tenant from image"""
    base64_image = encode_image(image_path)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": """Look at this building photo. Identify any business tenant you can see from signage, logos, or branding on the building.

ONLY respond with the tenant/business name if you can clearly identify one from visible signage.
If you see multiple tenants, list the most prominent one.
If you cannot identify any tenant from visible signage, respond with just: UNKNOWN

Examples of good responses:
- Walgreens
- McDonald's
- CVS Pharmacy
- Target
- UNKNOWN

Respond with ONLY the tenant name or UNKNOWN, nothing else."""
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                            "detail": "low"
                        }
                    }
                ]
            }
        ],
        max_tokens=50
    )

    return response.choices[0].message.content.strip()

def main():
    print("=" * 60)
    print("TENANT IDENTIFICATION SCRIPT")
    print("=" * 60)
    print("Loading data...", flush=True)

    # Get buildings to process
    missing_tenant = get_buildings_missing_tenant()
    print(f"  Buildings missing tenant: {len(missing_tenant)}")

    already_reviewed = get_already_reviewed()
    print(f"  Already reviewed: {len(already_reviewed)}")

    # Find buildings with images that need review
    need_review = [bid for bid in missing_tenant if bid not in already_reviewed]
    print(f"  Need review (not yet processed): {len(need_review)}")

    # Build image cache first
    get_image_cache()

    # Find buildings with images
    print("  Matching buildings to images...", flush=True)
    to_process = []
    for bid in need_review:
        img_path = find_image_for_building(bid)
        if img_path:
            to_process.append((bid, img_path))

    print(f"  To process: {len(to_process)}")
    print("-" * 60)

    if not to_process:
        print("Nothing to process!")
        return

    # Open CSV for appending
    file_exists = os.path.exists(OUTPUT_CSV)
    csvfile = open(OUTPUT_CSV, 'a', newline='')
    writer = csv.writer(csvfile)

    if not file_exists:
        writer.writerow(['building_id', 'identified_tenant', 'image_file', 'has_text'])

    # Stats
    total = len(to_process)
    no_text_count = 0
    identified_count = 0
    unknown_count = 0
    error_count = 0

    for i, (building_id, image_path) in enumerate(to_process):
        progress = (i + 1) / total * 100
        img_name = os.path.basename(image_path)

        print(f"[{i+1}/{total}] ({progress:.1f}%) {building_id}: ", end='', flush=True)

        # Step 1: OCR check
        print("OCR...", end='', flush=True)
        has_text = has_text_ocr(image_path)

        if not has_text:
            print(" No text, skipping API")
            writer.writerow([building_id, 'NO_TEXT', img_name, 'N'])
            csvfile.flush()
            no_text_count += 1
            continue

        # Step 2: API call
        print(" Text found, API...", end='', flush=True)
        try:
            tenant = identify_tenant(image_path)

            if tenant and tenant.upper() != 'UNKNOWN':
                identified_count += 1
                print(f" ✓ {tenant}")
            else:
                tenant = "UNKNOWN"
                unknown_count += 1
                print(" ?")

            writer.writerow([building_id, tenant, img_name, 'Y'])
            csvfile.flush()

        except Exception as e:
            error_count += 1
            print(f" ERROR: {str(e)[:40]}")
            writer.writerow([building_id, f"ERROR: {str(e)[:80]}", img_name, 'Y'])
            csvfile.flush()
            time.sleep(2)

        # Rate limit
        time.sleep(0.3)

    csvfile.close()

    print("-" * 60)
    print("COMPLETE!")
    print(f"  No text (skipped API): {no_text_count}")
    print(f"  Identified: {identified_count}")
    print(f"  Unknown: {unknown_count}")
    print(f"  Errors: {error_count}")
    print(f"  API calls saved: {no_text_count} (${no_text_count * 0.003:.2f} saved approx)")
    print(f"Results saved to: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
