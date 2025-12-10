# HANDOFF - Nationwide Prospector Script Fixes

**Created:** 2024-12-10
**Status:** BUGS IDENTIFIED, READY TO FIX

---

## ⛔ ABSOLUTE RULES - READ FIRST ⛔

```
┌─────────────────────────────────────────────────────────────────────────┐
│  1. NEVER EDIT MASTER CSV DIRECTLY                                      │
│     Path: /Users/forrestmiller/Desktop/nationwide-prospector/           │
│           data/source/portfolio_data.csv                                │
│     TEST IN TEST_SANDBOX/ FIRST!                                        │
│                                                                         │
│  2. USER HATES OVER-PLANNING                                            │
│     - No todo lists                                                     │
│     - No "should I do X?"                                               │
│     - Just execute immediately                                          │
│                                                                         │
│  3. WHEN USER SAYS STOP → STOP IMMEDIATELY                              │
│                                                                         │
│  4. READ THE DOCS IN /docs/methodology/ - THEY ARE THE SOURCE OF TRUTH  │
│     The previous handoff had WRONG emission factors!                    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## WHAT NEEDS TO BE DONE (3 TASKS)

### TASK 1: Fix 04_carbon_by_city.py emission factors
### TASK 2: Rewrite 01_hvac_pct.py (broken paths + column names)
### TASK 3: Delete 3 broken scripts from data_updates/

---

## TASK 1: FIX 04_carbon_by_city.py

**File:** `/Users/forrestmiller/Desktop/nationwide-prospector/scripts/populate_master/04_carbon_by_city.py`

**Problem:** Lines 33-43 have WRONG emission factors

**REPLACE lines 33-43 with this EXACT code:**

```python
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
    'DEFAULT':       {'electricity': 0.0000922,  'gas': 0.00005311, 'steam': 0.00004493, 'fuel_oil': 0.00007315},
}
```

**WHY these are correct:**
- Seattle electricity is 0.0000029 (98% hydropower - very clean)
- St. Louis/Chicago electricity is 0.0001649 (coal-heavy SRMW region - dirty)
- DEFAULT is 0.0000922 (US national average)
- Source: EPA eGRID 2023

---

## TASK 2: REWRITE 01_hvac_pct.py

**File:** `/Users/forrestmiller/Desktop/nationwide-prospector/scripts/populate_master/01_hvac_pct.py`

**Problem:** Script is COMPLETELY BROKEN:
1. Points to non-existent file paths
2. Uses OLD column names from a different project
3. Outputs to wrong location

**THE CURRENT SCRIPT DOES NOT WORK AT ALL.**

**HERE IS THE COMPLETE REPLACEMENT SCRIPT:**

```python
#!/usr/bin/env python3
"""
HVAC Percentage by Fuel Type Calculator
========================================
Calculates hvac_pct_elec, hvac_pct_gas, hvac_pct_steam, hvac_pct_fuel_oil
for each building based on building type, climate zone, and adjustments.

Based on EIA CBECS 2018 data with building-specific adjustments for:
- Energy Star score
- Year built
- EUI vs peer median

Usage: python3 01_hvac_pct.py
"""

import pandas as pd
import numpy as np
from datetime import datetime

# =============================================================================
# CONFIGURATION
# =============================================================================

INPUT_FILE = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv'

# =============================================================================
# CBECS-BASED HVAC PERCENTAGES BY BUILDING TYPE
# Source: EIA CBECS 2018, docs/methodology/HVAC Percentage by Fuel Type.md
# =============================================================================

# Base HVAC percentages by building type (from CBECS 2018)
BASE_HVAC_PCT = {
    # Building Type:        (elec,  gas,   steam, fuel_oil)
    'Office':               (0.45,  0.875, 0.90,  0.79),
    'Medical Office':       (0.45,  0.848, 0.90,  0.61),
    'Mixed Use':            (0.45,  0.80,  0.90,  0.09),
    'Retail Store':         (0.42,  0.777, 0.90,  0.97),
    'Strip Mall':           (0.42,  0.777, 0.90,  0.85),
    'Enclosed Mall':        (0.42,  0.777, 0.90,  0.85),
    'Supermarket/Grocery':  (0.38,  0.70,  0.90,  0.55),
    'Wholesale Club':       (0.38,  0.70,  0.90,  0.55),
    'Hotel':                (0.45,  0.197, 0.53,  0.70),  # Low gas - DHW/cooking
    'Restaurant/Bar':       (0.40,  0.176, 0.90,  0.63),  # Low gas - cooking
    'K-12 School':          (0.45,  0.796, 0.90,  0.90),
    'Higher Ed':            (0.45,  0.796, 0.90,  0.90),
    'Preschool/Daycare':    (0.45,  0.796, 0.90,  0.90),
    'Inpatient Hospital':   (0.48,  0.603, 0.85,  0.54),
    'Specialty Hospital':   (0.48,  0.603, 0.85,  0.54),
    'Outpatient Clinic':    (0.45,  0.848, 0.90,  0.61),
    'Residential Care Facility': (0.45, 0.75, 0.90, 0.42),
    'Laboratory':           (0.50,  0.825, 0.90,  0.13),
    'Gym':                  (0.45,  0.75,  0.90,  0.85),
    'Event Space':          (0.45,  0.75,  0.90,  0.85),
    'Venue':                (0.45,  0.75,  0.90,  0.85),
    'Theater':              (0.45,  0.75,  0.90,  0.85),
    'Arts & Culture':       (0.45,  0.75,  0.90,  0.85),
    'Library':              (0.45,  0.75,  0.90,  0.85),
    'Bank Branch':          (0.45,  0.875, 0.90,  0.79),
    'Vehicle Dealership':   (0.42,  0.75,  0.90,  0.96),
    'Courthouse':           (0.45,  0.75,  0.90,  0.67),
    'Public Service':       (0.45,  0.75,  0.90,  0.67),
    'Police Station':       (0.45,  0.75,  0.90,  0.67),
    'Fire Station':         (0.45,  0.75,  0.90,  0.67),
    'Public Transit':       (0.45,  0.75,  0.90,  0.67),
    'Sports/Gaming Center': (0.45,  0.75,  0.90,  0.85),
    'Data Center':          (0.42,  0.00,  0.00,  0.00),  # Cooling only, no gas HVAC
    'DEFAULT':              (0.45,  0.75,  0.90,  0.75),
}

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


def get_base_hvac_pct(building_type):
    """Get base HVAC percentages for a building type."""
    return BASE_HVAC_PCT.get(building_type, BASE_HVAC_PCT['DEFAULT'])


def calculate_adjustment(row, peer_stats):
    """
    Calculate building-specific adjustment based on:
    - Energy Star score (absolute thresholds)
    - Year built
    - EUI vs peer median

    Returns adjustment factor (-0.12 to +0.12)
    """
    # 1. Energy Star score adjustment
    score = safe_float(row.get('energy_star_score'))
    score_adj = 0.0
    if score is not None:
        if score >= 90:
            score_adj = -0.05  # Very efficient
        elif score >= 75:
            score_adj = 0.0   # Good
        elif score >= 50:
            score_adj = +0.03  # Below average
        else:
            score_adj = +0.05  # Poor efficiency

    # 2. Year built adjustment
    year = safe_float(row.get('bldg_year_built'))
    year_adj = 0.0
    if year is not None:
        if year < 1970:
            year_adj = +0.04  # Old building
        elif year < 1990:
            year_adj = +0.02
        elif year >= 2010:
            year_adj = -0.03  # New building

    # 3. EUI vs peer median adjustment
    eui = safe_float(row.get('energy_site_eui'))
    bldg_type = row.get('bldg_type', '')
    eui_adj = 0.0

    if eui is not None and eui > 0 and bldg_type in peer_stats:
        peer_median = peer_stats[bldg_type]
        if peer_median and peer_median > 0:
            eui_ratio = eui / peer_median
            if eui_ratio > 1.5:
                eui_adj = +0.06
            elif eui_ratio > 1.2:
                eui_adj = +0.03
            elif eui_ratio < 0.7:
                eui_adj = -0.04
            elif eui_ratio < 0.85:
                eui_adj = -0.02

    # Combined adjustment (capped at +/- 0.12)
    total_adj = max(-0.12, min(0.12, score_adj + year_adj + eui_adj))
    return total_adj


def calculate_hvac_pct(row, peer_stats):
    """Calculate HVAC percentages for a single building."""
    bldg_type = row.get('bldg_type', '')
    climate = row.get('energy_climate_zone', '')

    # Get energy values
    elec = safe_float(row.get('energy_elec_kbtu'), 0)
    gas = safe_float(row.get('energy_gas_kbtu'), 0)
    steam = safe_float(row.get('energy_steam_kbtu'), 0)
    fuel_oil = safe_float(row.get('energy_fuel_oil_kbtu'), 0)

    # Get base percentages
    base_elec, base_gas, base_steam, base_oil = get_base_hvac_pct(bldg_type)

    # Calculate adjustment
    adj = calculate_adjustment(row, peer_stats)

    # Data Center special case
    if bldg_type == 'Data Center':
        return (
            0.42 if elec > 0 else None,
            0.0 if gas > 0 else None,
            0.0 if steam > 0 else None,
            0.0 if fuel_oil > 0 else None,
            'data_center'
        )

    # Calculate adjusted percentages
    pct_elec = None
    pct_gas = None
    pct_steam = None
    pct_oil = None

    if elec > 0:
        pct_elec = base_elec + adj
        # All-electric buildings need higher electric HVAC (heating)
        if gas == 0 and steam == 0:
            if climate in ['Northern', 'North-Central']:
                pct_elec = min(pct_elec + 0.15, 0.65)
            elif climate == 'South-Central':
                pct_elec = min(pct_elec + 0.08, 0.55)
        # 15% minimum floor for ventilation fans, pumps, controls
        pct_elec = round(max(0.15, min(0.70, pct_elec)), 4)

    if gas > 0:
        pct_gas = base_gas + adj
        # Hotel/Restaurant special handling (low gas HVAC due to DHW/cooking)
        if bldg_type == 'Hotel':
            pct_gas = round(max(0.08, min(0.35, pct_gas)), 4)
        elif bldg_type == 'Restaurant/Bar':
            pct_gas = round(max(0.10, min(0.28, pct_gas)), 4)
        else:
            # Climate adjustment for Southern (less heating)
            if climate == 'Southern':
                pct_gas = pct_gas * 0.85
            pct_gas = round(max(0.40, min(0.98, pct_gas)), 4)

    if steam > 0:
        pct_steam = base_steam + (adj * 0.3)  # Dampened adjustment
        if bldg_type == 'Hotel':
            pct_steam = 0.53
        pct_steam = round(max(0.50, min(1.0, pct_steam)), 4)

    if fuel_oil > 0:
        pct_oil = base_oil + (adj * 0.3)  # Dampened adjustment
        pct_oil = round(max(0.05, min(1.0, pct_oil)), 4)

    return (pct_elec, pct_gas, pct_steam, pct_oil, 'cbecs_adjusted')


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("HVAC Percentage by Fuel Type Calculator")
    print("=" * 60)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Load data
    print(f"\nLoading: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df):,} buildings")

    # Calculate peer median EUI by building type
    print("\nCalculating peer median EUI by building type...")
    peer_stats = df.groupby('bldg_type')['energy_site_eui'].median().to_dict()

    # Calculate HVAC percentages for each building
    print("Calculating HVAC percentages...")

    hvac_results = df.apply(lambda row: calculate_hvac_pct(row, peer_stats), axis=1)

    df['hvac_pct_elec'] = hvac_results.apply(lambda x: x[0])
    df['hvac_pct_gas'] = hvac_results.apply(lambda x: x[1])
    df['hvac_pct_steam'] = hvac_results.apply(lambda x: x[2])
    df['hvac_pct_fuel_oil'] = hvac_results.apply(lambda x: x[3])
    df['hvac_pct_method'] = hvac_results.apply(lambda x: x[4])

    # Summary stats
    print("\n" + "-" * 60)
    print("RESULTS SUMMARY")
    print("-" * 60)

    for col in ['hvac_pct_elec', 'hvac_pct_gas', 'hvac_pct_steam', 'hvac_pct_fuel_oil']:
        valid = df[col].dropna()
        if len(valid) > 0:
            print(f"\n{col}:")
            print(f"  Count:  {len(valid):,}")
            print(f"  Min:    {valid.min():.2%}")
            print(f"  Max:    {valid.max():.2%}")
            print(f"  Mean:   {valid.mean():.2%}")
            print(f"  Median: {valid.median():.2%}")

    # Save
    print(f"\nSaving to: {INPUT_FILE}")
    df.to_csv(INPUT_FILE, index=False)
    print(f"Saved {len(df):,} buildings")

    print("\n" + "=" * 60)
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


if __name__ == '__main__':
    main()
```

---

## TASK 3: DELETE BROKEN SCRIPTS

Run this command:
```bash
rm /Users/forrestmiller/Desktop/nationwide-prospector/scripts/data_updates/calculate_carbon.py
rm /Users/forrestmiller/Desktop/nationwide-prospector/scripts/data_updates/calculate_savings_pct.py
rm /Users/forrestmiller/Desktop/nationwide-prospector/scripts/data_updates/update_retail_savings.py
```

---

## DATA FORMAT - DO NOT CHANGE

Verified actual values in portfolio_data.csv:

| Column | Format | Example | Meaning |
|--------|--------|---------|---------|
| val_cap_rate_pct | Decimal | 0.07 | 7% cap rate |
| hvac_pct_elec | Decimal | 0.45 | 45% of elec is HVAC |
| hvac_pct_gas | Decimal | 0.85 | 85% of gas is HVAC |
| odcv_hvac_savings_pct | Decimal | 0.26 | 26% HVAC savings |
| occ_vacancy_rate | Decimal | 0.15 | 15% vacancy |
| occ_utilization_rate | Decimal | 0.55 | 55% utilization |

**The 06_valuation.py formula `total_opex / cap_rate` is CORRECT.**
**DO NOT add division by 100 - cap_rate is already a decimal.**

---

## SCRIPTS STATUS AFTER FIXES

```
scripts/populate_master/
├── 01_hvac_pct.py       ← REWRITE with code above
├── 02_odcv_savings.py   ✓ OK - don't touch
├── 03_hvac_totals.py    ✓ OK - don't touch
├── 04_carbon_by_city.py ← FIX emission factors only
├── 05_bps_fines.py      ✓ OK - don't touch
├── 06_valuation.py      ✓ OK - don't touch
├── 07_nyc_update.py     ✓ OK - don't touch
└── orchestrate.py       ✓ OK - already created
```

---

## EXECUTION ORDER

```
1. 01_hvac_pct.py       ← Produces hvac_pct_*
2. 02_odcv_savings.py   ← Produces odcv_hvac_savings_pct
3. 03_hvac_totals.py    ← Needs hvac_pct from (1)
4. 04_carbon_by_city.py ← Needs hvac_pct (1), odcv_pct (2)
5. 05_bps_fines.py      ← Needs hvac_pct (1), odcv_pct (2)
6. 06_valuation.py      ← Needs (1), (2), bps_fine (5)
7. 07_nyc_update.py     ← MUST BE LAST (overwrites NYC)
```

---

## TEST PROCEDURE

1. **Copy data to sandbox:**
```bash
cp /Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv /Users/forrestmiller/Desktop/nationwide-prospector/TEST_SANDBOX/
```

2. **Temporarily modify INPUT_FILE in scripts to point to TEST_SANDBOX**

3. **Run orchestrate.py**

4. **Verify output values are in expected ranges**

---

## KEY FILE LOCATIONS

| What | Path |
|------|------|
| Master CSV | `/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv` |
| Test Sandbox | `/Users/forrestmiller/Desktop/nationwide-prospector/TEST_SANDBOX/` |
| Backups | `/Users/forrestmiller/Desktop/nationwide-prospector/BACKUPS_GO_HERE/csv_backups/` |
| Scripts | `/Users/forrestmiller/Desktop/nationwide-prospector/scripts/populate_master/` |
| Methodology Docs | `/Users/forrestmiller/Desktop/nationwide-prospector/docs/methodology/` |

---

## DOCUMENTATION TO READ

These are the SOURCE OF TRUTH:
1. `docs/methodology/DATA_DICTIONARY.md` - Column definitions
2. `docs/methodology/NATIONAL_BPS_METHODOLOGY.md` - Emission factors, BPS laws
3. `docs/methodology/ODCV_SAVINGS_METHODOLOGY_COMPLETE.md` - ODCV calculation
4. `docs/methodology/HVAC Percentage by Fuel Type.md` - HVAC % methodology
5. `docs/methodology/ODCV_Valuation_Impact_Methodology.md` - Valuation formulas

---

## DON'T DO THESE

- ❌ Don't edit master CSV directly
- ❌ Don't change cap_rate calculation (it's correct)
- ❌ Don't use emission factors from the old handoff (they were wrong)
- ❌ Don't ask user "should I do X?" - just do it
- ❌ Don't make todo lists
- ❌ Don't touch 02, 03, 05, 06, 07 scripts (they work)

---

## DO THESE

- ✅ Fix 04_carbon_by_city.py emission factors (copy exact code above)
- ✅ Replace 01_hvac_pct.py completely (copy exact code above)
- ✅ Delete 3 broken scripts from data_updates/
- ✅ Test in TEST_SANDBOX/ first
- ✅ Read the docs if unsure about anything
