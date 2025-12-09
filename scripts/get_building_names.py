import pandas as pd
import requests
import time
import sys
import os
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import BUILDING_DATA_PATH

CSV_PATH = str(BUILDING_DATA_PATH)
OUTPUT_PATH = '/Users/forrestmiller/Desktop/new data/building_names.csv'  # External output location
GOOGLE_API_KEY = 'REMOVED_GOOGLE_KEY'

# Create output directory if needed
os.makedirs('/Users/forrestmiller/Desktop/new data', exist_ok=True)

def get_place_name(address, city, state, zip_code):
    """Look up place name using Google Places API"""
    query = f"{address}, {city}, {state} {zip_code}"
    url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params = {
        'input': query,
        'inputtype': 'textquery',
        'fields': 'name',
        'key': GOOGLE_API_KEY
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get('candidates') and len(data['candidates']) > 0:
            name = data['candidates'][0].get('name', '')
            # Skip if name is just the address
            if name and name.lower() != address.lower():
                return name
    except Exception as e:
        print(f"  ERROR: {e}")
    return ''

print("Loading CSV...")
sys.stdout.flush()
df = pd.read_csv(CSV_PATH, low_memory=False)
print(f"Loaded {len(df)} rows")
sys.stdout.flush()

# Filter: missing property_name AND sqft > 100,000
mask = (df['property_name'].isna() | (df['property_name'] == '')) & (df['square_footage'] > 100000)
buildings = df[mask]
total = len(buildings)

print(f"Found {total} large buildings (>100k sqft) missing names")
print(f"Output will be saved to: {OUTPUT_PATH}")
print("=" * 60)
sys.stdout.flush()

# Results list
results = []

# Look up each
found_count = 0
for i, (idx, row) in enumerate(buildings.iterrows()):
    progress = f"[{i+1}/{total}]"
    building_id = row.get('building_id', '')
    addr = row.get('address', '')
    city = row.get('city', '')
    state = row.get('state', '')

    print(f"{progress} Looking up: {addr}, {city}, {state}...", end=" ")
    sys.stdout.flush()

    name = get_place_name(addr, city, state, row.get('zip_code', ''))

    if name:
        found_count += 1
        print(f"FOUND: {name}")
        results.append({
            'building_id': building_id,
            'address': addr,
            'city': city,
            'state': state,
            'property_name': name
        })
    else:
        print("not found")
    sys.stdout.flush()

    # Save every 10 buildings
    if (i + 1) % 10 == 0:
        print(f"  >>> Saving progress ({found_count} found so far)...")
        results_df = pd.DataFrame(results)
        results_df.to_csv(OUTPUT_PATH, index=False)
        sys.stdout.flush()

    time.sleep(0.1)  # Rate limit

# Final save
results_df = pd.DataFrame(results)
results_df.to_csv(OUTPUT_PATH, index=False)
print("=" * 60)
print(f"DONE! Found names for {found_count} out of {total} buildings.")
print(f"Results saved to: {OUTPUT_PATH}")
