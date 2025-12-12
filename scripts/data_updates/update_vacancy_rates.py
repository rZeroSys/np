#!/usr/bin/env python3
"""
Update office vacancy AND utilization rates with real 2024-2025 data by city.

Sources:
- Kastle Systems Return-to-Office data (2024-2025)
- CommercialEdge National Office Report (Jan 2025)
- CBRE Market Reports (Q4 2024)
- Cushman & Wakefield MarketBeats (2024-2025)
- Kidder Mathews Market Reports (2025)
- Colliers Market Reports (2024)
- CommercialCafe Market Trends (2024)
"""

import pandas as pd
import shutil
from pathlib import Path
from datetime import datetime

# Paths
INPUT_FILE = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv'
BACKUP_DIR = '/Users/forrestmiller/Desktop/nationwide-prospector/BACKUPS_GO_HERE/csv_backups'

# City data: (vacancy_rate, utilization_rate) - both as decimals
# Utilization = weekday avg % of seats used (Kastle Systems)
# Vacancy = % of leasable SF vacant
CITY_DATA = {
    # Major metros - from user-provided table (Kastle + market reports)
    'San Francisco': (0.34, 0.38),   # 34% vacancy, 38% utilization
    'San Diego': (0.16, 0.45),       # 16% vacancy, 45% utilization
    'Los Angeles': (0.239, 0.48),    # 23.9% vacancy, 48% utilization
    'San Jose': (0.222, 0.49),       # 22.2% vacancy, 49% utilization
    'Sacramento': (0.188, 0.43),     # 18.8% vacancy, 43% utilization
    'Portland': (0.266, 0.34),       # 26.6% vacancy, 34% utilization
    'New York': (0.15, 0.55),        # 15% vacancy (Manhattan), 55% utilization
    'Washington': (0.224, 0.34),     # 22.4% vacancy, 34% utilization
    'Boston': (0.236, 0.42),         # 23.6% vacancy, 42% utilization
    'Atlanta': (0.25, 0.48),         # 25% vacancy, 48% utilization
    'Denver': (0.26, 0.39),          # 26% vacancy, 39% utilization
    'Seattle': (0.27, 0.42),         # 27% vacancy, 42% utilization
    'Chicago': (0.255, 0.37),        # 25.5% vacancy, 37% utilization
    'Philadelphia': (0.193, 0.44),   # 19.3% vacancy, 44% utilization
    'Kansas City': (0.178, 0.49),    # 17.8% vacancy, 49% utilization

    # Other cities - vacancy from market reports, utilization estimated from similar metros
    'St. Louis': (0.33, 0.40),       # 33% CBD vacancy, ~40% util (Midwest)
    'Orlando': (0.20, 0.45),         # ~20% vacancy, ~45% util (Sunbelt)
    'Cambridge': (0.12, 0.42),       # 12% vacancy (LPC), Boston-area util

    # Bay Area / Silicon Valley
    'Oakland': (0.24, 0.38),         # 24% vacancy, SF-area utilization
    'Berkeley': (0.21, 0.38),        # East Bay market
    'Sunnyvale': (0.21, 0.49),       # Silicon Valley, San Jose-like util
    'Santa Clara': (0.18, 0.49),     # Silicon Valley
    'Mountain View': (0.20, 0.49),   # Silicon Valley
    'Palo Alto': (0.20, 0.49),       # Silicon Valley
    'Fremont': (0.21, 0.45),         # East Bay/Silicon Valley blend
    'Pleasanton': (0.20, 0.45),      # Tri-Valley

    # Orange County / Irvine
    'Irvine': (0.15, 0.48),          # OC market, LA-like util
    'Newport Beach': (0.15, 0.48),
    'Santa Ana': (0.15, 0.48),
    'Anaheim': (0.15, 0.48),
    'Costa Mesa': (0.15, 0.48),
    'Carlsbad': (0.16, 0.45),        # San Diego North

    # LA suburbs
    'Long Beach': (0.10, 0.48),      # 10% vacancy, LA-area util
    'Santa Monica': (0.20, 0.48),
    'Pasadena': (0.15, 0.48),
    'Glendale': (0.19, 0.48),
    'Burbank': (0.22, 0.48),
    'Torrance': (0.16, 0.48),
    'El Segundo': (0.16, 0.48),
    'Ontario': (0.16, 0.45),         # Inland Empire
    'Riverside': (0.16, 0.45),
    'San Bernardino': (0.18, 0.45),
    'Corona': (0.16, 0.45),

    # Central Valley CA
    'Fresno': (0.12, 0.43),          # Sacramento-like util
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

def update_vacancy_and_utilization():
    """Update vacancy AND utilization rates for office buildings by city."""
    print("Loading portfolio data...")
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
        if city in CITY_DATA:
            vacancy, utilization = CITY_DATA[city]
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
    for city in ['San Francisco', 'Seattle', 'Denver', 'Chicago', 'Boston', 'Los Angeles', 'New York', 'Kansas City']:
        if city in CITY_DATA:
            vac, util = CITY_DATA[city]
            print(f"  {city}: {vac*100:.1f}% vacancy, {util*100:.0f}% utilization")

if __name__ == '__main__':
    create_backup()
    update_vacancy_and_utilization()
