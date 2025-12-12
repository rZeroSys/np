#!/usr/bin/env python3
"""
Add Berkeley Buildings to Portfolio
====================================
Integrates Berkeley BESO building data into the nationwide portfolio.

Steps:
1. Load Berkeley data from berkeley_buildings_fetch
2. Add PG&E utility rates (same as San Francisco)
3. Align columns with portfolio schema
4. Append to portfolio_data.csv (avoiding duplicates)

Usage: python3 scripts/data_updates/add_berkeley.py
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

# External data source - keep hardcoded as it's outside the project
BERKELEY_CSV = '/Users/forrestmiller/Desktop/berkeley_buildings_fetch/data/05_final_new_buildings.csv'
PORTFOLIO_CSV = str(PORTFOLIO_DATA_PATH)
BACKUP_DIR = str(CONFIG_BACKUP_DIR)

# PG&E rates (same as San Francisco buildings)
PGE_RATES = {
    'cost_elec_rate_kwh': 0.200526,
    'cost_elec_rate_demand_kw': 37.63,
    'cost_gas_rate_therm': 1.8931,
    'cost_elec_load_factor': 0.45,
    'cost_calc_notes': 'PG&E rates (Berkeley)',
}


def create_backup():
    """Create timestamped backup before any changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(PORTFOLIO_CSV, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path


def main():
    print("=" * 60)
    print("ADD BERKELEY BUILDINGS TO PORTFOLIO")
    print("=" * 60)

    # Load Berkeley data
    print(f"\nLoading Berkeley data: {BERKELEY_CSV}")
    berkeley_df = pd.read_csv(BERKELEY_CSV, low_memory=False)
    print(f"  Loaded {len(berkeley_df):,} Berkeley buildings")

    # Load portfolio data
    print(f"\nLoading portfolio: {PORTFOLIO_CSV}")
    portfolio_df = pd.read_csv(PORTFOLIO_CSV, low_memory=False)
    print(f"  Loaded {len(portfolio_df):,} buildings")

    # Create backup
    create_backup()

    # Check for existing Berkeley buildings
    existing_berkeley = portfolio_df[portfolio_df['loc_city'] == 'Berkeley']
    print(f"\n  Existing Berkeley buildings in portfolio: {len(existing_berkeley)}")

    # Check for duplicate IDs
    berkeley_ids = set(berkeley_df['id_building'].tolist())
    portfolio_ids = set(portfolio_df['id_building'].tolist())
    duplicates = berkeley_ids.intersection(portfolio_ids)

    if duplicates:
        print(f"  Found {len(duplicates)} duplicate IDs - will skip these")
        berkeley_df = berkeley_df[~berkeley_df['id_building'].isin(duplicates)]
        print(f"  Remaining Berkeley buildings to add: {len(berkeley_df)}")

    if len(berkeley_df) == 0:
        print("\nNo new buildings to add!")
        return

    # Add PG&E rate columns
    print("\nAdding PG&E utility rates...")
    for col, val in PGE_RATES.items():
        berkeley_df[col] = val
        print(f"  {col} = {val}")

    # Get portfolio columns and add any missing ones to Berkeley
    portfolio_cols = portfolio_df.columns.tolist()
    berkeley_cols = berkeley_df.columns.tolist()

    missing_cols = [c for c in portfolio_cols if c not in berkeley_cols]
    print(f"\nAdding {len(missing_cols)} missing columns to Berkeley data...")
    for col in missing_cols:
        berkeley_df[col] = np.nan

    # Reorder Berkeley columns to match portfolio
    berkeley_df = berkeley_df[portfolio_cols]

    # Append to portfolio
    print("\nAppending Berkeley buildings to portfolio...")
    combined_df = pd.concat([portfolio_df, berkeley_df], ignore_index=True)

    # Save
    print(f"\nSaving to: {PORTFOLIO_CSV}")
    combined_df.to_csv(PORTFOLIO_CSV, index=False)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Original portfolio: {len(portfolio_df):,} buildings")
    print(f"  Berkeley added: {len(berkeley_df):,} buildings")
    print(f"  New portfolio total: {len(combined_df):,} buildings")

    # Verify Berkeley city count
    new_berkeley = combined_df[combined_df['loc_city'] == 'Berkeley']
    print(f"  Berkeley buildings now in portfolio: {len(new_berkeley):,}")

    print("\nDone! Now run orchestration scripts to calculate derived fields.")
    print("  python3 scripts/populate_master/orchestrate.py")


if __name__ == '__main__':
    main()
