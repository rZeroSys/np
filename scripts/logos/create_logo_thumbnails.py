#!/usr/bin/env python3
"""
Logo Thumbnail Generator - FAST PARALLEL VERSION
"""

import os
import csv
import requests
import boto3
from pathlib import Path
from PIL import Image
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

CSV_PATH = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_organizations.csv'
OUTPUT_DIR = Path('/Users/forrestmiller/Desktop/logo-thumbnails')
THUMBNAIL_SIZE = (64, 64)
S3_BUCKET = 'nationwide-odcv-images'
S3_PREFIX = 'logo-thumbnails/'
S3_REGION = 'us-east-2'
MAX_WORKERS = 30  # Parallel threads

s3_client = boto3.client('s3', region_name=S3_REGION)
lock = threading.Lock()
stats = {'downloaded': 0, 'failed': 0, 'uploaded': 0}


def process_logo(logo):
    """Download, thumbnail, and upload a single logo."""
    url = logo['url']
    filename = logo['filename']
    output_path = OUTPUT_DIR / filename

    try:
        # Download
        response = requests.get(url, timeout=15)
        response.raise_for_status()

        # Create thumbnail
        img = Image.open(BytesIO(response.content))
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        background = Image.new('RGBA', img.size, (255, 255, 255, 255))
        background.paste(img, mask=img.split()[3] if len(img.split()) == 4 else None)
        background = background.convert('RGB')
        background.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)

        final = Image.new('RGB', THUMBNAIL_SIZE, (255, 255, 255))
        offset = ((THUMBNAIL_SIZE[0] - background.width) // 2,
                  (THUMBNAIL_SIZE[1] - background.height) // 2)
        final.paste(background, offset)
        final.save(output_path, 'PNG', optimize=True)

        # Upload to S3
        s3_client.upload_file(
            str(output_path), S3_BUCKET, f"{S3_PREFIX}{filename}",
            ExtraArgs={'ContentType': 'image/png', 'CacheControl': 'max-age=31536000'}
        )

        with lock:
            stats['downloaded'] += 1
            stats['uploaded'] += 1
        return True

    except Exception as e:
        with lock:
            stats['failed'] += 1
        return False


def main():
    print("Logo Thumbnail Generator (PARALLEL)")
    print("=" * 50)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Read CSV
    logos = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            url = row.get('aws_logo_url', '').strip()
            if url and url.startswith('http'):
                logos.append({'url': url, 'filename': url.split('/')[-1]})

    print(f"Processing {len(logos)} logos with {MAX_WORKERS} threads...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_logo, logo): logo for logo in logos}
        for i, future in enumerate(as_completed(futures), 1):
            if i % 50 == 0 or i == len(logos):
                print(f"  [{i}/{len(logos)}] OK:{stats['downloaded']} Failed:{stats['failed']}")

    print(f"\nDone! {stats['uploaded']} thumbnails uploaded to s3://{S3_BUCKET}/{S3_PREFIX}")


if __name__ == '__main__':
    main()
