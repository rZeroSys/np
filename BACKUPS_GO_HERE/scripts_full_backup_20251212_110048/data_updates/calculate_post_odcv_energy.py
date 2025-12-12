#!/usr/bin/env python3
"""
Post-ODCV Energy Calculator
===========================
Calculates post-ODCV energy usage for each fuel type.

New columns added:
- energy_elec_kwh_post_odcv
- energy_gas_kbtu_post_odcv
- energy_steam_kbtu_post_odcv
- energy_fuel_oil_kbtu_post_odcv
- carbon_emissions_post_odcv_mt

Formula:
  new_value = current_value × (1 - hvac_pct × odcv_hvac_savings_pct)

Usage: python3 calculate_post_odcv_energy.py
"""

import pandas as pd
import numpy as np
import shutil
from pathlib import Path
from datetime import datetime

# =============================================================================
# CONFIGURATION
# =============================================================================

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

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def safe_float(val, default=0.0):
    """Convert value to float, return default if empty or invalid."""
    if val is None or val == '' or (isinstance(val, float) and np.isnan(val)):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def calculate_post_odcv_energy(current_energy, hvac_pct, odcv_savings_pct):
    """
    Calculate post-ODCV energy usage.

    Formula: new = current × (1 - hvac_pct × odcv_savings_pct)

    Only the HVAC portion is reduced by the ODCV savings percentage.
    """
    current = safe_float(current_energy)
    hvac = safe_float(hvac_pct)
    savings = safe_float(odcv_savings_pct)

    if current == 0:
        return None

    # HVAC portion that gets reduced
    hvac_reduction = current * hvac * savings
    new_energy = current - hvac_reduction

    return round(new_energy, 2)


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("Post-ODCV Energy Calculator")
    print("=" * 60)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Create backup
    create_backup()

    # Load data
    print(f"\nLoading: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df):,} buildings")

    # Calculate post-ODCV electricity (kWh)
    print("\nCalculating energy_elec_kwh_post_odcv...")
    df['energy_elec_kwh_post_odcv'] = df.apply(
        lambda row: calculate_post_odcv_energy(
            row.get('energy_elec_kwh'),
            row.get('hvac_pct_elec'),
            row.get('odcv_hvac_savings_pct')
        ), axis=1
    )

    # Calculate post-ODCV natural gas (kBtu)
    print("Calculating energy_gas_kbtu_post_odcv...")
    df['energy_gas_kbtu_post_odcv'] = df.apply(
        lambda row: calculate_post_odcv_energy(
            row.get('energy_gas_kbtu'),
            row.get('hvac_pct_gas'),
            row.get('odcv_hvac_savings_pct')
        ), axis=1
    )

    # Calculate post-ODCV steam (kBtu)
    print("Calculating energy_steam_kbtu_post_odcv...")
    df['energy_steam_kbtu_post_odcv'] = df.apply(
        lambda row: calculate_post_odcv_energy(
            row.get('energy_steam_kbtu'),
            row.get('hvac_pct_steam'),
            row.get('odcv_hvac_savings_pct')
        ), axis=1
    )

    # Calculate post-ODCV fuel oil (kBtu)
    print("Calculating energy_fuel_oil_kbtu_post_odcv...")
    df['energy_fuel_oil_kbtu_post_odcv'] = df.apply(
        lambda row: calculate_post_odcv_energy(
            row.get('energy_fuel_oil_kbtu'),
            row.get('hvac_pct_fuel_oil'),
            row.get('odcv_hvac_savings_pct')
        ), axis=1
    )

    # Calculate post-ODCV carbon emissions
    print("Calculating carbon_emissions_post_odcv_mt...")
    df['carbon_emissions_post_odcv_mt'] = df.apply(
        lambda row: (
            safe_float(row.get('carbon_emissions_total_mt')) -
            safe_float(row.get('odcv_carbon_reduction_yr1_mt'))
        ) if safe_float(row.get('carbon_emissions_total_mt')) > 0 else None,
        axis=1
    )

    # Round carbon emissions
    df['carbon_emissions_post_odcv_mt'] = df['carbon_emissions_post_odcv_mt'].round(2)

    # Summary stats
    print("\n" + "-" * 60)
    print("RESULTS SUMMARY")
    print("-" * 60)

    for col in ['energy_elec_kwh_post_odcv', 'energy_gas_kbtu_post_odcv',
                'energy_steam_kbtu_post_odcv', 'energy_fuel_oil_kbtu_post_odcv',
                'carbon_emissions_post_odcv_mt']:
        non_null = df[col].notna().sum()
        print(f"{col}: {non_null:,} non-null values")

    # Show sample comparison
    print("\n" + "-" * 60)
    print("SAMPLE COMPARISON (first 5 with electricity data)")
    print("-" * 60)

    sample = df[df['energy_elec_kwh'].notna() & (df['energy_elec_kwh'] > 0)].head(5)
    for _, row in sample.iterrows():
        bid = row.get('id_building', 'N/A')
        curr = safe_float(row.get('energy_elec_kwh'))
        new = safe_float(row.get('energy_elec_kwh_post_odcv'))
        hvac = safe_float(row.get('hvac_pct_elec'))
        odcv = safe_float(row.get('odcv_hvac_savings_pct'))
        reduction = curr - new if new else 0
        print(f"  {bid}: {curr:,.0f} kWh -> {new:,.0f} kWh (HVAC {hvac*100:.0f}%, ODCV {odcv*100:.1f}%, saved {reduction:,.0f})")

    # Save
    print(f"\nSaving to: {INPUT_FILE}")
    df.to_csv(INPUT_FILE, index=False)
    print("Done!")

    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    main()
