# AWS S3 Bucket Documentation

## Bucket Overview

| Property | Value |
|----------|-------|
| **Bucket Name** | `nationwide-odcv-images` |
| **Region** | `us-east-2` (Ohio) |
| **Base URL** | `https://nationwide-odcv-images.s3.us-east-2.amazonaws.com` |
| **Access** | Public read |

## What's Stored

The bucket stores two types of assets:

### 1. Organization Logos (`logos/` prefix)
- Company/organization logos displayed on portfolio cards and building reports
- Format: PNG with transparent backgrounds
- Naming: `{Organization_Name}.png` (spaces converted to underscores)
- Example: `logos/Marriott_International.png`

### 2. Building Images (`images/` prefix)
- Exterior photos of buildings
- Format: JPEG
- Naming: `{building_id}_{source}.jpg` (source = streetview, Serpapi, Bing, etc.)
- Example: `images/CHI_12345_streetview.jpg`

### 3. Thumbnails (`thumbnails/` prefix)
- Smaller versions of building images for faster loading
- Format: JPEG
- Size: 300x200 pixels
- Same naming as full images

## URL Patterns

```
# Logo URL
https://nationwide-odcv-images.s3.us-east-2.amazonaws.com/logos/{filename}.png

# Building Image URL
https://nationwide-odcv-images.s3.us-east-2.amazonaws.com/images/{filename}.jpg

# Thumbnail URL
https://nationwide-odcv-images.s3.us-east-2.amazonaws.com/thumbnails/{filename}.jpg
```

## Configuration

All AWS settings are centralized in `src/config.py`:

```python
AWS_BUCKET = 'nationwide-odcv-images'
AWS_REGION = 'us-east-2'
AWS_BASE_URL = f'https://{AWS_BUCKET}.s3.{AWS_REGION}.amazonaws.com'
AWS_LOGOS_PREFIX = 'logos/'
AWS_IMAGES_PREFIX = 'images/'

# Helper functions
def get_logo_url(filename: str) -> str:
    return f'{AWS_BASE_URL}/{AWS_LOGOS_PREFIX}{filename}'

def get_image_url(filename: str) -> str:
    return f'{AWS_BASE_URL}/{AWS_IMAGES_PREFIX}{filename}'
```

## Required Credentials

AWS credentials must be configured via one of these methods:

1. **AWS CLI** (recommended):
   ```bash
   aws configure
   ```

2. **Environment variables**:
   ```bash
   export AWS_ACCESS_KEY_ID=your_access_key
   export AWS_SECRET_ACCESS_KEY=your_secret_key
   ```

3. **~/.aws/credentials file**:
   ```ini
   [default]
   aws_access_key_id = your_access_key
   aws_secret_access_key = your_secret_key
   ```

The scripts use `boto3` which automatically picks up credentials from any of these sources.

## Scripts That Upload to S3

### Main Upload Script
**`scripts/images/upload_to_s3.py`**

Uploads all logos and building images to S3.

```bash
python scripts/images/upload_to_s3.py
```

Features:
- Creates bucket if it doesn't exist
- Configures public read access
- Skips already-uploaded files (unless `force=True`)
- Parallel uploads (20 workers by default)
- Sets `CacheControl: max-age=3600` header

### Logo Pipeline
**`scripts/logos/fetch_validate_upload_logos.py`**

Full pipeline: fetches logos via SerpAPI, validates with OpenAI Vision, removes backgrounds, uploads to S3.

```bash
python scripts/logos/fetch_validate_upload_logos.py
python scripts/logos/fetch_validate_upload_logos.py --max 50   # Process 50 orgs
python scripts/logos/fetch_validate_upload_logos.py --reset    # Start fresh
```

### Building Image Pipeline
**`scripts/images/fetch_validate_upload.py`**

Full pipeline: fetches building images from multiple sources, validates with AI, creates thumbnails, uploads to S3.

```bash
python scripts/images/fetch_validate_upload.py
python scripts/images/fetch_validate_upload.py --max 100  # Process 100 buildings
python scripts/images/fetch_validate_upload.py --reset    # Start fresh
```

### Darkened Logos Upload
**`scripts/logos/upload_darkened_logos.py`**

Uploads specific logos that have been darkened for visibility on white backgrounds.

## Upload Function Pattern

All scripts use this pattern for S3 uploads:

```python
import boto3

def upload_to_s3(local_path: str, s3_key: str) -> bool:
    """Upload file to S3."""
    try:
        s3 = boto3.client('s3', region_name='us-east-2')
        content_type = 'image/png' if local_path.endswith('.png') else 'image/jpeg'
        s3.upload_file(
            local_path,
            'nationwide-odcv-images',
            s3_key,
            ExtraArgs={
                'ContentType': content_type,
                'CacheControl': 'max-age=3600'  # 1 hour cache
            }
        )
        return True
    except Exception as e:
        print(f"Upload error: {e}")
        return False
```

## Bucket Permissions

The bucket is configured for public read access with this policy:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::nationwide-odcv-images/*"
        }
    ]
}
```

Public access block settings are disabled to allow public reads:
- `BlockPublicAcls`: False
- `IgnorePublicAcls`: False
- `BlockPublicPolicy`: False
- `RestrictPublicBuckets`: False

## Local Asset Directories

Before upload, assets are stored locally:

| Asset Type | Local Path |
|------------|------------|
| Logos | `assets/logos/` |
| Building Images | `assets/images/` |
| Thumbnails | `assets/thumbnails/` |

These paths are defined in `src/config.py` as `LOGOS_DIR`, `IMAGES_DIR`, and `THUMBNAILS_DIR`.

## Cache Headers

Different scripts set different cache headers:

| Script | Cache Setting | Purpose |
|--------|---------------|---------|
| `upload_to_s3.py` | `max-age=3600` | 1 hour - allows quick updates |
| `fetch_validate_upload.py` | `max-age=3600` | 1 hour - building images |
| `fetch_validate_upload_logos.py` | `max-age=86400` | 24 hours - logos change less often |
| `upload_darkened_logos.py` | `no-cache, max-age=0` | Force refresh for updated logos |

## Troubleshooting

### "Access Denied" errors
- Verify AWS credentials are configured
- Check IAM user has `s3:PutObject` permission on this bucket

### Images not updating
- Check cache headers - may need to wait for cache expiry
- Use `upload_darkened_logos.py` pattern with `no-cache` header for immediate updates
- Clear browser cache or use incognito mode

### boto3 not found
```bash
pip install boto3
```

### Checking what's in the bucket
```bash
aws s3 ls s3://nationwide-odcv-images/logos/ --summarize
aws s3 ls s3://nationwide-odcv-images/images/ --summarize
```

### Syncing local to S3
```bash
# Sync logos
aws s3 sync assets/logos/ s3://nationwide-odcv-images/logos/

# Sync images
aws s3 sync assets/images/ s3://nationwide-odcv-images/images/
```
