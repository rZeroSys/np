#!/usr/bin/env python3
"""
Update NYC buildings in portfolio_data.csv and buildings_tab_data.csv
using data from the NYC folder (/Users/forrestmiller/Desktop/New/data/).

This script maps the 1119 NYC buildings from 10_year_savings_by_building.csv
to the nationwide prospector format.

Usage: python3 update_nyc_buildings.py
"""

import pandas as pd
import numpy as np
import re
from datetime import datetime

# ============================================================================
# FILE PATHS
# ============================================================================

# NYC source data
NYC_DATA_PATH = '/Users/forrestmiller/Desktop/New/data/'
NYC_BUILDINGS = NYC_DATA_PATH + 'buildings_BIG_with_emails_complete_verified.csv'
NYC_10YR_SAVINGS = NYC_DATA_PATH + '10_year_savings_by_building.csv'
NYC_ENERGY = NYC_DATA_PATH + 'energy_BIG.csv'
NYC_ADDRESSES = NYC_DATA_PATH + 'all_building_addresses.csv'
NYC_BUILDING_LINKS = NYC_DATA_PATH + 'TOP_250_BUILDING_LINKS_VALID.csv'
NYC_SCORING = NYC_DATA_PATH + 'odcv_scoring_CORRECTED.csv'
NYC_HVAC = NYC_DATA_PATH + 'hvac_office_energy_BIG.csv'
NYC_OFFICE = NYC_DATA_PATH + 'office_energy_BIG.csv'
NYC_VALUATION = NYC_DATA_PATH + 'odcv_noi_value_impact_analysis.csv'

# Nationwide prospector target files (TEST COPIES)
PROSPECTOR_PATH = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/'
PORTFOLIO_DATA = PROSPECTOR_PATH + 'portfolio_data_TEST.csv'
BUILDINGS_TAB_DATA = PROSPECTOR_PATH + 'buildings_tab_data_TEST.csv'

# Backup paths
BACKUP_SUFFIX = datetime.now().strftime('%Y%m%d_%H%M%S')

# ============================================================================
# CONSTANTS FOR NYC
# ============================================================================

NYC_DEFAULTS = {
    'reporting_year': 2023.0,
    'building_type': 'Office',
    'vertical': 'Commercial',
    'state': 'NY',
    'city': 'New York',
    'utility_name_used': 'Consolidated Edison Co-NY Inc',
    'energy_rate_per_kwh': 0.292615,
    'gas_rate_per_therm': 1.0604,
    'steam_rate_per_mlb': None,  # Will be calculated
    'energy_star_climate_zone': 'North-Central',
    'load_factor_used': 0.45,
    'cost_calculation_notes': 'Demand: NREL',
    'vacancy_rate': 0.13,
    'utilization_rate': 0.55,
    'cap_rate': 0.07,
    'market_rent_per_sqft': 68.0,
    'operating_expense_ratio': 0.5,
    'method': 'cbecs_adjusted',
    'carbon_local_law': 'NYC LL97',
    'benchmark_building_type': 'Office',
    'eui_benchmark': 52.9,
    'radio_button_building_type': 'Office',
}


def load_nyc_data():
    """Load all NYC source data files."""
    print("Loading NYC source data...")

    buildings = pd.read_csv(NYC_BUILDINGS, encoding='utf-8')
    print(f"  - buildings_BIG: {len(buildings)} rows")

    ten_yr_savings = pd.read_csv(NYC_10YR_SAVINGS, encoding='utf-8')
    print(f"  - 10_year_savings: {len(ten_yr_savings)} rows")

    energy = pd.read_csv(NYC_ENERGY, encoding='utf-8')
    print(f"  - energy_BIG: {len(energy)} rows")

    addresses = pd.read_csv(NYC_ADDRESSES, encoding='utf-8')
    print(f"  - all_building_addresses: {len(addresses)} rows")

    building_links = pd.read_csv(NYC_BUILDING_LINKS, encoding='utf-8')
    print(f"  - TOP_250_BUILDING_LINKS: {len(building_links)} rows")

    scoring = pd.read_csv(NYC_SCORING, encoding='utf-8')
    print(f"  - odcv_scoring: {len(scoring)} rows")

    hvac = pd.read_csv(NYC_HVAC, encoding='utf-8')
    print(f"  - hvac_office_energy: {len(hvac)} rows")

    office = pd.read_csv(NYC_OFFICE, encoding='utf-8')
    print(f"  - office_energy: {len(office)} rows")

    valuation = pd.read_csv(NYC_VALUATION, encoding='utf-8')
    print(f"  - valuation_data: {len(valuation)} rows")

    return {
        'buildings': buildings,
        'ten_yr_savings': ten_yr_savings,
        'energy': energy,
        'addresses': addresses,
        'building_links': building_links,
        'scoring': scoring,
        'hvac': hvac,
        'office': office,
        'valuation': valuation,
    }


def extract_zip_code(address):
    """Extract zip code from address string."""
    if pd.isna(address):
        return None
    match = re.search(r'\b(\d{5})(?:-\d{4})?\b', str(address))
    return match.group(1) if match else None


def safe_float(value, default=None):
    """Safely convert to float."""
    if pd.isna(value):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_val(df, bbl, column, default=None):
    """Safely get value from dataframe by BBL."""
    if df.empty or column not in df.columns:
        return default
    filtered = df[df['bbl'] == bbl]
    if filtered.empty:
        return default
    val = filtered[column].iloc[0]
    if pd.isna(val):
        return default
    return val


def calculate_hvac_percentages(hvac_df, bbl):
    """Calculate HVAC percentages from monthly data."""
    hvac_row = hvac_df[hvac_df['bbl'] == bbl]
    if hvac_row.empty:
        return 0.45, 0.95, None, None  # defaults

    # Get annual HVAC percentages if available
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    elec_hvac_pcts = []
    for m in months:
        col = f'Elec_HVAC_{m}_2023_Pct'
        if col in hvac_row.columns:
            val = safe_float(hvac_row[col].iloc[0])
            if val is not None:
                elec_hvac_pcts.append(val)

    pct_elec_hvac = np.mean(elec_hvac_pcts) if elec_hvac_pcts else 0.45

    # Gas HVAC is typically high (heating)
    pct_gas_hvac = 0.95  # Default - most gas is for heating

    return pct_elec_hvac, pct_gas_hvac, None, None


def build_nyc_row(bbl, data):
    """Build a portfolio row for a single NYC building."""
    buildings = data['buildings']
    ten_yr = data['ten_yr_savings']
    energy = data['energy']
    addresses = data['addresses']
    links = data['building_links']
    scoring = data['scoring']
    hvac = data['hvac']
    office = data['office']
    valuation = data['valuation']

    # Get building basic info
    bldg = buildings[buildings['bbl'] == bbl]
    if bldg.empty:
        return None

    bldg = bldg.iloc[0]

    # Get 10-year savings data
    savings = ten_yr[ten_yr['bbl'] == bbl]
    if savings.empty:
        return None
    savings = savings.iloc[0]

    # Get energy data
    energy_row = energy[energy['bbl'] == bbl]

    # Get address data
    addr_row = addresses[addresses['bbl'] == bbl]

    # Get building link/url
    link_row = links[links['bbl'] == bbl]

    # Get scoring data
    score_row = scoring[scoring['bbl'] == bbl]

    # Calculate values
    building_id = f"NYC_{bbl}"
    address = bldg.get('address', '')

    # Square footage
    square_footage = safe_float(bldg.get('office_sqft')) or safe_float(bldg.get('total_gross_floor_area'))

    # Energy values from 10_year_savings
    electricity_use_kbtu = safe_float(savings.get('total_elec_kBtu'), 0)
    natural_gas_use_kbtu = safe_float(savings.get('total_gas_kBtu'), 0)
    district_steam_use_kbtu = safe_float(savings.get('total_steam_kBtu'), 0)
    total_site_energy_kbtu = electricity_use_kbtu + natural_gas_use_kbtu + district_steam_use_kbtu

    # Site EUI
    site_eui = total_site_energy_kbtu / square_footage if square_footage and square_footage > 0 else None

    # GHG emissions
    total_ghg_emissions = safe_float(savings.get('total_carbon_emissions_2024_tCO2e'))

    # Building URL from TOP_250
    building_url = None
    if not link_row.empty:
        building_url = link_row.iloc[0].get('url')

    # Property name from all_building_addresses
    property_name = None
    if not addr_row.empty:
        property_name = addr_row.iloc[0].get('primary_building_name')

    # Electricity calculations
    electricity_kwh = electricity_use_kbtu / 3.412 if electricity_use_kbtu else None
    energy_rate = NYC_DEFAULTS['energy_rate_per_kwh']
    annual_energy_cost = electricity_kwh * energy_rate if electricity_kwh else None

    # Peak demand calculations (using load factor)
    load_factor = NYC_DEFAULTS['load_factor_used']
    estimated_peak_kw = None
    if electricity_kwh:
        # Peak kW = kWh / (hours * load_factor), assuming 8760 hours/year
        estimated_peak_kw = electricity_kwh / (8760 * load_factor)

    # Demand rate (varies by building size, using average)
    demand_rate_per_kw = 59.06  # Average ConEd demand rate
    if square_footage and square_footage > 100000:
        demand_rate_per_kw = 68.63  # Larger buildings

    annual_demand_cost = estimated_peak_kw * demand_rate_per_kw * 12 if estimated_peak_kw else None
    total_annual_electricity_cost = (annual_energy_cost or 0) + (annual_demand_cost or 0)

    # Gas cost
    gas_rate = NYC_DEFAULTS['gas_rate_per_therm']
    natural_gas_therms = natural_gas_use_kbtu / 100 if natural_gas_use_kbtu else 0  # 1 therm = 100 kBtu
    annual_gas_cost = natural_gas_therms * gas_rate if natural_gas_therms else None

    # HVAC percentages
    pct_elec_hvac, pct_gas_hvac, pct_steam_hvac, pct_fuel_oil_hvac = calculate_hvac_percentages(hvac, bbl)

    # ODCV savings
    utility_savings_annual = safe_float(savings.get('utility_savings_annual'), 0)

    # ODCV savings percentage
    odcv_savings_pct = None
    if not score_row.empty:
        # Try to calculate from scoring data
        pass

    # Calculate based on HVAC costs
    total_hvac_energy_kbtu = (electricity_use_kbtu * pct_elec_hvac) + (natural_gas_use_kbtu * pct_gas_hvac) + (district_steam_use_kbtu * 0.5 if district_steam_use_kbtu else 0)

    total_hvac_energy_cost = None
    if total_annual_electricity_cost and annual_gas_cost:
        total_hvac_energy_cost = (total_annual_electricity_cost * pct_elec_hvac) + (annual_gas_cost * pct_gas_hvac)

    if total_hvac_energy_cost and total_hvac_energy_cost > 0:
        odcv_savings_pct = utility_savings_annual / total_hvac_energy_cost
        odcv_savings_pct = min(odcv_savings_pct, 0.35)  # Cap at 35%

    # Valuation impact - DIRECT FROM CSV (exactly like building.py)
    val_row = valuation[valuation['bbl'] == bbl]
    odcv_valuation_impact = None
    cap_rate = None

    if not val_row.empty:
        odcv_valuation_impact = safe_float(val_row['odcv_value_increase'].iloc[0])
        cap_rate = safe_float(val_row['cap_rate_median'].iloc[0])

    # Carbon emissions reduction - EXACTLY like building.py lines 542-566, 826
    carbon_emissions_reduction = None
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    elec_cost = []
    gas_cost = []
    steam_cost = []

    if not energy_row.empty:
        for m in months:
            # Elec cost = HVAC + NonHVAC (exactly like building.py line 544)
            hvac_col = f'Elec_HVAC_{m}_2023_Cost_USD'
            nonhvac_col = f'Elec_NonHVAC_{m}_2023_Cost_USD'
            hvac_val = safe_float(energy_row[hvac_col].iloc[0], 0) if hvac_col in energy_row.columns else 0
            nonhvac_val = safe_float(energy_row[nonhvac_col].iloc[0], 0) if nonhvac_col in energy_row.columns else 0
            elec_cost.append(hvac_val + nonhvac_val)

            # Gas cost (exactly like building.py line 545)
            gas_col = f'Gas_{m}_2023_Cost_USD'
            gas_val = safe_float(energy_row[gas_col].iloc[0], 0) if gas_col in energy_row.columns else 0
            gas_cost.append(gas_val)

            # Steam cost (exactly like building.py lines 547-551)
            steam_usage_col = f'District_Steam_{m}_2023_kBtu'
            steam_cost_col = f'Steam_{m}_2023_Cost_USD'
            steam_usage = safe_float(energy_row[steam_usage_col].iloc[0], 0) if steam_usage_col in energy_row.columns else 0
            if steam_usage > 0:
                steam_val = safe_float(energy_row[steam_cost_col].iloc[0], 0) if steam_cost_col in energy_row.columns else 0
                steam_cost.append(steam_val)
            else:
                steam_cost.append(0)

    annual_building_cost = sum(elec_cost) + sum(gas_cost) + sum(steam_cost)

    # Exactly like building.py line 826
    if annual_building_cost > 0 and total_ghg_emissions:
        carbon_emissions_reduction = (utility_savings_annual / annual_building_cost) * total_ghg_emissions

    # Fine avoidance (LL97)
    fine_avoidance_yr1 = safe_float(savings.get('ll97_avoidance_2026'), 0)
    if pd.isna(fine_avoidance_yr1) or str(savings.get('ll97_avoidance_2026', '')).startswith('NA'):
        fine_avoidance_yr1 = 0.0

    # Total building cost savings percentage
    total_building_cost_savings_pct = None
    total_annual_cost = (total_annual_electricity_cost or 0) + (annual_gas_cost or 0)
    if total_annual_cost > 0:
        total_building_cost_savings_pct = utility_savings_annual / total_annual_cost

    # Build the row
    row = {
        'building_id': building_id,
        'address': address,
        'site_eui': site_eui,
        'reporting_year': NYC_DEFAULTS['reporting_year'],
        'building_type': NYC_DEFAULTS['building_type'],
        'year_built': safe_float(bldg.get('yearalter')),
        'energy_star_score': safe_float(bldg.get('Latest_ENERGY_STAR_Score')),
        'vertical': NYC_DEFAULTS['vertical'],
        'square_footage': square_footage,
        'building_owner': bldg.get('ownername'),
        'property_manager': bldg.get('property_manager'),
        'total_site_energy_kbtu': total_site_energy_kbtu,
        'electricity_use_kbtu': electricity_use_kbtu,
        'natural_gas_use_kbtu': natural_gas_use_kbtu,
        'district_steam_use_kbtu': district_steam_use_kbtu if district_steam_use_kbtu else None,
        'fuel_oil_use_kbtu': None,
        'total_ghg_emissions_mt_co2e': total_ghg_emissions,
        'building_url': building_url,
        'property_plant_id': None,  # Will be set if available
        'latitude': safe_float(bldg.get('latitude')),
        'longitude': safe_float(bldg.get('longitude')),
        'tenant': None,
        'tenant_sub_org': None,
        'photo_url': None,
        'zip_code': extract_zip_code(address),
        'property_name': property_name,
        'electricity_kwh': electricity_kwh,
        'energy_rate_per_kwh': NYC_DEFAULTS['energy_rate_per_kwh'],
        'utility_name_used': NYC_DEFAULTS['utility_name_used'],
        'annual_energy_cost': annual_energy_cost,
        'load_factor_used': NYC_DEFAULTS['load_factor_used'],
        'estimated_peak_kw': estimated_peak_kw,
        'demand_rate_per_kw': demand_rate_per_kw,
        'annual_demand_cost': annual_demand_cost,
        'total_annual_electricity_cost': total_annual_electricity_cost,
        'cost_calculation_notes': NYC_DEFAULTS['cost_calculation_notes'],
        'annual_gas_cost': annual_gas_cost,
        'gas_rate_per_therm': NYC_DEFAULTS['gas_rate_per_therm'],
        'annual_steam_cost': None,
        'steam_rate_per_mlb': None,
        'energy_star_climate_zone': NYC_DEFAULTS['energy_star_climate_zone'],
        'fuel_oil_rate_per_gallon': None,
        'annual_fuel_oil_cost': None,
        'vacancy_rate': NYC_DEFAULTS['vacancy_rate'],
        'utilization_rate': NYC_DEFAULTS['utilization_rate'],
        'cap_rate': NYC_DEFAULTS['cap_rate'],
        'market_rent_per_sqft': NYC_DEFAULTS['market_rent_per_sqft'],
        'operating_expense_ratio': NYC_DEFAULTS['operating_expense_ratio'],
        'state': NYC_DEFAULTS['state'],
        'pct_elec_hvac': pct_elec_hvac,
        'pct_gas_hvac': pct_gas_hvac,
        'pct_steam_hvac': pct_steam_hvac,
        'pct_fuel_oil_hvac': pct_fuel_oil_hvac,
        'method': NYC_DEFAULTS['method'],
        'odcv_savings_pct': odcv_savings_pct,
        'current_valuation_usd': None,
        'post_odcv_valuation_usd': None,
        'odcv_valuation_impact_usd': odcv_valuation_impact,
        'total_hvac_energy_kbtu': total_hvac_energy_kbtu,
        'total_hvac_energy_cost': total_hvac_energy_cost,
        'odcv_dollar_savings': utility_savings_annual,
        'total_annual_opex_avoidance': utility_savings_annual + (fine_avoidance_yr1 if isinstance(fine_avoidance_yr1, (int, float)) else 0),
        'city': NYC_DEFAULTS['city'],
        'carbon_emissions_reduction_yr1': carbon_emissions_reduction,
        'fine_avoidance_yr1': fine_avoidance_yr1,
        'carbon_local_law': NYC_DEFAULTS['carbon_local_law'],
        'radio_button_building_type': NYC_DEFAULTS['radio_button_building_type'],
        'total_building_cost_savings_pct': total_building_cost_savings_pct,
        'benchmark_building_type': NYC_DEFAULTS['benchmark_building_type'],
        'eui_benchmark': NYC_DEFAULTS['eui_benchmark'],
    }

    return row


def update_csv_files(nyc_rows_df):
    """Update both portfolio_data.csv and buildings_tab_data.csv with NYC data."""

    # Fields to preserve from original nationwide CSV
    PRESERVE_ELEC_FIELDS = [
        'energy_rate_per_kwh',
        'demand_rate_per_kw',
        'annual_energy_cost',
        'annual_demand_cost',
        'total_annual_electricity_cost',
        'load_factor_used',
        'estimated_peak_kw',
        'cost_calculation_notes',
        'electricity_kwh',
    ]

    # Load existing files
    print("\nLoading existing CSV files...")
    portfolio_df = pd.read_csv(PORTFOLIO_DATA, encoding='utf-8')
    buildings_tab_df = pd.read_csv(BUILDINGS_TAB_DATA, encoding='utf-8')

    print(f"  - portfolio_data.csv: {len(portfolio_df)} rows")
    print(f"  - buildings_tab_data.csv: {len(buildings_tab_df)} rows")

    # Create backups
    print("\nCreating backups...")
    portfolio_backup = PORTFOLIO_DATA.replace('.csv', f'_backup_{BACKUP_SUFFIX}.csv')
    buildings_backup = BUILDINGS_TAB_DATA.replace('.csv', f'_backup_{BACKUP_SUFFIX}.csv')

    portfolio_df.to_csv(portfolio_backup, index=False)
    buildings_tab_df.to_csv(buildings_backup, index=False)
    print(f"  - Backed up to: {portfolio_backup}")
    print(f"  - Backed up to: {buildings_backup}")

    # Get list of NYC building IDs to update
    nyc_building_ids = set(nyc_rows_df['building_id'].tolist())
    print(f"\nUpdating {len(nyc_building_ids)} NYC buildings...")

    # Extract existing NYC rows to preserve elec rate fields
    portfolio_existing_nyc = portfolio_df[portfolio_df['building_id'].isin(nyc_building_ids)].copy()
    buildings_tab_existing_nyc = buildings_tab_df[buildings_tab_df['building_id'].isin(nyc_building_ids)].copy()

    print(f"  - Preserving elec rate fields from {len(portfolio_existing_nyc)} existing portfolio rows")
    print(f"  - Preserving elec rate fields from {len(buildings_tab_existing_nyc)} existing buildings_tab rows")

    # Create lookup dicts for preserved fields
    portfolio_preserved = {}
    for _, row in portfolio_existing_nyc.iterrows():
        bid = row['building_id']
        portfolio_preserved[bid] = {col: row[col] for col in PRESERVE_ELEC_FIELDS if col in row.index}

    buildings_tab_preserved = {}
    for _, row in buildings_tab_existing_nyc.iterrows():
        bid = row['building_id']
        buildings_tab_preserved[bid] = {col: row[col] for col in PRESERVE_ELEC_FIELDS if col in row.index}

    # Apply preserved fields to new NYC data
    for idx, row in nyc_rows_df.iterrows():
        bid = row['building_id']
        if bid in portfolio_preserved:
            for col, val in portfolio_preserved[bid].items():
                if col in nyc_rows_df.columns and pd.notna(val):
                    nyc_rows_df.at[idx, col] = val

    print(f"  - Preserved elec rate fields for {len(portfolio_preserved)} buildings")

    # Remove existing NYC rows (we'll replace them)
    portfolio_non_nyc = portfolio_df[~portfolio_df['building_id'].isin(nyc_building_ids)]
    buildings_tab_non_nyc = buildings_tab_df[~buildings_tab_df['building_id'].isin(nyc_building_ids)]

    print(f"  - Removed {len(portfolio_df) - len(portfolio_non_nyc)} existing NYC rows from portfolio_data")
    print(f"  - Removed {len(buildings_tab_df) - len(buildings_tab_non_nyc)} existing NYC rows from buildings_tab_data")

    # Ensure column order matches
    portfolio_columns = portfolio_df.columns.tolist()
    buildings_tab_columns = buildings_tab_df.columns.tolist()

    # Reorder nyc_rows_df to match existing column order
    nyc_for_portfolio = nyc_rows_df.reindex(columns=portfolio_columns)
    nyc_for_buildings_tab = nyc_rows_df.reindex(columns=buildings_tab_columns)

    # Concatenate
    updated_portfolio = pd.concat([portfolio_non_nyc, nyc_for_portfolio], ignore_index=True)
    updated_buildings_tab = pd.concat([buildings_tab_non_nyc, nyc_for_buildings_tab], ignore_index=True)

    # Save updated files
    print("\nSaving updated files...")
    updated_portfolio.to_csv(PORTFOLIO_DATA, index=False)
    updated_buildings_tab.to_csv(BUILDINGS_TAB_DATA, index=False)

    print(f"  - portfolio_data.csv: {len(updated_portfolio)} rows (was {len(portfolio_df)})")
    print(f"  - buildings_tab_data.csv: {len(updated_buildings_tab)} rows (was {len(buildings_tab_df)})")

    return updated_portfolio, updated_buildings_tab


def main():
    """Main function to update NYC buildings."""
    print("=" * 60)
    print("NYC Building Data Update Script")
    print("=" * 60)

    # Load NYC data
    data = load_nyc_data()

    # Get list of BBLs from 10_year_savings (the authoritative list)
    bbls = data['ten_yr_savings']['bbl'].unique()
    print(f"\nProcessing {len(bbls)} NYC buildings from 10_year_savings_by_building.csv...")

    # Build rows for each building
    rows = []
    errors = []

    for i, bbl in enumerate(bbls):
        if (i + 1) % 100 == 0:
            print(f"  Processing building {i + 1}/{len(bbls)}...")

        try:
            row = build_nyc_row(bbl, data)
            if row:
                rows.append(row)
            else:
                errors.append((bbl, "Could not build row"))
        except Exception as e:
            errors.append((bbl, str(e)))

    print(f"\nSuccessfully processed {len(rows)} buildings")
    if errors:
        print(f"Errors encountered: {len(errors)}")
        for bbl, err in errors[:5]:
            print(f"  - BBL {bbl}: {err}")
        if len(errors) > 5:
            print(f"  ... and {len(errors) - 5} more errors")

    # Convert to DataFrame
    nyc_df = pd.DataFrame(rows)

    # Update CSV files
    update_csv_files(nyc_df)

    print("\n" + "=" * 60)
    print("Update complete!")
    print("=" * 60)


if __name__ == '__main__':
    main()
