#!/usr/bin/env python3
"""
Update Library/Museum utilization rates based on visitor patterns.

Key insight: HVAC runs 24/7 for collection preservation, but visitors are sparse!

Operating hours:
- Typical library: 9am-5pm weekdays, limited weekends
- Museums: 10am-5pm, closed Mondays
- Both: ~50 hrs/week open to public

Visitor patterns during open hours:
- Morning (10am-12pm): 20-30% capacity
- Afternoon (12pm-4pm): 40-60% capacity
- Evening (if open): 20-40% capacity
- Weekend: 50-70% for museums, variable for libraries

BUT: HVAC runs 24/7 for preservation!
- Temperature: 68-72°F stable
- Humidity: 45-55% RH
- Air changes: Continuous for air quality

True occupancy calculation:
- Open 50 hrs/week = 30% of time
- Average occupancy during open: ~40%
- True utilization: 30% × 40% = 12%
- But HVAC runs 100% of time!

ODCV opportunity = ventilating empty spaces at preservation levels

Current data: 55% | Reality: ~25-35%
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

# ACTUAL CITIES IN DATASET
UTILIZATION_BY_CITY = {
    # Major cultural centers (more visitors)
    'Boston': 0.32,          # 19 buildings - MFA, public libraries
    'Washington': 0.35,      # 5 buildings - Smithsonian, etc.
    'New York': 0.36,        # Met, NYPL, etc.
    'Chicago': 0.32,         # 6 buildings - Art Institute, etc.
    'Denver': 0.30,          # 5 buildings
    'Los Angeles': 0.32,     # LACMA, Getty nearby
    'Atlanta': 0.28,         # 2 buildings

    # Smaller/college markets
    'Cambridge': 0.30,       # Harvard libraries
    'Stanford': 0.28,        # University
    'Santa Monica': 0.30,
    'Fresno': 0.25,
    'Monterey': 0.28,
    'Livermore': 0.25,
}

# State-level defaults
STATE_DEFAULTS = {
    'MA': 0.31,    # Boston influence
    'NY': 0.34,    # NYC influence
    'CA': 0.28,    # Mix
    'DC': 0.34,    # Smithsonian
    'IL': 0.31,    # Chicago
    'CO': 0.29,    # Denver
    'GA': 0.27,    # Atlanta
}

# National average
DEFAULT_UTILIZATION = 0.28


def create_backup():
    """Create timestamped backup before changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(INPUT_FILE, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path


def update_library_utilization():
    """Update utilization rates for library/museum buildings."""
    print("Loading portfolio data...")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df)} buildings")

    city_match = 0
    state_match = 0
    default_used = 0

    lb_mask = df['bldg_type'] == 'Library/Museum'
    print(f"Found {lb_mask.sum()} Library/Museum buildings")

    for idx in df[lb_mask].index:
        city = str(df.loc[idx, 'loc_city']).strip()
        state = str(df.loc[idx, 'loc_state']).strip()

        if city in UTILIZATION_BY_CITY:
            utilization = UTILIZATION_BY_CITY[city]
            city_match += 1
        elif state.upper() in STATE_DEFAULTS:
            utilization = STATE_DEFAULTS[state.upper()]
            state_match += 1
        else:
            utilization = DEFAULT_UTILIZATION
            default_used += 1

        df.loc[idx, 'occ_vacancy_rate'] = 0.0
        df.loc[idx, 'occ_utilization_rate'] = utilization

    print(f"\nUpdates summary:")
    print(f"  - City-specific: {city_match}")
    print(f"  - State-level: {state_match}")
    print(f"  - National average: {default_used}")

    print(f"\nSaving to {INPUT_FILE}...")
    df.to_csv(INPUT_FILE, index=False)
    print("Done!")

    print("\n=== LIBRARY/MUSEUM UTILIZATION ===")
    print("HVAC runs 24/7 for preservation, but visitors are sparse!")
    print()
    print("Schedule:")
    print("  Open: ~50 hrs/week (30% of time)")
    print("  Average occupancy when open: ~40%")
    print("  True utilization: 30% × 40% = 12%")
    print()
    print("But HVAC runs 100% of time for collections!")
    print("= Massive ODCV opportunity")
    print()
    print("Old: 42-70% | New: 25-36%")


if __name__ == '__main__':
    create_backup()
    update_library_utilization()
