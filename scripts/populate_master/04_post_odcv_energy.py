#!/usr/bin/env python3
"""
Post-ODCV Energy Calculator
===========================
Calculates post-ODCV energy usage by applying ODCV savings to each fuel type.

Formula:
  post_odcv_energy = current_energy × (1 - hvac_pct × odcv_hvac_savings_pct)

Output columns:
- energy_elec_kwh_post_odcv: Electricity after ODCV (kWh)
- energy_elec_kbtu_post_odcv: Electricity after ODCV (kBtu)
- energy_gas_kbtu_post_odcv: Natural gas after ODCV (kBtu)
- energy_steam_kbtu_post_odcv: District steam after ODCV (kBtu)
- energy_fuel_oil_kbtu_post_odcv: Fuel oil after ODCV (kBtu)
- energy_total_kbtu_post_odcv: Total energy after ODCV (kBtu)

Requires (from previous scripts):
- hvac_pct_elec, hvac_pct_gas, hvac_pct_steam, hvac_pct_fuel_oil (from 01_hvac_pct.py)
- odcv_hvac_savings_pct (from 02_odcv_savings.py)

Usage: python3 02b_post_odcv_energy.py
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


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def safe_float(val, default=None):
    """Convert value to float, return default if empty or invalid."""
    if val is None or val == '' or (isinstance(val, float) and np.isnan(val)):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def calculate_post_odcv_energy(row):
    """
    Calculate post-ODCV energy for all fuel types.

    Formula: post_odcv = current × (1 - hvac_pct × odcv_savings_pct)

    Returns dict with all post-ODCV energy values.
    """
    odcv_pct = safe_float(row.get('odcv_hvac_savings_pct'), 0.0)

    result = {
        'energy_elec_kwh_post_odcv': None,
        'energy_elec_kbtu_post_odcv': None,
        'energy_gas_kbtu_post_odcv': None,
        'energy_steam_kbtu_post_odcv': None,
        'energy_fuel_oil_kbtu_post_odcv': None,
        'energy_total_kbtu_post_odcv': None,
    }

    # If no ODCV savings, post-ODCV = current
    if odcv_pct == 0:
        result['energy_elec_kwh_post_odcv'] = safe_float(row.get('energy_elec_kwh'))
        result['energy_elec_kbtu_post_odcv'] = safe_float(row.get('energy_elec_kbtu'))
        result['energy_gas_kbtu_post_odcv'] = safe_float(row.get('energy_gas_kbtu'))
        result['energy_steam_kbtu_post_odcv'] = safe_float(row.get('energy_steam_kbtu'))
        result['energy_fuel_oil_kbtu_post_odcv'] = safe_float(row.get('energy_fuel_oil_kbtu'))
        # Calculate total
        total = 0.0
        for key in ['energy_elec_kbtu_post_odcv', 'energy_gas_kbtu_post_odcv',
                    'energy_steam_kbtu_post_odcv', 'energy_fuel_oil_kbtu_post_odcv']:
            if result[key] is not None:
                total += result[key]
        result['energy_total_kbtu_post_odcv'] = round(total, 2) if total > 0 else None
        return result

    total_post_odcv_kbtu = 0.0

    # Electricity (kWh)
    elec_kwh = safe_float(row.get('energy_elec_kwh'))
    hvac_pct_elec = safe_float(row.get('hvac_pct_elec'), 0.0)
    if elec_kwh is not None and elec_kwh > 0:
        reduction_factor = 1 - (hvac_pct_elec * odcv_pct)
        result['energy_elec_kwh_post_odcv'] = round(elec_kwh * reduction_factor, 2)

    # Electricity (kBtu)
    elec_kbtu = safe_float(row.get('energy_elec_kbtu'))
    if elec_kbtu is not None and elec_kbtu > 0:
        reduction_factor = 1 - (hvac_pct_elec * odcv_pct)
        post_odcv = elec_kbtu * reduction_factor
        result['energy_elec_kbtu_post_odcv'] = round(post_odcv, 2)
        total_post_odcv_kbtu += post_odcv

    # Natural Gas (kBtu)
    gas_kbtu = safe_float(row.get('energy_gas_kbtu'))
    hvac_pct_gas = safe_float(row.get('hvac_pct_gas'), 0.0)
    if gas_kbtu is not None and gas_kbtu > 0:
        reduction_factor = 1 - (hvac_pct_gas * odcv_pct)
        post_odcv = gas_kbtu * reduction_factor
        result['energy_gas_kbtu_post_odcv'] = round(post_odcv, 2)
        total_post_odcv_kbtu += post_odcv

    # Steam (kBtu)
    steam_kbtu = safe_float(row.get('energy_steam_kbtu'))
    hvac_pct_steam = safe_float(row.get('hvac_pct_steam'), 0.0)
    if steam_kbtu is not None and steam_kbtu > 0:
        reduction_factor = 1 - (hvac_pct_steam * odcv_pct)
        post_odcv = steam_kbtu * reduction_factor
        result['energy_steam_kbtu_post_odcv'] = round(post_odcv, 2)
        total_post_odcv_kbtu += post_odcv

    # Fuel Oil (kBtu)
    oil_kbtu = safe_float(row.get('energy_fuel_oil_kbtu'))
    hvac_pct_oil = safe_float(row.get('hvac_pct_fuel_oil'), 0.0)
    if oil_kbtu is not None and oil_kbtu > 0:
        reduction_factor = 1 - (hvac_pct_oil * odcv_pct)
        post_odcv = oil_kbtu * reduction_factor
        result['energy_fuel_oil_kbtu_post_odcv'] = round(post_odcv, 2)
        total_post_odcv_kbtu += post_odcv

    # Total
    if total_post_odcv_kbtu > 0:
        result['energy_total_kbtu_post_odcv'] = round(total_post_odcv_kbtu, 2)

    return result


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("POST-ODCV ENERGY CALCULATOR")
    print("=" * 60)

    # Load data
    print(f"\nLoading: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df):,} buildings")

    # Create backup
    create_backup()

    # Check for required columns
    required = ['odcv_hvac_savings_pct', 'hvac_pct_elec']
    missing = [col for col in required if col not in df.columns]
    if missing:
        print(f"\nERROR: Missing required columns: {missing}")
        print("Make sure to run 01_hvac_pct.py and 02_odcv_savings.py first!")
        return

    # Initialize counters
    calculated = 0

    # Process each building
    print("\nCalculating post-ODCV energy...")

    for idx, row in df.iterrows():
        result = calculate_post_odcv_energy(row)

        # Update dataframe
        for col, val in result.items():
            df.at[idx, col] = val

        if result['energy_total_kbtu_post_odcv'] is not None:
            calculated += 1

    # Save results
    print(f"\nSaving to: {INPUT_FILE}")
    df.to_csv(INPUT_FILE, index=False)

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Buildings with post-ODCV energy: {calculated:,}")

    # Show sample reduction
    sample = df[df['odcv_hvac_savings_pct'].notna() & (df['odcv_hvac_savings_pct'] > 0)].head(1)
    if len(sample) > 0:
        row = sample.iloc[0]
        print(f"\n  Sample building:")
        print(f"    ODCV savings %: {row['odcv_hvac_savings_pct']:.1%}")
        if pd.notna(row.get('energy_total_kbtu')) and pd.notna(row.get('energy_total_kbtu_post_odcv')):
            orig = row['energy_total_kbtu']
            post = row['energy_total_kbtu_post_odcv']
            reduction = (orig - post) / orig * 100
            print(f"    Total energy: {orig:,.0f} → {post:,.0f} kBtu ({reduction:.1f}% reduction)")

    print("\nDone!")


if __name__ == '__main__':
    main()
