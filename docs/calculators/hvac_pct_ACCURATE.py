#!/usr/bin/env python3
"""
HVAC % by Fuel Type - ACCURATE Building-Specific Estimates (v2)

Improvements over v1:
1. ENERGY STAR score adjustment - efficient buildings get lower HVAC %
2. Year built adjustment - older buildings get higher HVAC %
3. EUI vs peer median - high EUI buildings get higher HVAC %

Sources:
- EIA CBECS 2018: https://www.eia.gov/consumption/commercial/
"""

import csv
from collections import defaultdict
from statistics import median

INPUT_FILE = '/Users/forrestmiller/Desktop/Final real/merged_property_matches_updated.csv'
CBECS_FILE = '/Users/forrestmiller/Desktop/Final real/CBECS data/cbecs2018_final_public.csv'
OUTPUT_FILE = '/Users/forrestmiller/Desktop/analysis stage/buildings_hvac_pct_ACCURATE.csv'

# Building type to CBECS PBA mapping
BUILDING_TYPE_TO_PBA = {
    'Office': 2, 'Bank Branch': 2,
    'Laboratory': 4,
    'Supermarket/Grocery': 6,
    'Police Station': 7, 'Fire Station': 7, 'Courthouse': 7,
    'Medical Office': 8, 'Outpatient Clinic': 8,
    'Arts & Culture': 13, 'Theater': 13, 'Event Space': 13, 'Gym': 13, 'Library': 13, 'Sports/Gaming Center': 13,
    'K-12 School': 14, 'Higher Ed': 14, 'Preschool/Daycare': 14,
    'Restaurant/Bar': 15,
    'Inpatient Hospital': 16, 'Specialty Hospital': 16,
    'Residential Care Facility': 17,
    'Hotel': 18,
    'Strip Mall': 23,
    'Enclosed Mall': 24,
    'Retail Store': 25, 'Wholesale Club': 25,
    'Vehicle Dealership': 26, 'Public Service': 26, 'Public Transit': 26,
    'Mixed Use': 91,
    'Data Center': 'DC',
}

PUBCLIM_TO_ZONE = {1: 'Northern', 2: 'North-Central', 3: 'South-Central', 4: 'Southern', 5: 'Northern'}


def safe_float(val, default=None):
    if val is None or str(val).strip() in ['', 'NA', 'N/A', '.', 'None', 'null']:
        return default
    try:
        return float(val)
    except:
        return default


def compute_peer_stats(buildings):
    """Compute EUI median, score percentiles, year median for each (type × climate) peer group."""
    peer_data = defaultdict(lambda: {'eui': [], 'score': [], 'year': []})

    for b in buildings:
        bt = b.get('building type', '')
        climate = b.get('ENERGY STAR Climate Zone', '')
        key = (bt, climate)

        eui = safe_float(b.get('site_eui'))
        score = safe_float(b.get('energy_star_score'))
        year = safe_float(b.get('year_built'))

        if eui and eui > 0:
            peer_data[key]['eui'].append(eui)
        if score and 1 <= score <= 100:
            peer_data[key]['score'].append(score)
        if year and 1800 < year <= 2025:
            peer_data[key]['year'].append(year)

    # Convert to stats
    peer_stats = {}
    for key, d in peer_data.items():
        stats = {}
        if d['eui']:
            sorted_eui = sorted(d['eui'])
            stats['eui_median'] = median(sorted_eui)
        if d['score']:
            sorted_score = sorted(d['score'])
            n = len(sorted_score)
            stats['score_p25'] = sorted_score[n // 4]
            stats['score_p75'] = sorted_score[3 * n // 4]
        if d['year']:
            stats['year_median'] = median(d['year'])
        peer_stats[key] = stats

    return peer_stats


def compute_cbecs_benchmarks(cbecs_file):
    """Compute HVAC % from CBECS by (PBA × climate) for each fuel."""
    data = defaultdict(lambda: {
        'elec_hvac': 0, 'elec_total': 0,
        'gas_hvac': 0, 'gas_total': 0,
        'steam_hvac': 0, 'steam_total': 0,
        'oil_hvac': 0, 'oil_total': 0,
        'n': 0
    })
    national = defaultdict(lambda: {
        'elec_hvac': 0, 'elec_total': 0,
        'gas_hvac': 0, 'gas_total': 0,
        'steam_hvac': 0, 'steam_total': 0,
        'oil_hvac': 0, 'oil_total': 0,
        'n': 0
    })

    with open(cbecs_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            pba = int(safe_float(row.get('PBA', -1), -1))
            if pba < 0:
                continue
            pubclim = int(safe_float(row.get('PUBCLIM', -1), -1))
            climate = PUBCLIM_TO_ZONE.get(pubclim)
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

            fk_ht = safe_float(row.get('FKHTBTU', 0), 0)
            fk_cl = safe_float(row.get('FKCLBTU', 0), 0)
            fk_tot = safe_float(row.get('FKBTU', 0), 0)

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

            if fk_tot > 0:
                data[key]['oil_hvac'] += weight * (fk_ht + fk_cl)
                data[key]['oil_total'] += weight * fk_tot
                national[pba]['oil_hvac'] += weight * (fk_ht + fk_cl)
                national[pba]['oil_total'] += weight * fk_tot

            data[key]['n'] += 1
            national[pba]['n'] += 1

    benchmarks = {}
    for key, d in data.items():
        benchmarks[key] = {
            'elec': d['elec_hvac'] / d['elec_total'] if d['elec_total'] > 0 else None,
            'gas': d['gas_hvac'] / d['gas_total'] if d['gas_total'] > 0 else None,
            'steam': d['steam_hvac'] / d['steam_total'] if d['steam_total'] > 0 else None,
            'oil': d['oil_hvac'] / d['oil_total'] if d['oil_total'] > 0 else None,
            'n': d['n']
        }

    national_benchmarks = {}
    for pba, d in national.items():
        national_benchmarks[pba] = {
            'elec': d['elec_hvac'] / d['elec_total'] if d['elec_total'] > 0 else None,
            'gas': d['gas_hvac'] / d['gas_total'] if d['gas_total'] > 0 else None,
            'steam': d['steam_hvac'] / d['steam_total'] if d['steam_total'] > 0 else None,
            'oil': d['oil_hvac'] / d['oil_total'] if d['oil_total'] > 0 else None,
            'n': d['n']
        }

    return benchmarks, national_benchmarks


def get_hvac_pct(bldg, benchmarks, national_benchmarks, peer_stats):
    """Get HVAC % for each fuel with building-specific adjustments."""
    bt = bldg.get('building type', '')
    climate = bldg.get('ENERGY STAR Climate Zone', '')

    elec = safe_float(bldg.get('electricity_use_kbtu'), 0) or 0
    gas = safe_float(bldg.get('natural_gas_use_kbtu'), 0) or 0
    steam = safe_float(bldg.get('district_steam_use_kbtu'), 0) or 0
    oil = safe_float(bldg.get('other_fuels_use_kbtu'), 0) or 0
    sqft = safe_float(bldg.get('square_footage'), 0) or 0
    eui = safe_float(bldg.get('site_eui'), 0) or 0
    score = safe_float(bldg.get('energy_star_score'))
    year = safe_float(bldg.get('year_built'))
    total_energy = elec + gas + steam + oil

    pba = BUILDING_TYPE_TO_PBA.get(bt, 2)
    peer_key = (bt, climate)
    peer = peer_stats.get(peer_key, {})

    # Data Center special handling
    if pba == 'DC':
        return {
            'pct_elec_hvac': 0.42 if elec > 0 else None,
            'pct_gas_hvac': 0.0 if gas > 0 else None,
            'pct_steam_hvac': 0.0 if steam > 0 else None,
            'pct_other_hvac': 0.0 if oil > 0 else None,
            'method': 'data_center'
        }

    # === COMPUTE ADJUSTMENT FACTORS ===
    # Based on HVAC_ELECTRICITY_DISAGGREGATION_METHODOLOGY.md

    # 1. ENERGY STAR Score adjustment (absolute thresholds, not peer-relative)
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

    results = {'method': 'cbecs_adjusted'}

    # ==== ELECTRIC HVAC % ====
    if elec > 0:
        pct_elec = bench.get('elec')
        if pct_elec is None:
            pct_elec = nat.get('elec')
            if pct_elec is None:
                pct_elec = 0.40

        # Fuel-heated vs electric-heated distinction
        # Buildings with gas/steam: electric HVAC is mainly cooling + fans (lower in winter)
        # All-electric buildings: electric HVAC includes heating (much higher)
        if gas == 0 and steam == 0:
            # All-electric building - likely has electric heat
            if climate in ['Northern', 'North-Central']:
                pct_elec = min(pct_elec + 0.15, 0.65)  # Significant electric heating
            elif climate == 'South-Central':
                pct_elec = min(pct_elec + 0.08, 0.55)  # Some electric heating
        # else: fuel-heated, electric is mainly cooling/ventilation (base CBECS value)

        # Apply building-specific adjustment
        pct_elec = pct_elec + total_adj

        # 15% minimum floor - ventilation fans, pumps, controls always running
        results['pct_elec_hvac'] = round(min(max(pct_elec, 0.15), 0.70), 4)
    else:
        results['pct_elec_hvac'] = None

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
            # Apply adjustment but keep in hotel range
            pct_gas = pct_gas + (total_adj * 0.5)  # Dampen adjustment for hotels
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

        results['pct_gas_hvac'] = round(pct_gas, 4)
    else:
        results['pct_gas_hvac'] = None

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
        results['pct_steam_hvac'] = round(min(max(pct_steam, 0.50), 1.0), 4)
    else:
        results['pct_steam_hvac'] = None

    # ==== FUEL OIL HVAC % ====
    if oil > 0:
        oil_by_type = {
            'Laboratory': 0.125, 'Mixed Use': 0.091,
            'Nursing': 0.419, 'Residential Care Facility': 0.419,
            'Inpatient Hospital': 0.537, 'Specialty Hospital': 0.537,
            'Supermarket/Grocery': 0.552,
            'Medical Office': 0.612, 'Outpatient Clinic': 0.612,
            'Restaurant/Bar': 0.626,
            'Police Station': 0.674, 'Fire Station': 0.674, 'Courthouse': 0.674,
            'Hotel': 0.696,
            'Office': 0.789, 'Bank Branch': 0.789,
            'Arts & Culture': 0.847, 'Theater': 0.847, 'Event Space': 0.847,
            'Gym': 0.847, 'Library': 0.847, 'Sports/Gaming Center': 0.847,
            'K-12 School': 0.896, 'Higher Ed': 0.896, 'Preschool/Daycare': 0.896,
            'Vehicle Dealership': 0.963, 'Public Service': 0.963, 'Public Transit': 0.963,
            'Retail Store': 0.974, 'Wholesale Club': 0.974,
            'Strip Mall': 0.85, 'Enclosed Mall': 0.85,
        }

        pct_oil = oil_by_type.get(bt, 0.75)

        # Tiny oil fraction = likely backup generator
        if total_energy > 0 and (oil / total_energy) < 0.03:
            pct_oil = 0.30

        # Apply adjustment (dampened)
        pct_oil = pct_oil + (total_adj * 0.3)
        results['pct_other_hvac'] = round(min(max(pct_oil, 0.05), 1.0), 4)
    else:
        results['pct_other_hvac'] = None

    return results


def main():
    print("Loading buildings...")
    buildings = []
    with open(INPUT_FILE, 'r') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            buildings.append(row)
    print(f"  {len(buildings):,} buildings")

    print("\nComputing peer group stats...")
    peer_stats = compute_peer_stats(buildings)
    print(f"  {len(peer_stats)} peer groups")

    print("\nLoading CBECS benchmarks...")
    benchmarks, national_benchmarks = compute_cbecs_benchmarks(CBECS_FILE)
    print(f"  {len(benchmarks)} (type × climate) combinations")

    print("\nEstimating HVAC % by fuel (with building-specific adjustments)...")
    for bldg in buildings:
        results = get_hvac_pct(bldg, benchmarks, national_benchmarks, peer_stats)
        bldg.update(results)

    print("\nWriting output...")
    # Slim output - just building_id and HVAC columns
    output_cols = ['building_id', 'pct_elec_hvac', 'pct_gas_hvac', 'pct_steam_hvac', 'pct_other_hvac', 'method']

    with open(OUTPUT_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=output_cols, extrasaction='ignore')
        writer.writeheader()
        for bldg in buildings:
            writer.writerow(bldg)

    print(f"\nOutput: {OUTPUT_FILE}")

    # Summary stats
    print("\n" + "=" * 80)
    print("SUMMARY - HVAC % BY FUEL TYPE (with adjustments)")
    print("=" * 80)

    for fuel in ['elec', 'gas', 'steam', 'other']:
        col = f'pct_{fuel}_hvac'
        vals = [float(b[col]) for b in buildings if b.get(col) is not None]
        if vals:
            vals.sort()
            n = len(vals)
            print(f"\npct_{fuel}_hvac (n={n:,}):")
            print(f"  Mean: {100 * sum(vals) / n:.1f}%")
            print(f"  Median: {100 * vals[n // 2]:.1f}%")
            print(f"  P10-P90: {100 * vals[int(n * 0.1)]:.1f}% - {100 * vals[int(n * 0.9)]:.1f}%")

    # Show adjustment impact
    print("\n" + "=" * 80)
    print("ADJUSTMENT IMPACT - Sample buildings")
    print("=" * 80)

    # Find buildings with extreme adjustments
    sample_types = ['Office', 'Hotel', 'K-12 School']
    for bt in sample_types:
        bt_buildings = [b for b in buildings if b.get('building type') == bt]
        if len(bt_buildings) >= 10:
            gas_vals = [(b, float(b['pct_gas_hvac'])) for b in bt_buildings if b.get('pct_gas_hvac')]
            if gas_vals:
                gas_vals.sort(key=lambda x: x[1])
                low = gas_vals[0]
                high = gas_vals[-1]
                print(f"\n{bt}:")
                print(f"  Lowest gas HVAC: {100*low[1]:.1f}% (score={low[0].get('energy_star_score', 'N/A')}, year={low[0].get('year_built', 'N/A')})")
                print(f"  Highest gas HVAC: {100*high[1]:.1f}% (score={high[0].get('energy_star_score', 'N/A')}, year={high[0].get('year_built', 'N/A')})")


if __name__ == '__main__':
    main()
