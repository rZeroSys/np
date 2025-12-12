#!/usr/bin/env python3
"""
Add Berkeley CA Buildings to Nationwide Prospector
===================================================
Fetches building data from City of Berkeley BESO open data portal,
transforms to portfolio schema, geocodes, fetches images, and adds to portfolio.

Usage:
    python3 scripts/data_updates/add_berkeley_buildings.py

Data Source:
    https://data.cityofberkeley.info/resource/5vy5-rwja.json
"""

import os
import sys
import re
import json
import time
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
import boto3
from io import BytesIO

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# =============================================================================
# API KEYS (from environment variables)
# =============================================================================

GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY', '')

AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID', '')
AWS_SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
AWS_BUCKET = 'nationwide-odcv-images'
AWS_REGION = 'us-east-2'

# =============================================================================
# FILE PATHS
# =============================================================================

PORTFOLIO_DATA_PATH = PROJECT_ROOT / 'data' / 'source' / 'portfolio_data.csv'
PORTFOLIO_ORGS_PATH = PROJECT_ROOT / 'data' / 'source' / 'portfolio_organizations.csv'
BACKUP_DIR = PROJECT_ROOT / 'BACKUPS_GO_HERE' / 'csv_backups'
IMAGES_DIR = PROJECT_ROOT / 'assets' / 'images'
ORCHESTRATE_SCRIPT = PROJECT_ROOT / 'scripts' / 'populate_master' / 'orchestrate.py'

# Berkeley BESO API
BESO_API_URL = 'https://data.cityofberkeley.info/resource/5vy5-rwja.json'

# =============================================================================
# CONSTANTS
# =============================================================================

BERKELEY_DEFAULTS = {
    'loc_city': 'Berkeley',
    'loc_state': 'CA',
    'data_year': 2024.0,
    'cost_utility_name': 'Pacific Gas & Electric Co.',
    'energy_climate_zone': 'South-Central',
    'bldg_vertical': 'Commercial',
}

# Commercial building types to include (BESO type -> Portfolio type)
COMMERCIAL_TYPES = {
    'Office': 'Office',
    'Medical Office': 'Medical Office',
    'Bank Branch': 'Bank Branch',
    'Retail Store': 'Retail Store',
    'Hotel': 'Hotel',
    'Supermarket/Grocery Store': 'Supermarket/Grocery',
    'Mixed Use Property': 'Mixed Use',
    'Wholesale Club/Supercenter': 'Wholesale Club',
    'Strip Mall': 'Strip Mall',
    'Enclosed Mall': 'Enclosed Mall',
    'Restaurant': 'Restaurant/Bar',
    'Data Center': 'Data Center',
    'Distribution Center': 'Distribution Center',
    'Warehouse': 'Warehouse',
    'Laboratory': 'Laboratory',
    'Financial Office': 'Office',
    'Other - Mall': 'Strip Mall',
    'Convenience Store with Gas Station': 'Retail Store',
    'Convenience Store without Gas Station': 'Retail Store',
    'Automobile Dealership': 'Vehicle Dealership',
    'Self-Storage Facility': 'Warehouse',
    'Fitness Center/Health Club/Gym': 'Gym',
    'Movie Theater': 'Theater',
    'Performing Arts': 'Theater',
    'Museum': 'Library/Museum',
    'Library': 'Library',
    'Convention Center': 'Event Space',
    'Social/Meeting Hall': 'Event Space',
    'Parking': 'Parking',
}

# Types to exclude (non-commercial)
EXCLUDED_TYPES = [
    'K-12 School', 'College/University', 'Multifamily Housing',
    'Senior Care Community', 'Residence Hall/Dormitory', 'Residential',
    'Worship Facility', 'Police Station', 'Fire Station', 'Prison/Incarceration',
    'Single Family Home', 'Other - Education', 'Pre-school/Daycare',
    'Vocational School', 'Adult Education', 'Hospital', 'Urgent Care',
    'Outpatient Rehabilitation/Physical Therapy',
]

# Building type to vertical mapping
TYPE_TO_VERTICAL = {
    'Office': 'Commercial', 'Medical Office': 'Healthcare', 'Bank Branch': 'Commercial',
    'Retail Store': 'Commercial', 'Hotel': 'Commercial', 'Supermarket/Grocery': 'Commercial',
    'Mixed Use': 'Commercial', 'Wholesale Club': 'Commercial', 'Strip Mall': 'Commercial',
    'Enclosed Mall': 'Commercial', 'Restaurant/Bar': 'Commercial', 'Data Center': 'Commercial',
    'Distribution Center': 'Commercial', 'Warehouse': 'Commercial', 'Laboratory': 'Commercial',
    'Vehicle Dealership': 'Commercial', 'Gym': 'Commercial', 'Theater': 'Commercial',
    'Library/Museum': 'Commercial', 'Library': 'Government', 'Event Space': 'Commercial',
    'Parking': 'Commercial',
}

# Building type to benchmark mapping
TYPE_TO_BENCHMARK = {
    'Office': 'Office', 'Medical Office': 'Medical Office', 'Bank Branch': 'Office',
    'Retail Store': 'Retail Store', 'Hotel': 'Hotel', 'Supermarket/Grocery': 'Supermarket/Grocery',
    'Mixed Use': 'Mixed Use', 'Wholesale Club': 'Wholesale Club', 'Strip Mall': 'Strip Mall',
    'Enclosed Mall': 'Enclosed Mall', 'Restaurant/Bar': 'Restaurant', 'Data Center': 'Data Center',
    'Distribution Center': 'Distribution Center', 'Warehouse': 'Warehouse', 'Laboratory': 'Laboratory',
    'Vehicle Dealership': 'Vehicle Dealership', 'Gym': 'Fitness Center/Health Club/Gym',
    'Theater': 'Movie Theater', 'Library/Museum': 'Museum', 'Library': 'Library',
    'Event Space': 'Convention Center', 'Parking': 'Parking',
}

# Building type to filter mapping
TYPE_TO_FILTER = {
    'Office': 'Office', 'Medical Office': 'Medical Office', 'Bank Branch': 'Office',
    'Retail Store': 'Retail', 'Hotel': 'Hotel', 'Supermarket/Grocery': 'Retail',
    'Mixed Use': 'Mixed Use', 'Wholesale Club': 'Retail', 'Strip Mall': 'Retail',
    'Enclosed Mall': 'Retail', 'Restaurant/Bar': 'Restaurant', 'Data Center': 'Data Center',
    'Distribution Center': 'Industrial', 'Warehouse': 'Industrial', 'Laboratory': 'Laboratory',
    'Vehicle Dealership': 'Retail', 'Gym': 'Fitness', 'Theater': 'Entertainment',
    'Library/Museum': 'Arts & Culture', 'Library': 'Arts & Culture', 'Event Space': 'Entertainment',
    'Parking': 'Parking',
}

# EUI benchmarks by building type
EUI_BENCHMARKS = {
    'Office': 52.9, 'Medical Office': 97.7, 'Retail Store': 51.4, 'Hotel': 95.0,
    'Supermarket/Grocery': 171.0, 'Mixed Use': 70.0, 'Wholesale Club': 80.0,
    'Strip Mall': 65.0, 'Restaurant/Bar': 246.0, 'Data Center': 1000.0,
    'Warehouse': 25.0, 'Laboratory': 141.0, 'Gym': 64.0, 'Theater': 70.0,
    'Library': 80.0, 'Event Space': 70.0, 'Bank Branch': 52.9,
}

# =============================================================================
# ORGANIZATION MATCHING
# =============================================================================

def load_organizations():
    """Load portfolio organizations with search aliases."""
    orgs_df = pd.read_csv(PORTFOLIO_ORGS_PATH)

    # Build lookup dict: alias -> canonical name
    org_lookup = {}
    for _, row in orgs_df.iterrows():
        canonical = row['organization']
        if pd.notna(canonical):
            # Add the canonical name itself
            org_lookup[canonical.lower().strip()] = canonical

            # Add search aliases
            aliases = row.get('search_aliases', '')
            if pd.notna(aliases) and aliases:
                for alias in str(aliases).split('|'):
                    alias_clean = alias.lower().strip()
                    if alias_clean:
                        org_lookup[alias_clean] = canonical

    return org_lookup


def match_organization(name, org_lookup):
    """Match an organization name to canonical form."""
    if not name or pd.isna(name):
        return None

    name_lower = str(name).lower().strip()

    # Direct match
    if name_lower in org_lookup:
        return org_lookup[name_lower]

    # Partial match - check if any alias is contained in the name
    for alias, canonical in org_lookup.items():
        if len(alias) >= 4 and alias in name_lower:
            return canonical

    # Return original if no match found
    return name


# =============================================================================
# DATA FETCHING
# =============================================================================

def fetch_beso_data(limit=10000, retries=3):
    """Fetch all buildings from Berkeley BESO API."""
    print("Fetching Berkeley BESO building data...")

    all_data = []
    offset = 0
    batch_size = 1000

    for attempt in range(retries):
        try:
            while True:
                params = {
                    '$limit': batch_size,
                    '$offset': offset,
                    '$order': 'pm_property_id'
                }

                response = requests.get(BESO_API_URL, params=params, timeout=60)
                response.raise_for_status()

                batch = response.json()
                if not batch:
                    break

                all_data.extend(batch)
                print(f"  Fetched {len(all_data)} buildings...")

                if len(batch) < batch_size:
                    break

                offset += batch_size
                time.sleep(0.5)  # Rate limiting

            print(f"Total buildings fetched: {len(all_data)}")
            return all_data

        except requests.RequestException as e:
            print(f"  Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise


def filter_commercial_buildings(buildings):
    """Filter to commercial building types only."""
    filtered = []
    excluded_count = 0

    for bldg in buildings:
        beso_type = bldg.get('primary_property_type_self_selected', '')

        # Check if it's a commercial type
        if beso_type in COMMERCIAL_TYPES:
            filtered.append(bldg)
        else:
            excluded_count += 1

    print(f"Filtered to {len(filtered)} commercial buildings (excluded {excluded_count})")
    return filtered


# =============================================================================
# GEOCODING
# =============================================================================

def geocode_address(address, api_key=GOOGLE_MAPS_API_KEY):
    """Geocode an address using Google Maps API."""
    if not address:
        return None, None

    url = 'https://maps.googleapis.com/maps/api/geocode/json'
    params = {
        'address': address,
        'key': api_key
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data['status'] == 'OK' and data['results']:
            location = data['results'][0]['geometry']['location']
            return location['lat'], location['lng']
        else:
            return None, None

    except Exception as e:
        print(f"  Geocoding error for {address}: {e}")
        return None, None


def batch_geocode(buildings, max_workers=5):
    """Geocode all buildings in parallel."""
    print("Geocoding addresses...")

    results = {}
    addresses_to_geocode = []

    for bldg in buildings:
        address = bldg.get('address', '')
        city = 'Berkeley'
        state = 'CA'
        zip_code = bldg.get('postal_code', '')

        full_address = f"{address}, {city}, {state} {zip_code}".strip()
        addresses_to_geocode.append((bldg.get('pm_property_id'), full_address))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(geocode_address, addr): (prop_id, addr)
            for prop_id, addr in addresses_to_geocode
        }

        completed = 0
        for future in as_completed(futures):
            prop_id, addr = futures[future]
            try:
                lat, lon = future.result()
                results[prop_id] = (lat, lon)
                completed += 1
                if completed % 20 == 0:
                    print(f"  Geocoded {completed}/{len(addresses_to_geocode)} addresses")
            except Exception as e:
                print(f"  Error geocoding {addr}: {e}")
                results[prop_id] = (None, None)

            time.sleep(0.1)  # Rate limiting

    print(f"Geocoding complete: {len(results)} addresses processed")
    return results


# =============================================================================
# IMAGE FETCHING
# =============================================================================

def fetch_street_view_image(lat, lon, building_id, api_key=GOOGLE_MAPS_API_KEY):
    """Fetch Google Street View image for a location."""
    if not lat or not lon:
        return None

    url = 'https://maps.googleapis.com/maps/api/streetview'
    params = {
        'size': '600x400',
        'location': f'{lat},{lon}',
        'fov': 90,
        'pitch': 10,
        'key': api_key
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        # Check if we got an actual image (not the "no image available" placeholder)
        content_type = response.headers.get('content-type', '')
        if 'image' in content_type and len(response.content) > 5000:
            return response.content
        else:
            return None

    except Exception as e:
        print(f"  Street View error for {building_id}: {e}")
        return None


def upload_image_to_s3(image_data, filename, s3_client):
    """Upload image to S3 bucket."""
    try:
        s3_client.put_object(
            Bucket=AWS_BUCKET,
            Key=f'images/{filename}',
            Body=image_data,
            ContentType='image/jpeg',
            CacheControl='max-age=31536000'
        )

        url = f'https://{AWS_BUCKET}.s3.{AWS_REGION}.amazonaws.com/images/{filename}'
        return url

    except Exception as e:
        print(f"  S3 upload error for {filename}: {e}")
        return None


def fetch_and_upload_images(buildings_df, geocode_results, max_workers=5):
    """Fetch Street View images and upload to S3."""
    print("Fetching building images and uploading to S3...")

    # Initialize S3 client
    s3_client = boto3.client(
        's3',
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY
    )

    image_urls = {}

    def process_building(row):
        building_id = row['id_building']
        prop_id = row.get('id_source_plant_id')

        # Get coordinates
        if prop_id in geocode_results:
            lat, lon = geocode_results[prop_id]
        else:
            lat, lon = row.get('loc_lat'), row.get('loc_lon')

        if not lat or not lon:
            return building_id, None

        # Fetch image
        image_data = fetch_street_view_image(lat, lon, building_id)

        if image_data:
            # Save locally
            local_filename = f'{building_id}_streetview.jpg'
            local_path = IMAGES_DIR / local_filename
            with open(local_path, 'wb') as f:
                f.write(image_data)

            # Upload to S3
            s3_url = upload_image_to_s3(image_data, local_filename, s3_client)
            return building_id, s3_url

        return building_id, None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(process_building, row): row['id_building']
            for _, row in buildings_df.iterrows()
        }

        completed = 0
        for future in as_completed(futures):
            building_id = futures[future]
            try:
                bid, url = future.result()
                if url:
                    image_urls[bid] = url
                completed += 1
                if completed % 10 == 0:
                    print(f"  Processed {completed}/{len(buildings_df)} building images")
            except Exception as e:
                print(f"  Error processing {building_id}: {e}")

            time.sleep(0.2)  # Rate limiting

    print(f"Images fetched: {len(image_urls)} successful")
    return image_urls


# =============================================================================
# DATA TRANSFORMATION
# =============================================================================

def extract_zip_code(address):
    """Extract ZIP code from address string."""
    if not address or pd.isna(address):
        return None
    match = re.search(r'\b(\d{5})(?:-\d{4})?\b', str(address))
    return match.group(1) if match else None


def safe_float(value, default=None):
    """Safely convert to float."""
    if value is None or pd.isna(value) or value == '':
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def transform_to_portfolio_schema(beso_buildings, geocode_results, org_lookup):
    """Transform BESO data to portfolio schema."""
    print("Transforming to portfolio schema...")

    rows = []

    for bldg in beso_buildings:
        # Get basic info
        prop_id = bldg.get('pm_property_id', '')
        building_id = f"BERK_{prop_id}"

        # Get building type
        beso_type = bldg.get('primary_property_type_self_selected', '')
        portfolio_type = COMMERCIAL_TYPES.get(beso_type, 'Office')

        # Get coordinates
        lat, lon = geocode_results.get(prop_id, (None, None))

        # Get energy data
        site_eui = safe_float(bldg.get('site_eui_kbtu_ft'))
        sqft = safe_float(bldg.get('property_gfa_self_reported'))
        energy_star = safe_float(bldg.get('energy_star_score'))

        # Calculate energy totals
        elec_kwh = safe_float(bldg.get('electricity_use_grid_purchase_kwh'))
        gas_therms = safe_float(bldg.get('natural_gas_use_therms'))

        # Convert to kBtu
        elec_kbtu = elec_kwh * 3.412 if elec_kwh else None
        gas_kbtu = gas_therms * 100 if gas_therms else None  # 1 therm = 100 kBtu

        # Calculate total energy
        total_kbtu = None
        if site_eui and sqft:
            total_kbtu = site_eui * sqft
        elif elec_kbtu or gas_kbtu:
            total_kbtu = (elec_kbtu or 0) + (gas_kbtu or 0)

        # Get owner/tenant - match to canonical org names
        owner_raw = bldg.get('owner', '')
        owner = match_organization(owner_raw, org_lookup) if owner_raw else None

        # Build address
        address = bldg.get('address', '')
        zip_code = bldg.get('postal_code') or extract_zip_code(address)

        # Create row
        row = {
            'id_building': building_id,
            'id_property_name': bldg.get('property_name', ''),
            'id_source_plant_id': prop_id,
            'id_source_url': f'https://data.cityofberkeley.info/resource/5vy5-rwja.json?pm_property_id={prop_id}',

            'loc_address': f"{address}, Berkeley, CA {zip_code}".strip(', '),
            'loc_city': 'Berkeley',
            'loc_state': 'CA',
            'loc_zip': zip_code,
            'loc_lat': lat,
            'loc_lon': lon,

            'bldg_type': portfolio_type,
            'bldg_type_benchmark': TYPE_TO_BENCHMARK.get(portfolio_type, portfolio_type),
            'bldg_type_filter': TYPE_TO_FILTER.get(portfolio_type, portfolio_type),
            'bldg_vertical': TYPE_TO_VERTICAL.get(portfolio_type, 'Commercial'),
            'bldg_sqft': sqft,
            'bldg_year_built': safe_float(bldg.get('year_built')),

            'data_year': 2024.0,

            'org_owner': owner,
            'org_manager': None,
            'org_tenant': None,
            'org_tenant_subunit': None,

            'energy_site_eui': site_eui,
            'energy_eui_benchmark': EUI_BENCHMARKS.get(portfolio_type, 52.9),
            'energy_total_kbtu': total_kbtu,
            'energy_elec_kbtu': elec_kbtu,
            'energy_elec_kwh': elec_kwh,
            'energy_gas_kbtu': gas_kbtu,
            'energy_steam_kbtu': None,
            'energy_fuel_oil_kbtu': None,
            'energy_star_score': energy_star,
            'energy_climate_zone': 'South-Central',

            'cost_utility_name': 'Pacific Gas & Electric Co.',

            'meta_photo_url': None,  # Will be populated by image fetching
        }

        rows.append(row)

    df = pd.DataFrame(rows)
    print(f"Transformed {len(df)} buildings to portfolio schema")
    return df


# =============================================================================
# PORTFOLIO MERGING
# =============================================================================

def normalize_address(address):
    """Normalize address for comparison."""
    if not address or pd.isna(address):
        return ''

    addr = str(address).lower()
    # Remove common variations
    addr = re.sub(r'\s+', ' ', addr)
    addr = re.sub(r'[,.]', '', addr)
    addr = re.sub(r'\b(street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|lane|ln|way|court|ct)\b', '', addr)
    addr = addr.strip()

    return addr


def merge_with_portfolio(new_buildings_df, portfolio_df):
    """Merge new buildings into portfolio, avoiding duplicates."""
    print("Merging with existing portfolio...")

    # Get existing Berkeley addresses (normalized)
    existing_berkeley = portfolio_df[portfolio_df['loc_city'] == 'Berkeley'].copy()
    existing_addresses = set(
        existing_berkeley['loc_address'].apply(normalize_address)
    )

    print(f"  Existing Berkeley buildings: {len(existing_berkeley)}")

    # Filter out buildings that already exist
    new_buildings_df['_normalized_addr'] = new_buildings_df['loc_address'].apply(normalize_address)

    new_only = new_buildings_df[~new_buildings_df['_normalized_addr'].isin(existing_addresses)].copy()
    new_only = new_only.drop(columns=['_normalized_addr'])

    duplicates = len(new_buildings_df) - len(new_only)
    print(f"  New buildings to add: {len(new_only)} (skipped {duplicates} duplicates)")

    if len(new_only) == 0:
        print("  No new buildings to add!")
        return portfolio_df, 0

    # Ensure all portfolio columns exist in new data
    for col in portfolio_df.columns:
        if col not in new_only.columns:
            new_only[col] = None

    # Reorder columns to match portfolio
    new_only = new_only[portfolio_df.columns]

    # Concatenate
    merged = pd.concat([portfolio_df, new_only], ignore_index=True)

    return merged, len(new_only)


# =============================================================================
# ORCHESTRATION
# =============================================================================

def run_orchestration():
    """Run the populate_master orchestration pipeline."""
    print("\nRunning orchestration pipeline...")

    import subprocess
    result = subprocess.run(
        [sys.executable, str(ORCHESTRATE_SCRIPT)],
        capture_output=False,
        cwd=str(PROJECT_ROOT)
    )

    if result.returncode != 0:
        print("WARNING: Orchestration pipeline had errors")
        return False

    print("Orchestration pipeline completed successfully")
    return True


# =============================================================================
# MAIN
# =============================================================================

def main():
    start_time = datetime.now()

    print("=" * 70)
    print("ADD BERKELEY CA BUILDINGS TO NATIONWIDE PROSPECTOR")
    print("=" * 70)
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Step 1: Create backup
    print("Step 1: Creating backup...")
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = BACKUP_DIR / f'portfolio_data_backup_{timestamp}.csv'
    shutil.copy2(PORTFOLIO_DATA_PATH, backup_path)
    print(f"  Backup created: {backup_path}")
    print()

    # Step 2: Load existing data
    print("Step 2: Loading existing portfolio data...")
    portfolio_df = pd.read_csv(PORTFOLIO_DATA_PATH)
    print(f"  Loaded {len(portfolio_df)} existing buildings")
    print()

    # Step 3: Load organizations for matching
    print("Step 3: Loading organization lookup...")
    org_lookup = load_organizations()
    print(f"  Loaded {len(org_lookup)} organization aliases")
    print()

    # Step 4: Fetch BESO data
    print("Step 4: Fetching BESO data from Berkeley API...")
    try:
        beso_buildings = fetch_beso_data()
    except Exception as e:
        print(f"ERROR: Failed to fetch BESO data: {e}")
        print("Attempting fallback with smaller batch...")
        # Try smaller batch as fallback
        beso_buildings = []
        for offset in range(0, 500, 50):
            try:
                params = {'$limit': 50, '$offset': offset}
                resp = requests.get(BESO_API_URL, params=params, timeout=30)
                if resp.ok:
                    batch = resp.json()
                    if not batch:
                        break
                    beso_buildings.extend(batch)
                    print(f"  Fetched batch: {len(beso_buildings)} total")
                time.sleep(1)
            except:
                break

    if not beso_buildings:
        print("ERROR: No BESO data retrieved. Exiting.")
        return
    print()

    # Step 5: Filter to commercial buildings
    print("Step 5: Filtering to commercial building types...")
    commercial_buildings = filter_commercial_buildings(beso_buildings)
    print()

    if not commercial_buildings:
        print("No commercial buildings found. Exiting.")
        return

    # Step 6: Geocode addresses
    print("Step 6: Geocoding addresses...")
    geocode_results = batch_geocode(commercial_buildings)
    print()

    # Step 7: Transform to portfolio schema
    print("Step 7: Transforming to portfolio schema...")
    new_buildings_df = transform_to_portfolio_schema(commercial_buildings, geocode_results, org_lookup)
    print()

    # Step 8: Merge with portfolio (skip duplicates)
    print("Step 8: Merging with existing portfolio...")
    merged_df, added_count = merge_with_portfolio(new_buildings_df, portfolio_df)
    print()

    if added_count == 0:
        print("No new buildings to add. Portfolio unchanged.")
        return

    # Step 9: Save updated portfolio
    print("Step 9: Saving updated portfolio...")
    merged_df.to_csv(PORTFOLIO_DATA_PATH, index=False)
    print(f"  Saved {len(merged_df)} buildings to portfolio")
    print()

    # Step 10: Fetch images and upload to S3
    print("Step 10: Fetching building images and uploading to S3...")
    # Get only the new Berkeley buildings for image fetching
    new_berkeley = merged_df[merged_df['id_building'].str.startswith('BERK_')]
    image_urls = fetch_and_upload_images(new_berkeley, geocode_results)

    # Update photo URLs in the dataframe
    if image_urls:
        merged_df.loc[merged_df['id_building'].isin(image_urls.keys()), 'meta_photo_url'] = \
            merged_df[merged_df['id_building'].isin(image_urls.keys())]['id_building'].map(image_urls)

        # Save again with image URLs
        merged_df.to_csv(PORTFOLIO_DATA_PATH, index=False)
        print(f"  Updated {len(image_urls)} buildings with image URLs")
    print()

    # Step 11: Run orchestration pipeline
    print("Step 11: Running orchestration pipeline...")
    run_orchestration()
    print()

    # Summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("=" * 70)
    print("COMPLETED SUCCESSFULLY")
    print("=" * 70)
    print(f"Buildings added: {added_count}")
    print(f"Images uploaded: {len(image_urls)}")
    print(f"Total portfolio: {len(merged_df)}")
    print(f"Duration: {duration:.1f} seconds")
    print(f"Backup: {backup_path}")
    print("=" * 70)


if __name__ == '__main__':
    main()
