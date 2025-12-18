#!/usr/bin/env python3
"""
Update office vacancy AND utilization rates with real Q3 2025 data by city.

Sources:
- CBRE Q3 2025 Market Reports (vacancy)
- Kastle Systems Return-to-Office data (utilization)
- Data file: data/source/market_vacancy_utilization_Q3_2025.csv
"""

import pandas as pd
import shutil
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import PORTFOLIO_DATA_PATH, BACKUP_DIR as CONFIG_BACKUP_DIR, SOURCE_DATA_DIR

# Paths
INPUT_FILE = str(PORTFOLIO_DATA_PATH)
BACKUP_DIR = str(CONFIG_BACKUP_DIR)
MARKET_DATA_FILE = str(SOURCE_DATA_DIR / 'market_vacancy_utilization_Q3_2025.csv')

# Kastle-based utilization estimates for cities without utilization in CSV
# These are kept from original research when CSV only has vacancy
KASTLE_UTILIZATION_ESTIMATES = {
    'San Francisco': 0.38,   # Tech WFH heavy
    'San Diego': 0.45,
    'Los Angeles': 0.48,
    'San Jose': 0.49,        # Silicon Valley
    'Sacramento': 0.43,
    'Portland': 0.34,        # WFH heavy
    'Boston': 0.42,
    'Denver': 0.39,
    'Seattle': 0.42,
    'Chicago': 0.37,
    'Philadelphia': 0.44,
    'Kansas City': 0.49,
    'St. Louis': 0.40,
    'Orlando': 0.45,
    'Jacksonville': 0.45,
    'Oakland': 0.38,         # SF-area
    'Irvine': 0.48,          # OC market
    'Anaheim': 0.48,
    'Santa Ana': 0.48,
    'Newport Beach': 0.48,
    'Costa Mesa': 0.48,
    'Ontario': 0.45,         # Inland Empire
    'Riverside': 0.45,
    'San Bernardino': 0.45,
}

# Additional cities not in CSV - keep full (vacancy, utilization) data
ADDITIONAL_CITIES = {
    # Bay Area suburbs
    'Berkeley': (0.21, 0.38),
    'Sunnyvale': (0.21, 0.49),
    'Santa Clara': (0.18, 0.49),
    'Mountain View': (0.20, 0.49),
    'Palo Alto': (0.20, 0.49),
    'Fremont': (0.21, 0.45),
    'Pleasanton': (0.20, 0.45),
    'Cambridge': (0.12, 0.42),

    # LA suburbs
    'Long Beach': (0.10, 0.48),
    'Santa Monica': (0.20, 0.48),
    'Pasadena': (0.15, 0.48),
    'Glendale': (0.19, 0.48),
    'Burbank': (0.22, 0.48),
    'Torrance': (0.16, 0.48),
    'El Segundo': (0.16, 0.48),
    'Corona': (0.16, 0.45),
    'Carlsbad': (0.16, 0.45),

    # Central Valley CA
    'Fresno': (0.12, 0.43),
    'Bakersfield': (0.15, 0.43),
    'Roseville': (0.14, 0.43),
    'Rancho Cordova': (0.14, 0.43),
}

# Default for unknown cities (national averages)
DEFAULT_VACANCY = 0.20      # 20% national average
DEFAULT_UTILIZATION = 0.42  # ~42% national average

def create_backup():
    """Create timestamped backup before changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(INPUT_FILE, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path

def load_market_data():
    """Load Q3 2025 market data from CSV and combine with estimates."""
    print(f"Loading market data from {MARKET_DATA_FILE}...")
    market_df = pd.read_csv(MARKET_DATA_FILE)

    # Build city data dictionary
    city_data = {}
    csv_cities = 0

    for _, row in market_df.iterrows():
        city = row['loc_city']
        vacancy = row['occ_vacancy_rate']

        # Use CSV utilization if available, otherwise use Kastle estimate
        if pd.notna(row['occ_utilization_rate']):
            utilization = row['occ_utilization_rate']
            source = "CSV"
        elif city in KASTLE_UTILIZATION_ESTIMATES:
            utilization = KASTLE_UTILIZATION_ESTIMATES[city]
            source = "Kastle estimate"
        else:
            utilization = DEFAULT_UTILIZATION
            source = "default"

        city_data[city] = (vacancy, utilization)
        csv_cities += 1

    # Add additional cities not in CSV
    for city, (vac, util) in ADDITIONAL_CITIES.items():
        if city not in city_data:
            city_data[city] = (vac, util)

    print(f"  - {csv_cities} cities from Q3 2025 CSV")
    print(f"  - {len(ADDITIONAL_CITIES)} additional cities from estimates")
    print(f"  - {len(city_data)} total cities in lookup")

    return city_data

def update_vacancy_and_utilization():
    """Update vacancy AND utilization rates for office buildings by city."""
    # Load market data
    city_data = load_market_data()

    print("\nLoading portfolio data...")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df)} buildings")

    # Track updates
    city_match = 0
    default_used = 0

    # Get office buildings only
    office_mask = df['bldg_type'] == 'Office'
    print(f"Found {office_mask.sum()} office buildings")

    for idx in df[office_mask].index:
        city = str(df.loc[idx, 'loc_city']).strip()

        # Look up city data
        if city in city_data:
            vacancy, utilization = city_data[city]
            df.loc[idx, 'occ_vacancy_rate'] = vacancy
            df.loc[idx, 'occ_utilization_rate'] = utilization
            city_match += 1
        else:
            # Use national averages for unknown cities
            df.loc[idx, 'occ_vacancy_rate'] = DEFAULT_VACANCY
            df.loc[idx, 'occ_utilization_rate'] = DEFAULT_UTILIZATION
            default_used += 1

    print(f"\nUpdates summary:")
    print(f"  - Updated with city-specific data: {city_match}")
    print(f"  - Updated with national averages: {default_used}")

    # Save
    print(f"\nSaving to {INPUT_FILE}...")
    df.to_csv(INPUT_FILE, index=False)
    print("Done!")

    # Show sample of updates by city
    print("\nSample rates applied (vacancy / utilization):")
    sample_cities = ['San Francisco', 'Seattle', 'Denver', 'Chicago', 'Boston',
                     'Los Angeles', 'New York', 'Washington', 'Atlanta']
    for city in sample_cities:
        if city in city_data:
            vac, util = city_data[city]
            print(f"  {city}: {vac*100:.1f}% vacancy, {util*100:.1f}% utilization")

if __name__ == '__main__':
    create_backup()
    update_vacancy_and_utilization()
