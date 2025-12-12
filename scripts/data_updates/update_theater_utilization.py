#!/usr/bin/env python3
"""
Update Theater utilization rates based on actual show schedules.

Key insight: Theaters are EMPTY most of the time!

Broadway/professional theater schedule:
- ~8 shows/week (6 evenings + 2 matinees)
- Each show ~2.5-3 hours
- 24 hours of actual shows / 168 hours in week = 14%
- During shows, maybe 70-90% capacity (not always sold out)
- True utilization: 14% × 80% = ~11%

But HVAC runs longer than just show time:
- Pre-show (lobby, warmup): +1 hr
- Post-show (exit, cleanup): +0.5 hr
- Tech/rehearsal time: varies
- Total conditioned time: maybe 30-40 hrs/week

Adjusted calculation:
- 35 hrs HVAC operation / 168 hrs = 21% of week
- During those hours, ~70% average occupancy (some rehearsals, some full shows)
- True utilization: ~15-20%

Movie theaters (multiplex):
- More hours of operation (12pm-midnight daily = 12 hrs × 7 = 84 hrs)
- But most screens empty most showings (10% occupied daytime, 50% evenings)
- Average: 84/168 × 30% = ~15%

Current data shows 48-55% - WAY TOO HIGH!
"""

import pandas as pd
import shutil
from pathlib import Path
from datetime import datetime

# Paths
INPUT_FILE = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv'
BACKUP_DIR = '/Users/forrestmiller/Desktop/nationwide-prospector/BACKUPS_GO_HERE/csv_backups'

# ACTUAL CITIES IN DATASET
UTILIZATION_BY_CITY = {
    # Broadway/major theater markets (more shows, higher occupancy)
    'New York': 0.22,        # 62 buildings - Broadway, more shows
    'Chicago': 0.18,         # 14 buildings - strong theater scene
    'Los Angeles': 0.16,     # 13 buildings - mix of theater/film
    'Boston': 0.18,          # 11 buildings
    'Denver': 0.17,          # 11 buildings
    'Seattle': 0.17,         # 10 buildings
    'San Jose': 0.15,        # 8 buildings
    'San Francisco': 0.18,   # 8 buildings
    'Washington': 0.18,      # 7 buildings - Kennedy Center etc
    'Atlanta': 0.16,         # 5 buildings
    'Philadelphia': 0.17,    # 5 buildings
    'Portland': 0.16,        # 5 buildings
    'San Diego': 0.15,       # 4 buildings
    'Kansas City': 0.15,     # 3 buildings
    'Riverside': 0.14,       # 3 buildings
}

# State-level defaults
STATE_DEFAULTS = {
    'NY': 0.20,    # Broadway influence
    'CA': 0.16,    # Mix of venues
    'IL': 0.17,    # Chicago
    'MA': 0.17,    # Boston
    'CO': 0.16,    # Denver
    'WA': 0.16,    # Seattle
    'DC': 0.17,    # Kennedy Center
    'PA': 0.16,    # Philly
    'GA': 0.15,    # Atlanta
    'OR': 0.15,    # Portland
    'TX': 0.15,    # Variable
    'FL': 0.15,    # Variable
}

# National average
DEFAULT_UTILIZATION = 0.16


def create_backup():
    """Create timestamped backup before changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(INPUT_FILE, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path


def get_utilization(city, state):
    """Get theater utilization for a city/state."""
    if city in UTILIZATION_BY_CITY:
        return UTILIZATION_BY_CITY[city]

    state_upper = str(state).upper().strip()
    if state_upper in STATE_DEFAULTS:
        return STATE_DEFAULTS[state_upper]

    return DEFAULT_UTILIZATION


def update_theater_utilization():
    """Update utilization rates for theater buildings."""
    print("Loading portfolio data...")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df)} buildings")

    city_match = 0
    state_match = 0
    default_used = 0

    theater_mask = df['bldg_type'] == 'Theater'
    print(f"Found {theater_mask.sum()} Theater buildings")

    for idx in df[theater_mask].index:
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

    print("\n=== THEATER UTILIZATION ===")
    print("Theaters are EMPTY most of the time!")
    print()
    print("Broadway schedule:")
    print("  8 shows/week × 3 hrs = 24 hrs of shows")
    print("  + pre/post + rehearsal = ~35 hrs HVAC on")
    print("  35/168 × 70% occupancy = ~15% utilization")
    print()
    print("Old: 48-55% | New: 14-22%")
    print("Opportunity: 1 - 16% = 84% → capped at 40% ceiling")


if __name__ == '__main__':
    create_backup()
    update_theater_utilization()
