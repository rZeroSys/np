#!/usr/bin/env python3
"""
Energy Cost Calculator
======================
Calculates annual energy costs from usage data and utility rates.

Output columns:
- cost_elec_peak_kw: Peak demand in kW
- cost_elec_energy_annual: Annual electricity energy charges ($)
- cost_elec_demand_annual: Annual electricity demand charges ($)
- cost_elec_total_annual: Total annual electricity cost ($)
- cost_gas_annual: Annual natural gas cost ($)
- cost_steam_annual: Annual district steam cost ($)
- cost_fuel_oil_annual: Annual fuel oil cost ($)

Formulas:
  Electricity:
    peak_kw = energy_elec_kwh / (8760 × load_factor)
    energy_annual = energy_elec_kwh × rate_kwh × 1.10
    demand_annual = peak_kw × rate_demand_kw × 12 × 1.265
    total = energy_annual + demand_annual

  Gas:
    therms = energy_gas_kbtu / 100
    cost = therms × rate_therm × 1.10

  Steam:
    mlb = energy_steam_kbtu / 909
    cost = mlb × rate_mlb

  Fuel Oil:
    mmbtu = energy_fuel_oil_kbtu / 1000
    cost = mmbtu × rate_mmbtu × 1.10

Multipliers:
  1.10 = Taxes, fees, distribution charges
  1.265 = Demand charge adder (ratchet clauses, seasonal peaks)
  909 = kBtu per Mlb of steam

Usage: python3 00_energy_costs.py
"""

import pandas as pd
import numpy as np
import shutil
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import PORTFOLIO_DATA_PATH, BACKUP_DIR

# =============================================================================
# CONFIGURATION
# =============================================================================

INPUT_FILE = str(PORTFOLIO_DATA_PATH)
BACKUP_DIR = str(BACKUP_DIR)

# Conversion factors
KBTU_PER_THERM = 100
KBTU_PER_MLB_STEAM = 909
KBTU_PER_MMBTU = 1000
HOURS_PER_YEAR = 8760

# Cost multipliers
ENERGY_CHARGE_MULTIPLIER = 1.10      # Taxes, fees, distribution
DEMAND_CHARGE_MULTIPLIER = 1.265     # Ratchet clauses, seasonal peaks
MONTHS_PER_YEAR = 12

# Default load factor if not specified
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


def calculate_electricity_costs(row):
    """
    Calculate electricity costs from usage and rates.

    Returns dict with:
    - cost_elec_peak_kw
    - cost_elec_energy_annual
    - cost_elec_demand_annual
    - cost_elec_total_annual
    """
    kwh = safe_float(row.get('energy_elec_kwh'))
    rate_kwh = safe_float(row.get('cost_elec_rate_kwh'))
    rate_demand = safe_float(row.get('cost_elec_rate_demand_kw'))
    load_factor = safe_float(row.get('cost_elec_load_factor'), DEFAULT_LOAD_FACTOR)

    result = {
        'cost_elec_peak_kw': None,
        'cost_elec_energy_annual': None,
        'cost_elec_demand_annual': None,
        'cost_elec_total_annual': None,
    }

    # Need at minimum kwh and rate to calculate
    if kwh is None or kwh <= 0 or rate_kwh is None:
        return result

    # Calculate peak demand
    peak_kw = kwh / (HOURS_PER_YEAR * load_factor)
    result['cost_elec_peak_kw'] = round(peak_kw, 2)

    # Energy charges
    energy_annual = kwh * rate_kwh * ENERGY_CHARGE_MULTIPLIER
    result['cost_elec_energy_annual'] = round(energy_annual, 2)

    # Demand charges (only if rate provided)
    if rate_demand is not None and rate_demand > 0:
        demand_annual = peak_kw * rate_demand * MONTHS_PER_YEAR * DEMAND_CHARGE_MULTIPLIER
        result['cost_elec_demand_annual'] = round(demand_annual, 2)
        result['cost_elec_total_annual'] = round(energy_annual + demand_annual, 2)
    else:
        result['cost_elec_demand_annual'] = 0.0
        result['cost_elec_total_annual'] = round(energy_annual, 2)

    return result


def calculate_gas_cost(row):
    """
    Calculate natural gas cost from usage and rate.

    Formula: cost = (kbtu / 100) × rate_therm × 1.10
    """
    kbtu = safe_float(row.get('energy_gas_kbtu'))
    rate = safe_float(row.get('cost_gas_rate_therm'))

    if kbtu is None or kbtu <= 0 or rate is None:
        return None

    therms = kbtu / KBTU_PER_THERM
    cost = therms * rate * ENERGY_CHARGE_MULTIPLIER
    return round(cost, 2)


def calculate_steam_cost(row):
    """
    Calculate district steam cost from usage and rate.

    Formula: cost = (kbtu / 909) × rate_mlb
    Note: No 1.10 multiplier for steam
    """
    kbtu = safe_float(row.get('energy_steam_kbtu'))
    rate = safe_float(row.get('cost_steam_rate_mlb'))

    if kbtu is None or kbtu <= 0 or rate is None:
        return None

    mlb = kbtu / KBTU_PER_MLB_STEAM
    cost = mlb * rate
    return round(cost, 2)


def calculate_fuel_oil_cost(row):
    """
    Calculate fuel oil cost from usage and rate.

    Formula: cost = (kbtu / 1000) × rate_mmbtu × 1.10
    """
    kbtu = safe_float(row.get('energy_fuel_oil_kbtu'))
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
    print("ENERGY COST CALCULATOR")
    print("=" * 60)

    # Load data
    print(f"\nLoading: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df):,} buildings")

    # Create backup
    create_backup()

    # Initialize counters
    stats = {
        'elec_calculated': 0,
        'gas_calculated': 0,
        'steam_calculated': 0,
        'fuel_oil_calculated': 0,
    }

    # Process each building
    print("\nCalculating energy costs...")

    for idx, row in df.iterrows():
        # Electricity
        elec = calculate_electricity_costs(row)
        if elec['cost_elec_total_annual'] is not None:
            df.at[idx, 'cost_elec_peak_kw'] = elec['cost_elec_peak_kw']
            df.at[idx, 'cost_elec_energy_annual'] = elec['cost_elec_energy_annual']
            df.at[idx, 'cost_elec_demand_annual'] = elec['cost_elec_demand_annual']
            df.at[idx, 'cost_elec_total_annual'] = elec['cost_elec_total_annual']
            stats['elec_calculated'] += 1

        # Gas
        gas_cost = calculate_gas_cost(row)
        if gas_cost is not None:
            df.at[idx, 'cost_gas_annual'] = gas_cost
            stats['gas_calculated'] += 1

        # Steam
        steam_cost = calculate_steam_cost(row)
        if steam_cost is not None:
            df.at[idx, 'cost_steam_annual'] = steam_cost
            stats['steam_calculated'] += 1

        # Fuel Oil
        fuel_oil_cost = calculate_fuel_oil_cost(row)
        if fuel_oil_cost is not None:
            df.at[idx, 'cost_fuel_oil_annual'] = fuel_oil_cost
            stats['fuel_oil_calculated'] += 1

    # Save results
    print(f"\nSaving to: {INPUT_FILE}")
    df.to_csv(INPUT_FILE, index=False)

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Electricity costs calculated: {stats['elec_calculated']:,}")
    print(f"  Gas costs calculated:         {stats['gas_calculated']:,}")
    print(f"  Steam costs calculated:       {stats['steam_calculated']:,}")
    print(f"  Fuel oil costs calculated:    {stats['fuel_oil_calculated']:,}")
    print("\nDone!")


if __name__ == '__main__':
    main()
