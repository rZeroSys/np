#!/usr/bin/env python3
"""
Update NYC buildings in portfolio_data.csv
using data from the NYC folder (/Users/forrestmiller/Desktop/New/data/).

This script copies data for ~1k NYC buildings from:
- energy_BIG.csv (costs - summed from monthly values)
- 10_year_savings_by_building.csv (energy usage, savings)
- buildings_BIG_with_emails_complete_verified.csv (building info)
- hvac_office_energy_BIG.csv (HVAC percentages)
- odcv_noi_value_impact_analysis.csv (valuation)

Usage: python3 07_nyc_update.py
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

# Nationwide prospector target files
PROSPECTOR_PATH = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/'
PORTFOLIO_DATA = PROSPECTOR_PATH + 'portfolio_data.csv'
BUILDINGS_TAB_DATA = PROSPECTOR_PATH + 'buildings_tab_data.csv'

# Backup paths
BACKUP_DIR = '/Users/forrestmiller/Desktop/nationwide-prospector/BACKUPS_GO_HERE/csv_backups'
BACKUP_SUFFIX = datetime.now().strftime('%Y%m%d_%H%M%S')

# ============================================================================
# CONSTANTS FOR NYC
# ============================================================================

NYC_DEFAULTS = {
    'data_year': 2023.0,
    'bldg_type': 'Office',
    'bldg_vertical': 'Commercial',
    'loc_state': 'NY',
    'loc_city': 'New York',
    'cost_utility_name': 'Consolidated Edison Co-NY Inc',
    'energy_climate_zone': 'North-Central',
    # occ_vacancy_rate - READ FROM CSV (1 - % Leased)
    # occ_utilization_rate - calculated
    # val_cap_rate_pct - READ FROM CSV (cap_rate_median)
    'val_market_rent_sqft': 68.0,
    'val_opex_ratio': 0.5,
    'hvac_pct_method': 'nyc_real_data',
    'bps_law_name': 'NYC LL97',
    'bldg_type_benchmark': 'Office',
    'energy_eui_benchmark': 52.9,
    'bldg_type_filter': 'Office',
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

    # Vacancy rate - READ FROM CSV (1 - % Leased)
    pct_leased = safe_float(bldg.get('% Leased'))
    if pct_leased is not None:
        vacancy_rate = 1.0 - (pct_leased / 100.0)
        vacancy_rate = max(0.0, min(1.0, vacancy_rate))  # Clamp 0-1
    else:
        vacancy_rate = 0.13  # Default only if not in CSV

    # Utilization rate - use 0.55 (matches other NYC offices in portfolio)
    utilization_rate = 0.55

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

    # Electricity kWh (for reference)
    electricity_kwh = electricity_use_kbtu / 3.412 if electricity_use_kbtu else None

    # Sum monthly costs from energy_BIG.csv
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    total_annual_electricity_cost = 0
    annual_gas_cost = 0
    annual_steam_cost = 0

    if not energy_row.empty:
        for m in months:
            # Electricity = HVAC + NonHVAC
            hvac_col = f'Elec_HVAC_{m}_2023_Cost_USD'
            nonhvac_col = f'Elec_NonHVAC_{m}_2023_Cost_USD'
            if hvac_col in energy_row.columns:
                total_annual_electricity_cost += safe_float(energy_row[hvac_col].iloc[0], 0)
            if nonhvac_col in energy_row.columns:
                total_annual_electricity_cost += safe_float(energy_row[nonhvac_col].iloc[0], 0)

            # Gas
            gas_col = f'Gas_{m}_2023_Cost_USD'
            if gas_col in energy_row.columns:
                annual_gas_cost += safe_float(energy_row[gas_col].iloc[0], 0)

            # Steam
            steam_col = f'Steam_{m}_2023_Cost_USD'
            if steam_col in energy_row.columns:
                annual_steam_cost += safe_float(energy_row[steam_col].iloc[0], 0)

    # Convert 0 to None for empty values
    total_annual_electricity_cost = total_annual_electricity_cost if total_annual_electricity_cost > 0 else None
    annual_gas_cost = annual_gas_cost if annual_gas_cost > 0 else None
    annual_steam_cost = annual_steam_cost if annual_steam_cost > 0 else None

    # HVAC percentages
    pct_elec_hvac, pct_gas_hvac, pct_steam_hvac, pct_fuel_oil_hvac = calculate_hvac_percentages(hvac, bbl)

    # ODCV savings
    utility_savings_annual = safe_float(savings.get('utility_savings_annual'), 0)

    # ODCV savings percentage - READ FROM HVAC CSV (real per-building value)
    hvac_row = hvac[hvac['bbl'] == bbl]
    odcv_savings_pct = None
    if not hvac_row.empty:
        odcv_savings_pct = safe_float(hvac_row['odcv_hvac_savings_pct'].iloc[0])

    # Calculate HVAC totals
    total_hvac_energy_kbtu = ((electricity_use_kbtu or 0) * pct_elec_hvac) + ((natural_gas_use_kbtu or 0) * pct_gas_hvac) + ((district_steam_use_kbtu or 0) * (pct_steam_hvac or 0.5))

    total_hvac_energy_cost = (
        ((total_annual_electricity_cost or 0) * pct_elec_hvac) +
        ((annual_gas_cost or 0) * pct_gas_hvac) +
        ((annual_steam_cost or 0) * (pct_steam_hvac or 0.5))
    )
    total_hvac_energy_cost = total_hvac_energy_cost if total_hvac_energy_cost > 0 else None

    # Valuation impact - DIRECT FROM CSV (exactly like building.py)
    val_row = valuation[valuation['bbl'] == bbl]
    odcv_valuation_impact = None
    cap_rate = None

    if not val_row.empty:
        odcv_valuation_impact = safe_float(val_row['odcv_value_increase'].iloc[0])
        cap_rate = safe_float(val_row['cap_rate_median'].iloc[0])

    # Carbon emissions reduction
    carbon_emissions_reduction = None
    annual_building_cost = (total_annual_electricity_cost or 0) + (annual_gas_cost or 0) + (annual_steam_cost or 0)
    if annual_building_cost > 0 and total_ghg_emissions:
        carbon_emissions_reduction = (utility_savings_annual / annual_building_cost) * total_ghg_emissions

    # Fine avoidance (LL97)
    fine_avoidance_yr1 = safe_float(savings.get('ll97_avoidance_2026'), 0)
    if pd.isna(fine_avoidance_yr1) or str(savings.get('ll97_avoidance_2026', '')).startswith('NA'):
        fine_avoidance_yr1 = 0.0

    # Total building cost savings percentage
    total_building_cost_savings_pct = None
    total_annual_cost = (total_annual_electricity_cost or 0) + (annual_gas_cost or 0) + (annual_steam_cost or 0)
    if total_annual_cost > 0:
        total_building_cost_savings_pct = utility_savings_annual / total_annual_cost

    # Build the row
    row = {
        'id_building': building_id,
        'loc_address': address,
        'energy_site_eui': site_eui,
        'data_year': NYC_DEFAULTS['data_year'],
        'bldg_type': NYC_DEFAULTS['bldg_type'],
        'bldg_year_built': safe_float(bldg.get('yearalter')),
        'energy_star_score': safe_float(bldg.get('Latest_ENERGY_STAR_Score')),
        'bldg_vertical': NYC_DEFAULTS['bldg_vertical'],
        'bldg_sqft': square_footage,
        'org_owner': bldg.get('ownername'),
        'org_manager': bldg.get('property_manager'),
        'energy_total_kbtu': total_site_energy_kbtu,
        'energy_elec_kbtu': electricity_use_kbtu,
        'energy_gas_kbtu': natural_gas_use_kbtu,
        'energy_steam_kbtu': district_steam_use_kbtu if district_steam_use_kbtu else None,
        'energy_fuel_oil_kbtu': None,
        'carbon_emissions_total_mt': total_ghg_emissions,
        'id_source_url': building_url,
        'id_source_plant_id': None,  # Will be set if available
        'loc_lat': safe_float(bldg.get('latitude')),
        'loc_lon': safe_float(bldg.get('longitude')),
        'org_tenant': None,
        'org_tenant_subunit': None,
        'meta_photo_url': None,
        'loc_zip': extract_zip_code(address),
        'id_property_name': property_name,
        'energy_elec_kwh': electricity_kwh,
        'cost_elec_rate_kwh': None,
        'cost_utility_name': NYC_DEFAULTS['cost_utility_name'],
        'cost_elec_energy_annual': None,
        'cost_elec_load_factor': None,
        'cost_elec_peak_kw': None,
        'cost_elec_rate_demand_kw': None,
        'cost_elec_demand_annual': None,
        'cost_elec_total_annual': total_annual_electricity_cost,
        'cost_calc_notes': 'Copied from energy_BIG.csv',
        'cost_gas_annual': annual_gas_cost,
        'cost_gas_rate_therm': None,
        'cost_steam_annual': annual_steam_cost,
        'cost_steam_rate_mlb': None,
        'energy_climate_zone': NYC_DEFAULTS['energy_climate_zone'],
        'cost_fuel_oil_rate_gal': None,
        'cost_fuel_oil_annual': None,
        'occ_vacancy_rate': vacancy_rate,
        'occ_utilization_rate': utilization_rate,
        'val_cap_rate_pct': cap_rate if cap_rate else 0.07,  # Real from CSV, default 7% if missing
        'val_market_rent_sqft': NYC_DEFAULTS['val_market_rent_sqft'],
        'val_opex_ratio': NYC_DEFAULTS['val_opex_ratio'],
        'loc_state': NYC_DEFAULTS['loc_state'],
        'hvac_pct_elec': pct_elec_hvac,
        'hvac_pct_gas': pct_gas_hvac,
        'hvac_pct_steam': pct_steam_hvac,
        'hvac_pct_fuel_oil': pct_fuel_oil_hvac,
        'hvac_pct_method': NYC_DEFAULTS['hvac_pct_method'],
        'odcv_hvac_savings_pct': odcv_savings_pct,
        'val_current_usd': None,
        'val_post_odcv_usd': None,
        'val_odcv_impact_usd': odcv_valuation_impact,
        'hvac_energy_total_kbtu': total_hvac_energy_kbtu,
        'hvac_cost_total_annual': total_hvac_energy_cost,
        'odcv_hvac_savings_annual_usd': utility_savings_annual,
        'savings_opex_avoided_annual_usd': utility_savings_annual + (fine_avoidance_yr1 if isinstance(fine_avoidance_yr1, (int, float)) else 0),
        'loc_city': NYC_DEFAULTS['loc_city'],
        'odcv_carbon_reduction_yr1_mt': carbon_emissions_reduction,
        'bps_fine_avoided_yr1_usd': fine_avoidance_yr1,
        'bps_law_name': NYC_DEFAULTS['bps_law_name'],
        'bldg_type_filter': NYC_DEFAULTS['bldg_type_filter'],
        'savings_pct_of_energy_cost': total_building_cost_savings_pct,
        'bldg_type_benchmark': NYC_DEFAULTS['bldg_type_benchmark'],
        'energy_eui_benchmark': NYC_DEFAULTS['energy_eui_benchmark'],
    }

    return row


def update_csv_files(nyc_rows_df):
    """Update portfolio_data.csv with NYC data."""
    import os

    # Fields to preserve from original nationwide CSV
    PRESERVE_FIELDS = [
        'cost_elec_rate_kwh',
        'cost_elec_rate_demand_kw',
        'cost_elec_energy_annual',
        'cost_elec_demand_annual',
        'cost_elec_total_annual',
        'cost_elec_load_factor',
        'cost_elec_peak_kw',
        'cost_calc_notes',
        'energy_elec_kwh',
        # NEVER overwrite org names
        'org_owner',
        'org_manager',
        'org_tenant',
        'org_tenant_subunit',
        # NEVER overwrite utilization
        'occ_utilization_rate',
    ]

    # Load existing files
    print("\nLoading existing CSV files...")
    portfolio_df = pd.read_csv(PORTFOLIO_DATA, encoding='utf-8', low_memory=False)

    # Check if buildings_tab_data exists
    has_buildings_tab = os.path.exists(BUILDINGS_TAB_DATA)
    if has_buildings_tab:
        buildings_tab_df = pd.read_csv(BUILDINGS_TAB_DATA, encoding='utf-8', low_memory=False)
        print(f"  - buildings_tab_data.csv: {len(buildings_tab_df)} rows")
    else:
        print("  - buildings_tab_data.csv: NOT FOUND (skipping)")

    print(f"  - portfolio_data.csv: {len(portfolio_df)} rows")

    # Get list of NYC building IDs to update
    nyc_building_ids = set(nyc_rows_df['id_building'].tolist())
    print(f"\nUpdating {len(nyc_building_ids)} NYC buildings...")

    # Extract existing NYC rows to preserve elec rate fields
    portfolio_existing_nyc = portfolio_df[portfolio_df['id_building'].isin(nyc_building_ids)].copy()
    print(f"  - Preserving elec rate fields from {len(portfolio_existing_nyc)} existing portfolio rows")

    if has_buildings_tab:
        buildings_tab_existing_nyc = buildings_tab_df[buildings_tab_df['id_building'].isin(nyc_building_ids)].copy()
        print(f"  - Preserving elec rate fields from {len(buildings_tab_existing_nyc)} existing buildings_tab rows")

    # Create lookup dicts for preserved fields
    portfolio_preserved = {}
    for _, row in portfolio_existing_nyc.iterrows():
        bid = row['id_building']
        portfolio_preserved[bid] = {col: row[col] for col in PRESERVE_FIELDS if col in row.index}

    buildings_tab_preserved = {}
    if has_buildings_tab:
        for _, row in buildings_tab_existing_nyc.iterrows():
            bid = row['id_building']
            buildings_tab_preserved[bid] = {col: row[col] for col in PRESERVE_FIELDS if col in row.index}

    # Apply preserved fields to new NYC data
    for idx, row in nyc_rows_df.iterrows():
        bid = row['id_building']
        if bid in portfolio_preserved:
            for col, val in portfolio_preserved[bid].items():
                if col in nyc_rows_df.columns and pd.notna(val):
                    nyc_rows_df.at[idx, col] = val

    print(f"  - Preserved elec rate fields for {len(portfolio_preserved)} buildings")

    # Remove existing NYC rows (we'll replace them)
    portfolio_non_nyc = portfolio_df[~portfolio_df['id_building'].isin(nyc_building_ids)]
    print(f"  - Removed {len(portfolio_df) - len(portfolio_non_nyc)} existing NYC rows from portfolio_data")

    if has_buildings_tab:
        buildings_tab_non_nyc = buildings_tab_df[~buildings_tab_df['id_building'].isin(nyc_building_ids)]
        print(f"  - Removed {len(buildings_tab_df) - len(buildings_tab_non_nyc)} existing NYC rows from buildings_tab_data")

    # Ensure column order matches
    portfolio_columns = portfolio_df.columns.tolist()

    # Reorder nyc_rows_df to match existing column order
    nyc_for_portfolio = nyc_rows_df.reindex(columns=portfolio_columns)

    # Concatenate
    updated_portfolio = pd.concat([portfolio_non_nyc, nyc_for_portfolio], ignore_index=True)

    if has_buildings_tab:
        buildings_tab_columns = buildings_tab_df.columns.tolist()
        nyc_for_buildings_tab = nyc_rows_df.reindex(columns=buildings_tab_columns)
        updated_buildings_tab = pd.concat([buildings_tab_non_nyc, nyc_for_buildings_tab], ignore_index=True)

    # Save updated files
    print("\nSaving updated files...")
    updated_portfolio.to_csv(PORTFOLIO_DATA, index=False)
    print(f"  - portfolio_data.csv: {len(updated_portfolio)} rows (was {len(portfolio_df)})")

    if has_buildings_tab:
        updated_buildings_tab.to_csv(BUILDINGS_TAB_DATA, index=False)
        print(f"  - buildings_tab_data.csv: {len(updated_buildings_tab)} rows (was {len(buildings_tab_df)})")

    return updated_portfolio, (updated_buildings_tab if has_buildings_tab else None)


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
