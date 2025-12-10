#!/usr/bin/env python3
"""
Upload darkened logos to AWS S3 with cache-busting headers.
Uses nationwide-odcv-images bucket with logos/ prefix.
"""

import boto3
import os
from botocore.exceptions import ClientError
from datetime import datetime

BUCKET_NAME = 'nationwide-odcv-images'
REGION = 'us-east-2'
LOGOS_DIR = '/Users/forrestmiller/Desktop/nationwide propector/Logos'
WHITE_LOGOS_LIST = os.path.join(LOGOS_DIR, 'white_logos_list.txt')

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def main():
    s3_client = boto3.client('s3', region_name=REGION)

    # Read list of darkened logos
    with open(WHITE_LOGOS_LIST, 'r') as f:
        lines = f.readlines()

    uploaded = 0
    failed = 0

    for line in lines:
        line = line.strip()
        if not line or ',' not in line:
            continue

        filename = line.split(',')[0]
        filepath = os.path.join(LOGOS_DIR, filename)
        s3_key = f"logos/{filename}"  # lowercase logos/ prefix

        if not os.path.exists(filepath):
            log(f"Not found: {filename}")
            failed += 1
            continue

        try:
            s3_client.upload_file(
                filepath,
                BUCKET_NAME,
                s3_key,
                ExtraArgs={
                    'ContentType': 'image/png',
                    'CacheControl': 'no-cache, max-age=0, must-revalidate',
                }
            )
            log(f"Uploaded: {filename}")
            uploaded += 1
        except ClientError as e:
            log(f"Failed: {filename} - {e}")
            failed += 1

    log(f"\nDone! Uploaded: {uploaded}, Failed: {failed}")
    log(f"URL: https://{BUCKET_NAME}.s3.{REGION}.amazonaws.com/logos/")

if __name__ == '__main__':
    main()
