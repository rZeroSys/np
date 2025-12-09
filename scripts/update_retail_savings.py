#!/usr/bin/env python3
"""
Update Retail Savings by 25%
============================
Increases odcv_savings_pct by 25% (multiplicative) for all retail building types,
then recalculates all downstream dependent columns.

Building types affected:
- Retail Store
- Strip Mall
- Enclosed Mall
- Outlet Mall
"""

import csv
import os
import shutil
from datetime import datetime

# =============================================================================
# CONFIGURATION
# =============================================================================

FILES_TO_PROCESS = [
    '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/buildings_tab_data.csv',
    '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv',
]

RETAIL_TYPES = ['Retail Store', 'Strip Mall', 'Enclosed Mall', 'Outlet Mall']

INCREASE_FACTOR = 1.25  # 25% increase

# Emission factors by city (tCO2e per kBtu) - from methodology docs
EMISSION_FACTORS = {
    'New York': {'elec': 0.0000847, 'gas': 0.00005311, 'steam': 0.00004493},
    'Boston': {'elec': 0.0000717, 'gas': 0.00005311, 'steam': 0.00004493},
    'Cambridge': {'elec': 0.0000717, 'gas': 0.00005311, 'steam': 0.00004493},
    'Washington': {'elec': 0.0000794, 'gas': 0.00005311, 'steam': 0.00004493},
    'Denver': {'elec': 0.0001378, 'gas': 0.00005311, 'steam': 0.00004493},
    'Seattle': {'elec': 0.0000029, 'gas': 0.000053, 'steam': 0.000081},
    'St. Louis': {'elec': 0.0001649, 'gas': 0.00005311, 'steam': 0.00004493},
    'default': {'elec': 0.0000922, 'gas': 0.00005311, 'steam': 0.00004493},
}

# BPS parameters by city
BPS_LAWS = {
    'New York': {'type': 'emission', 'fine_rate': 268, 'cap': 0.00758, 'min_sqft': 25000},
    'Boston': {'type': 'emission', 'fine_rate': 234, 'cap': 0.0053, 'min_sqft': 20000},
    'Cambridge': {'type': 'emission', 'fine_rate': 234, 'cap': 0.0053, 'min_sqft': 25000},
    'Washington': {'type': 'energy_star', 'fine_rate': 10, 'max_fine': 7500000, 'min_sqft': 50000},
    'Denver': {'type': 'eui', 'fine_rate': 0.30, 'eui_target': 48.3, 'min_sqft': 25000},
    'Seattle': {'type': 'emission', 'fine_rate': 10, 'cap': 0.00081, 'min_sqft': 20000, 'cycle_years': 5},
    'St. Louis': {'type': 'eui', 'fine_rate': 500, 'eui_target': 65, 'min_sqft': 50000},
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def safe_float(val, default=0.0):
    """Convert value to float, return default if empty or invalid."""
    if val is None or val == '' or (isinstance(val, str) and val.strip() == ''):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def get_emission_factors(city):
    """Get emission factors for a city."""
    return EMISSION_FACTORS.get(city, EMISSION_FACTORS['default'])


def calc_emissions(elec, gas, steam, factors):
    """Calculate emissions from energy data."""
    return (elec * factors['elec'] + gas * factors['gas'] + steam * factors['steam'])


def calc_fine_avoidance(row, new_odcv_pct):
    """Calculate fine avoidance for BPS cities with new ODCV percentage."""
    city = row.get('city', '')
    if city not in BPS_LAWS:
        return 0.0

    params = BPS_LAWS[city]
    factors = get_emission_factors(city)

    sqft = safe_float(row.get('square_footage'))
    elec = safe_float(row.get('electricity_use_kbtu'))
    gas = safe_float(row.get('natural_gas_use_kbtu'))
    steam = safe_float(row.get('district_steam_use_kbtu'))
    site_eui = safe_float(row.get('site_eui'))

    elec_hvac = safe_float(row.get('pct_elec_hvac'))
    gas_hvac = safe_float(row.get('pct_gas_hvac'))
    steam_hvac = safe_float(row.get('pct_steam_hvac'))

    if sqft < params.get('min_sqft', 0):
        return 0.0

    if params['type'] == 'emission':
        # Calculate baseline and with-ODCV emissions
        baseline_emissions = calc_emissions(elec, gas, steam, factors)

        net_elec = elec * (1 - elec_hvac * new_odcv_pct) if elec > 0 else 0
        net_gas = gas * (1 - gas_hvac * new_odcv_pct) if gas > 0 else 0
        net_steam = steam * (1 - steam_hvac * new_odcv_pct) if steam > 0 else 0
        with_odcv_emissions = calc_emissions(net_elec, net_gas, net_steam, factors)

        cap = sqft * params['cap']
        baseline_overage = max(0, baseline_emissions - cap)
        with_odcv_overage = max(0, with_odcv_emissions - cap)

        if city == 'Seattle':
            # Seattle: binary - either over cap or not
            baseline_over = (baseline_emissions / sqft) > params['cap']
            with_odcv_over = (with_odcv_emissions / sqft) > params['cap']
            if baseline_over and not with_odcv_over:
                return sqft * params['fine_rate'] / params['cycle_years']
            return 0.0
        else:
            return (baseline_overage - with_odcv_overage) * params['fine_rate']

    elif params['type'] == 'eui':
        target_eui = params['eui_target']

        # Calculate energy reduction
        elec_red = elec * elec_hvac * new_odcv_pct if elec > 0 else 0
        gas_red = gas * gas_hvac * new_odcv_pct if gas > 0 else 0
        steam_red = steam * steam_hvac * new_odcv_pct if steam > 0 else 0
        energy_reduction = elec_red + gas_red + steam_red

        eui_reduction = energy_reduction / sqft if sqft > 0 else 0
        with_odcv_eui = max(0, site_eui - eui_reduction)

        if city == 'St. Louis':
            # Binary compliance
            if site_eui > target_eui and with_odcv_eui <= target_eui:
                return params['fine_rate'] * 365
            return 0.0
        else:  # Denver
            baseline_overage = max(0, site_eui - target_eui) * sqft
            with_odcv_overage = max(0, with_odcv_eui - target_eui) * sqft
            return (baseline_overage - with_odcv_overage) * params['fine_rate']

    elif params['type'] == 'energy_star':
        # DC BEPS - simplified calculation
        energy_reduction_pct = new_odcv_pct * elec_hvac
        fine_avoidance = sqft * params['fine_rate'] * energy_reduction_pct * 0.3
        return min(fine_avoidance, params['max_fine'])

    return 0.0


def calc_carbon_reduction(row, new_odcv_pct):
    """Calculate carbon emissions reduction with new ODCV percentage."""
    city = row.get('city', '')
    factors = get_emission_factors(city)

    elec = safe_float(row.get('electricity_use_kbtu'))
    gas = safe_float(row.get('natural_gas_use_kbtu'))
    steam = safe_float(row.get('district_steam_use_kbtu'))

    elec_hvac = safe_float(row.get('pct_elec_hvac'))
    gas_hvac = safe_float(row.get('pct_gas_hvac'))
    steam_hvac = safe_float(row.get('pct_steam_hvac'))

    # Energy reductions
    elec_red = elec * elec_hvac * new_odcv_pct if elec > 0 else 0
    gas_red = gas * gas_hvac * new_odcv_pct if gas > 0 else 0
    steam_red = steam * steam_hvac * new_odcv_pct if steam > 0 else 0

    # Carbon reduction
    return (elec_red * factors['elec'] + gas_red * factors['gas'] + steam_red * factors['steam'])


def process_row(row):
    """Process a single retail row - update all savings columns."""
    # Step 1: Increase ODCV savings by 25%
    old_odcv = safe_float(row.get('odcv_savings_pct'))
    new_odcv = old_odcv * INCREASE_FACTOR
    row['odcv_savings_pct'] = f"{new_odcv:.6f}"

    # Step 2: Recalculate dollar savings
    total_hvac_cost = safe_float(row.get('total_hvac_energy_cost'))
    new_dollar_savings = total_hvac_cost * new_odcv
    row['odcv_dollar_savings'] = f"{new_dollar_savings:.2f}"

    # Step 3: Recalculate carbon reduction
    new_carbon_reduction = calc_carbon_reduction(row, new_odcv)
    row['carbon_emissions_reduction_yr1'] = f"{new_carbon_reduction:.6f}"

    # Step 4: Recalculate fine avoidance
    new_fine_avoidance = calc_fine_avoidance(row, new_odcv)
    row['fine_avoidance_yr1'] = f"{new_fine_avoidance:.2f}"

    # Step 5: Recalculate total annual OpEx avoidance
    new_opex_avoidance = new_dollar_savings + new_fine_avoidance
    row['total_annual_opex_avoidance'] = f"{new_opex_avoidance:.2f}"

    # Step 6: Recalculate valuation impact
    cap_rate = safe_float(row.get('cap_rate'))
    if cap_rate > 0:
        new_valuation_impact = new_opex_avoidance / (cap_rate / 100)
        row['odcv_valuation_impact_usd'] = f"{new_valuation_impact:.2f}"

        # Step 7: Recalculate post-ODCV valuation
        current_val = safe_float(row.get('current_valuation_usd'))
        if current_val > 0:
            row['post_odcv_valuation_usd'] = f"{current_val + new_valuation_impact:.2f}"

    # Step 8: Recalculate total building cost savings percentage
    annual_energy_cost = safe_float(row.get('annual_energy_cost'))
    if annual_energy_cost > 0:
        new_cost_savings_pct = new_dollar_savings / annual_energy_cost
        row['total_building_cost_savings_pct'] = f"{new_cost_savings_pct:.8f}"

    return row


def process_file(filepath):
    """Process a single CSV file."""
    print(f"\nProcessing: {filepath}")

    # Create backup
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = filepath.replace('.csv', f'_backup_{timestamp}.csv')
    shutil.copy2(filepath, backup_path)
    print(f"  Backup created: {backup_path}")

    # Read file
    with open(filepath, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    print(f"  Total rows: {len(rows)}")

    # Track statistics
    retail_count = 0
    stats_before = {'odcv_savings_pct': 0, 'odcv_dollar_savings': 0, 'fine_avoidance_yr1': 0}
    stats_after = {'odcv_savings_pct': 0, 'odcv_dollar_savings': 0, 'fine_avoidance_yr1': 0}

    # Process rows
    for row in rows:
        building_type = row.get('building_type', '')
        if building_type in RETAIL_TYPES:
            # Track before
            stats_before['odcv_savings_pct'] += safe_float(row.get('odcv_savings_pct'))
            stats_before['odcv_dollar_savings'] += safe_float(row.get('odcv_dollar_savings'))
            stats_before['fine_avoidance_yr1'] += safe_float(row.get('fine_avoidance_yr1'))

            # Process
            process_row(row)
            retail_count += 1

            # Track after
            stats_after['odcv_savings_pct'] += safe_float(row.get('odcv_savings_pct'))
            stats_after['odcv_dollar_savings'] += safe_float(row.get('odcv_dollar_savings'))
            stats_after['fine_avoidance_yr1'] += safe_float(row.get('fine_avoidance_yr1'))

    print(f"  Retail rows processed: {retail_count}")

    # Write updated file
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  File updated successfully")

    return {
        'file': os.path.basename(filepath),
        'retail_count': retail_count,
        'before': stats_before,
        'after': stats_after,
    }


def main():
    print("=" * 70)
    print("Retail Savings Update - 25% Increase")
    print("=" * 70)
    print(f"Increase factor: {INCREASE_FACTOR} (25% increase)")
    print(f"Building types: {', '.join(RETAIL_TYPES)}")

    all_stats = []

    for filepath in FILES_TO_PROCESS:
        if os.path.exists(filepath):
            stats = process_file(filepath)
            all_stats.append(stats)
        else:
            print(f"\nWARNING: File not found: {filepath}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for stats in all_stats:
        print(f"\n{stats['file']}:")
        print(f"  Retail buildings updated: {stats['retail_count']}")
        print(f"  ODCV Savings %:")
        print(f"    Before (sum): {stats['before']['odcv_savings_pct']:.4f}")
        print(f"    After (sum):  {stats['after']['odcv_savings_pct']:.4f}")
        print(f"    Change: +{(stats['after']['odcv_savings_pct'] / stats['before']['odcv_savings_pct'] - 1) * 100:.1f}%")
        print(f"  Dollar Savings:")
        print(f"    Before: ${stats['before']['odcv_dollar_savings']:,.2f}")
        print(f"    After:  ${stats['after']['odcv_dollar_savings']:,.2f}")
        print(f"    Change: +${stats['after']['odcv_dollar_savings'] - stats['before']['odcv_dollar_savings']:,.2f}")
        print(f"  Fine Avoidance:")
        print(f"    Before: ${stats['before']['fine_avoidance_yr1']:,.2f}")
        print(f"    After:  ${stats['after']['fine_avoidance_yr1']:,.2f}")

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == '__main__':
    main()
