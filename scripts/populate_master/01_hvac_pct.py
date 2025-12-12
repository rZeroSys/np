#!/usr/bin/env python3
"""
HVAC Percentage Calculator
==========================
Calculates HVAC % by fuel type for each building using CBECS 2018 benchmarks
with building-specific adjustments.

Output columns:
- hvac_pct_elec: % of electricity used for HVAC
- hvac_pct_gas: % of natural gas used for HVAC
- hvac_pct_steam: % of district steam used for HVAC
- hvac_pct_fuel_oil: % of fuel oil used for HVAC (fixed at 93%)
- hvac_pct_method: 'cbecs_adjusted' or 'data_center'

Adjustments applied (elec/gas/steam):
- Energy Star Score: -5% (90+) to +5% (<50)
- Year Built: -3% (2010+) to +4% (<1970)
- EUI vs Peer Median: -4% (<0.7x) to +6% (>1.5x)
- Combined cap: +/- 12%

Sources:
- EIA CBECS 2018: https://www.eia.gov/consumption/commercial/
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import shutil

# =============================================================================
# CONFIGURATION
# =============================================================================

INPUT_FILE = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv'
CBECS_FILE = '/Users/forrestmiller/Desktop/Final real/CBECS data/cbecs2018_final_public.csv'
BACKUP_DIR = '/Users/forrestmiller/Desktop/nationwide-prospector/BACKUPS_GO_HERE/csv_backups'

# Building type to CBECS PBA mapping
BUILDING_TYPE_TO_PBA = {
    'Office': 2, 'Bank Branch': 2,
    'Laboratory': 4,
    'Supermarket/Grocery': 6,
    'Police Station': 7, 'Fire Station': 7, 'Courthouse': 7,
    'Medical Office': 8, 'Outpatient Clinic': 8,
    'Arts & Culture': 13, 'Theater': 13, 'Event Space': 13, 'Gym': 13,
    'Library': 13, 'Library/Museum': 13, 'Sports/Gaming Center': 13,
    'K-12 School': 14, 'Higher Ed': 14, 'Preschool/Daycare': 14,
    'Restaurant/Bar': 15,
    'Inpatient Hospital': 16, 'Specialty Hospital': 16,
    'Residential Care Facility': 17, 'Residential Care': 17,
    'Hotel': 18,
    'Strip Mall': 23,
    'Enclosed Mall': 24,
    'Retail Store': 25, 'Wholesale Club': 25,
    'Vehicle Dealership': 26, 'Public Service': 26, 'Public Transit': 26,
    'Mixed Use': 91,
    'Venue': 13,
    'Data Center': 'DC',
}

PUBCLIM_TO_ZONE = {1: 'Northern', 2: 'North-Central', 3: 'South-Central', 4: 'Southern', 5: 'Northern'}

# Fixed fuel oil HVAC % for all buildings
FUEL_OIL_HVAC_PCT = 0.93


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


def compute_cbecs_benchmarks(cbecs_file):
    """Compute HVAC % from CBECS by (PBA x climate) for each fuel."""
    from collections import defaultdict

    data = defaultdict(lambda: {
        'elec_hvac': 0, 'elec_total': 0,
        'gas_hvac': 0, 'gas_total': 0,
        'steam_hvac': 0, 'steam_total': 0,
        'n': 0
    })
    national = defaultdict(lambda: {
        'elec_hvac': 0, 'elec_total': 0,
        'gas_hvac': 0, 'gas_total': 0,
        'steam_hvac': 0, 'steam_total': 0,
        'n': 0
    })

    cbecs_df = pd.read_csv(cbecs_file, low_memory=False)

    for _, row in cbecs_df.iterrows():
        pba = safe_float(row.get('PBA', -1), -1)
        if pba < 0:
            continue
        pba = int(pba)

        pubclim = safe_float(row.get('PUBCLIM', -1), -1)
        if pubclim < 0:
            continue
        climate = PUBCLIM_TO_ZONE.get(int(pubclim))
        if not climate:
            continue

        weight = safe_float(row.get('FINALWT', 1), 1) or 1

        el_ht = safe_float(row.get('ELHTBTU', 0), 0)
        el_cl = safe_float(row.get('ELCLBTU', 0), 0)
        el_vn = safe_float(row.get('ELVNBTU', 0), 0)
        el_tot = safe_float(row.get('ELBTU', 0), 0)

        ng_ht = safe_float(row.get('NGHTBTU', 0), 0)
        ng_cl = safe_float(row.get('NGCLBTU', 0), 0)
        ng_tot = safe_float(row.get('NGBTU', 0), 0)

        dh_ht = safe_float(row.get('DHHTBTU', 0), 0)
        dh_cl = safe_float(row.get('DHCLBTU', 0), 0)
        dh_tot = safe_float(row.get('DHBTU', 0), 0)

        key = (pba, climate)

        if el_tot > 0:
            data[key]['elec_hvac'] += weight * (el_ht + el_cl + el_vn)
            data[key]['elec_total'] += weight * el_tot
            national[pba]['elec_hvac'] += weight * (el_ht + el_cl + el_vn)
            national[pba]['elec_total'] += weight * el_tot

        if ng_tot > 0:
            data[key]['gas_hvac'] += weight * (ng_ht + ng_cl)
            data[key]['gas_total'] += weight * ng_tot
            national[pba]['gas_hvac'] += weight * (ng_ht + ng_cl)
            national[pba]['gas_total'] += weight * ng_tot

        if dh_tot > 0:
            data[key]['steam_hvac'] += weight * (dh_ht + dh_cl)
            data[key]['steam_total'] += weight * dh_tot
            national[pba]['steam_hvac'] += weight * (dh_ht + dh_cl)
            national[pba]['steam_total'] += weight * dh_tot

        data[key]['n'] += 1
        national[pba]['n'] += 1

    benchmarks = {}
    for key, d in data.items():
        benchmarks[key] = {
            'elec': d['elec_hvac'] / d['elec_total'] if d['elec_total'] > 0 else None,
            'gas': d['gas_hvac'] / d['gas_total'] if d['gas_total'] > 0 else None,
            'steam': d['steam_hvac'] / d['steam_total'] if d['steam_total'] > 0 else None,
            'n': d['n']
        }

    national_benchmarks = {}
    for pba, d in national.items():
        national_benchmarks[pba] = {
            'elec': d['elec_hvac'] / d['elec_total'] if d['elec_total'] > 0 else None,
            'gas': d['gas_hvac'] / d['gas_total'] if d['gas_total'] > 0 else None,
            'steam': d['steam_hvac'] / d['steam_total'] if d['steam_total'] > 0 else None,
            'n': d['n']
        }

    return benchmarks, national_benchmarks


def compute_peer_stats(df):
    """Compute EUI median for each (type x climate) peer group."""
    peer_stats = {}

    for (bt, climate), group in df.groupby(['bldg_type', 'energy_climate_zone']):
        eui_vals = group['energy_site_eui'].dropna()
        eui_vals = eui_vals[eui_vals > 0]

        if len(eui_vals) > 0:
            peer_stats[(bt, climate)] = {'eui_median': eui_vals.median()}
        else:
            peer_stats[(bt, climate)] = {}

    return peer_stats


def calculate_hvac_pct(row, benchmarks, national_benchmarks, peer_stats):
    """Calculate HVAC % for each fuel with building-specific adjustments."""
    bt = row.get('bldg_type', '')
    climate = row.get('energy_climate_zone', '')

    elec = safe_float(row.get('energy_elec_kbtu'), 0) or 0
    gas = safe_float(row.get('energy_gas_kbtu'), 0) or 0
    steam = safe_float(row.get('energy_steam_kbtu'), 0) or 0
    oil = safe_float(row.get('energy_fuel_oil_kbtu'), 0) or 0
    sqft = safe_float(row.get('bldg_sqft'), 0) or 0
    eui = safe_float(row.get('energy_site_eui'), 0) or 0
    score = safe_float(row.get('energy_star_score'))
    year = safe_float(row.get('bldg_year_built'))

    pba = BUILDING_TYPE_TO_PBA.get(bt, 2)
    peer_key = (bt, climate)
    peer = peer_stats.get(peer_key, {})

    # Data Center special handling
    if pba == 'DC':
        return {
            'hvac_pct_elec': 0.42 if elec > 0 else None,
            'hvac_pct_gas': 0.0 if gas > 0 else None,
            'hvac_pct_steam': 0.0 if steam > 0 else None,
            'hvac_pct_fuel_oil': 0.0 if oil > 0 else None,
            'hvac_pct_method': 'data_center'
        }

    # === COMPUTE ADJUSTMENT FACTORS ===

    # 1. ENERGY STAR Score adjustment (absolute thresholds)
    score_adj = 0.0
    if score:
        if score >= 90:
            score_adj = -0.05  # Very efficient
        elif score >= 75:
            score_adj = 0.0   # Good
        elif score >= 50:
            score_adj = +0.03  # Below average
        else:
            score_adj = +0.05  # Poor efficiency

    # 2. Year built adjustment (-0.03 to +0.04)
    year_adj = 0.0
    if year:
        if year < 1970:
            year_adj = +0.04  # Old building, less efficient HVAC
        elif year < 1990:
            year_adj = +0.02
        elif year >= 2010:
            year_adj = -0.03  # New building, more efficient HVAC

    # 3. EUI vs peer median adjustment (-0.04 to +0.06)
    eui_adj = 0.0
    if eui > 0 and 'eui_median' in peer and peer['eui_median'] > 0:
        eui_ratio = eui / peer['eui_median']
        if eui_ratio > 1.5:
            eui_adj = +0.06  # High EUI = likely higher HVAC %
        elif eui_ratio > 1.2:
            eui_adj = +0.03
        elif eui_ratio < 0.7:
            eui_adj = -0.04  # Low EUI = likely lower HVAC %
        elif eui_ratio < 0.85:
            eui_adj = -0.02

    # Combined adjustment (capped at +/- 0.12)
    total_adj = max(-0.12, min(0.12, score_adj + year_adj + eui_adj))

    # Get CBECS benchmark
    key = (pba, climate)
    bench = benchmarks.get(key, {})
    nat = national_benchmarks.get(pba, {})

    results = {'hvac_pct_method': 'cbecs_adjusted'}

    # ==== ELECTRIC HVAC % ====
    if elec > 0:
        pct_elec = bench.get('elec')
        if pct_elec is None:
            pct_elec = nat.get('elec')
            if pct_elec is None:
                pct_elec = 0.40

        # Fuel-heated vs electric-heated distinction
        if gas == 0 and steam == 0:
            # All-electric building - likely has electric heat
            if climate in ['Northern', 'North-Central']:
                pct_elec = min(pct_elec + 0.15, 0.65)
            elif climate == 'South-Central':
                pct_elec = min(pct_elec + 0.08, 0.55)

        # Apply building-specific adjustment
        pct_elec = pct_elec + total_adj

        # 15% minimum floor - ventilation fans, pumps, controls always running
        results['hvac_pct_elec'] = round(min(max(pct_elec, 0.15), 0.70), 4)
    else:
        results['hvac_pct_elec'] = None

    # ==== GAS HVAC % ====
    if gas > 0:
        pct_gas = bench.get('gas')
        if pct_gas is None:
            pct_gas = nat.get('gas')
            if pct_gas is None:
                pct_gas = 0.75

        # Hotels: 19.7% HVAC, varies by intensity
        if bt == 'Hotel' and sqft > 0:
            gas_intensity = gas / sqft
            if gas_intensity < 15:
                pct_gas = 0.12
            elif gas_intensity < 30:
                pct_gas = 0.18
            elif gas_intensity < 50:
                pct_gas = 0.22
            else:
                pct_gas = 0.28
            pct_gas = pct_gas + (total_adj * 0.5)
            pct_gas = min(max(pct_gas, 0.08), 0.35)

        # Restaurants: 17.6% HVAC
        elif bt == 'Restaurant/Bar':
            pct_gas = 0.18 + (total_adj * 0.5)
            pct_gas = min(max(pct_gas, 0.10), 0.28)

        else:
            # Climate adjustment
            if climate == 'Southern':
                pct_gas = pct_gas * 0.85
            # Apply building-specific adjustment
            pct_gas = pct_gas + total_adj
            pct_gas = min(max(pct_gas, 0.40), 0.98)

        results['hvac_pct_gas'] = round(pct_gas, 4)
    else:
        results['hvac_pct_gas'] = None

    # ==== STEAM HVAC % ====
    if steam > 0:
        pct_steam = bench.get('steam')
        if pct_steam is None:
            pct_steam = nat.get('steam')
            if pct_steam is None:
                pct_steam = 0.90

        if bt == 'Hotel':
            pct_steam = 0.53
        elif bt in ['Inpatient Hospital', 'Specialty Hospital']:
            pct_steam = 0.85

        # Apply adjustment (dampened for steam - less variability)
        pct_steam = pct_steam + (total_adj * 0.3)
        results['hvac_pct_steam'] = round(min(max(pct_steam, 0.50), 1.0), 4)
    else:
        results['hvac_pct_steam'] = None

    # ==== FUEL OIL HVAC % ====
    # Fixed at 93% for all buildings with fuel oil
    if oil > 0:
        results['hvac_pct_fuel_oil'] = FUEL_OIL_HVAC_PCT
    else:
        results['hvac_pct_fuel_oil'] = None

    return results


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("HVAC Percentage Calculator")
    print("=" * 60)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Load portfolio data
    print(f"\nLoading: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df):,} buildings")

    # Load CBECS benchmarks
    print(f"\nLoading CBECS benchmarks from: {CBECS_FILE}")
    benchmarks, national_benchmarks = compute_cbecs_benchmarks(CBECS_FILE)
    print(f"  {len(benchmarks)} (type x climate) combinations")

    # Compute peer stats
    print("\nComputing peer group stats...")
    peer_stats = compute_peer_stats(df)
    print(f"  {len(peer_stats)} peer groups")

    # Calculate HVAC % for each building
    print("\nCalculating HVAC % for each building...")

    hvac_results = []
    for idx, row in df.iterrows():
        results = calculate_hvac_pct(row, benchmarks, national_benchmarks, peer_stats)
        hvac_results.append(results)

    # Add results to dataframe
    results_df = pd.DataFrame(hvac_results)
    for col in results_df.columns:
        df[col] = results_df[col]

    # Summary stats
    print("\n" + "-" * 60)
    print("RESULTS SUMMARY")
    print("-" * 60)

    for col in ['hvac_pct_elec', 'hvac_pct_gas', 'hvac_pct_steam', 'hvac_pct_fuel_oil']:
        vals = df[col].dropna()
        if len(vals) > 0:
            print(f"\n{col} (n={len(vals):,}):")
            print(f"  Min:    {vals.min():.1%}")
            print(f"  Max:    {vals.max():.1%}")
            print(f"  Mean:   {vals.mean():.1%}")
            print(f"  Median: {vals.median():.1%}")

    # Method counts
    print(f"\nhvac_pct_method:")
    print(df['hvac_pct_method'].value_counts().to_string())

    # Save
    print(f"\nSaving to: {INPUT_FILE}")
    df.to_csv(INPUT_FILE, index=False)
    print(f"Saved {len(df):,} buildings")

    print("\n" + "=" * 60)
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


if __name__ == '__main__':
    main()
