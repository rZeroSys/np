#!/usr/bin/env python3
"""
Update Restaurant/Bar utilization rates based on actual dining patterns.

Key insight: Restaurants have intense ventilation but variable occupancy.

Kitchen area (~40% of building):
- Exhaust hoods run at full blast during ALL cooking hours
- Limited ODCV opportunity - exhaust-driven, not demand-driven
- 2-5 people during prep, 5-15 during service

Dining area (~60% of building):
- HVAC is demand-controllable
- Lunch: 11am-2pm, 50-70% of seats filled
- Dinner: 5pm-10pm, 60-90% of seats filled
- Between meals: Nearly empty (cleaning, setup)
- Late night/early morning: CLOSED

Weekly calculation:
- Open 12 hrs/day × 7 = 84 hrs/week
- 84/168 = 50% of time operating
- During operation: ~40% average dining occupancy
- True dining utilization: 50% × 40% = 20%

But kitchen limits overall ODCV opportunity:
- Dining (60% of space): 20% true utilization
- Kitchen (40% of space): Limited ODCV potential
- ODCV bounds: 10-25% (limited opportunity type)

Setting utilization at 35-45% to account for meal rushes.
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
    # Major dining markets (more evening activity)
    'Boston': 0.40,          # 26 buildings - college town, late dining
    'New York': 0.42,        # Dense, late night scene
    'Washington': 0.38,      # 6 buildings - business lunch heavy
    'Los Angeles': 0.40,     # 4 buildings - entertainment dining
    'Denver': 0.38,          # 4 buildings
    'Chicago': 0.40,         # 1 building
    'Cambridge': 0.38,       # 2 buildings - college area
    'Atlanta': 0.38,         # 1 building

    # California markets
    'Irvine': 0.36,
    'Sacramento': 0.36,
    'San Diego': 0.38,
    'San Mateo': 0.38,
}

# State-level defaults
STATE_DEFAULTS = {
    'MA': 0.39,    # Boston influence
    'NY': 0.41,    # NYC influence
    'CA': 0.37,    # Mix
    'DC': 0.38,    # Business dining
    'CO': 0.37,    # Denver
    'IL': 0.39,    # Chicago
    'GA': 0.37,    # Atlanta
    'TX': 0.36,    # Variable
    'FL': 0.37,    # Variable
}

# National average
DEFAULT_UTILIZATION = 0.37


def create_backup():
    """Create timestamped backup before changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(INPUT_FILE, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path


def update_restaurant_utilization():
    """Update utilization rates for restaurant buildings."""
    print("Loading portfolio data...")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df)} buildings")

    city_match = 0
    state_match = 0
    default_used = 0

    rb_mask = df['bldg_type'] == 'Restaurant/Bar'
    print(f"Found {rb_mask.sum()} Restaurant/Bar buildings")

    for idx in df[rb_mask].index:
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

    print("\n=== RESTAURANT UTILIZATION ===")
    print("Kitchen exhaust limits ODCV, but dining area has opportunity")
    print()
    print("Building zones:")
    print("  Kitchen (40%): Exhaust-driven, limited ODCV")
    print("  Dining (60%): ODCV opportunity exists")
    print()
    print("Dining patterns:")
    print("  Lunch rush: 11am-2pm, 50-70% full")
    print("  Dinner rush: 5pm-10pm, 60-90% full")
    print("  Between: Nearly empty")
    print()
    print("Old: 34-70% | New: 36-42%")


if __name__ == '__main__':
    create_backup()
    update_restaurant_utilization()
