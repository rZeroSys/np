#!/usr/bin/env python3
"""
Fix Energy Totals Calculator
=============================
Fixes 481 buildings where energy_total_kbtu_post_odcv > energy_total_kbtu.

Root cause: Original energy_total_kbtu excluded steam for some buildings,
but post-ODCV calculation correctly included all fuel types.

Solution: Recalculate energy_total_kbtu as sum of all fuel types:
  energy_total_kbtu = elec + gas + steam + fuel_oil

Also recalculates energy_total_kbtu_post_odcv to ensure consistency.

Usage: python3 fix_energy_totals.py
"""

import pandas as pd
import numpy as np
import shutil
from pathlib import Path
from datetime import datetime

# =============================================================================
# CONFIGURATION
# =============================================================================

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import PORTFOLIO_DATA_PATH, BACKUP_DIR as CONFIG_BACKUP_DIR

INPUT_FILE = str(PORTFOLIO_DATA_PATH)
BACKUP_DIR = str(CONFIG_BACKUP_DIR)


def create_backup():
    """Create timestamped backup before any changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(INPUT_FILE, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path


def safe_float(val, default=0.0):
    """Convert value to float, return default if empty or invalid."""
    if val is None or val == '' or (isinstance(val, float) and np.isnan(val)):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 70)
    print("Fix Energy Totals Calculator")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Create backup
    create_backup()

    # Load data
    print(f"\nLoading: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df):,} buildings")

    # ==========================================================================
    # STEP 1: Identify buildings with impossible energy values BEFORE fix
    # ==========================================================================
    print("\n" + "-" * 70)
    print("STEP 1: Analyzing existing data issues")
    print("-" * 70)

    # Check how many have post > pre (allowing 0.1% tolerance for floating point)
    pre_fix_issues = df[
        (df['energy_total_kbtu_post_odcv'].notna()) &
        (df['energy_total_kbtu'].notna()) &
        (df['energy_total_kbtu_post_odcv'] > df['energy_total_kbtu'] * 1.001)
    ]
    print(f"Buildings with post-ODCV > pre-ODCV energy: {len(pre_fix_issues):,}")

    if len(pre_fix_issues) > 0:
        print("\nSample of problematic buildings:")
        for _, row in pre_fix_issues.head(5).iterrows():
            bid = row.get('id_building', 'N/A')
            pre = safe_float(row.get('energy_total_kbtu'))
            post = safe_float(row.get('energy_total_kbtu_post_odcv'))
            diff = post - pre
            print(f"  {bid}: {pre:,.0f} kBtu -> {post:,.0f} kBtu (diff: +{diff:,.0f})")

    # ==========================================================================
    # STEP 2: Recalculate energy_total_kbtu as sum of all fuel types
    # ==========================================================================
    print("\n" + "-" * 70)
    print("STEP 2: Recalculating energy_total_kbtu")
    print("-" * 70)

    # Store original for comparison
    df['energy_total_kbtu_original'] = df['energy_total_kbtu'].copy()

    # Recalculate as sum of all fuel types
    df['energy_total_kbtu'] = (
        df['energy_elec_kbtu'].fillna(0) +
        df['energy_gas_kbtu'].fillna(0) +
        df['energy_steam_kbtu'].fillna(0) +
        df['energy_fuel_oil_kbtu'].fillna(0)
    )

    # Round to 2 decimal places
    df['energy_total_kbtu'] = df['energy_total_kbtu'].round(2)

    # Check how many changed
    changed = df[
        (df['energy_total_kbtu_original'].notna()) &
        (abs(df['energy_total_kbtu'] - df['energy_total_kbtu_original']) > 1)
    ]
    print(f"Buildings with energy_total_kbtu changed: {len(changed):,}")

    # ==========================================================================
    # STEP 3: Recalculate energy_total_kbtu_post_odcv
    # ==========================================================================
    print("\n" + "-" * 70)
    print("STEP 3: Recalculating energy_total_kbtu_post_odcv")
    print("-" * 70)

    # Recalculate as sum of all post-ODCV fuel types
    df['energy_total_kbtu_post_odcv'] = (
        df['energy_elec_kbtu_post_odcv'].fillna(0) +
        df['energy_gas_kbtu_post_odcv'].fillna(0) +
        df['energy_steam_kbtu_post_odcv'].fillna(0) +
        df['energy_fuel_oil_kbtu_post_odcv'].fillna(0)
    )

    # Round to 2 decimal places
    df['energy_total_kbtu_post_odcv'] = df['energy_total_kbtu_post_odcv'].round(2)

    # Set to None where all components are zero (building has no energy data)
    no_energy_mask = (
        df['energy_elec_kbtu_post_odcv'].fillna(0) +
        df['energy_gas_kbtu_post_odcv'].fillna(0) +
        df['energy_steam_kbtu_post_odcv'].fillna(0) +
        df['energy_fuel_oil_kbtu_post_odcv'].fillna(0)
    ) == 0
    df.loc[no_energy_mask, 'energy_total_kbtu_post_odcv'] = np.nan

    print(f"Non-null energy_total_kbtu_post_odcv values: {df['energy_total_kbtu_post_odcv'].notna().sum():,}")

    # ==========================================================================
    # STEP 4: Verify the fix
    # ==========================================================================
    print("\n" + "-" * 70)
    print("STEP 4: Verifying fix")
    print("-" * 70)

    # Check for any remaining impossible values (post > pre by more than 0.1%)
    post_fix_issues = df[
        (df['energy_total_kbtu_post_odcv'].notna()) &
        (df['energy_total_kbtu'].notna()) &
        (df['energy_total_kbtu_post_odcv'] > df['energy_total_kbtu'] * 1.001)
    ]

    if len(post_fix_issues) == 0:
        print("SUCCESS: No buildings have post-ODCV > pre-ODCV energy!")
    else:
        print(f"WARNING: {len(post_fix_issues):,} buildings still have issues:")
        for _, row in post_fix_issues.head(10).iterrows():
            bid = row.get('id_building', 'N/A')
            pre = safe_float(row.get('energy_total_kbtu'))
            post = safe_float(row.get('energy_total_kbtu_post_odcv'))
            print(f"  {bid}: {pre:,.0f} kBtu -> {post:,.0f} kBtu")

    # ==========================================================================
    # STEP 5: Summary statistics
    # ==========================================================================
    print("\n" + "-" * 70)
    print("STEP 5: Summary Statistics")
    print("-" * 70)

    print(f"Total buildings: {len(df):,}")
    print(f"With energy_total_kbtu: {df['energy_total_kbtu'].notna().sum():,}")
    print(f"With energy_total_kbtu_post_odcv: {df['energy_total_kbtu_post_odcv'].notna().sum():,}")

    # Show energy savings statistics
    df['energy_savings_kbtu'] = df['energy_total_kbtu'] - df['energy_total_kbtu_post_odcv']
    df['energy_savings_pct'] = df['energy_savings_kbtu'] / df['energy_total_kbtu'] * 100

    valid_savings = df[
        (df['energy_total_kbtu'] > 0) &
        (df['energy_total_kbtu_post_odcv'].notna())
    ]

    if len(valid_savings) > 0:
        print(f"\nEnergy savings (for {len(valid_savings):,} buildings with valid data):")
        print(f"  Mean savings: {valid_savings['energy_savings_pct'].mean():.1f}%")
        print(f"  Median savings: {valid_savings['energy_savings_pct'].median():.1f}%")
        print(f"  Min savings: {valid_savings['energy_savings_pct'].min():.1f}%")
        print(f"  Max savings: {valid_savings['energy_savings_pct'].max():.1f}%")

    # ==========================================================================
    # STEP 6: Clean up and save
    # ==========================================================================
    print("\n" + "-" * 70)
    print("STEP 6: Saving results")
    print("-" * 70)

    # Remove temporary columns
    df.drop(columns=['energy_total_kbtu_original', 'energy_savings_kbtu', 'energy_savings_pct'],
            inplace=True, errors='ignore')

    # Save
    print(f"Saving to: {INPUT_FILE}")
    df.to_csv(INPUT_FILE, index=False)
    print("Done!")

    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)


if __name__ == '__main__':
    main()
