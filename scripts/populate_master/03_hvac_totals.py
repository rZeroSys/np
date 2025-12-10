#!/usr/bin/env python3
"""
HVAC Totals Calculator
======================
Calculates hvac_energy_total_kbtu and hvac_cost_total_annual for ALL buildings.

Formulas:
  hvac_energy_total_kbtu = (energy_elec_kbtu × hvac_pct_elec)
                         + (energy_gas_kbtu × hvac_pct_gas)
                         + (energy_steam_kbtu × hvac_pct_steam)
                         + (energy_fuel_oil_kbtu × hvac_pct_fuel_oil)

  hvac_cost_total_annual = (cost_elec_total_annual × hvac_pct_elec)
                         + (cost_gas_annual × hvac_pct_gas)
                         + (cost_steam_annual × hvac_pct_steam)
                         + (cost_fuel_oil_annual × hvac_pct_fuel_oil)

Usage: python3 calculate_hvac_totals.py
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


def calculate_hvac_energy(row):
    """Calculate total HVAC energy in kBtu."""
    elec_kbtu = safe_float(row.get('energy_elec_kbtu'))
    gas_kbtu = safe_float(row.get('energy_gas_kbtu'))
    steam_kbtu = safe_float(row.get('energy_steam_kbtu'))
    fuel_oil_kbtu = safe_float(row.get('energy_fuel_oil_kbtu'))

    pct_elec = safe_float(row.get('hvac_pct_elec'))
    pct_gas = safe_float(row.get('hvac_pct_gas'))
    pct_steam = safe_float(row.get('hvac_pct_steam'))
    pct_fuel_oil = safe_float(row.get('hvac_pct_fuel_oil'))

    hvac_energy = (
        elec_kbtu * pct_elec +
        gas_kbtu * pct_gas +
        steam_kbtu * pct_steam +
        fuel_oil_kbtu * pct_fuel_oil
    )

    return round(hvac_energy, 2)


def calculate_hvac_cost(row):
    """Calculate total HVAC cost in USD."""
    elec_cost = safe_float(row.get('cost_elec_total_annual'))
    gas_cost = safe_float(row.get('cost_gas_annual'))
    steam_cost = safe_float(row.get('cost_steam_annual'))
    fuel_oil_cost = safe_float(row.get('cost_fuel_oil_annual'))

    pct_elec = safe_float(row.get('hvac_pct_elec'))
    pct_gas = safe_float(row.get('hvac_pct_gas'))
    pct_steam = safe_float(row.get('hvac_pct_steam'))
    pct_fuel_oil = safe_float(row.get('hvac_pct_fuel_oil'))

    hvac_cost = (
        elec_cost * pct_elec +
        gas_cost * pct_gas +
        steam_cost * pct_steam +
        fuel_oil_cost * pct_fuel_oil
    )

    return round(hvac_cost, 2)


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("HVAC Totals Calculator")
    print("=" * 60)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Load data
    print(f"\nLoading: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df):,} buildings")

    # Calculate HVAC energy
    print("\nCalculating hvac_energy_total_kbtu...")
    df['hvac_energy_total_kbtu'] = df.apply(calculate_hvac_energy, axis=1)

    # Calculate HVAC cost
    print("Calculating hvac_cost_total_annual...")
    df['hvac_cost_total_annual'] = df.apply(calculate_hvac_cost, axis=1)

    # Summary stats
    print("\n" + "-" * 60)
    print("RESULTS SUMMARY")
    print("-" * 60)

    energy_nonzero = (df['hvac_energy_total_kbtu'] > 0).sum()
    cost_nonzero = (df['hvac_cost_total_annual'] > 0).sum()

    print(f"Buildings with HVAC energy > 0: {energy_nonzero:,} ({100*energy_nonzero/len(df):.1f}%)")
    print(f"Buildings with HVAC cost > 0:   {cost_nonzero:,} ({100*cost_nonzero/len(df):.1f}%)")

    print(f"\nHVAC Energy (kBtu):")
    print(f"  Min:    {df['hvac_energy_total_kbtu'].min():,.0f}")
    print(f"  Max:    {df['hvac_energy_total_kbtu'].max():,.0f}")
    print(f"  Mean:   {df['hvac_energy_total_kbtu'].mean():,.0f}")
    print(f"  Median: {df['hvac_energy_total_kbtu'].median():,.0f}")
    print(f"  Total:  {df['hvac_energy_total_kbtu'].sum():,.0f}")

    print(f"\nHVAC Cost (USD):")
    print(f"  Min:    ${df['hvac_cost_total_annual'].min():,.2f}")
    print(f"  Max:    ${df['hvac_cost_total_annual'].max():,.2f}")
    print(f"  Mean:   ${df['hvac_cost_total_annual'].mean():,.2f}")
    print(f"  Median: ${df['hvac_cost_total_annual'].median():,.2f}")
    print(f"  Total:  ${df['hvac_cost_total_annual'].sum():,.2f}")

    # Save
    print(f"\nSaving to: {INPUT_FILE}")
    df.to_csv(INPUT_FILE, index=False)
    print(f"Saved {len(df):,} buildings")

    print("\n" + "=" * 60)
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


if __name__ == '__main__':
    main()
