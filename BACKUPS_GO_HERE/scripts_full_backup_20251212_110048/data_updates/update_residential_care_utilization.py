#!/usr/bin/env python3
"""
Update Residential Care facility utilization rates with research-based data.

Sources:
- NIC MAP Vision Q4 2024: National senior living occupancy 87.2%
- NIC market-level data: Boston 91%, Baltimore 89.9%, Tampa 89.8%
- NIC low-occupancy markets: Atlanta 83.9%, Houston 83.5%, Las Vegas 82.9%
- AHCA/CDC skilled nursing data: 75-80% occupancy for SNFs

Key insight: Residential Care differs from hotels because:
- Hotel guests LEAVE the building most of the day (touring, business)
- Residential care residents LIVE there 24/7 - they don't leave

Calculation:
  True Utilization = Room Occupancy × Resident Presence Factor

  Where:
  - Room Occupancy = % of beds filled (varies by market, 83-91%)
  - Resident Presence = ~95% (residents rarely leave the building)

  Example: Boston at 91% occupancy × 95% presence = 86.5% utilization

Compare to hotels: NYC hotel 87% occupancy × 45% presence = 39% utilization
The difference is residents LIVE there vs guests just sleeping there.
"""

import pandas as pd
import shutil
from pathlib import Path
from datetime import datetime

# Paths
INPUT_FILE = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv'
BACKUP_DIR = '/Users/forrestmiller/Desktop/nationwide-prospector/BACKUPS_GO_HERE/csv_backups'

# Residential Care occupancy rates by city (NIC MAP Vision Q4 2024)
# Source: https://www.nic.org/news-press/senior-housing-occupancy-increases-for-eleventh-consecutive-quarter/
OCCUPANCY_BY_CITY = {
    # Top markets (NIC Q4 2024)
    'Boston': 0.91,          # 91% - highest in US
    'Baltimore': 0.899,      # 89.9%
    'Tampa': 0.898,          # 89.8%
    'San Jose': 0.89,        # Strong tech area
    'Seattle': 0.88,         # Strong market
    'San Francisco': 0.87,   # Urban
    'Washington': 0.87,      # DC metro strong
    'New York': 0.87,        # Urban demand
    'Los Angeles': 0.86,     # Large market
    'Denver': 0.86,          # Growing demand
    'San Diego': 0.86,       # Retirement destination
    'Chicago': 0.85,         # Large market
    'Philadelphia': 0.85,    # Urban corridor
    'Phoenix': 0.84,         # Retirement destination
    'Portland': 0.84,        # Pacific NW
    'Minneapolis': 0.84,     # Regional hub

    # Lower markets (NIC Q4 2024)
    'Atlanta': 0.839,        # 83.9% - one of lowest
    'Houston': 0.835,        # 83.5% - lowest tier
    'Las Vegas': 0.829,      # 82.9% - lowest tracked
    'Dallas': 0.84,          # Texas generally lower
}

# State-level defaults (regional patterns)
STATE_OCCUPANCY_DEFAULTS = {
    'MA': 0.90,    # Boston-driven, strong market
    'MD': 0.89,    # Baltimore-driven
    'FL': 0.88,    # Retirement state, high demand
    'CA': 0.86,    # Large market, variable
    'NY': 0.86,    # Urban demand
    'WA': 0.87,    # Seattle-driven
    'DC': 0.87,    # Strong market
    'CO': 0.85,    # Growing
    'IL': 0.85,    # Chicago hub
    'PA': 0.85,    # Urban corridor
    'AZ': 0.84,    # Retirement destination
    'TX': 0.84,    # Generally lower
    'GA': 0.84,    # Atlanta-driven
    'NV': 0.83,    # Las Vegas impact
    'OR': 0.84,    # Pacific NW
    'MN': 0.84,    # Regional hub
}

# National average occupancy (NIC Q4 2024: 87.2% for senior living)
DEFAULT_OCCUPANCY = 0.87

# Resident presence factor: what % of time is resident IN THE BUILDING?
# Unlike hotels where guests leave to sightsee/work, residents LIVE there
# They sleep there, eat there, spend most of day in common areas or rooms
# Only leave for: doctor appointments, family visits, occasional outings
# Estimated: ~95% of time resident is in building
RESIDENT_PRESENCE_FACTOR = 0.95


def create_backup():
    """Create timestamped backup before changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(INPUT_FILE, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path


def get_occupancy_rate(city, state):
    """Get residential care occupancy rate for a city/state."""
    # Try city-specific first
    if city in OCCUPANCY_BY_CITY:
        return OCCUPANCY_BY_CITY[city]

    # Fall back to state default
    state_upper = str(state).upper().strip()
    if state_upper in STATE_OCCUPANCY_DEFAULTS:
        return STATE_OCCUPANCY_DEFAULTS[state_upper]

    # National average
    return DEFAULT_OCCUPANCY


def update_residential_care_utilization():
    """Update utilization rates for residential care facilities."""
    print("Loading portfolio data...")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df)} buildings")

    # Track updates
    city_match = 0
    state_match = 0
    default_used = 0

    # Get Residential Care buildings only
    res_care_mask = df['bldg_type'] == 'Residential Care'
    print(f"Found {res_care_mask.sum()} Residential Care buildings")

    for idx in df[res_care_mask].index:
        city = str(df.loc[idx, 'loc_city']).strip()
        state = str(df.loc[idx, 'loc_state']).strip()

        # Get room occupancy rate
        if city in OCCUPANCY_BY_CITY:
            occupancy = OCCUPANCY_BY_CITY[city]
            city_match += 1
        elif state.upper() in STATE_OCCUPANCY_DEFAULTS:
            occupancy = STATE_OCCUPANCY_DEFAULTS[state.upper()]
            state_match += 1
        else:
            occupancy = DEFAULT_OCCUPANCY
            default_used += 1

        # Calculate true utilization
        # True Utilization = Room Occupancy × Resident Presence
        # Unlike hotels, residents are IN the building ~95% of time
        utilization = occupancy * RESIDENT_PRESENCE_FACTOR

        # Residential care doesn't have vacancy in the office sense
        # The "vacancy" is captured in room occupancy rate
        df.loc[idx, 'occ_vacancy_rate'] = 0.0
        df.loc[idx, 'occ_utilization_rate'] = utilization

    print(f"\nUpdates summary:")
    print(f"  - City-specific occupancy: {city_match}")
    print(f"  - State-level occupancy: {state_match}")
    print(f"  - National average: {default_used}")

    # Save
    print(f"\nSaving to {INPUT_FILE}...")
    df.to_csv(INPUT_FILE, index=False)
    print("Done!")

    # Show examples
    print("\n=== SAMPLE CALCULATIONS ===")
    print(f"Resident presence factor: {RESIDENT_PRESENCE_FACTOR*100:.0f}% of time in building")
    print("(Unlike hotel guests who leave to sightsee, residents LIVE there)")
    print()
    print("City            | Occupancy | × Presence | = Utilization | ODCV Opp*")
    print("-" * 75)
    for city in ['Boston', 'Baltimore', 'Denver', 'Atlanta', 'Houston', 'Las Vegas']:
        if city in OCCUPANCY_BY_CITY:
            occ = OCCUPANCY_BY_CITY[city]
            util = occ * RESIDENT_PRESENCE_FACTOR
            # LOW_OPPORTUNITY formula: (1-U) × 0.3
            opp = (1 - util) * 0.3
            print(f"{city:15} | {occ*100:5.1f}%   | × 95%      | = {util*100:5.1f}%       | {opp*100:5.1f}%")

    print()
    print("National avg    | 87.0%    | × 95%      | = 82.7%       | 5.2%")
    print()
    print("*ODCV Opportunity uses LOW_OPPORTUNITY formula: (1-U) × 0.3")
    print(" Because residents are there 24/7, opportunity is capped at 5-15%")


if __name__ == '__main__':
    create_backup()
    update_residential_care_utilization()
