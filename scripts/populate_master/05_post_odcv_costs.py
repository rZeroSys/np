#!/usr/bin/env python3
"""
Post-ODCV Energy Cost Calculator
================================
Calculates energy costs from POST-ODCV energy usage.

Uses same formulas as 02_energy_costs.py but with post-ODCV energy values.
ODCV only reduces HVAC energy, so these costs reflect the reduced consumption.

Output columns:
- cost_elec_energy_annual_post_odcv: Electricity energy charges after ODCV ($)
- cost_elec_demand_annual_post_odcv: Electricity demand charges after ODCV ($)
- cost_elec_total_annual_post_odcv: Total electricity cost after ODCV ($)
- cost_gas_annual_post_odcv: Natural gas cost after ODCV ($)
- cost_steam_annual_post_odcv: District steam cost after ODCV ($)
- cost_fuel_oil_annual_post_odcv: Fuel oil cost after ODCV ($)

Formulas (same as current, using post-ODCV energy):
  Electricity:
    peak_kw_post_odcv = energy_elec_kwh_post_odcv / (8760 × load_factor)
    energy_annual = kwh_post_odcv × rate_kwh × 1.10
    demand_annual = peak_kw_post_odcv × rate_demand × 12 × 1.265

  Gas:    (kbtu_post_odcv / 100) × rate_therm × 1.10
  Steam:  (kbtu_post_odcv / 909) × rate_mlb
  Fuel:   (kbtu_post_odcv / 1000) × rate_mmbtu × 1.10

Requires:
- energy_elec_kwh_post_odcv, energy_gas_kbtu_post_odcv, etc. (from 04_post_odcv_energy.py)
- Utility rates (cost_elec_rate_kwh, etc.)

Usage: python3 05_post_odcv_costs.py
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

# Conversion factors (same as 02_energy_costs.py)
KBTU_PER_THERM = 100
KBTU_PER_MLB_STEAM = 909
KBTU_PER_MMBTU = 1000
HOURS_PER_YEAR = 8760

# Cost multipliers
ENERGY_CHARGE_MULTIPLIER = 1.10
DEMAND_CHARGE_MULTIPLIER = 1.265
MONTHS_PER_YEAR = 12

DEFAULT_LOAD_FACTOR = 0.45


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


def calculate_elec_costs_post_odcv(row):
    """
    Calculate post-ODCV electricity costs from post-ODCV usage.
    """
    kwh = safe_float(row.get('energy_elec_kwh_post_odcv'))
    rate_kwh = safe_float(row.get('cost_elec_rate_kwh'))
    rate_demand = safe_float(row.get('cost_elec_rate_demand_kw'))
    load_factor = safe_float(row.get('cost_elec_load_factor'), DEFAULT_LOAD_FACTOR)

    result = {
        'cost_elec_energy_annual_post_odcv': None,
        'cost_elec_demand_annual_post_odcv': None,
        'cost_elec_total_annual_post_odcv': None,
    }

    if kwh is None or kwh <= 0 or rate_kwh is None:
        return result

    # Energy charges
    energy_annual = kwh * rate_kwh * ENERGY_CHARGE_MULTIPLIER
    result['cost_elec_energy_annual_post_odcv'] = round(energy_annual, 2)

    # Demand charges
    if rate_demand is not None and rate_demand > 0:
        peak_kw = kwh / (HOURS_PER_YEAR * load_factor)
        demand_annual = peak_kw * rate_demand * MONTHS_PER_YEAR * DEMAND_CHARGE_MULTIPLIER
        result['cost_elec_demand_annual_post_odcv'] = round(demand_annual, 2)
        result['cost_elec_total_annual_post_odcv'] = round(energy_annual + demand_annual, 2)
    else:
        result['cost_elec_demand_annual_post_odcv'] = 0.0
        result['cost_elec_total_annual_post_odcv'] = round(energy_annual, 2)

    return result


def calculate_gas_cost_post_odcv(row):
    """Calculate post-ODCV gas cost from post-ODCV usage."""
    kbtu = safe_float(row.get('energy_gas_kbtu_post_odcv'))
    rate = safe_float(row.get('cost_gas_rate_therm'))

    if kbtu is None or kbtu <= 0 or rate is None:
        return None

    therms = kbtu / KBTU_PER_THERM
    cost = therms * rate * ENERGY_CHARGE_MULTIPLIER
    return round(cost, 2)


def calculate_steam_cost_post_odcv(row):
    """Calculate post-ODCV steam cost from post-ODCV usage."""
    kbtu = safe_float(row.get('energy_steam_kbtu_post_odcv'))
    rate = safe_float(row.get('cost_steam_rate_mlb'))

    if kbtu is None or kbtu <= 0 or rate is None:
        return None

    mlb = kbtu / KBTU_PER_MLB_STEAM
    cost = mlb * rate  # No 1.10 multiplier for steam
    return round(cost, 2)


def calculate_fuel_oil_cost_post_odcv(row):
    """Calculate post-ODCV fuel oil cost from post-ODCV usage."""
    kbtu = safe_float(row.get('energy_fuel_oil_kbtu_post_odcv'))
    rate = safe_float(row.get('cost_fuel_oil_rate_mmbtu'))

    if kbtu is None or kbtu <= 0 or rate is None:
        return None

    mmbtu = kbtu / KBTU_PER_MMBTU
    cost = mmbtu * rate * ENERGY_CHARGE_MULTIPLIER
    return round(cost, 2)


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("POST-ODCV ENERGY COST CALCULATOR")
    print("=" * 60)

    # Load data
    print(f"\nLoading: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df):,} buildings")

    # Create backup
    create_backup()

    # Check for required columns
    required = ['energy_elec_kwh_post_odcv']
    missing = [col for col in required if col not in df.columns]
    if missing:
        print(f"\nERROR: Missing required columns: {missing}")
        print("Make sure to run 04_post_odcv_energy.py first!")
        return

    # Initialize counters
    stats = {
        'elec': 0,
        'gas': 0,
        'steam': 0,
        'fuel_oil': 0,
    }

    # Process each building
    print("\nCalculating post-ODCV energy costs...")

    for idx, row in df.iterrows():
        # Electricity
        elec = calculate_elec_costs_post_odcv(row)
        if elec['cost_elec_total_annual_post_odcv'] is not None:
            for col, val in elec.items():
                df.at[idx, col] = val
            stats['elec'] += 1

        # Gas
        gas_cost = calculate_gas_cost_post_odcv(row)
        if gas_cost is not None:
            df.at[idx, 'cost_gas_annual_post_odcv'] = gas_cost
            stats['gas'] += 1

        # Steam
        steam_cost = calculate_steam_cost_post_odcv(row)
        if steam_cost is not None:
            df.at[idx, 'cost_steam_annual_post_odcv'] = steam_cost
            stats['steam'] += 1

        # Fuel Oil
        fuel_oil_cost = calculate_fuel_oil_cost_post_odcv(row)
        if fuel_oil_cost is not None:
            df.at[idx, 'cost_fuel_oil_annual_post_odcv'] = fuel_oil_cost
            stats['fuel_oil'] += 1

    # Save results
    print(f"\nSaving to: {INPUT_FILE}")
    df.to_csv(INPUT_FILE, index=False)

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Electricity costs (post-ODCV): {stats['elec']:,}")
    print(f"  Gas costs (post-ODCV):         {stats['gas']:,}")
    print(f"  Steam costs (post-ODCV):       {stats['steam']:,}")
    print(f"  Fuel oil costs (post-ODCV):    {stats['fuel_oil']:,}")

    # Show sample savings
    sample = df[
        (df['cost_elec_total_annual'].notna()) &
        (df['cost_elec_total_annual_post_odcv'].notna()) &
        (df['odcv_hvac_savings_pct'].notna()) &
        (df['odcv_hvac_savings_pct'] > 0)
    ].head(1)

    if len(sample) > 0:
        row = sample.iloc[0]
        curr = row['cost_elec_total_annual']
        post = row['cost_elec_total_annual_post_odcv']
        savings = curr - post
        pct = savings / curr * 100
        print(f"\n  Sample building (electricity):")
        print(f"    Current:   ${curr:,.0f}")
        print(f"    Post-ODCV: ${post:,.0f}")
        print(f"    Savings:   ${savings:,.0f} ({pct:.1f}%)")

    print("\nDone!")


if __name__ == '__main__':
    main()
