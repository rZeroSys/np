#!/usr/bin/env python3
"""
Update Venue utilization rates based on actual event schedules.

Key insight: Venues are EMPTY most of the time! HUGE savings opportunity!

Venue types and schedules:
- Concert hall: 2-3 shows/week × 4 hrs = 8-12 hrs of shows
- Sports arena: 60-80 events/year × 5 hrs = 300-400 hrs/year
- Convention center: Variable, often empty weekends

Sports arena example (NBA + concerts):
- 41 home games × 4 hrs = 164 hrs
- 20 concerts × 5 hrs = 100 hrs
- 20 other events × 4 hrs = 80 hrs
- Total events: ~350 hrs/year
- Setup/teardown: +200 hrs
- Total HVAC active: ~550 hrs / 8760 = 6% of year!

But HVAC runs more than just events:
- Pre-event (2-4 hrs before): conditioning
- Post-event (1-2 hrs after): clearing
- Maintenance days: partial conditioning
- Total conditioned time: maybe 15-20% of year

During events: 70-90% capacity (not always sold out)
True utilization: 18% × 75% = ~14%

Adjusted for Boston (lots of venues, college events): ~20%
Adjusted for smaller markets: ~16-18%

Current data shows 48% - WAY TOO HIGH!
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
    # Major venue markets (more events, higher utilization)
    'Boston': 0.20,          # 25 buildings - colleges, sports, concerts
    'New York': 0.22,        # Dense, lots of events
    'Chicago': 0.19,         # 7 buildings - sports, concerts
    'Denver': 0.18,          # 8 buildings
    'Washington': 0.19,      # 4 buildings - Kennedy Center area
    'Los Angeles': 0.20,     # 2 buildings - entertainment hub
    'Cambridge': 0.18,       # 4 buildings - Harvard/MIT events

    # Smaller markets
    'San Diego': 0.17,
    'Sacramento': 0.16,
    'Kansas City': 0.17,
    'Fresno': 0.15,
    'Riverside': 0.15,
    'Ontario': 0.15,
    'Stanford': 0.18,        # College events
}

# State-level defaults
STATE_DEFAULTS = {
    'MA': 0.19,    # Boston influence
    'NY': 0.21,    # NYC influence
    'CA': 0.17,    # Mix of venues
    'IL': 0.18,    # Chicago
    'CO': 0.17,    # Denver
    'DC': 0.18,    # DC events
    'TX': 0.17,    # Variable
    'FL': 0.17,    # Variable
}

# National average
DEFAULT_UTILIZATION = 0.17


def create_backup():
    """Create timestamped backup before changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(INPUT_FILE, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path


def get_utilization(city, state):
    """Get venue utilization for a city/state."""
    if city in UTILIZATION_BY_CITY:
        return UTILIZATION_BY_CITY[city]

    state_upper = str(state).upper().strip()
    if state_upper in STATE_DEFAULTS:
        return STATE_DEFAULTS[state_upper]

    return DEFAULT_UTILIZATION


def update_venue_utilization():
    """Update utilization rates for venue buildings."""
    print("Loading portfolio data...")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df)} buildings")

    city_match = 0
    state_match = 0
    default_used = 0

    venue_mask = df['bldg_type'] == 'Venue'
    print(f"Found {venue_mask.sum()} Venue buildings")

    for idx in df[venue_mask].index:
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

    print("\n=== VENUE UTILIZATION ===")
    print("Venues are EMPTY most of the time! HUGE opportunity!")
    print()
    print("Sports arena example:")
    print("  41 NBA games + 20 concerts + 20 other = 81 events")
    print("  81 events × 5 hrs = 405 hrs/year")
    print("  + setup/teardown = ~600 hrs")
    print("  600 / 8760 = 7% of year with activity")
    print()
    print("Old: 48% | New: 15-22%")
    print("Opportunity: 1 - 18% = 82% → capped at 45% ceiling")


if __name__ == '__main__':
    create_backup()
    update_venue_utilization()
