#!/usr/bin/env python3
"""
Download images for buildings that have image files in assets but no URL in portfolio_data.csv
Uses parallel downloads for 10x speed
"""

import csv
import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Configuration
PORTFOLIO_CSV = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv'
ASSETS_IMAGES_DIR = '/Users/forrestmiller/Desktop/nationwide-prospector/assets/images'
OUTPUT_DIR = '/Users/forrestmiller/Desktop/missing_building_images'
FAILED_CSV = '/Users/forrestmiller/Desktop/missing_building_images/failed_downloads.csv'
AWS_BASE_URL = 'https://nationwide-odcv-images.s3.us-east-2.amazonaws.com/images'
MAX_WORKERS = 20  # Parallel downloads

# Thread-safe counters
lock = threading.Lock()
successful = 0
failed = []
completed = 0

def download_image(item, total):
    """Download a single image. Returns success status."""
    global successful, failed, completed

    bid = item['building_id']
    name = item['building_name'][:35] if item['building_name'] else '(unnamed)'
    url = item['url']
    filename = item['image_file']
    output_path = os.path.join(OUTPUT_DIR, filename)

    try:
        response = requests.get(url, timeout=30)

        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response.content)
            size_kb = len(response.content) / 1024

            with lock:
                successful += 1
                completed += 1
                print(f"[{completed}/{total}] OK  {bid}: {name} ({size_kb:.0f}KB)")
            return True
        else:
            with lock:
                completed += 1
                failed.append({
                    'building_id': bid,
                    'building_name': item['building_name'],
                    'image_file': filename,
                    'url': url,
                    'error': f"HTTP {response.status_code}"
                })
                print(f"[{completed}/{total}] FAIL {bid}: HTTP {response.status_code}")
            return False
    except Exception as e:
        with lock:
            completed += 1
            failed.append({
                'building_id': bid,
                'building_name': item['building_name'],
                'image_file': filename,
                'url': url,
                'error': str(e)
            })
            print(f"[{completed}/{total}] FAIL {bid}: {str(e)[:40]}")
        return False

def main():
    global successful, failed, completed

    print("=" * 60)
    print("DOWNLOAD MISSING BUILDING IMAGES (PARALLEL)")
    print("=" * 60)
    print()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Output: {OUTPUT_DIR}")
    print(f"Workers: {MAX_WORKERS} parallel downloads")
    print()

    # Load portfolio data
    print("Loading portfolio data...")
    with open(PORTFOLIO_CSV, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    col_idx = {name: i for i, name in enumerate(header)}
    id_idx = col_idx['id_building']
    image_url_idx = col_idx['bldg_image_url']
    name_idx = col_idx['id_property_name']

    buildings = {}
    for row in rows:
        bid = row[id_idx]
        img_url = row[image_url_idx].strip() if image_url_idx < len(row) else ''
        name = row[name_idx] if name_idx < len(row) else ''
        buildings[bid] = {'url': img_url, 'name': name}

    # Get images in assets folder
    print("Scanning assets/images...")
    image_files = os.listdir(ASSETS_IMAGES_DIR)

    bid_to_images = {}
    for img in image_files:
        if img.endswith('.jpg') or img.endswith('.png'):
            parts = img.rsplit('.', 1)[0].split('_')
            if len(parts) >= 2:
                bid = f"{parts[0]}_{parts[1]}"
                if bid not in bid_to_images:
                    bid_to_images[bid] = []
                bid_to_images[bid].append(img)

    # Find buildings with images but no URL
    to_download = []
    for bid, imgs in bid_to_images.items():
        if bid in buildings and not buildings[bid]['url']:
            to_download.append({
                'building_id': bid,
                'building_name': buildings[bid]['name'],
                'image_file': imgs[0],
                'url': f"{AWS_BASE_URL}/{imgs[0]}"
            })

    total = len(to_download)
    print(f"Found {total} images to download")
    print()
    print("=" * 60)
    print("DOWNLOADING...")
    print("=" * 60)

    # Parallel downloads
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(download_image, item, total) for item in to_download]
        for future in as_completed(futures):
            pass  # Results handled in download_image

    # Write failures
    if failed:
        with open(FAILED_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['building_id', 'building_name', 'image_file', 'url', 'error'])
            writer.writeheader()
            writer.writerows(failed)

    # Summary
    print()
    print("=" * 60)
    print("DONE")
    print("=" * 60)
    print(f"  Successful: {successful}/{total}")
    print(f"  Failed:     {len(failed)}")
    if failed:
        print(f"  See:        {FAILED_CSV}")
    print()

if __name__ == '__main__':
    main()
