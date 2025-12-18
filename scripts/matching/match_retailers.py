#!/usr/bin/env python3
"""
Retail Location to Portfolio Building Matching Script
Optimized: Groups by city, then haversine, then address matching
"""

import pandas as pd
import numpy as np
import re
from math import radians, cos, sin, asin, sqrt

# Configuration
PORTFOLIO_FILE = '/Users/forrestmiller/Desktop/additional/ADDITIONAL RETIAL portfolio_data.csv'
RETAIL_FILE = '/Users/forrestmiller/Desktop/additional/all_retail_locations_merged.csv'

# Density thresholds (in meters)
HIGH_DENSITY_THRESHOLD = 15
MEDIUM_DENSITY_THRESHOLD = 30
LOW_DENSITY_THRESHOLD = 50

def haversine(lon1, lat1, lon2, lat2):
    """Calculate haversine distance in meters between two points"""
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return c * 6371000  # Earth radius in meters

def extract_city_state(address):
    """Extract city and state from portfolio address"""
    if pd.isna(address):
        return None, None
    match = re.search(r',\s*([^,]+),\s*([A-Z]{2})', str(address))
    if match:
        return match.group(1).strip().upper(), match.group(2).strip()
    return None, None

def normalize_city(city):
    """Normalize city name for matching"""
    if pd.isna(city) or not city:
        return None
    city = str(city).upper().strip()
    city = city.replace('SAINT ', 'ST ')
    city = city.replace('MOUNT ', 'MT ')
    city = re.sub(r'\s+', ' ', city)
    return city

def normalize_address(address):
    """Normalize address for comparison"""
    if pd.isna(address):
        return ''
    addr = str(address).upper()
    # Remove punctuation
    addr = re.sub(r'[^\w\s]', ' ', addr)
    # Standardize common abbreviations
    replacements = {
        ' STREET': ' ST',
        ' AVENUE': ' AVE',
        ' BOULEVARD': ' BLVD',
        ' DRIVE': ' DR',
        ' ROAD': ' RD',
        ' LANE': ' LN',
        ' COURT': ' CT',
        ' PLACE': ' PL',
        ' PARKWAY': ' PKWY',
        ' HIGHWAY': ' HWY',
        ' NORTH ': ' N ',
        ' SOUTH ': ' S ',
        ' EAST ': ' E ',
        ' WEST ': ' W ',
        ' NORTHEAST': ' NE',
        ' NORTHWEST': ' NW',
        ' SOUTHEAST': ' SE',
        ' SOUTHWEST': ' SW',
    }
    for old, new in replacements.items():
        addr = addr.replace(old, new)
    addr = ' '.join(addr.split())
    return addr

def extract_street_number_and_name(address):
    """Extract street number and first part of street name"""
    if not address:
        return None, None
    # Match: number + street name (first 2-3 words)
    match = re.match(r'^(\d+)\s+(.+?)(?:\s+(?:UNIT|STE|SUITE|APT|#|\d{5}).*)?$', address)
    if match:
        num = match.group(1)
        street_parts = match.group(2).split()[:3]  # First 3 words
        return num, ' '.join(street_parts)
    return None, None

def get_threshold_by_density(num_buildings_in_city):
    """Get threshold based on city density"""
    if num_buildings_in_city >= 20:
        return HIGH_DENSITY_THRESHOLD, 'high'
    elif num_buildings_in_city >= 5:
        return MEDIUM_DENSITY_THRESHOLD, 'medium'
    else:
        return LOW_DENSITY_THRESHOLD, 'low'

def main():
    print("="*60)
    print("RETAIL LOCATION TO PORTFOLIO BUILDING MATCHING")
    print("(Haversine + Address Normalization)")
    print("="*60)

    # Load data
    print("\n[1/5] Loading data...")
    portfolio_df = pd.read_csv(PORTFOLIO_FILE)
    retail_df = pd.read_csv(RETAIL_FILE)
    print(f"  Portfolio buildings: {len(portfolio_df)}")
    print(f"  Retail locations: {len(retail_df)}")

    # Extract city/state
    print("\n[2/5] Extracting and grouping by city...")
    portfolio_df['_city'], portfolio_df['_state'] = zip(*portfolio_df['address'].apply(extract_city_state))
    portfolio_df['_city_norm'] = portfolio_df['_city'].apply(normalize_city)
    retail_df['_city_norm'] = retail_df['city'].apply(normalize_city)
    retail_df['_state'] = retail_df['state'].str.upper().str.strip()

    # Normalize addresses
    print("\n[3/5] Normalizing addresses...")
    portfolio_df['_addr_norm'] = portfolio_df['address'].apply(normalize_address)
    retail_df['_addr_norm'] = retail_df['address'].apply(normalize_address)

    # Extract street number and name
    portfolio_df['_street_num'], portfolio_df['_street_name'] = zip(*portfolio_df['_addr_norm'].apply(extract_street_number_and_name))
    retail_df['_street_num'], retail_df['_street_name'] = zip(*retail_df['_addr_norm'].apply(extract_street_number_and_name))

    # Group by city
    portfolio_cities = portfolio_df.groupby(['_city_norm', '_state']).size().sort_values(ascending=False)
    retail_cities = retail_df.groupby(['_city_norm', '_state']).size().sort_values(ascending=False)
    common_cities = set(portfolio_cities.index) & set(retail_cities.index)
    print(f"  Cities in common: {len(common_cities)}")

    # STEP 1: Haversine Matching
    print("\n[4/5] Matching...")
    print("  Phase A: Haversine distance matching...")
    matches = []
    matched_building_ids = set()

    for city_state in common_cities:
        city, state = city_state
        if not city:
            continue

        city_buildings = portfolio_df[(portfolio_df['_city_norm'] == city) & (portfolio_df['_state'] == state)]
        city_retail = retail_df[(retail_df['_city_norm'] == city) & (retail_df['_state'] == state)]

        num_buildings = len(city_buildings)
        threshold, density_tier = get_threshold_by_density(num_buildings)

        for idx, building in city_buildings.iterrows():
            b_lat, b_lon = building['latitude'], building['longitude']
            if pd.isna(b_lat) or pd.isna(b_lon):
                continue

            best_match = None
            best_distance = float('inf')

            for r_idx, retail in city_retail.iterrows():
                r_lat, r_lon = retail['latitude'], retail['longitude']
                if pd.isna(r_lat) or pd.isna(r_lon):
                    continue

                dist = haversine(b_lon, b_lat, r_lon, r_lat)
                if dist < best_distance:
                    best_distance = dist
                    best_match = retail

            if best_match is not None and best_distance <= threshold:
                matches.append({
                    'building_idx': idx,
                    'building_id': building['building_id'],
                    'building_address': building['address'],
                    'current_tenant': building.get('tenant', ''),
                    'retailer': best_match['retailer'],
                    'retail_address': best_match['address'],
                    'distance_m': round(best_distance, 1),
                    'city': city,
                    'state': state,
                    'density_tier': density_tier,
                    'threshold': threshold,
                    'match_method': 'haversine'
                })
                matched_building_ids.add(idx)

    haversine_count = len(matches)
    print(f"    Haversine matches: {haversine_count}")

    # STEP 2: Address Matching for unmatched buildings
    print("  Phase B: Address normalization matching...")

    # Build address lookup for retail (by city+state+street_num+street_name)
    retail_addr_lookup = {}
    for r_idx, retail in retail_df.iterrows():
        city = retail['_city_norm']
        state = retail['_state']
        num = retail['_street_num']
        street = retail['_street_name']
        if city and state and num and street:
            key = (city, state, num, street)
            if key not in retail_addr_lookup:
                retail_addr_lookup[key] = []
            retail_addr_lookup[key].append(retail)

    # Try address matching for unmatched buildings
    for idx, building in portfolio_df.iterrows():
        if idx in matched_building_ids:
            continue

        city = building['_city_norm']
        state = building['_state']
        num = building['_street_num']
        street = building['_street_name']

        if not city or not state or not num or not street:
            continue

        key = (city, state, num, street)
        if key in retail_addr_lookup:
            retail = retail_addr_lookup[key][0]
            matches.append({
                'building_idx': idx,
                'building_id': building['building_id'],
                'building_address': building['address'],
                'current_tenant': building.get('tenant', ''),
                'retailer': retail['retailer'],
                'retail_address': retail['address'],
                'distance_m': 'N/A',
                'city': city,
                'state': state,
                'density_tier': 'N/A',
                'threshold': 'N/A',
                'match_method': 'address'
            })
            matched_building_ids.add(idx)

    address_count = len(matches) - haversine_count
    print(f"    Address matches: {address_count}")

    # Generate report
    print("\n[5/5] Generating match report...")
    print("\n" + "="*60)
    print("MATCH REPORT")
    print("="*60)

    print(f"\nTOTAL MATCHES FOUND: {len(matches)}")
    print(f"  - Haversine matches: {haversine_count}")
    print(f"  - Address matches: {address_count}")

    # By retailer
    print("\nMATCHES BY RETAILER:")
    retailer_counts = {}
    for m in matches:
        r = m['retailer']
        retailer_counts[r] = retailer_counts.get(r, 0) + 1
    for retailer, count in sorted(retailer_counts.items(), key=lambda x: -x[1]):
        print(f"  {retailer}: {count}")

    # By method
    print("\nMATCHES BY METHOD:")
    method_counts = {}
    for m in matches:
        method = m['match_method']
        method_counts[method] = method_counts.get(method, 0) + 1
    for method, count in sorted(method_counts.items(), key=lambda x: -x[1]):
        print(f"  {method}: {count}")

    # Detailed matches
    print("\n" + "-"*60)
    print("DETAILED MATCH LIST:")
    print("-"*60)

    for i, m in enumerate(matches, 1):
        current = m['current_tenant'] if m['current_tenant'] and not pd.isna(m['current_tenant']) else '(empty)'
        print(f"\n[{i}] {m['building_id']}")
        print(f"    Building: {m['building_address']}")
        print(f"    Current tenant: {current}")
        print(f"    -> MATCHED: {m['retailer']}")
        print(f"    Retail addr: {m['retail_address']}")
        print(f"    Method: {m['match_method']} | Distance: {m['distance_m']}m")

    # Save matches
    matches_df = pd.DataFrame(matches)
    matches_df.to_csv('/Users/forrestmiller/Desktop/additional/proposed_matches.csv', index=False)
    print(f"\n\nProposed matches saved to: /Users/forrestmiller/Desktop/additional/proposed_matches.csv")

    return matches, portfolio_df

if __name__ == '__main__':
    matches, portfolio_df = main()
