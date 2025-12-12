#!/usr/bin/env python3
"""
ODCV Valuation Impact Calculator
=================================
Calculates the valuation impact of ODCV (Occupancy-Driven Control Ventilation)
energy savings for commercial buildings.

Methodology (Round 3 - includes fine avoidance):
1. Calculate annual HVAC cost for each fuel type:
   - Electricity HVAC cost = total_annual_electricity_cost × pct_elec_hvac
   - Gas HVAC cost = annual_gas_cost × pct_gas_hvac
   - Steam HVAC cost = annual_steam_cost × pct_steam_hvac
   - Fuel oil HVAC cost = annual_fuel_oil_cost × pct_fuel_oil_hvac

2. Calculate total annual HVAC cost:
   total_hvac_cost = sum of all fuel HVAC costs

3. Calculate annual ODCV dollar savings:
   odcv_dollar_savings = total_hvac_cost × odcv_savings_pct

4. Calculate total annual OpEx avoidance (utility + regulatory):
   total_annual_opex_avoidance = odcv_dollar_savings + fine_avoidance_yr1

5. Calculate valuation impact using income capitalization approach:
   valuation_impact = total_annual_opex_avoidance / cap_rate

6. Calculate current and post-ODCV valuations:
   - Current valuation estimated from energy costs and cap rate
   - Post-ODCV valuation = current_valuation + valuation_impact

Output columns:
- current_valuation_usd: Estimated current property value
- post_odcv_valuation_usd: Estimated value after ODCV implementation
- odcv_valuation_impact_usd: Dollar increase in property value from ODCV
- total_annual_opex_avoidance: ODCV savings + fine avoidance
"""

import csv
import os
import shutil
from pathlib import Path
from datetime import datetime

# =============================================================================
# CONFIGURATION
# =============================================================================

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import PORTFOLIO_DATA_PATH, BACKUP_DIR as CONFIG_BACKUP_DIR

INPUT_FILES = [str(PORTFOLIO_DATA_PATH)]
BACKUP_DIR = str(CONFIG_BACKUP_DIR)

def create_backup(input_file):
    """Create timestamped backup before any changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(input_file, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path

# Commercial building types (cap rate valuation applies to these)
COMMERCIAL_TYPES = [
    'Office', 'Medical Office', 'Mixed Use', 'Retail Store', 'Strip Mall',
    'Hotel', 'Supermarket/Grocery', 'Enclosed Mall', 'Outlet Mall', 'Restaurant/Bar',
    'Gym', 'Vehicle Dealership', 'Wholesale Club', 'Bank Branch', 'Venue', 'Theater',
    'Sports/Gaming Center'
]

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


def calculate_valuation_metrics(row):
    """
    Calculate ODCV dollar savings for ALL buildings.
    Calculate valuation impact ONLY for commercial buildings.

    Returns tuple: (current_valuation, post_odcv_valuation, valuation_impact, total_opex_avoidance, odcv_dollar_savings)
    """
    building_type = row.get('bldg_type', '')

    # Get HVAC costs by fuel type (for ALL buildings)
    elec_cost = safe_float(row.get('cost_elec_total_annual'))
    gas_cost = safe_float(row.get('cost_gas_annual'))
    steam_cost = safe_float(row.get('cost_steam_annual'))
    fuel_oil_cost = safe_float(row.get('cost_fuel_oil_annual'))

    # Get HVAC percentages
    pct_elec_hvac = safe_float(row.get('hvac_pct_elec'))
    pct_gas_hvac = safe_float(row.get('hvac_pct_gas'))
    pct_steam_hvac = safe_float(row.get('hvac_pct_steam'))
    pct_fuel_oil_hvac = safe_float(row.get('hvac_pct_fuel_oil'))

    # Calculate HVAC costs
    elec_hvac_cost = elec_cost * pct_elec_hvac
    gas_hvac_cost = gas_cost * pct_gas_hvac
    steam_hvac_cost = steam_cost * pct_steam_hvac
    fuel_oil_hvac_cost = fuel_oil_cost * pct_fuel_oil_hvac

    total_hvac_cost = elec_hvac_cost + gas_hvac_cost + steam_hvac_cost + fuel_oil_hvac_cost

    # Get ODCV savings percentage
    odcv_pct = safe_float(row.get('odcv_hvac_savings_pct'))

    # Calculate annual ODCV dollar savings (utility savings) - FOR ALL BUILDINGS
    odcv_dollar_savings = total_hvac_cost * odcv_pct

    # Get fine avoidance (all buildings can have this)
    fine_avoidance = safe_float(row.get('bps_fine_avoided_yr1_usd'))

    # Calculate total annual OpEx avoidance for ALL buildings
    total_opex_avoidance = odcv_dollar_savings + fine_avoidance

    # Non-commercial buildings: dollar savings + opex YES, valuation NO
    if building_type not in COMMERCIAL_TYPES:
        return ('', '', '', f'{total_opex_avoidance:.2f}', f'{odcv_dollar_savings:.2f}')

    # Get cap rate (commercial only need this for valuation)
    cap_rate = safe_float(row.get('val_cap_rate_pct'))

    # Skip valuation if missing cap rate, but still return opex
    if cap_rate == 0:
        return ('', '', '', f'{total_opex_avoidance:.2f}', f'{odcv_dollar_savings:.2f}')

    # Calculate valuation impact (total_opex_avoidance already calculated above)
    valuation_impact = total_opex_avoidance / cap_rate

    # Estimate current valuation from total energy costs
    total_energy_cost = elec_cost + gas_cost + steam_cost + fuel_oil_cost
    estimated_gross_income = total_energy_cost / 0.12
    estimated_noi = estimated_gross_income * 0.60
    current_valuation = estimated_noi / cap_rate

    # Post-ODCV valuation
    post_odcv_valuation = current_valuation + valuation_impact

    return (
        f'{current_valuation:.2f}',
        f'{post_odcv_valuation:.2f}',
        f'{valuation_impact:.2f}',
        f'{total_opex_avoidance:.2f}',
        f'{odcv_dollar_savings:.2f}'
    )


# =============================================================================
# MAIN
# =============================================================================

def process_file(input_file):
    """Process a single CSV file."""
    print(f"\n{'=' * 70}")
    print(f"Processing: {input_file}")
    print("=" * 70)

    # Load data
    with open(input_file, 'r') as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames)
        rows = list(reader)

    print(f"Loaded {len(rows):,} buildings")

    # Add new columns
    new_cols = ['val_current_usd', 'val_post_odcv_usd', 'val_odcv_impact_usd',
                'savings_opex_avoided_annual_usd', 'odcv_hvac_savings_annual_usd']
    for col in new_cols:
        if col not in headers:
            headers.append(col)

    # Calculate valuation metrics for each building
    print("\nCalculating valuation impact (Round 3 methodology: includes fine_avoidance_yr1)...")

    commercial_count = 0
    calculated_count = 0
    total_impact = 0.0
    total_opex = 0.0

    for row in rows:
        current_val, post_val, impact, opex_avoidance, dollar_savings = calculate_valuation_metrics(row)
        row['val_current_usd'] = current_val
        row['val_post_odcv_usd'] = post_val
        row['val_odcv_impact_usd'] = impact
        row['savings_opex_avoided_annual_usd'] = opex_avoidance
        row['odcv_hvac_savings_annual_usd'] = dollar_savings

        if row.get('bldg_type') in COMMERCIAL_TYPES:
            commercial_count += 1
            if impact and impact != '':
                calculated_count += 1
                total_impact += safe_float(impact)
                total_opex += safe_float(opex_avoidance)

    # Write output
    print(f"\nSaving to: {input_file}")
    with open(input_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    # Summary statistics
    print("\n" + "-" * 70)
    print("RESULTS SUMMARY (Round 3 Methodology)")
    print("-" * 70)
    print(f"Commercial buildings: {commercial_count:,}")
    print(f"Valuations calculated: {calculated_count:,}")
    if calculated_count > 0:
        print(f"Total annual OpEx avoidance (utility + fine): ${total_opex:,.2f}")
        print(f"Total ODCV valuation impact: ${total_impact:,.2f}")
        print(f"Average impact per building: ${total_impact/calculated_count:,.2f}")

    # By building type
    print("\nBy Building Type:")
    type_impacts = {}
    for row in rows:
        bt = row.get('bldg_type', '')
        if bt in COMMERCIAL_TYPES:
            if bt not in type_impacts:
                type_impacts[bt] = {'count': 0, 'total_impact': 0.0}
            type_impacts[bt]['count'] += 1
            type_impacts[bt]['total_impact'] += safe_float(row.get('val_odcv_impact_usd'))

    for bt in sorted(type_impacts.keys(), key=lambda x: type_impacts[x]['total_impact'], reverse=True):
        stats = type_impacts[bt]
        avg = stats['total_impact'] / stats['count'] if stats['count'] > 0 else 0
        print(f"  {bt:<25} n={stats['count']:>5}  total=${stats['total_impact']:>15,.0f}  avg=${avg:>12,.0f}")


def main():
    print("=" * 70)
    print("ODCV Valuation Impact Calculator")
    print("=" * 70)

    for input_file in INPUT_FILES:
        process_file(input_file)

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == '__main__':
    main()
