#!/usr/bin/env python3
"""
Update Hotel utilization rates with research-based data.

Sources:
- STR (Smith Travel Research) 2024-2025 hotel occupancy data
- AHLA 2025 State of the Industry Report: 63% national occupancy
- DOE Guest Room HVAC Occupancy-Based Control Technology Report (2012)
- LEED FTE calculation: guests present ~10 hours/day (42% of day)
- IEA: Hotels can reduce HVAC 20-30% with smart controls

Calculation methodology:
  True Utilization = Room Occupancy Rate × Guest Presence Factor

  Where:
  - Room Occupancy = % of rooms sold (varies by city, 50-88%)
  - Guest Presence = % of day guest is physically in room (~42-45%)

  Example: NYC at 87% occupancy × 45% presence = 39% true utilization

This differs from offices where "utilization" means weekday seat occupancy.
For hotels, we must account for guests being OUT of the room most of the day.
"""

import pandas as pd
import shutil
from pathlib import Path
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import PORTFOLIO_DATA_PATH, BACKUP_DIR as CONFIG_BACKUP_DIR

# Paths
INPUT_FILE = str(PORTFOLIO_DATA_PATH)
BACKUP_DIR = str(CONFIG_BACKUP_DIR)

# Hotel occupancy rates by city (STR 2024-2025 data)
# Source: STR monthly reports, AHLA State of Industry
HOTEL_OCCUPANCY_BY_CITY = {
    # Top performers (STR 2024-2025)
    'New York': 0.87,       # 87% - consistently highest in US
    'Miami': 0.83,          # 83% - strong leisure market
    'Seattle': 0.82,        # 82% - tech business travel
    'Boston': 0.78,         # 78% - business + education
    'San Francisco': 0.75,  # 75% - recovering from COVID lows
    'Los Angeles': 0.74,    # 74% - large market, variable
    'Chicago': 0.72,        # 72% - convention city
    'Washington': 0.71,     # 71% - government/business
    'San Diego': 0.73,      # 73% - leisure + military
    'Denver': 0.68,         # 68% - mountain/business
    'Atlanta': 0.70,        # 70% - hub city
    'Philadelphia': 0.69,   # 69% - business corridor
    'Portland': 0.65,       # 65% - smaller market
    'Phoenix': 0.55,        # 55% - seasonal, one of lowest
    'Houston': 0.56,        # 56% - hurricane impacts
    'Minneapolis': 0.50,    # 50% - lowest tier
    'St. Louis': 0.52,      # 52% - lowest tier
    'Kansas City': 0.60,    # 60% - midmarket
    'Orlando': 0.75,        # 75% - theme parks

    # California cities (use regional data)
    'San Jose': 0.70,       # 70% - tech business
    'Irvine': 0.70,         # 70% - business
    'Long Beach': 0.70,     # 70% - port city
    'Sacramento': 0.65,     # 65% - state capital
    'Fresno': 0.58,         # 58% - central valley
    'Bakersfield': 0.55,    # 55% - central valley
}

# Guest presence factor: what % of 24-hour period is guest in room?
# Source: DOE study, LEED calculations estimate 10 hrs/day = 42%
# Business travelers: in room 8-10 hrs (33-42%)
# Leisure travelers: in room 10-14 hrs (42-58%)
# Weighted average: ~45%
GUEST_PRESENCE_FACTOR = 0.45

# State-level defaults (for cities not in lookup)
STATE_OCCUPANCY_DEFAULTS = {
    'NY': 0.80,    # Strong urban markets
    'CA': 0.68,    # Mixed - coastal high, inland lower
    'FL': 0.72,    # Tourism strong
    'TX': 0.62,    # Variable markets
    'IL': 0.68,    # Chicago-driven
    'MA': 0.75,    # Boston-driven
    'WA': 0.72,    # Seattle-driven
    'CO': 0.65,    # Mountain tourism
    'DC': 0.71,    # Government travel
    'GA': 0.68,    # Atlanta hub
    'PA': 0.65,    # Philadelphia corridor
    'NV': 0.75,    # Las Vegas
    'AZ': 0.58,    # Seasonal
    'OR': 0.62,    # Portland + coast
}

# National average occupancy (AHLA 2025)
DEFAULT_OCCUPANCY = 0.63

def create_backup():
    """Create timestamped backup before changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(INPUT_FILE, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path

def get_occupancy_rate(city, state):
    """Get hotel occupancy rate for a city/state."""
    # Try city-specific first
    if city in HOTEL_OCCUPANCY_BY_CITY:
        return HOTEL_OCCUPANCY_BY_CITY[city]

    # Fall back to state default
    state_upper = str(state).upper().strip()
    if state_upper in STATE_OCCUPANCY_DEFAULTS:
        return STATE_OCCUPANCY_DEFAULTS[state_upper]

    # National average
    return DEFAULT_OCCUPANCY

def update_hotel_utilization():
    """Update utilization rates for hotel buildings."""
    print("Loading portfolio data...")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df)} buildings")

    # Track updates
    city_match = 0
    state_match = 0
    default_used = 0

    # Get hotel buildings only
    hotel_mask = df['bldg_type'] == 'Hotel'
    print(f"Found {hotel_mask.sum()} hotel buildings")

    for idx in df[hotel_mask].index:
        city = str(df.loc[idx, 'loc_city']).strip()
        state = str(df.loc[idx, 'loc_state']).strip()

        # Get room occupancy rate
        if city in HOTEL_OCCUPANCY_BY_CITY:
            occupancy = HOTEL_OCCUPANCY_BY_CITY[city]
            city_match += 1
        elif state.upper() in STATE_OCCUPANCY_DEFAULTS:
            occupancy = STATE_OCCUPANCY_DEFAULTS[state.upper()]
            state_match += 1
        else:
            occupancy = DEFAULT_OCCUPANCY
            default_used += 1

        # Calculate true utilization
        # True Utilization = Room Occupancy × Guest Presence
        utilization = occupancy * GUEST_PRESENCE_FACTOR

        # Hotels don't have vacancy in the office sense
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
    print(f"Guest presence factor: {GUEST_PRESENCE_FACTOR*100:.0f}% of day in room")
    print()
    print("City            | Occupancy | × Presence | = Utilization | Opportunity")
    print("-" * 75)
    for city in ['New York', 'Miami', 'Chicago', 'Denver', 'Phoenix', 'Minneapolis']:
        if city in HOTEL_OCCUPANCY_BY_CITY:
            occ = HOTEL_OCCUPANCY_BY_CITY[city]
            util = occ * GUEST_PRESENCE_FACTOR
            opp = 1 - util
            print(f"{city:15} | {occ*100:5.0f}%    | × 45%      | = {util*100:5.1f}%       | {opp*100:5.1f}%")

    print()
    print("National avg    | 63%       | × 45%      | = 28.4%       | 71.6%")

if __name__ == '__main__':
    create_backup()
    update_hotel_utilization()
