#!/usr/bin/env python3
"""
ODCV Savings Percentage Calculator
===================================
Calculates per-building ODCV (Occupancy-Driven Demand Control Ventilation) 
savings percentage based on:
- Vacancy rate (primary for multi-tenant commercial)
- Utilization rate (primary for owner-occupied/schedule-driven)
- Year built (automation proxy)
- Square footage (automation proxy)
- Building type (formula selector + floor/ceiling)
- Energy Star score / EUI (efficiency modifier)
- Climate zone (conditioning penalty modifier)

Output: 20-40% range for Office, type-specific ranges for others
"""

import pandas as pd
import numpy as np
import os
import shutil
from pathlib import Path
from datetime import datetime

# =============================================================================
# CONFIGURATION
# =============================================================================

INPUT_FILES = [
    '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv',
]
BACKUP_DIR = '/Users/forrestmiller/Desktop/nationwide-prospector/BACKUPS_GO_HERE/csv_backups'

def create_backup(input_file):
    """Create timestamped backup before any changes."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{BACKUP_DIR}/portfolio_data_backup_{timestamp}.csv"
    shutil.copy(input_file, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path

# =============================================================================
# BUILDING TYPE CONFIGURATION
# =============================================================================

# Floor and ceiling for each building type
BUILDING_TYPE_BOUNDS = {
    'Office':                    (0.20, 0.40),
    'Medical Office':            (0.20, 0.40),
    'Mixed Use':                 (0.18, 0.38),
    'Strip Mall':                (0.15, 0.35),
    'K-12 School':               (0.20, 0.45),
    'Higher Ed':                 (0.20, 0.45),
    'Preschool/Daycare':         (0.18, 0.38),
    'Retail Store':              (0.15, 0.35),
    'Supermarket/Grocery':       (0.10, 0.25),
    'Wholesale Club':            (0.10, 0.25),
    'Enclosed Mall':             (0.12, 0.30),
    'Hotel':                     (0.15, 0.35),
    'Restaurant/Bar':            (0.10, 0.25),
    'Gym':                       (0.15, 0.35),
    'Event Space':               (0.20, 0.45),
    'Venue':                     (0.20, 0.45),  # Same as Event Space
    'Theater':                   (0.18, 0.40),
    'Arts & Culture':            (0.15, 0.35),
    'Library':                   (0.12, 0.28),
    'Library/Museum':            (0.12, 0.28),  # Same as Library
    'Bank Branch':               (0.12, 0.28),
    'Vehicle Dealership':        (0.15, 0.35),
    'Courthouse':                (0.10, 0.25),
    'Public Service':            (0.10, 0.25),
    'Outpatient Clinic':         (0.15, 0.32),
    'Sports/Gaming Center':      (0.18, 0.40),
    'Inpatient Hospital':        (0.05, 0.15),
    'Specialty Hospital':        (0.05, 0.15),
    'Residential Care Facility': (0.05, 0.15),
    'Residential Care':          (0.05, 0.15),  # Same as Residential Care Facility
    'Laboratory':                (0.05, 0.15),
    'Police Station':            (0.05, 0.15),
    'Fire Station':              (0.05, 0.15),
    'Public Transit':            (0.05, 0.15),
    'Data Center':               (0.00, 0.00),
}

# Building types where vacancy + utilization both matter (multi-tenant central HVAC)
VACANCY_PLUS_UTIL_TYPES = ['Office', 'Medical Office', 'Mixed Use', 'Strip Mall']

# Building types with reduced opportunity (24/7, infection control, high OA codes)
LOW_OPPORTUNITY_TYPES = [
    'Inpatient Hospital', 'Specialty Hospital', 'Residential Care Facility',
    'Laboratory', 'Police Station', 'Fire Station', 'Public Transit'
]

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def safe_float(val, default=None):
    """Convert value to float, return default if empty or invalid."""
    if val == '' or val is None or (isinstance(val, float) and np.isnan(val)):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def calculate_opportunity_score(building_type, vacancy, utilization):
    """
    Calculate opportunity score (0-1) based on building type.
    
    - Office/Medical Office/Mixed Use/Strip Mall: vacancy + (1-vacancy) * (1-util)
    - Low opportunity types (Hospital, Lab, etc.): (1-util) * 0.3
    - Data Center: 0
    - Everything else: 1 - util
    """
    if building_type == 'Data Center':
        return 0.0
    
    if building_type in VACANCY_PLUS_UTIL_TYPES:
        # Both vacancy and utilization matter
        # Vacant space = full waste, leased space = partial waste from low utilization
        return vacancy + (1 - vacancy) * (1 - utilization)
    
    if building_type in LOW_OPPORTUNITY_TYPES:
        # 24/7 or high OA requirements - reduced opportunity
        return (1 - utilization) * 0.3
    
    # Everything else - utilization driven
    return 1 - utilization


def calculate_year_score(year_built):
    """
    Convert year_built to automation likelihood score (0-1).
    Newer buildings more likely to have BMS, better controls.
    """
    if year_built is None:
        return 0.5  # Middle value
    
    if year_built < 1970:
        return 0.0
    elif year_built < 1990:
        return 0.25
    elif year_built < 2005:
        return 0.50
    elif year_built < 2015:
        return 0.75
    else:
        return 1.0


def calculate_size_score(sqft):
    """
    Convert square footage to automation likelihood score (0-1).
    Larger buildings more likely to have sophisticated BMS.
    """
    if sqft is None:
        return 0.5  # Middle value
    
    if sqft < 50000:
        return 0.25
    elif sqft < 100000:
        return 0.50
    elif sqft < 250000:
        return 0.75
    else:
        return 1.0


def calculate_automation_score(year_built, sqft):
    """Combined automation score from year and size."""
    year_score = calculate_year_score(year_built)
    size_score = calculate_size_score(sqft)
    return (year_score + size_score) / 2.0


def calculate_efficiency_modifier_energy_star(score):
    """
    Efficiency modifier based on Energy Star score.
    Lower score = more waste = more opportunity.
    """
    if score is None:
        return None  # Will fall back to EUI
    
    if score >= 90:
        return 0.85  # Very efficient, less waste to capture
    elif score >= 75:
        return 0.95
    elif score >= 50:
        return 1.00
    elif score >= 25:
        return 1.05
    else:
        return 1.10  # Inefficient, more waste to capture


def calculate_efficiency_modifier_eui(eui, peer_median_eui):
    """
    Efficiency modifier based on EUI vs peer median.
    Higher EUI = more waste = more opportunity.
    """
    if eui is None or peer_median_eui is None or peer_median_eui == 0:
        return 1.0
    
    ratio = eui / peer_median_eui
    
    if ratio > 1.5:
        return 1.10  # Very inefficient
    elif ratio > 1.2:
        return 1.05
    elif ratio > 0.85:
        return 1.00
    elif ratio > 0.70:
        return 0.95
    else:
        return 0.90  # Very efficient


def calculate_climate_modifier(climate_zone):
    """
    Climate modifier - Northern climates have more heating penalty per CFM.
    """
    modifiers = {
        'Northern': 1.10,
        'North-Central': 1.05,
        'South-Central': 1.00,
        'Southern': 0.95,
        '': 1.00  # Default for missing
    }
    return modifiers.get(climate_zone, 1.00)


# =============================================================================
# MAIN CALCULATION
# =============================================================================

def process_file(input_file):
    """Process a single CSV file."""
    print(f"\n{'=' * 60}")
    print(f"Processing: {input_file}")
    print("=" * 60)

    # Load data
    df = pd.read_csv(input_file, dtype=str, low_memory=False)
    print(f"Loaded {len(df):,} buildings")

    # Calculate peer median EUI by building type (for efficiency modifier fallback)
    print("\nCalculating peer median EUI by building type...")
    df['site_eui_float'] = df['energy_site_eui'].apply(lambda x: safe_float(x))
    peer_median_eui = df.groupby('bldg_type')['site_eui_float'].median().to_dict()

    # Calculate median year_built by building type (for missing value fallback)
    print("Calculating median year_built by building type...")
    df['year_built_float'] = df['bldg_year_built'].apply(lambda x: safe_float(x))
    median_year_by_type = df.groupby('bldg_type')['year_built_float'].median().to_dict()

    # Default values
    DEFAULT_VACANCY = 0.15
    DEFAULT_UTILIZATION = 0.60

    # Calculate ODCV savings for each building
    print("\nCalculating ODCV savings percentage for each building...")

    odcv_savings_list = []

    for idx, row in df.iterrows():
        building_type = row['bldg_type']

        # Get floor/ceiling for this building type
        floor, ceiling = BUILDING_TYPE_BOUNDS.get(building_type, (0.15, 0.35))

        # Data Center = 0%
        if building_type == 'Data Center':
            odcv_savings_list.append(0.0)
            continue

        # Parse values with defaults
        vacancy = safe_float(row['occ_vacancy_rate'], DEFAULT_VACANCY)
        utilization = safe_float(row['occ_utilization_rate'], DEFAULT_UTILIZATION)
        year_built = safe_float(row['bldg_year_built'], median_year_by_type.get(building_type, 1982))
        sqft = safe_float(row['bldg_sqft'], 89000)
        energy_star = safe_float(row['energy_star_score'])
        eui = safe_float(row['energy_site_eui'])
        climate_zone = row['energy_climate_zone'] if pd.notna(row['energy_climate_zone']) and row['energy_climate_zone'] else ''

        # Step 1: Opportunity score
        opportunity = calculate_opportunity_score(building_type, vacancy, utilization)

        # Step 2: Automation score
        automation = calculate_automation_score(year_built, sqft)

        # Step 3: Efficiency modifier (Energy Star if available, else EUI)
        efficiency_modifier = calculate_efficiency_modifier_energy_star(energy_star)
        if efficiency_modifier is None:
            efficiency_modifier = calculate_efficiency_modifier_eui(eui, peer_median_eui.get(building_type))

        # Step 4: Climate modifier
        climate_modifier = calculate_climate_modifier(climate_zone)

        # Step 5: Calculate final ODCV savings %
        # Base calculation: floor + (opportunity * automation * range)
        range_size = ceiling - floor
        base_odcv = floor + (opportunity * automation * range_size)

        # Apply modifiers
        final_odcv = base_odcv * efficiency_modifier * climate_modifier

        # Apply 20% increase (multiplicative, not additive)
        final_odcv = final_odcv * 1.20

        # Clamp to building type floor/ceiling first
        final_odcv = max(floor, min(ceiling, final_odcv))

        # GLOBAL bounds: never below 20%, never above 50%
        final_odcv = max(0.20, min(0.50, final_odcv))

        odcv_savings_list.append(round(final_odcv, 4))

    # Add column to dataframe
    df['odcv_hvac_savings_pct'] = odcv_savings_list

    # Drop temp columns
    df = df.drop(columns=['site_eui_float', 'year_built_float'])

    # Summary statistics
    print("\n" + "-" * 60)
    print("RESULTS SUMMARY")
    print("-" * 60)

    df['odcv_savings_pct_float'] = df['odcv_hvac_savings_pct'].astype(float)

    print(f"\nOverall Statistics:")
    print(f"  Min:    {df['odcv_savings_pct_float'].min():.1%}")
    print(f"  Max:    {df['odcv_savings_pct_float'].max():.1%}")
    print(f"  Mean:   {df['odcv_savings_pct_float'].mean():.1%}")
    print(f"  Median: {df['odcv_savings_pct_float'].median():.1%}")

    print(f"\nBy Building Type:")
    print("-" * 50)
    type_stats = df.groupby('bldg_type')['odcv_savings_pct_float'].agg(['count', 'min', 'max', 'mean', 'median'])
    type_stats = type_stats.sort_values('count', ascending=False)

    for btype, stats in type_stats.iterrows():
        print(f"  {btype:30s} n={int(stats['count']):5d}  "
              f"min={stats['min']:.1%}  max={stats['max']:.1%}  "
              f"mean={stats['mean']:.1%}  median={stats['median']:.1%}")

    # Drop temp column
    df = df.drop(columns=['odcv_savings_pct_float'])

    # Save back to same file
    print(f"\nSaving to: {input_file}")
    df.to_csv(input_file, index=False)
    print(f"Saved {len(df):,} buildings with updated odcv_savings_pct")


def main():
    print("=" * 60)
    print("ODCV Savings Percentage Calculator (20% increase)")
    print("=" * 60)

    for input_file in INPUT_FILES:
        process_file(input_file)

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == '__main__':
    main()
