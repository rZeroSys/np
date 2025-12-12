#!/usr/bin/env python3
"""
Update Specialty Hospital utilization rates with research-based data.

Sources:
- AHA Fast Facts 2024: ~65% average US hospital bed occupancy
- Statista: Specialty hospitals (children's, cancer) have higher occupancy
- ASHRAE 170: Hospital ventilation requirements (15-25 ACH for critical areas)

Key insight: Specialty hospitals are LOW OPPORTUNITY because:
1. 24/7 operation - building never empties
2. Patients stay continuously (unlike hotel guests who leave)
3. ASHRAE 170 code requirements mandate minimum ventilation
4. Infection control requires high air change rates
5. Pressure relationships between zones are critical

Utilization calculation:
- Bed occupancy: 65-80% depending on specialty
- Patient presence: ~95% of time (they live there during stay)
- Clinical areas: staffed 24/7
- Admin areas: business hours only

Formula applies 0.3 multiplier: (1-U) × 0.3
So even moderate utilization results in very low opportunity.

Specialty types:
- Psychiatric: 70-80% occupancy, longer stays
- Rehabilitation: 75-85% occupancy, scheduled admissions
- Children's: 65-75% occupancy, variable
- Cancer centers: 70-80% occupancy
- Cardiac: 75-85% occupancy, high acuity
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

# Specialty Hospital utilization by city
# Higher in urban areas with more demand, lower in rural
# Based on AHA bed occupancy data adjusted for 24/7 operation

UTILIZATION_BY_CITY = {
    # Major medical hubs (higher occupancy)
    'New York': 0.82,        # Dense, high demand
    'Boston': 0.80,          # Major medical hub
    'Houston': 0.78,         # Texas Medical Center
    'Cleveland': 0.80,       # Cleveland Clinic
    'Baltimore': 0.78,       # Johns Hopkins
    'Philadelphia': 0.78,    # Major medical center
    'Chicago': 0.76,         # Large metro
    'Los Angeles': 0.75,     # Large metro
    'San Francisco': 0.76,   # UCSF, Stanford nearby
    'Seattle': 0.75,         # Regional hub
    'Denver': 0.74,          # Regional hub
    'Atlanta': 0.75,         # CDC, Emory
    'Dallas': 0.74,          # Texas medical
    'Phoenix': 0.72,         # Growing market
    'Miami': 0.76,           # Retirement population

    # Secondary markets
    'Minneapolis': 0.76,     # Mayo nearby
    'Pittsburgh': 0.78,      # UPMC
    'San Diego': 0.74,       # Regional
    'Portland': 0.72,        # Regional
    'Washington': 0.75,      # NIH nearby
}

# State-level defaults
STATE_DEFAULTS = {
    'NY': 0.78,    # Dense, high demand
    'MA': 0.78,    # Boston hub
    'TX': 0.75,    # Large state, variable
    'CA': 0.74,    # Large state, variable
    'OH': 0.76,    # Cleveland Clinic
    'PA': 0.76,    # Philadelphia, Pittsburgh
    'FL': 0.74,    # Retirement, variable
    'IL': 0.75,    # Chicago hub
    'MD': 0.76,    # Johns Hopkins
    'MN': 0.76,    # Mayo
    'WA': 0.74,    # Seattle hub
    'CO': 0.73,    # Denver hub
    'GA': 0.74,    # Atlanta hub
}

# National average (based on 65% bed occupancy + 24/7 clinical areas)
DEFAULT_UTILIZATION = 0.74


def create_backup():
    """Create timestamped backup before changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(INPUT_FILE, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path


def get_utilization(city, state):
    """Get specialty hospital utilization for a city/state."""
    if city in UTILIZATION_BY_CITY:
        return UTILIZATION_BY_CITY[city]

    state_upper = str(state).upper().strip()
    if state_upper in STATE_DEFAULTS:
        return STATE_DEFAULTS[state_upper]

    return DEFAULT_UTILIZATION


def update_specialty_hospital_utilization():
    """Update utilization rates for specialty hospital buildings."""
    print("Loading portfolio data...")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df)} buildings")

    # Track updates
    city_match = 0
    state_match = 0
    default_used = 0

    # Get Specialty Hospital buildings only
    spec_mask = df['bldg_type'] == 'Specialty Hospital'
    print(f"Found {spec_mask.sum()} Specialty Hospital buildings")

    for idx in df[spec_mask].index:
        city = str(df.loc[idx, 'loc_city']).strip()
        state = str(df.loc[idx, 'loc_state']).strip()

        # Get utilization
        if city in UTILIZATION_BY_CITY:
            utilization = UTILIZATION_BY_CITY[city]
            city_match += 1
        elif state.upper() in STATE_DEFAULTS:
            utilization = STATE_DEFAULTS[state.upper()]
            state_match += 1
        else:
            utilization = DEFAULT_UTILIZATION
            default_used += 1

        # Hospitals don't have vacancy
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

    # Show examples
    print("\n=== SPECIALTY HOSPITAL UTILIZATION ===")
    print("LOW OPPORTUNITY building type - 24/7 operation, infection control")
    print()
    print("City            | Utilization | Raw Opp* | Final (capped)")
    print("-" * 60)
    for city in ['New York', 'Boston', 'Denver', 'Phoenix']:
        if city in UTILIZATION_BY_CITY:
            util = UTILIZATION_BY_CITY[city]
            raw_opp = (1 - util) * 0.3
            # Building floor 5%, ceiling 15%, but global floor 20%
            final = max(0.20, min(0.15, max(0.05, raw_opp)))
            print(f"{city:15} | {util*100:5.0f}%       | {raw_opp*100:5.1f}%    | {final*100:5.0f}%")

    print()
    print("*Raw opportunity = (1-U) × 0.3 (capped formula for hospitals)")
    print(" Global floor of 20% overrides building-type ceiling of 15%")


if __name__ == '__main__':
    create_backup()
    update_specialty_hospital_utilization()
