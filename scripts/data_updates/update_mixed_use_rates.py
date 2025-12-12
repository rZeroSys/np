#!/usr/bin/env python3
"""
Update Mixed Use vacancy AND utilization rates with research-based data.

Sources:
- Same as Office: Kastle Systems, CBRE, Cushman & Wakefield
- Mixed Use typically = Office + Ground Floor Retail

Key insight: Mixed Use buildings should have similar patterns to offices:
- Centralized HVAC controlled by landlord
- Multi-tenant with vacancy challenges
- Utilization similar to office (staff schedules, WFH patterns)

Vacancy: Similar to or slightly better than pure office
- Premium mixed-use in urban cores may have lower vacancy
- But still affected by same market dynamics

Utilization: Blend of office and retail
- Office floors: Same as regular office (Kastle data)
- Retail floors: Traffic-based (40-50%)
- Weighted average: Slightly lower than pure office
"""

import pandas as pd
import shutil
from pathlib import Path
from datetime import datetime

# Paths
INPUT_FILE = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv'
BACKUP_DIR = '/Users/forrestmiller/Desktop/nationwide-prospector/BACKUPS_GO_HERE/csv_backups'

# Mixed Use vacancy and utilization by city
# Based on office market data with slight adjustments for mixed-use premium
# Utilization blends office (Kastle) and retail patterns

CITY_DATA = {
    # Format: (vacancy_rate, utilization_rate)

    # Major metros - similar to office but often premium locations
    'San Francisco': (0.30, 0.40),   # High vacancy but mixed-use premium
    'Los Angeles': (0.22, 0.46),     # Similar to office
    'New York': (0.14, 0.52),        # Mixed-use premium in NYC
    'Chicago': (0.24, 0.38),         # Similar to office
    'Boston': (0.22, 0.44),          # Similar to office
    'Washington': (0.21, 0.36),      # Similar to office
    'Seattle': (0.25, 0.44),         # Similar to office
    'Denver': (0.24, 0.40),          # Similar to office
    'Atlanta': (0.23, 0.46),         # Similar to office
    'Philadelphia': (0.18, 0.44),    # Similar to office
    'San Diego': (0.15, 0.46),       # Mixed-use premium
    'Portland': (0.25, 0.36),        # Similar to office
    'Phoenix': (0.22, 0.48),         # Sunbelt growth
    'Dallas': (0.23, 0.48),          # Texas growth
    'Houston': (0.24, 0.46),         # Texas market
    'Miami': (0.18, 0.50),           # Mixed-use premium

    # California markets
    'San Jose': (0.20, 0.48),        # Tech hub
    'Oakland': (0.22, 0.40),         # East Bay
    'Irvine': (0.14, 0.48),          # OC premium
    'Sacramento': (0.17, 0.44),      # State capital

    # Secondary markets
    'Minneapolis': (0.20, 0.42),     # Midwest
    'Kansas City': (0.16, 0.48),     # Midwest stable
    'St. Louis': (0.30, 0.42),       # Higher vacancy
}

# State-level defaults
STATE_DEFAULTS = {
    'CA': (0.22, 0.44),    # California average
    'NY': (0.16, 0.50),    # NYC influence
    'TX': (0.23, 0.47),    # Texas markets
    'FL': (0.19, 0.48),    # Florida growth
    'IL': (0.23, 0.40),    # Chicago influence
    'MA': (0.21, 0.44),    # Boston influence
    'WA': (0.24, 0.44),    # Seattle influence
    'CO': (0.24, 0.42),    # Denver influence
    'PA': (0.18, 0.44),    # Philly influence
    'GA': (0.23, 0.46),    # Atlanta influence
}

# National average
DEFAULT_VACANCY = 0.22       # Similar to office
DEFAULT_UTILIZATION = 0.45   # Blend of office and retail


def create_backup():
    """Create timestamped backup before changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(INPUT_FILE, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path


def get_rates(city, state):
    """Get vacancy and utilization rates for a city/state."""
    if city in CITY_DATA:
        return CITY_DATA[city]

    state_upper = str(state).upper().strip()
    if state_upper in STATE_DEFAULTS:
        return STATE_DEFAULTS[state_upper]

    return (DEFAULT_VACANCY, DEFAULT_UTILIZATION)


def update_mixed_use_rates():
    """Update vacancy and utilization rates for Mixed Use buildings."""
    print("Loading portfolio data...")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df)} buildings")

    # Track updates
    city_match = 0
    state_match = 0
    default_used = 0

    # Get Mixed Use buildings only
    mixed_mask = df['bldg_type'] == 'Mixed Use'
    print(f"Found {mixed_mask.sum()} Mixed Use buildings")

    for idx in df[mixed_mask].index:
        city = str(df.loc[idx, 'loc_city']).strip()
        state = str(df.loc[idx, 'loc_state']).strip()

        # Get rates
        if city in CITY_DATA:
            vacancy, utilization = CITY_DATA[city]
            city_match += 1
        elif state.upper() in STATE_DEFAULTS:
            vacancy, utilization = STATE_DEFAULTS[state.upper()]
            state_match += 1
        else:
            vacancy, utilization = DEFAULT_VACANCY, DEFAULT_UTILIZATION
            default_used += 1

        df.loc[idx, 'occ_vacancy_rate'] = vacancy
        df.loc[idx, 'occ_utilization_rate'] = utilization

    print(f"\nUpdates summary:")
    print(f"  - City-specific: {city_match}")
    print(f"  - State-level: {state_match}")
    print(f"  - National average: {default_used}")

    # Save
    print(f"\nSaving to {INPUT_FILE}...")
    df.to_csv(INPUT_FILE, index=False)
    print("Done!")

    # Show comparison
    print("\n=== MIXED USE vs OFFICE COMPARISON ===")
    print()
    print("City            | MU Vacancy | Off Vacancy | MU Util | Off Util")
    print("-" * 70)
    comparisons = [
        ('New York', 0.14, 0.15, 0.52, 0.55),
        ('San Francisco', 0.30, 0.34, 0.40, 0.38),
        ('Chicago', 0.24, 0.255, 0.38, 0.37),
        ('Boston', 0.22, 0.236, 0.44, 0.42),
    ]
    for city, mu_vac, off_vac, mu_util, off_util in comparisons:
        print(f"{city:15} | {mu_vac*100:5.0f}%      | {off_vac*100:5.0f}%       | {mu_util*100:4.0f}%   | {off_util*100:4.0f}%")

    print()
    print("Mixed Use uses same formula as Office: V + (1-V)(1-U)")


if __name__ == '__main__':
    create_backup()
    update_mixed_use_rates()
