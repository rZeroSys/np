#!/usr/bin/env python3
"""
HVAC Fuel Oil Percentage Fix
=============================
Sets hvac_pct_fuel_oil to 0.93 for all buildings with fuel oil.
Does NOT change hvac_pct_elec, hvac_pct_gas, or hvac_pct_steam.

Usage: python3 01_hvac_pct.py
"""

import pandas as pd
import shutil
from pathlib import Path
from datetime import datetime

INPUT_FILE = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv'
BACKUP_DIR = '/Users/forrestmiller/Desktop/nationwide-prospector/BACKUPS_GO_HERE/csv_backups'

def create_backup():
    """Create timestamped backup before any changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(INPUT_FILE, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path

def main():
    print("=" * 60)
    print("HVAC Fuel Oil Percentage Fix")
    print("=" * 60)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Create backup first
    create_backup()

    # Load data
    print(f"\nLoading: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df):,} buildings")

    # Count buildings with fuel oil
    has_fuel_oil = df['energy_fuel_oil_kbtu'].notna() & (df['energy_fuel_oil_kbtu'] > 0)
    print(f"\nBuildings with fuel oil: {has_fuel_oil.sum():,}")

    # Before
    print(f"\nBEFORE - hvac_pct_fuel_oil stats:")
    valid = df.loc[has_fuel_oil, 'hvac_pct_fuel_oil'].dropna()
    if len(valid) > 0:
        print(f"  Count:  {len(valid):,}")
        print(f"  Mean:   {valid.mean():.2%}")
        print(f"  Median: {valid.median():.2%}")

    # Set fuel oil HVAC % to 93%
    df.loc[has_fuel_oil, 'hvac_pct_fuel_oil'] = 0.93

    # After
    print(f"\nAFTER - hvac_pct_fuel_oil stats:")
    valid = df.loc[has_fuel_oil, 'hvac_pct_fuel_oil'].dropna()
    if len(valid) > 0:
        print(f"  Count:  {len(valid):,}")
        print(f"  Mean:   {valid.mean():.2%}")
        print(f"  Median: {valid.median():.2%}")

    # Save
    print(f"\nSaving to: {INPUT_FILE}")
    df.to_csv(INPUT_FILE, index=False)
    print(f"Saved {len(df):,} buildings")

    print("\n" + "=" * 60)
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


if __name__ == '__main__':
    main()
