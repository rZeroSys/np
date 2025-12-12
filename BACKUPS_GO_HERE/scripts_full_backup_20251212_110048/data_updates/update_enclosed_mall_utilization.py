#!/usr/bin/env python3
"""
Update Enclosed Mall utilization rates based on shopper traffic patterns.

Key insight: Retail apocalypse + variable traffic = low real utilization!

Mall vacancy reality:
- 25% of malls expected to close by 2025
- Anchor stores (Sears, JCPenney) gone
- Many malls have 20-40% vacancy in inline stores

Operating hours:
- Typical: 10am-9pm (11 hrs/day)
- 77 hrs/week = 46% of time open

Shopper traffic patterns:
- Weekday morning: 10-20% of design capacity
- Weekday afternoon: 25-40%
- Weekday evening: 30-50%
- Saturday afternoon: 60-80%
- Sunday: 40-60%
- Average during open: ~35%

Common area challenge:
- Food court, hallways, entrances all conditioned
- Whether 10 people or 1000, HVAC runs same
- Massive overcooling on slow days

True utilization: 46% × 35% = ~16%
Conservative: 35-45%

Current data: 57% | Reality: ~35-45%
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
    # Major retail markets
    'Los Angeles': 0.42,     # 4 buildings - some healthy malls
    'Chicago': 0.40,         # 2 buildings
    'Cambridge': 0.44,       # 2 buildings - CambridgeSide, etc.
    'Boston': 0.44,          # 1 building - Prudential, etc.
    'Denver': 0.38,          # 1 building
}

# State-level defaults
STATE_DEFAULTS = {
    'CA': 0.40,    # California
    'IL': 0.39,    # Chicago area
    'MA': 0.43,    # Boston area
    'CO': 0.38,    # Denver
    'NY': 0.42,    # NYC area
    'TX': 0.38,    # Texas
    'FL': 0.40,    # Florida
}

# National average
DEFAULT_UTILIZATION = 0.40


def create_backup():
    """Create timestamped backup before changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(INPUT_FILE, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path


def update_enclosed_mall_utilization():
    """Update utilization rates for enclosed mall buildings."""
    print("Loading portfolio data...")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df)} buildings")

    city_match = 0
    state_match = 0
    default_used = 0

    em_mask = df['bldg_type'] == 'Enclosed Mall'
    print(f"Found {em_mask.sum()} Enclosed Mall buildings")

    for idx in df[em_mask].index:
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

        # Enclosed malls also have vacancy (anchor closures)
        df.loc[idx, 'occ_vacancy_rate'] = 0.15  # 15% average vacancy
        df.loc[idx, 'occ_utilization_rate'] = utilization

    print(f"\nUpdates summary:")
    print(f"  - City-specific: {city_match}")
    print(f"  - State-level: {state_match}")
    print(f"  - National average: {default_used}")

    print(f"\nSaving to {INPUT_FILE}...")
    df.to_csv(INPUT_FILE, index=False)
    print("Done!")

    print("\n=== ENCLOSED MALL UTILIZATION ===")
    print("Retail apocalypse + variable traffic = opportunity!")
    print()
    print("Traffic patterns:")
    print("  Weekday morning: 10-20% of design")
    print("  Weekend peak: 60-80% of design")
    print("  Average: ~35%")
    print()
    print("Old: 57% | New: 38-44%")


if __name__ == '__main__':
    create_backup()
    update_enclosed_mall_utilization()
