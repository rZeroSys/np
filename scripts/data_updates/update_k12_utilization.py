#!/usr/bin/env python3
"""
Update K-12 school utilization rates with research-based data.

Sources:
- Pew Research Center: 180 school days is US standard (2023)
- NCES Table 5.14: State instructional days/hours requirements
- ASHRAE: HVAC runs 2 hours before/after occupancy
- Norwegian DCV studies (Mysen et al.): 38% energy savings in schools
- DOE Energy Smart Schools O&M Guide
- PMC study: School operates 203 days, 6.5-8 hrs/day classrooms

Calculation basis:
- 180 school days/year (US average)
- 11 hours/day HVAC operation (6am-5pm, includes pre/post conditioning)
- 1,980 occupied hours / 8,760 total hours = 22.6% annual utilization
- Adjusted for year-round schools, climate, after-school programs

Note: Schools don't have "vacancy" in the office sense - districts own buildings.
Utilization drives the entire opportunity calculation.
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

# K-12 school utilization by state/region
# Base: 22.6% (180 days × 11 hrs / 8,760 hrs)
# Adjusted for: year-round programs, after-school usage, climate

# Year-round school adoption by state (higher = more utilization)
# Source: National Association for Year-Round Education
K12_UTILIZATION_BY_STATE = {
    # High utilization states (year-round programs common, extensive after-school)
    'CA': 0.28,    # 28% - Year-round schools common, warm climate = summer programs
    'AZ': 0.27,    # Year-round common
    'NV': 0.27,    # Year-round common
    'TX': 0.26,    # Some year-round, warm climate
    'FL': 0.26,    # Year-round, warm climate
    'NC': 0.26,    # Year-round adoption
    'GA': 0.25,    # Warm climate, after-school programs
    'HI': 0.28,    # Year-round common

    # Medium-high utilization (urban districts, after-school programs)
    'NY': 0.25,    # NYC extensive after-school, some year-round
    'IL': 0.24,    # Chicago after-school programs
    'MA': 0.24,    # Boston extended learning time
    'PA': 0.23,    # Urban after-school
    'NJ': 0.24,    # Dense urban, after-school
    'MD': 0.24,    # DC suburbs, after-school
    'VA': 0.24,    # DC suburbs
    'DC': 0.25,    # Year-round, extensive after-school

    # Standard utilization (traditional calendar)
    'WA': 0.22,    # Traditional calendar
    'OR': 0.22,    # Traditional calendar
    'CO': 0.22,    # Traditional calendar
    'MN': 0.21,    # Cold climate, shorter summer but harsh winter
    'WI': 0.21,    # Cold climate
    'MI': 0.21,    # Cold climate
    'OH': 0.22,    # Traditional
    'IN': 0.22,    # Traditional
    'MO': 0.22,    # Traditional
    'KS': 0.22,    # Traditional

    # Lower utilization (rural, harsh winters, traditional calendar)
    'MT': 0.20,    # Rural, harsh winter
    'ND': 0.20,    # Rural, harsh winter
    'SD': 0.20,    # Rural, harsh winter
    'WY': 0.20,    # Rural
    'ID': 0.21,    # Traditional
    'NE': 0.21,    # Traditional
    'IA': 0.21,    # Traditional
    'ME': 0.20,    # Rural, harsh winter
    'VT': 0.20,    # Rural
    'NH': 0.21,    # Traditional
}

# Default utilization for states not listed
DEFAULT_K12_UTILIZATION = 0.22  # 22% - US average based on 180 days × 11 hrs

def create_backup():
    """Create timestamped backup before changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(INPUT_FILE, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path

def update_k12_utilization():
    """Update utilization rates for K-12 school buildings."""
    print("Loading portfolio data...")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df)} buildings")

    # Track updates
    state_match = 0
    default_used = 0

    # Get K-12 school buildings only
    k12_mask = df['bldg_type'] == 'K-12 School'
    print(f"Found {k12_mask.sum()} K-12 school buildings")

    for idx in df[k12_mask].index:
        state = str(df.loc[idx, 'loc_state']).strip().upper()

        # Schools don't have vacancy in the traditional sense
        # Set to 0 - the building is "fully leased" to the school district
        df.loc[idx, 'occ_vacancy_rate'] = 0.0

        # Look up state-specific utilization
        if state in K12_UTILIZATION_BY_STATE:
            utilization = K12_UTILIZATION_BY_STATE[state]
            state_match += 1
        else:
            utilization = DEFAULT_K12_UTILIZATION
            default_used += 1

        df.loc[idx, 'occ_utilization_rate'] = utilization

    print(f"\nUpdates summary:")
    print(f"  - Updated with state-specific data: {state_match}")
    print(f"  - Updated with default (22%): {default_used}")

    # Save
    print(f"\nSaving to {INPUT_FILE}...")
    df.to_csv(INPUT_FILE, index=False)
    print("Done!")

    # Show sample of updates by state
    print("\nSample utilization rates by state:")
    for state in ['CA', 'NY', 'TX', 'IL', 'WA', 'CO', 'MN']:
        if state in K12_UTILIZATION_BY_STATE:
            util = K12_UTILIZATION_BY_STATE[state]
            print(f"  {state}: {util*100:.0f}% utilization")

    # Show what this means for opportunity
    print("\nWhat this means for ODCV opportunity:")
    print("  Formula: Opportunity = 1 - Utilization")
    print("  CA (28% util): 72% opportunity - most time building ventilates empty")
    print("  NY (25% util): 75% opportunity")
    print("  WA (22% util): 78% opportunity")
    print("  MN (21% util): 79% opportunity (cold climate, long shutdown)")

if __name__ == '__main__':
    create_backup()
    update_k12_utilization()
