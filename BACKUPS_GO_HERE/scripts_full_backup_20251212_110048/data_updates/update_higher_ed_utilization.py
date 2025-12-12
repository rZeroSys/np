#!/usr/bin/env python3
"""
Update Higher Education utilization rates based on academic schedules.

Sources:
- APPA (Association of Physical Plant Administrators) classroom utilization studies
- SIGHTLINES/Gordian Higher Ed Facilities benchmarks
- Internal methodology: Similar to K-12 but with more variability

Key factors:
- Academic year: ~32 weeks in session (2 semesters × 15-16 weeks)
- Summer break: ~12 weeks (23% of year)
- Winter/spring breaks: ~4-6 weeks
- Classroom utilization during semester: 30-40% of available hours
  (rooms scheduled for specific classes sit empty rest of time)

Calculation:
- Weeks in session: 32/52 = 62% of year
- Room utilization during session: ~35%
- Base utilization: 62% × 35% = 22%
- HVAC buffer (pre-conditioning, evening events): +30%
- Final utilization: ~28%

Variation by institution type:
- Research universities: more lab space, higher utilization
- Liberal arts colleges: more variable schedules
- Community colleges: evening/weekend classes increase utilization
"""

import pandas as pd
import shutil
from pathlib import Path
from datetime import datetime

# Paths
INPUT_FILE = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv'
BACKUP_DIR = '/Users/forrestmiller/Desktop/nationwide-prospector/BACKUPS_GO_HERE/csv_backups'

# Higher Ed utilization by state
# Based on: academic calendar length, climate (affects break patterns),
# mix of institution types
HIGHER_ED_UTILIZATION_BY_STATE = {
    # Year-round programs more common (higher utilization)
    'CA': 0.30,    # Quarter system common, summer sessions
    'FL': 0.29,    # Year-round programs
    'AZ': 0.29,    # Year-round programs
    'TX': 0.28,    # Large systems, summer sessions

    # Traditional academic calendar (standard utilization)
    'MA': 0.26,    # Many traditional liberal arts
    'NY': 0.27,    # Mix of types
    'PA': 0.26,    # Traditional
    'IL': 0.26,    # Traditional
    'OH': 0.26,    # Traditional
    'DC': 0.27,    # Urban, some year-round

    # Cold climate (longer winter break, lower utilization)
    'MN': 0.24,    # Harsh winters
    'WI': 0.24,    # Harsh winters
    'MI': 0.25,    # Cold climate
    'CO': 0.25,    # Mountain climate

    # Research-heavy states (labs run more hours)
    'NC': 0.28,    # Research triangle
    'GA': 0.27,    # Research institutions
    'WA': 0.27,    # Research universities
    'OR': 0.26,    # Traditional + research
}

# Default (based on national average academic calendar)
DEFAULT_HIGHER_ED_UTILIZATION = 0.26  # 26%

def create_backup():
    """Create timestamped backup before changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(INPUT_FILE, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path

def update_higher_ed_utilization():
    """Update utilization rates for Higher Ed buildings."""
    print("Loading portfolio data...")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df)} buildings")

    # Track updates
    state_match = 0
    default_used = 0

    # Get Higher Ed buildings only
    higher_ed_mask = df['bldg_type'] == 'Higher Ed'
    print(f"Found {higher_ed_mask.sum()} Higher Ed buildings")

    for idx in df[higher_ed_mask].index:
        state = str(df.loc[idx, 'loc_state']).strip().upper()

        # Higher Ed doesn't have vacancy like offices
        df.loc[idx, 'occ_vacancy_rate'] = 0.0

        # Look up state-specific utilization
        if state in HIGHER_ED_UTILIZATION_BY_STATE:
            utilization = HIGHER_ED_UTILIZATION_BY_STATE[state]
            state_match += 1
        else:
            utilization = DEFAULT_HIGHER_ED_UTILIZATION
            default_used += 1

        df.loc[idx, 'occ_utilization_rate'] = utilization

    print(f"\nUpdates summary:")
    print(f"  - State-specific: {state_match}")
    print(f"  - Default (26%): {default_used}")

    # Save
    print(f"\nSaving to {INPUT_FILE}...")
    df.to_csv(INPUT_FILE, index=False)
    print("Done!")

    # Show examples
    print("\n=== HIGHER ED UTILIZATION ===")
    print("Based on: 32 weeks in session × 35% room utilization + HVAC buffer")
    print()
    print("State | Utilization | Opportunity | Notes")
    print("-" * 60)
    for state, util in [('CA', 0.30), ('MA', 0.26), ('MN', 0.24)]:
        opp = 1 - util
        note = "year-round programs" if util >= 0.29 else "traditional calendar" if util >= 0.26 else "cold climate"
        print(f"{state:5} | {util*100:5.0f}%       | {opp*100:5.0f}%       | {note}")
    print()
    print("Compare to old: 62% utilization (bogus default)")

if __name__ == '__main__':
    create_backup()
    update_higher_ed_utilization()
