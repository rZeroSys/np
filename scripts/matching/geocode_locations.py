#!/usr/bin/env python3
"""
Geocode retailer locations using Google Geocoding API.
Saves results incrementally to CSV.
"""

import csv
import urllib.request
import urllib.parse
import json
import time
import os
from datetime import datetime

# Configuration
API_KEY = os.environ.get("GOOGLE_API_KEY", "")
INPUT_FILE = "/Users/forrestmiller/Desktop/additional/consolidated_retailer_locations.csv"
OUTPUT_FILE = "/Users/forrestmiller/Desktop/additional/consolidated_retailer_locations_geocoded.csv"
DELAY_BETWEEN_REQUESTS = 0.1  # seconds between API calls

def geocode_address(address, city, state):
    """Call Google Geocoding API to get lat/lon for an address."""
    # Build full address string
    if address:
        full_address = f"{address}, {city}, {state}"
    else:
        full_address = f"{city}, {state}"

    # URL encode the address
    encoded_address = urllib.parse.quote(full_address)
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={API_KEY}"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

        if data['status'] == 'OK' and data['results']:
            location = data['results'][0]['geometry']['location']
            return location['lat'], location['lng'], 'OK'
        else:
            return None, None, data.get('status', 'UNKNOWN')

    except Exception as e:
        return None, None, f'ERROR: {str(e)}'

def main():
    print("=" * 70)
    print("RETAILER LOCATION GEOCODER")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print(f"\nInput:  {INPUT_FILE}")
    print(f"Output: {OUTPUT_FILE}")
    print()

    # Read input file
    rows = []
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        input_fieldnames = reader.fieldnames
        rows = list(reader)

    total = len(rows)
    print(f"Total locations to geocode: {total}")
    print("-" * 70)

    # Output fieldnames (add lat/lon)
    output_fieldnames = list(input_fieldnames) + ['latitude', 'longitude', 'geocode_status']

    # Check if output file exists and has data (for resuming)
    already_processed = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = f"{row['retailer']}|{row['city']}|{row['address']}"
                already_processed.add(key)
        print(f"Resuming: {len(already_processed)} already processed")
        print("-" * 70)

    # Open output file in append mode if resuming, else write mode
    mode = 'a' if already_processed else 'w'

    with open(OUTPUT_FILE, mode, newline='', encoding='utf-8') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=output_fieldnames)

        # Write header only if new file
        if not already_processed:
            writer.writeheader()

        success_count = 0
        error_count = 0
        skipped_count = len(already_processed)

        for i, row in enumerate(rows, 1):
            # Check if already processed
            key = f"{row['retailer']}|{row['city']}|{row['address']}"
            if key in already_processed:
                continue

            retailer = row['retailer']
            city = row['city']
            state = row['state']
            address = row.get('address', '')

            # Geocode
            lat, lon, status = geocode_address(address, city, state)

            # Add geocoding results to row
            row['latitude'] = lat if lat else ''
            row['longitude'] = lon if lon else ''
            row['geocode_status'] = status

            # Write to CSV immediately
            writer.writerow(row)
            outfile.flush()  # Ensure it's written to disk

            # Update counters
            if status == 'OK':
                success_count += 1
                status_icon = "✓"
            else:
                error_count += 1
                status_icon = "✗"

            # Verbose output
            processed = skipped_count + success_count + error_count
            pct = (processed / total) * 100

            if lat and lon:
                print(f"[{processed:4d}/{total}] {pct:5.1f}% {status_icon} {retailer:15} | {city:20} | {lat:.6f}, {lon:.6f}")
            else:
                print(f"[{processed:4d}/{total}] {pct:5.1f}% {status_icon} {retailer:15} | {city:20} | {status}")

            # Rate limiting
            time.sleep(DELAY_BETWEEN_REQUESTS)

    # Summary
    print("-" * 70)
    print(f"\nCOMPLETE!")
    print(f"  Successful: {success_count}")
    print(f"  Errors:     {error_count}")
    print(f"  Skipped:    {skipped_count}")
    print(f"  Total:      {success_count + error_count + skipped_count}")
    print(f"\nResults saved to: {OUTPUT_FILE}")
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
