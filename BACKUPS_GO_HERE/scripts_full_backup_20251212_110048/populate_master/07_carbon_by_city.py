#!/usr/bin/env python3
"""
City-Specific Carbon Emissions Calculator
==========================================
Calculates carbon_emissions_total_mt and odcv_carbon_reduction_yr1_mt
using city-specific emission factors.

Formulas:
  carbon_emissions_total_mt = (energy_elec_kbtu × elec_factor)
                            + (energy_gas_kbtu × gas_factor)
                            + (energy_steam_kbtu × steam_factor)
                            + (energy_fuel_oil_kbtu × fuel_oil_factor)

  carbon_emissions_post_odcv_mt = (energy_elec_kbtu_post_odcv × elec_factor)
                                + (energy_gas_kbtu_post_odcv × gas_factor)
                                + (energy_steam_kbtu_post_odcv × steam_factor)
                                + (energy_fuel_oil_kbtu_post_odcv × fuel_oil_factor)

  odcv_carbon_reduction_yr1_mt = carbon_emissions_total_mt - carbon_emissions_post_odcv_mt

Usage: python3 04_carbon_by_city.py
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

# City-specific emission factors (tCO2e per kBtu)
# SOURCE: docs/methodology/NATIONAL_BPS_METHODOLOGY.md (EPA eGRID 2023)
CITY_EMISSION_FACTORS = {
    'New York':      {'electricity': 0.0000847,  'gas': 0.00005311, 'steam': 0.00004493, 'fuel_oil': 0.00007315},
    'Boston':        {'electricity': 0.0000717,  'gas': 0.00005311, 'steam': 0.00004493, 'fuel_oil': 0.00007315},
    'Cambridge':     {'electricity': 0.0000717,  'gas': 0.00005311, 'steam': 0.00004493, 'fuel_oil': 0.00007315},
    'Washington':    {'electricity': 0.0000794,  'gas': 0.00005311, 'steam': 0.00004493, 'fuel_oil': 0.00007315},
    'Denver':        {'electricity': 0.0001378,  'gas': 0.00005311, 'steam': 0.00004493, 'fuel_oil': 0.00007315},
    'Seattle':       {'electricity': 0.0000029,  'gas': 0.000053,   'steam': 0.000081,   'fuel_oil': 0.00007315},
    'San Francisco': {'electricity': 0.0000570,  'gas': 0.00005311, 'steam': 0.00004493, 'fuel_oil': 0.00007315},
    'St. Louis':     {'electricity': 0.0001649,  'gas': 0.00005311, 'steam': 0.00004493, 'fuel_oil': 0.00007315},
    'Los Angeles':   {'electricity': 0.0000570,  'gas': 0.00005311, 'steam': 0.00004493, 'fuel_oil': 0.00007315},
    'Chicago':       {'electricity': 0.0001649,  'gas': 0.00005311, 'steam': 0.00004493, 'fuel_oil': 0.00007315},
    'Portland':      {'electricity': 0.0000595,  'gas': 0.00005311, 'steam': 0.00004493, 'fuel_oil': 0.00007315},
    'Atlanta':       {'electricity': 0.0000988,  'gas': 0.00005311, 'steam': 0.00004493, 'fuel_oil': 0.00007315},
    'Berkeley':      {'electricity': 0.0000570,  'gas': 0.00005311, 'steam': 0.00004493, 'fuel_oil': 0.00007315},  # PG&E grid (same as SF)
    'DEFAULT':       {'electricity': 0.0000922,  'gas': 0.00005311, 'steam': 0.00004493, 'fuel_oil': 0.00007315},
}

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


def get_emission_factors(city):
    """Get emission factors for a city, defaulting to US average."""
    if city and city in CITY_EMISSION_FACTORS:
        return CITY_EMISSION_FACTORS[city]
    return CITY_EMISSION_FACTORS['DEFAULT']


def calculate_carbon_emissions(row):
    """Calculate total carbon emissions in metric tons CO2e."""
    city = row.get('loc_city', '')
    factors = get_emission_factors(city)

    elec_kbtu = safe_float(row.get('energy_elec_kbtu'))
    gas_kbtu = safe_float(row.get('energy_gas_kbtu'))
    steam_kbtu = safe_float(row.get('energy_steam_kbtu'))
    fuel_oil_kbtu = safe_float(row.get('energy_fuel_oil_kbtu'))

    total_emissions = (
        elec_kbtu * factors['electricity'] +
        gas_kbtu * factors['gas'] +
        steam_kbtu * factors['steam'] +
        fuel_oil_kbtu * factors['fuel_oil']
    )

    return round(total_emissions, 4)


def calculate_odcv_carbon_reduction(row):
    """Calculate ODCV carbon reduction in metric tons CO2e."""
    city = row.get('loc_city', '')
    factors = get_emission_factors(city)

    elec_kbtu = safe_float(row.get('energy_elec_kbtu'))
    gas_kbtu = safe_float(row.get('energy_gas_kbtu'))
    steam_kbtu = safe_float(row.get('energy_steam_kbtu'))
    fuel_oil_kbtu = safe_float(row.get('energy_fuel_oil_kbtu'))

    pct_elec = safe_float(row.get('hvac_pct_elec'))
    pct_gas = safe_float(row.get('hvac_pct_gas'))
    pct_steam = safe_float(row.get('hvac_pct_steam'))
    pct_fuel_oil = safe_float(row.get('hvac_pct_fuel_oil'))

    odcv_pct = safe_float(row.get('odcv_hvac_savings_pct'))

    carbon_reduction = (
        elec_kbtu * pct_elec * odcv_pct * factors['electricity'] +
        gas_kbtu * pct_gas * odcv_pct * factors['gas'] +
        steam_kbtu * pct_steam * odcv_pct * factors['steam'] +
        fuel_oil_kbtu * pct_fuel_oil * odcv_pct * factors['fuel_oil']
    )

    return round(carbon_reduction, 4)


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("City-Specific Carbon Emissions Calculator")
    print("=" * 60)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Load data
    print(f"\nLoading: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df):,} buildings")

    # Calculate carbon emissions
    print("\nCalculating carbon_emissions_total_mt...")
    df['carbon_emissions_total_mt'] = df.apply(calculate_carbon_emissions, axis=1)

    # Calculate ODCV carbon reduction
    print("Calculating odcv_carbon_reduction_yr1_mt...")
    df['odcv_carbon_reduction_yr1_mt'] = df.apply(calculate_odcv_carbon_reduction, axis=1)

    # Summary stats
    print("\n" + "-" * 60)
    print("RESULTS SUMMARY")
    print("-" * 60)

    emissions_nonzero = (df['carbon_emissions_total_mt'] > 0).sum()
    reduction_nonzero = (df['odcv_carbon_reduction_yr1_mt'] > 0).sum()

    print(f"Buildings with emissions > 0: {emissions_nonzero:,} ({100*emissions_nonzero/len(df):.1f}%)")
    print(f"Buildings with reduction > 0: {reduction_nonzero:,} ({100*reduction_nonzero/len(df):.1f}%)")

    print(f"\nCarbon Emissions (tCO2e):")
    print(f"  Min:    {df['carbon_emissions_total_mt'].min():,.2f}")
    print(f"  Max:    {df['carbon_emissions_total_mt'].max():,.2f}")
    print(f"  Mean:   {df['carbon_emissions_total_mt'].mean():,.2f}")
    print(f"  Median: {df['carbon_emissions_total_mt'].median():,.2f}")
    print(f"  Total:  {df['carbon_emissions_total_mt'].sum():,.2f}")

    print(f"\nODCV Carbon Reduction (tCO2e):")
    print(f"  Min:    {df['odcv_carbon_reduction_yr1_mt'].min():,.2f}")
    print(f"  Max:    {df['odcv_carbon_reduction_yr1_mt'].max():,.2f}")
    print(f"  Mean:   {df['odcv_carbon_reduction_yr1_mt'].mean():,.2f}")
    print(f"  Median: {df['odcv_carbon_reduction_yr1_mt'].median():,.2f}")
    print(f"  Total:  {df['odcv_carbon_reduction_yr1_mt'].sum():,.2f}")

    # Stats by city
    print("\nBy City (top 10):")
    city_stats = df.groupby('loc_city').agg({
        'carbon_emissions_total_mt': 'sum',
        'odcv_carbon_reduction_yr1_mt': 'sum',
        'id_building': 'count'
    }).rename(columns={'id_building': 'count'})
    city_stats = city_stats.sort_values('carbon_emissions_total_mt', ascending=False).head(10)

    for city, stats in city_stats.iterrows():
        factors = get_emission_factors(city)
        print(f"  {city:20s} n={int(stats['count']):>5}  "
              f"emissions={stats['carbon_emissions_total_mt']:>12,.0f}  "
              f"reduction={stats['odcv_carbon_reduction_yr1_mt']:>10,.0f}  "
              f"elec_factor={factors['electricity']:.7f}")

    # Save
    print(f"\nSaving to: {INPUT_FILE}")
    df.to_csv(INPUT_FILE, index=False)
    print(f"Saved {len(df):,} buildings")

    print("\n" + "=" * 60)
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


if __name__ == '__main__':
    main()
