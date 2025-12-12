#!/usr/bin/env python3
"""
Update Supermarket/Grocery utilization rates based on traffic patterns.

Sources:
- Placer.ai grocery foot traffic analytics (2024)
- ASHRAE RP-1747: DCV savings simulation for retail/supermarket
- Verde grocery store energy efficiency studies
- Purdue DCV research: retail/supermarket ~25% HVAC savings potential

Key insight: Supermarkets have HIGHLY variable traffic patterns:
- Peak hours (5-7pm, weekends): 80-100% of design capacity
- Moderate hours (lunch, morning): 40-60% of design
- Slow hours (early morning, late night): 15-30% of design
- Overnight (24/7 stores): 5-15% of design

Weighted average utilization:
- 18-hour store (6am-midnight): ~50% of design capacity
- 24/7 store: ~40% of design capacity

Current data shows 70-75% utilization - this is TOO HIGH and understates
the DCV opportunity.

Additional considerations:
- Refrigeration cases run regardless of traffic (but benefit from reduced humidity)
- Deli/kitchen have code exhaust requirements
- Staff always present but represents small fraction of design occupancy
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

# Supermarket utilization by city/region
# Based on: operating hours, population density, traffic patterns
#
# Urban stores: Higher baseline traffic, longer hours
# Suburban stores: More peak/valley pattern (commuter-driven)
# 24/7 stores: Lower average due to overnight hours

UTILIZATION_BY_CITY = {
    # Dense urban (higher baseline, steadier traffic)
    'New York': 0.55,        # Dense, frequent shopping trips
    'San Francisco': 0.52,   # Dense urban
    'Chicago': 0.52,         # Dense urban
    'Boston': 0.53,          # Dense, walkable
    'Washington': 0.50,      # Urban
    'Philadelphia': 0.52,    # Dense urban
    'Seattle': 0.50,         # Urban

    # Large suburban metros (more peak/valley)
    'Los Angeles': 0.48,     # Car-dependent, peak-driven
    'Houston': 0.45,         # Suburban sprawl, many 24/7
    'Dallas': 0.46,          # Suburban sprawl
    'Phoenix': 0.44,         # Low density, many 24/7
    'Atlanta': 0.47,         # Suburban sprawl
    'Denver': 0.48,          # Mixed
    'San Diego': 0.49,       # Suburban

    # Smaller metros
    'Portland': 0.48,        # Mixed urban/suburban
    'Minneapolis': 0.46,     # Suburban
    'Kansas City': 0.45,     # Suburban
    'St. Louis': 0.46,       # Suburban
}

# State-level defaults
STATE_DEFAULTS = {
    'NY': 0.52,    # Dense urban
    'CA': 0.48,    # Mixed, many 24/7
    'TX': 0.45,    # Suburban, many 24/7
    'FL': 0.46,    # Suburban, many 24/7
    'IL': 0.50,    # Chicago influence
    'PA': 0.50,    # Urban corridor
    'OH': 0.47,    # Midwest suburban
    'GA': 0.47,    # Atlanta influence
    'MA': 0.52,    # Dense urban
    'WA': 0.49,    # Seattle influence
    'CO': 0.48,    # Denver influence
    'AZ': 0.44,    # Low density, 24/7 common
    'NV': 0.43,    # Las Vegas 24/7
}

# National average
# Based on weighted traffic patterns:
# Peak (4 hrs × 90%) + Moderate (8 hrs × 50%) + Slow (6 hrs × 20%) / 18 hrs = ~49%
DEFAULT_UTILIZATION = 0.48


def create_backup():
    """Create timestamped backup before changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(INPUT_FILE, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path


def get_utilization(city, state):
    """Get supermarket utilization for a city/state."""
    if city in UTILIZATION_BY_CITY:
        return UTILIZATION_BY_CITY[city]

    state_upper = str(state).upper().strip()
    if state_upper in STATE_DEFAULTS:
        return STATE_DEFAULTS[state_upper]

    return DEFAULT_UTILIZATION


def update_supermarket_utilization():
    """Update utilization rates for supermarket buildings."""
    print("Loading portfolio data...")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df)} buildings")

    # Track updates
    city_match = 0
    state_match = 0
    default_used = 0

    # Get Supermarket/Grocery buildings only
    grocery_mask = df['bldg_type'] == 'Supermarket/Grocery'
    print(f"Found {grocery_mask.sum()} Supermarket/Grocery buildings")

    for idx in df[grocery_mask].index:
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

        # Supermarkets don't have vacancy in the traditional sense
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
    print("\n=== SUPERMARKET TRAFFIC-BASED UTILIZATION ===")
    print("(Average customer density as % of design capacity)")
    print()
    print("City            | Old Util | New Util | Opportunity | Notes")
    print("-" * 70)
    examples = [
        ('New York', 0.70, 0.55, 'dense urban'),
        ('Los Angeles', 0.70, 0.48, 'suburban sprawl'),
        ('Phoenix', 0.70, 0.44, 'low density, 24/7'),
        ('Houston', 0.70, 0.45, 'suburban, 24/7'),
    ]
    for city, old, new, notes in examples:
        opp = 1 - new
        print(f"{city:15} | {old*100:5.0f}%    | {new*100:5.0f}%    | {opp*100:5.0f}%        | {notes}")

    print()
    print("Traffic pattern basis:")
    print("  Peak (4 hrs): 80-100% capacity")
    print("  Moderate (8 hrs): 40-60% capacity")
    print("  Slow (6 hrs): 15-30% capacity")
    print("  Weighted avg: ~48% nationally")


if __name__ == '__main__':
    create_backup()
    update_supermarket_utilization()
