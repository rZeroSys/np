#!/usr/bin/env python3
"""
Update Retail Store utilization rates based on customer traffic patterns.

Sources:
- Internal methodology: ODCV_SAVINGS_METHODOLOGY_COMPLETE.md
- StoreForce: "50% of week's traffic in busiest 20 hours"
- NRF retail traffic studies

Methodology:
For retail, "utilization" represents average customer density as % of design
capacity DURING OPERATING HOURS. Closed hours are already in setback mode,
so the DCV opportunity comes from traffic variability when open.

Traffic patterns (from docs):
- Opening/closing: 5% of design (staff only)
- Mid-morning lull: 15-20% capacity
- Lunch rush: 60-70% capacity
- Afternoon lull: 20-30% capacity
- Evening rush: 60-80% capacity

Weighted average during operating hours: ~35-45% of design capacity

Store types vary:
- Grocery: more consistent traffic, higher baseline (~50%)
- Apparel: more peaks/valleys (~35%)
- Big box: weekend-heavy, weekday-light (~40%)
- Mall stores: follows mall traffic (~38%)
"""

import pandas as pd
import shutil
from pathlib import Path
from datetime import datetime

# Paths
INPUT_FILE = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv'
BACKUP_DIR = '/Users/forrestmiller/Desktop/nationwide-prospector/BACKUPS_GO_HERE/csv_backups'

# Retail utilization = average customer density during operating hours
# This represents what % of design ventilation capacity is needed on average
#
# Based on traffic patterns in methodology docs:
# - Morning lull (15-20%), lunch rush (60-70%), afternoon lull (20-30%), evening rush (60-80%)
# - Weighted average across a typical day: ~40% of design capacity
#
# Variation by location (urban stores busier, suburban more peaks/valleys):
RETAIL_UTILIZATION_BY_CITY = {
    # High-traffic urban (more consistent, higher baseline)
    'New York': 0.48,        # Dense urban, consistent foot traffic
    'San Francisco': 0.45,   # Urban core
    'Chicago': 0.45,         # Urban core
    'Boston': 0.45,          # Urban/walkable
    'Washington': 0.44,      # Urban
    'Seattle': 0.43,         # Urban
    'Philadelphia': 0.43,    # Urban

    # Medium-traffic suburban/mixed
    'Los Angeles': 0.40,     # Car-dependent, peak-driven
    'Denver': 0.40,          # Mixed
    'San Diego': 0.40,       # Suburban
    'Portland': 0.40,        # Mixed
    'Atlanta': 0.38,         # Suburban sprawl
    'Phoenix': 0.38,         # Suburban sprawl
    'Houston': 0.38,         # Suburban sprawl
    'Dallas': 0.38,          # Suburban sprawl

    # Lower-traffic / highly variable
    'Minneapolis': 0.35,     # Seasonal
    'Kansas City': 0.35,     # Regional
    'St. Louis': 0.35,       # Regional
}

# State-level defaults
STATE_UTILIZATION_DEFAULTS = {
    'NY': 0.45,    # Urban-heavy
    'CA': 0.40,    # Mixed
    'IL': 0.42,    # Chicago + suburbs
    'TX': 0.38,    # Suburban sprawl
    'FL': 0.40,    # Tourism + suburban
    'PA': 0.42,    # Urban corridor
    'MA': 0.44,    # Boston-heavy
    'WA': 0.42,    # Seattle + suburban
    'CO': 0.40,    # Denver + mountain
    'GA': 0.38,    # Atlanta sprawl
    'AZ': 0.38,    # Phoenix sprawl
}

# National average (based on weighted traffic patterns)
DEFAULT_RETAIL_UTILIZATION = 0.40  # 40% average density during operating hours

def create_backup():
    """Create timestamped backup before changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(INPUT_FILE, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path

def get_retail_utilization(city, state):
    """Get retail utilization for a city/state."""
    if city in RETAIL_UTILIZATION_BY_CITY:
        return RETAIL_UTILIZATION_BY_CITY[city]

    state_upper = str(state).upper().strip()
    if state_upper in STATE_UTILIZATION_DEFAULTS:
        return STATE_UTILIZATION_DEFAULTS[state_upper]

    return DEFAULT_RETAIL_UTILIZATION

def update_retail_utilization():
    """Update utilization rates for retail store buildings."""
    print("Loading portfolio data...")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df)} buildings")

    # Track updates
    city_match = 0
    state_match = 0
    default_used = 0

    # Get retail buildings only
    retail_mask = df['bldg_type'] == 'Retail Store'
    print(f"Found {retail_mask.sum()} retail store buildings")

    for idx in df[retail_mask].index:
        city = str(df.loc[idx, 'loc_city']).strip()
        state = str(df.loc[idx, 'loc_state']).strip()

        # Get utilization
        if city in RETAIL_UTILIZATION_BY_CITY:
            utilization = RETAIL_UTILIZATION_BY_CITY[city]
            city_match += 1
        elif state.upper() in STATE_UTILIZATION_DEFAULTS:
            utilization = STATE_UTILIZATION_DEFAULTS[state.upper()]
            state_match += 1
        else:
            utilization = DEFAULT_RETAIL_UTILIZATION
            default_used += 1

        # Retail vacancy stays as-is (it's storefront vacancy, not relevant to DCV)
        # The opportunity comes from traffic variability, not empty storefronts
        df.loc[idx, 'occ_utilization_rate'] = utilization

    print(f"\nUpdates summary:")
    print(f"  - City-specific: {city_match}")
    print(f"  - State-level: {state_match}")
    print(f"  - National average: {default_used}")

    # Save
    print(f"\nSaving to {INPUT_FILE}...")
    df.to_csv(INPUT_FILE, index=False)
    print("Done!")

    # Show examples
    print("\n=== RETAIL TRAFFIC-BASED UTILIZATION ===")
    print("(Average customer density during operating hours as % of design capacity)")
    print()
    print("City            | Utilization | Opportunity | Notes")
    print("-" * 70)
    for city, util in [('New York', 0.48), ('Los Angeles', 0.40), ('Atlanta', 0.38), ('Minneapolis', 0.35)]:
        opp = 1 - util
        note = "urban/consistent" if util > 0.44 else "suburban/variable" if util < 0.40 else "mixed"
        print(f"{city:15} | {util*100:5.0f}%       | {opp*100:5.0f}%       | {note}")

    print()
    print("National avg    | 40%         | 60%         | typical retail")
    print()
    print("Compare to old: | 65%         | 35%         | (was bogus default)")

if __name__ == '__main__':
    create_backup()
    update_retail_utilization()
