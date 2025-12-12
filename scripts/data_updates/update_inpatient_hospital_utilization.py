#!/usr/bin/env python3
"""
Update Inpatient Hospital utilization rates with research-based data.

Sources:
- AHA Fast Facts 2024: ~65% average US hospital bed occupancy
- ASHRAE 170: Hospital ventilation requirements

Key insight from user: Hospitals have HUGE non-clinical areas ventilated at
medical-grade rates 24/7 but with office-like or worse occupancy:

Building breakdown:
- Patient rooms (~40%): 65-75% bed occupancy, patients there 24/7
- Clinical/OR/ICU (~20%): Staffed 24/7, high utilization ~85%
- Waiting rooms (~10%): Medical-grade air 24/7, EMPTY at night, variable day
- Exam rooms (~10%): Full ventilation 24/7, patients only there periodically
- Admin offices (~10%): 2x office ventilation rates, staff only business hours
- Cafeteria/lobby (~10%): Variable occupancy, maybe 35% average

Weighted calculation:
- Patient rooms: 40% × 70% = 28%
- Clinical: 20% × 85% = 17%
- Waiting rooms: 10% × 30% = 3%
- Exam rooms: 10% × 35% = 3.5%
- Admin: 10% × 40% = 4%
- Cafeteria/lobby: 10% × 35% = 3.5%
- TOTAL: ~59%

Current data shows 75% - TOO HIGH!

Even with LOW_OPPORTUNITY formula (1-U) × 0.3, lower utilization = more savings.
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
    # Major hospital markets (higher bed occupancy, busier waiting rooms)
    'New York': 0.62,        # 78 buildings, dense, high demand
    'Boston': 0.60,          # 21 buildings, major medical hub
    'Chicago': 0.58,         # 31 buildings
    'Los Angeles': 0.57,     # 25 buildings
    'Philadelphia': 0.58,    # 21 buildings
    'Washington': 0.56,      # 21 buildings
    'Seattle': 0.56,         # 15 buildings
    'San Francisco': 0.58,   # 7 buildings
    'San Diego': 0.55,       # 8 buildings
    'Denver': 0.55,          # 7 buildings
    'Kansas City': 0.54,     # 6 buildings
    'Atlanta': 0.56,         # 6 buildings
    'Anaheim': 0.54,         # 5 buildings (OC)
    'Sacramento': 0.55,      # 5 buildings
    'Oakland': 0.56,         # 4 buildings
}

# State-level defaults
STATE_DEFAULTS = {
    'NY': 0.60,    # NYC influence
    'MA': 0.59,    # Boston hub
    'IL': 0.57,    # Chicago
    'CA': 0.56,    # Large state
    'PA': 0.58,    # Philly/Pittsburgh
    'DC': 0.56,    # Urban
    'WA': 0.55,    # Seattle
    'TX': 0.54,    # Variable
    'FL': 0.55,    # Variable
    'CO': 0.55,    # Denver
    'GA': 0.55,    # Atlanta
    'MO': 0.54,    # Kansas City/St Louis
}

# National average based on weighted building zones
DEFAULT_UTILIZATION = 0.56


def create_backup():
    """Create timestamped backup before changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(INPUT_FILE, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path


def get_utilization(city, state):
    """Get hospital utilization for a city/state."""
    if city in UTILIZATION_BY_CITY:
        return UTILIZATION_BY_CITY[city]

    state_upper = str(state).upper().strip()
    if state_upper in STATE_DEFAULTS:
        return STATE_DEFAULTS[state_upper]

    return DEFAULT_UTILIZATION


def update_inpatient_hospital_utilization():
    """Update utilization rates for inpatient hospital buildings."""
    print("Loading portfolio data...")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df)} buildings")

    # Track updates
    city_match = 0
    state_match = 0
    default_used = 0

    # Get Inpatient Hospital buildings only
    hosp_mask = df['bldg_type'] == 'Inpatient Hospital'
    print(f"Found {hosp_mask.sum()} Inpatient Hospital buildings")

    for idx in df[hosp_mask].index:
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

    # Save
    print(f"\nSaving to {INPUT_FILE}...")
    df.to_csv(INPUT_FILE, index=False)
    print("Done!")

    # Show insight
    print("\n=== HOSPITAL UTILIZATION BREAKDOWN ===")
    print("Not just patient rooms! Huge non-clinical areas ventilated 24/7:")
    print()
    print("Zone              | % of Bldg | Occupancy | Contribution")
    print("-" * 60)
    print("Patient rooms     |    40%    |    70%    |    28%")
    print("Clinical/OR/ICU   |    20%    |    85%    |    17%")
    print("Waiting rooms     |    10%    |    30%    |     3%")
    print("Exam rooms        |    10%    |    35%    |     4%")
    print("Admin offices     |    10%    |    40%    |     4%")
    print("Cafeteria/lobby   |    10%    |    35%    |     4%")
    print("-" * 60)
    print("TOTAL             |   100%    |           |    ~60%")
    print()
    print("Old utilization: 75% (assumed all 24/7)")
    print("New utilization: 55-62% (accounts for empty waiting/exam/admin)")


if __name__ == '__main__':
    create_backup()
    update_inpatient_hospital_utilization()
