#!/usr/bin/env python3
"""
S3 Upload Script for Nationwide ODCV Prospector
================================================
Uploads organization logos and building images to AWS S3.

Usage:
    python scripts/upload_to_s3.py

Requirements:
    pip install boto3 tqdm
"""

import os
import sys
import boto3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import mimetypes

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import (
    AWS_BUCKET, AWS_REGION, LOGOS_DIR, IMAGES_DIR,
    AWS_LOGOS_PREFIX, AWS_IMAGES_PREFIX, MAX_UPLOAD_WORKERS
)

# =============================================================================
# CONFIGURATION - from centralized config
# =============================================================================

BUCKET_NAME = AWS_BUCKET
REGION = AWS_REGION

# Source directories
LOGOS_PATH = str(LOGOS_DIR)
IMAGES_PATH = str(IMAGES_DIR)

# S3 prefixes
LOGOS_PREFIX = AWS_LOGOS_PREFIX
IMAGES_PREFIX = AWS_IMAGES_PREFIX

# Max concurrent uploads
MAX_WORKERS = MAX_UPLOAD_WORKERS

# =============================================================================
# S3 CLIENT
# =============================================================================

s3_client = boto3.client('s3', region_name=REGION)

def create_bucket_if_not_exists():
    """Create S3 bucket if it doesn't exist."""
    try:
        s3_client.head_bucket(Bucket=BUCKET_NAME)
        print(f"Bucket {BUCKET_NAME} already exists")
    except:
        print(f"Creating bucket {BUCKET_NAME}...")
        s3_client.create_bucket(
            Bucket=BUCKET_NAME,
            CreateBucketConfiguration={'LocationConstraint': REGION}
        )
        print(f"Bucket {BUCKET_NAME} created")

def set_bucket_public_access():
    """Configure bucket for public read access."""
    # Disable block public access
    s3_client.put_public_access_block(
        Bucket=BUCKET_NAME,
        PublicAccessBlockConfiguration={
            'BlockPublicAcls': False,
            'IgnorePublicAcls': False,
            'BlockPublicPolicy': False,
            'RestrictPublicBuckets': False
        }
    )

    # Set bucket policy for public read
    policy = f'''{{
        "Version": "2012-10-17",
        "Statement": [
            {{
                "Sid": "PublicReadGetObject",
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": "arn:aws:s3:::{BUCKET_NAME}/*"
            }}
        ]
    }}'''

    s3_client.put_bucket_policy(Bucket=BUCKET_NAME, Policy=policy)
    print("Bucket configured for public access")

def get_content_type(filename):
    """Get content type for file."""
    ext = os.path.splitext(filename)[1].lower()
    content_types = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
    }
    return content_types.get(ext, 'application/octet-stream')

def upload_file(local_path, s3_key):
    """Upload a single file to S3."""
    try:
        content_type = get_content_type(local_path)
        s3_client.upload_file(
            local_path,
            BUCKET_NAME,
            s3_key,
            ExtraArgs={
                'ContentType': content_type,
                'CacheControl': 'max-age=3600'  # 1 hour cache (force refresh)
            }
        )
        return True, s3_key
    except Exception as e:
        return False, f"{s3_key}: {str(e)}"

def upload_directory(local_dir, s3_prefix, description, force=False):
    """Upload all files from a directory to S3 with progress."""
    files = [f for f in os.listdir(local_dir) if os.path.isfile(os.path.join(local_dir, f))]
    total = len(files)

    print(f"\nUploading {total} {description}...")

    if force:
        # Force upload ALL files (overwrite existing)
        print(f"  FORCE MODE: Will upload all {total} files")
        to_upload = [(os.path.join(local_dir, f), s3_prefix + f) for f in files]
    else:
        # Check which files already exist
        existing = set()
        paginator = s3_client.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=s3_prefix):
            for obj in page.get('Contents', []):
                existing.add(obj['Key'])

        # Filter to only new files
        to_upload = []
        for f in files:
            s3_key = s3_prefix + f
            if s3_key not in existing:
                to_upload.append((os.path.join(local_dir, f), s3_key))

        if not to_upload:
            print(f"  All {total} files already uploaded, skipping")
            return total, 0, 0

        print(f"  {len(existing)} already uploaded, {len(to_upload)} to upload")

    success = 0
    failed = 0
    errors = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(upload_file, local, s3key): s3key
                   for local, s3key in to_upload}

        for i, future in enumerate(as_completed(futures)):
            ok, result = future.result()
            if ok:
                success += 1
            else:
                failed += 1
                errors.append(result)

            # Progress update every 100 files
            if (i + 1) % 100 == 0 or (i + 1) == len(to_upload):
                pct = 100 * (i + 1) / len(to_upload)
                print(f"  Progress: {i + 1}/{len(to_upload)} ({pct:.1f}%)")

    if errors:
        print(f"  Errors ({len(errors)}):")
        for err in errors[:10]:
            print(f"    {err}")
        if len(errors) > 10:
            print(f"    ... and {len(errors) - 10} more")

    return total, success, failed

def main():
    print("=" * 60)
    print("Nationwide ODCV Prospector - S3 Upload")
    print("=" * 60)

    # Step 1: Create bucket
    create_bucket_if_not_exists()

    # Step 2: Configure public access
    set_bucket_public_access()

    # Step 3: Upload logos (FORCE to overwrite existing)
    logos_total, logos_success, logos_failed = upload_directory(
        LOGOS_PATH, LOGOS_PREFIX, "organization logos", force=True
    )

    # Step 4: Upload building images
    images_total, images_success, images_failed = upload_directory(
        IMAGES_PATH, IMAGES_PREFIX, "building images"
    )

    # Summary
    print("\n" + "=" * 60)
    print("UPLOAD COMPLETE")
    print("=" * 60)
    print(f"\nLogos:    {logos_total:,} total, {logos_success:,} uploaded, {logos_failed:,} failed")
    print(f"Images:   {images_total:,} total, {images_success:,} uploaded, {images_failed:,} failed")
    print(f"\nBucket URL: https://{BUCKET_NAME}.s3.{REGION}.amazonaws.com")
    print(f"Logo URL pattern: https://{BUCKET_NAME}.s3.{REGION}.amazonaws.com/logos/{{logo_file}}")
    print(f"Image URL pattern: https://{BUCKET_NAME}.s3.{REGION}.amazonaws.com/images/{{image_file}}")

if __name__ == '__main__':
    main()
