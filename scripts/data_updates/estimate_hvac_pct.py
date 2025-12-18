#!/usr/bin/env python3
"""
Estimate HVAC percentage of energy use by fuel type for commercial buildings.

Uses CBECS 2018 microdata to derive benchmarks by (building type × climate zone),
then applies to portfolio buildings.

Output columns:
- pct_elec_hvac: % of electricity going to HVAC (heating + cooling + ventilation)
- pct_gas_hvac: % of natural gas going to HVAC (heating + cooling)
- pct_steam_hvac: % of district steam going to HVAC (heating + cooling)
- pct_other_hvac: % of other fuels (fuel oil) going to HVAC (heating)

Blank if building doesn't use that fuel type.
"""

import csv
import math
from collections import defaultdict

# =============================================================================
# FILE PATHS
# =============================================================================
INPUT_FILE = '/Users/forrestmiller/Desktop/Final real/merged_property_matches_updated.csv'
CBECS_FILE = '/Users/forrestmiller/Desktop/Final real/CBECS data/cbecs2018_final_public.csv'
OUTPUT_FILE = '/Users/forrestmiller/Desktop/analysis stage/merged_property_matches_with_hvac_pct.csv'

# =============================================================================
# MAPPING: Your building types → CBECS PBA codes
# =============================================================================
BUILDING_TYPE_TO_PBA = {
    'Office': 2,
    'K-12 School': 14,
    'Higher Ed': 14,
    'Preschool/Daycare': 14,
    'Hotel': 18,
    'Retail Store': 25,
    'Wholesale Club': 25,
    'Strip Mall': 23,
    'Enclosed Mall': 24,
    'Supermarket/Grocery': 6,
    'Restaurant/Bar': 15,
    'Medical Office': 8,
    'Outpatient Clinic': 8,
    'Inpatient Hospital': 16,
    'Specialty Hospital': 16,
    'Residential Care Facility': 17,
    'Laboratory': 4,
    'Police Station': 7,
    'Fire Station': 7,
    'Courthouse': 7,
    'Arts & Culture': 13,
    'Theater': 13,
    'Event Space': 13,
    'Gym': 13,
    'Library': 13,
    'Sports/Gaming Center': 13,
    'Vehicle Dealership': 26,
    'Public Service': 26,
    'Public Transit': 26,
    'Bank Branch': 2,
    'Mixed Use': 91,
    'Data Center': 'DATA_CENTER',  # Special handling
}

# ENERGY STAR Climate Zone → CBECS PUBCLIM mapping
# PUBCLIM: 1=Very Cold/Cold, 2=Mixed-Humid, 3=Mixed-Dry/Hot-Dry, 4=Hot-Humid, 5=Marine
CLIMATE_ZONE_TO_PUBCLIM = {
    'Northern': [1, 5],        # Very cold/Cold + Marine
    'North-Central': [2],      # Mixed-humid
    'South-Central': [3],      # Mixed-dry/Hot-dry
    'Southern': [4],           # Hot-humid
}

# Reverse mapping for lookup
PUBCLIM_TO_ZONE = {}
for zone, pubclims in CLIMATE_ZONE_TO_PUBCLIM.items():
    for pc in pubclims:
        PUBCLIM_TO_ZONE[pc] = zone

# =============================================================================
# DATA CENTER FIXED PERCENTAGES (no CBECS category)
# Based on LBNL 2024 Data Center Energy Report
# =============================================================================
DATA_CENTER_PCT = {
    'elec': 0.42,   # Cooling (~40%) + minimal ventilation (~2%)
    'gas': 0.0,     # Data centers rarely use gas for HVAC
    'steam': 0.0,   # Rare
    'other': 0.0,   # Rare
}

# =============================================================================
# MINIMUM SAMPLE SIZE THRESHOLDS
# =============================================================================
MIN_SAMPLE_PREFERRED = 30
MIN_SAMPLE_ACCEPTABLE = 10


def safe_float(val, default=0.0):
    """Convert to float, return default if empty/invalid."""
    if val is None or val == '' or val == 'NA' or val == '.':
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def compute_cbecs_benchmarks(cbecs_file):
    """
    Compute HVAC percentage benchmarks from CBECS microdata.
    
    Returns dict: {(pba, climate_zone): {'elec': pct, 'gas': pct, 'steam': pct, 'other': pct, 'n': count}}
    Also returns national averages by PBA only for fallback.
    """
    # Accumulators for weighted sums
    # Structure: {(pba, zone): {fuel: {'hvac': weighted_sum, 'total': weighted_sum}}}
    by_pba_climate = defaultdict(lambda: {
        'elec': {'hvac': 0.0, 'total': 0.0},
        'gas': {'hvac': 0.0, 'total': 0.0},
        'steam': {'hvac': 0.0, 'total': 0.0},
        'other': {'hvac': 0.0, 'total': 0.0},
        'weight_sum': 0.0,
        'n': 0
    })
    
    by_pba_only = defaultdict(lambda: {
        'elec': {'hvac': 0.0, 'total': 0.0},
        'gas': {'hvac': 0.0, 'total': 0.0},
        'steam': {'hvac': 0.0, 'total': 0.0},
        'other': {'hvac': 0.0, 'total': 0.0},
        'weight_sum': 0.0,
        'n': 0
    })
    
    with open(cbecs_file, 'r') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            pba = safe_float(row.get('PBA', ''), default=-1)
            if pba < 0:
                continue
            pba = int(pba)
            
            pubclim = safe_float(row.get('PUBCLIM', ''), default=-1)
            if pubclim < 0:
                continue
            pubclim = int(pubclim)
            
            climate_zone = PUBCLIM_TO_ZONE.get(pubclim)
            if climate_zone is None:
                continue
            
            weight = safe_float(row.get('FINALWT', 1.0), default=1.0)
            if weight <= 0:
                weight = 1.0
            
            # Electric: HVAC = heating + cooling + ventilation
            el_ht = safe_float(row.get('ELHTBTU', 0))
            el_cl = safe_float(row.get('ELCLBTU', 0))
            el_vn = safe_float(row.get('ELVNBTU', 0))
            el_total = safe_float(row.get('ELBTU', 0))
            
            # Gas: HVAC = heating + cooling (absorption chillers, rare but exists)
            ng_ht = safe_float(row.get('NGHTBTU', 0))
            ng_cl = safe_float(row.get('NGCLBTU', 0))
            ng_total = safe_float(row.get('NGBTU', 0))
            
            # District heat/steam: HVAC = heating + cooling
            dh_ht = safe_float(row.get('DHHTBTU', 0))
            dh_cl = safe_float(row.get('DHCLBTU', 0))
            dh_total = safe_float(row.get('DHBTU', 0))
            
            # Fuel oil/other: HVAC = heating + cooling
            fk_ht = safe_float(row.get('FKHTBTU', 0))
            fk_cl = safe_float(row.get('FKCLBTU', 0))
            fk_total = safe_float(row.get('FKBTU', 0))
            
            key = (pba, climate_zone)
            
            # Accumulate weighted values
            # Only include buildings that actually use each fuel type
            if el_total > 0:
                by_pba_climate[key]['elec']['hvac'] += weight * (el_ht + el_cl + el_vn)
                by_pba_climate[key]['elec']['total'] += weight * el_total
                by_pba_only[pba]['elec']['hvac'] += weight * (el_ht + el_cl + el_vn)
                by_pba_only[pba]['elec']['total'] += weight * el_total
            
            if ng_total > 0:
                by_pba_climate[key]['gas']['hvac'] += weight * (ng_ht + ng_cl)
                by_pba_climate[key]['gas']['total'] += weight * ng_total
                by_pba_only[pba]['gas']['hvac'] += weight * (ng_ht + ng_cl)
                by_pba_only[pba]['gas']['total'] += weight * ng_total
            
            if dh_total > 0:
                by_pba_climate[key]['steam']['hvac'] += weight * (dh_ht + dh_cl)
                by_pba_climate[key]['steam']['total'] += weight * dh_total
                by_pba_only[pba]['steam']['hvac'] += weight * (dh_ht + dh_cl)
                by_pba_only[pba]['steam']['total'] += weight * dh_total
            
            if fk_total > 0:
                by_pba_climate[key]['other']['hvac'] += weight * (fk_ht + fk_cl)
                by_pba_climate[key]['other']['total'] += weight * fk_total
                by_pba_only[pba]['other']['hvac'] += weight * (fk_ht + fk_cl)
                by_pba_only[pba]['other']['total'] += weight * fk_total
            
            by_pba_climate[key]['weight_sum'] += weight
            by_pba_climate[key]['n'] += 1
            by_pba_only[pba]['weight_sum'] += weight
            by_pba_only[pba]['n'] += 1
    
    # Convert to percentages
    benchmarks_pba_climate = {}
    for key, data in by_pba_climate.items():
        benchmarks_pba_climate[key] = {
            'n': data['n'],
        }
        for fuel in ['elec', 'gas', 'steam', 'other']:
            if data[fuel]['total'] > 0:
                pct = data[fuel]['hvac'] / data[fuel]['total']
                # Cap at 1.0 (shouldn't exceed but just in case)
                benchmarks_pba_climate[key][fuel] = min(pct, 1.0)
            else:
                benchmarks_pba_climate[key][fuel] = None  # No data for this fuel
    
    benchmarks_pba_only = {}
    for pba, data in by_pba_only.items():
        benchmarks_pba_only[pba] = {
            'n': data['n'],
        }
        for fuel in ['elec', 'gas', 'steam', 'other']:
            if data[fuel]['total'] > 0:
                pct = data[fuel]['hvac'] / data[fuel]['total']
                benchmarks_pba_only[pba][fuel] = min(pct, 1.0)
            else:
                benchmarks_pba_only[pba][fuel] = None
    
    return benchmarks_pba_climate, benchmarks_pba_only


def get_hvac_pct(building_type, climate_zone, fuel, benchmarks_pba_climate, benchmarks_pba_only):
    """
    Get HVAC percentage for a building, using tiered fallback.
    
    Returns: (pct, method) where method is 'type_climate', 'type_only', 'data_center', or 'no_data'
    """
    # Special handling for Data Centers
    if building_type == 'Data Center':
        return DATA_CENTER_PCT.get(fuel, 0.0), 'data_center'
    
    pba = BUILDING_TYPE_TO_PBA.get(building_type)
    if pba is None or pba == 'DATA_CENTER':
        # Unknown building type, use generic office as fallback
        pba = 2
    
    key = (pba, climate_zone)
    
    # Tier 1: Try (PBA × climate) with sufficient sample
    if key in benchmarks_pba_climate:
        data = benchmarks_pba_climate[key]
        if data['n'] >= MIN_SAMPLE_ACCEPTABLE and data.get(fuel) is not None:
            return data[fuel], 'type_climate'
    
    # Tier 2: Fall back to PBA-only national average
    if pba in benchmarks_pba_only:
        data = benchmarks_pba_only[pba]
        if data.get(fuel) is not None:
            return data[fuel], 'type_only'
    
    # Tier 3: No data - return None
    return None, 'no_data'


def main():
    print("Loading CBECS benchmarks...")
    benchmarks_pba_climate, benchmarks_pba_only = compute_cbecs_benchmarks(CBECS_FILE)
    
    print(f"  Loaded {len(benchmarks_pba_climate)} (type × climate) combinations")
    print(f"  Loaded {len(benchmarks_pba_only)} building types (national)")
    
    # Print some example benchmarks for sanity check
    print("\nSample benchmarks (Office in each climate zone):")
    for zone in ['Northern', 'North-Central', 'South-Central', 'Southern']:
        key = (2, zone)  # PBA 2 = Office
        if key in benchmarks_pba_climate:
            b = benchmarks_pba_climate[key]
            print(f"  {zone}: elec={b['elec']:.1%}, gas={b['gas']:.1%}, n={b['n']}")
    
    print("\nProcessing buildings...")
    
    # Read input, add columns, write output
    rows_processed = 0
    rows_with_flags = 0
    
    with open(INPUT_FILE, 'r') as f_in:
        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames + ['pct_elec_hvac', 'pct_gas_hvac', 'pct_steam_hvac', 'pct_other_hvac']
        
        with open(OUTPUT_FILE, 'w', newline='') as f_out:
            writer = csv.DictWriter(f_out, fieldnames=fieldnames)
            writer.writeheader()
            
            for row in reader:
                building_type = row.get('building type', '')
                climate_zone = row.get('ENERGY STAR Climate Zone', '')
                
                # Get fuel usage to determine which columns to populate
                elec_use = safe_float(row.get('electricity_use_kbtu', 0))
                gas_use = safe_float(row.get('natural_gas_use_kbtu', ''))
                steam_use = safe_float(row.get('district_steam_use_kbtu', ''))
                other_use = safe_float(row.get('other_fuels_use_kbtu', ''))
                
                # Get HVAC percentages
                # Electric - always present
                if elec_use > 0:
                    pct_elec, method_elec = get_hvac_pct(building_type, climate_zone, 'elec', 
                                                          benchmarks_pba_climate, benchmarks_pba_only)
                    row['pct_elec_hvac'] = f"{pct_elec:.4f}" if pct_elec is not None else ''
                else:
                    row['pct_elec_hvac'] = ''
                
                # Gas - only if building uses it
                if gas_use > 0:
                    pct_gas, method_gas = get_hvac_pct(building_type, climate_zone, 'gas',
                                                        benchmarks_pba_climate, benchmarks_pba_only)
                    row['pct_gas_hvac'] = f"{pct_gas:.4f}" if pct_gas is not None else ''
                else:
                    row['pct_gas_hvac'] = ''
                
                # Steam - only if building uses it
                if steam_use > 0:
                    pct_steam, method_steam = get_hvac_pct(building_type, climate_zone, 'steam',
                                                            benchmarks_pba_climate, benchmarks_pba_only)
                    row['pct_steam_hvac'] = f"{pct_steam:.4f}" if pct_steam is not None else ''
                else:
                    row['pct_steam_hvac'] = ''
                
                # Other fuels (fuel oil) - only if building uses it
                if other_use > 0:
                    pct_other, method_other = get_hvac_pct(building_type, climate_zone, 'other',
                                                            benchmarks_pba_climate, benchmarks_pba_only)
                    row['pct_other_hvac'] = f"{pct_other:.4f}" if pct_other is not None else ''
                else:
                    row['pct_other_hvac'] = ''
                
                writer.writerow(row)
                rows_processed += 1
                
                if rows_processed % 5000 == 0:
                    print(f"  Processed {rows_processed} buildings...")
    
    print(f"\nComplete! Processed {rows_processed} buildings.")
    print(f"Output saved to: {OUTPUT_FILE}")
    
    # Summary statistics
    print("\n" + "="*60)
    print("SUMMARY STATISTICS")
    print("="*60)
    
    # Re-read to compute stats
    elec_pcts = []
    gas_pcts = []
    steam_pcts = []
    other_pcts = []
    
    with open(OUTPUT_FILE, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['pct_elec_hvac']:
                elec_pcts.append(float(row['pct_elec_hvac']))
            if row['pct_gas_hvac']:
                gas_pcts.append(float(row['pct_gas_hvac']))
            if row['pct_steam_hvac']:
                steam_pcts.append(float(row['pct_steam_hvac']))
            if row['pct_other_hvac']:
                other_pcts.append(float(row['pct_other_hvac']))
    
    def print_stats(name, values):
        if not values:
            print(f"{name}: No data")
            return
        values.sort()
        n = len(values)
        mean = sum(values) / n
        median = values[n // 2]
        p25 = values[int(n * 0.25)]
        p75 = values[int(n * 0.75)]
        print(f"{name}:")
        print(f"  Count: {n:,}")
        print(f"  Mean:  {mean:.1%}")
        print(f"  Median: {median:.1%}")
        print(f"  25th-75th percentile: {p25:.1%} - {p75:.1%}")
    
    print_stats("Electric HVAC %", elec_pcts)
    print()
    print_stats("Gas HVAC %", gas_pcts)
    print()
    print_stats("Steam HVAC %", steam_pcts)
    print()
    print_stats("Other Fuels (Fuel Oil) HVAC %", other_pcts)


if __name__ == '__main__':
    main()
