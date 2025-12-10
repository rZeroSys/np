# HANDOFF - Nationwide Prospector

**Last Updated:** 2024-12-10
**Status:** Ready for file reorganization + new scripts

---

## ⚠️ ABSOLUTE RULES ⚠️

```
┌────────────────────────────────────────────────────────────────────────┐
│  1. NEVER EDIT MASTER CSV DIRECTLY                                     │
│     Path: /Users/forrestmiller/Desktop/nationwide-prospector/          │
│           data/source/portfolio_data.csv                               │
│     You test in TEST_SANDBOX/. User runs scripts on master.            │
│                                                                        │
│  2. USER HATES OVER-PLANNING                                           │
│     - No todo lists                                                    │
│     - No "should I do X?"                                              │
│     - No discussing approaches                                         │
│     - Just execute immediately                                         │
│                                                                        │
│  3. WHEN USER SAYS STOP → STOP IMMEDIATELY                             │
│     - Don't finish current command                                     │
│     - Don't "just wrap up"                                             │
│     - STOP                                                             │
│                                                                        │
│  4. USER COMMUNICATION STYLE                                           │
│     - Types fast with typos                                            │
│     - Uses CAPS for emphasis                                           │
│     - Gets frustrated with delays                                      │
│     - Respond with ACTION not discussion                               │
└────────────────────────────────────────────────────────────────────────┘
```

---

## PROJECT OVERVIEW

### What This Is
Database of **23,882 commercial buildings** across the US with energy consumption data. Used to calculate potential savings from ODCV (Occupancy-Driven Control Ventilation) systems.

### What ODCV Is
Smart HVAC controls that reduce heating/cooling based on real-time occupancy. Different from traditional systems that run at fixed schedules regardless of whether anyone is in the building.

### Business Value
Show building owners/investors:
1. **HVAC Savings:** How much they'd save on heating/cooling with ODCV
2. **Fine Avoidance:** How much they'd save on BPS (Building Performance Standard) penalties
3. **Valuation Impact:** How much building value increases from reduced operating costs

### Portfolio Totals
| Metric | Value |
|--------|-------|
| Total Buildings | 23,882 |
| Total ODCV Savings | $2.87B/year |
| Total BPS Fines Avoided | $834M/year |
| Total Valuation Impact | $39.6B |
| NYC Buildings | 2,387 (from LL97 data) |

---

## YOUR 4 TASKS

### Task 1: Reorganize Files + Fix Paths

**Current State (messy):**
```
scripts/
├── data_updates/           # Calculator scripts (some with wrong paths)
│   ├── hvac_pct_ACCURATE.py
│   ├── calculate_hvac_totals.py
│   ├── calculate_odcv_savings.py
│   ├── calculate_carbon.py        # DELETE - replace with city-specific
│   ├── calculate_savings_pct.py   # DELETE - redundant
│   ├── calculate_valuation_impact.py
│   ├── national_bps_calculator.py
│   ├── update_nyc_buildings.py
│   └── update_retail_savings.py   # DELETE - broken
├── images/
├── logos/
└── utils/
```

**Target State (clean):**
```
scripts/
├── populate_master/              # ALL scripts that WRITE to master CSV
│   ├── orchestrate.py            # NEW - runs all in correct order
│   ├── 01_hvac_pct.py
│   ├── 02_odcv_savings.py
│   ├── 03_hvac_totals.py
│   ├── 04_carbon_by_city.py      # NEW - city-specific emission factors
│   ├── 05_bps_fines.py
│   ├── 06_valuation.py
│   └── 07_nyc_update.py          # MUST BE LAST
├── images/                       # Keep as-is
├── logos/                        # Keep as-is
└── utils/                        # Keep as-is
```

**Commands to audit first:**
```bash
# Find all Python files
find /Users/forrestmiller/Desktop/nationwide-prospector -name "*.py" -type f | grep -v __pycache__

# Check what references master CSV
grep -r "portfolio_data" --include="*.py" .

# Check for broken imports
grep -r "from docs.calculators" --include="*.py" .
grep -r "data_updates" --include="*.py" .
```

---

### Task 2: Delete Broken Scripts

```bash
# Delete these:
rm scripts/data_updates/update_retail_savings.py    # Broken - wrong column names
rm scripts/data_updates/calculate_carbon.py         # Replace with city-specific
rm scripts/data_updates/calculate_savings_pct.py    # Redundant - valuation handles this
```

---

### Task 3: Write City-Specific Carbon Script

**Problem:** Current carbon calculation uses US average emission factors. But electricity grids vary dramatically by city.

**Create:** `scripts/populate_master/04_carbon_by_city.py`

**City Emission Factors (tCO2e per kBtu):**

```python
CITY_EMISSION_FACTORS = {
    # BPS Cities - use their grid-specific factors
    'New York': {
        'electricity': 0.000084689,   # NYC grid (cleaner than US avg)
        'gas': 0.00005311,
        'steam': 0.00004493,
        'fuel_oil': 0.00007315,
    },
    'Boston': {
        'electricity': 0.000084689,   # ISO-NE grid (same as NYC)
        'gas': 0.00005311,
        'steam': 0.00004493,
        'fuel_oil': 0.00007315,
    },
    'Cambridge': {
        'electricity': 0.000084689,   # ISO-NE grid
        'gas': 0.00005311,
        'steam': 0.00004493,
        'fuel_oil': 0.00007315,
    },
    'Washington': {
        'electricity': 0.000082,      # PJM grid
        'gas': 0.00005311,
        'steam': 0.00004493,
        'fuel_oil': 0.00007315,
    },
    'Denver': {
        'electricity': 0.000095,      # Xcel Energy (more coal)
        'gas': 0.00005311,
        'steam': 0.00004493,
        'fuel_oil': 0.00007315,
    },
    'Seattle': {
        'electricity': 0.000035,      # Seattle City Light (hydro - very clean!)
        'gas': 0.00005311,
        'steam': 0.00004493,
        'fuel_oil': 0.00007315,
    },
    'San Francisco': {
        'electricity': 0.000040,      # CA grid (very clean)
        'gas': 0.00005311,
        'steam': 0.00004493,
        'fuel_oil': 0.00007315,
    },
    'St. Louis': {
        'electricity': 0.000090,      # Ameren (more coal)
        'gas': 0.00005311,
        'steam': 0.00004493,
        'fuel_oil': 0.00007315,
    },
    'DEFAULT': {
        'electricity': 0.0000847,     # US average
        'gas': 0.00005311,            # Same everywhere (combustion)
        'steam': 0.00004493,          # Same everywhere (combustion)
        'fuel_oil': 0.00007315,       # Same everywhere (combustion)
    }
}
```

**Script Logic:**
```python
def get_emission_factors(city):
    """Get emission factors for a city, DEFAULT if not BPS city."""
    if pd.isna(city) or city == '':
        return CITY_EMISSION_FACTORS['DEFAULT']

    city_clean = str(city).strip().title()

    # Direct match
    if city_clean in CITY_EMISSION_FACTORS:
        return CITY_EMISSION_FACTORS[city_clean]

    # Partial match (e.g., "New York City" → "New York")
    for key in CITY_EMISSION_FACTORS:
        if key in city_clean or city_clean in key:
            return CITY_EMISSION_FACTORS[key]

    return CITY_EMISSION_FACTORS['DEFAULT']

def calculate_row(row):
    factors = get_emission_factors(row['loc_city'])

    # Safe float conversion
    def sf(val):
        try: return float(val) if pd.notna(val) else 0.0
        except: return 0.0

    # Total emissions
    emissions = (
        sf(row['energy_elec_kbtu']) * factors['electricity'] +
        sf(row['energy_gas_kbtu']) * factors['gas'] +
        sf(row['energy_steam_kbtu']) * factors['steam'] +
        sf(row['energy_fuel_oil_kbtu']) * factors['fuel_oil']
    )

    # ODCV carbon reduction (only HVAC portion)
    odcv_pct = sf(row['odcv_hvac_savings_pct'])
    reduction = (
        sf(row['energy_elec_kbtu']) * sf(row['hvac_pct_elec']) * odcv_pct * factors['electricity'] +
        sf(row['energy_gas_kbtu']) * sf(row['hvac_pct_gas']) * odcv_pct * factors['gas'] +
        sf(row['energy_steam_kbtu']) * sf(row['hvac_pct_steam']) * odcv_pct * factors['steam'] +
        sf(row['energy_fuel_oil_kbtu']) * sf(row['hvac_pct_fuel_oil']) * odcv_pct * factors['fuel_oil']
    )

    return pd.Series({
        'carbon_emissions_total_mt': round(emissions, 4),
        'odcv_carbon_reduction_yr1_mt': round(reduction, 4)
    })
```

---

### Task 4: Write Master Orchestration Script

**Create:** `scripts/populate_master/orchestrate.py`

This is the most important script. It runs all calculators in the correct dependency order.

---

## SCRIPT EXECUTION ORDER (VERIFIED)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DEPENDENCY GRAPH                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  1. 01_hvac_pct.py                                               │   │
│  │     INPUT:  energy_star_score, bldg_type (BASE DATA ONLY)        │   │
│  │     OUTPUT: hvac_pct_elec, hvac_pct_gas, hvac_pct_steam,         │   │
│  │             hvac_pct_fuel_oil                                    │   │
│  │     WHY 1ST: Everything else needs these percentages             │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                                    ▼                                     │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  2. 02_odcv_savings.py                                           │   │
│  │     INPUT:  energy_star_score, energy_site_eui, bldg_type,       │   │
│  │             bldg_sqft, bldg_year_built, occ_* (BASE DATA)        │   │
│  │     OUTPUT: odcv_hvac_savings_pct                                │   │
│  │     WHY 2ND: Carbon, BPS, Valuation all need this percentage     │   │
│  │     NOTE:   Does NOT need hvac_pct - uses building characteristics│   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                                    ▼                                     │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  3. 03_hvac_totals.py                                            │   │
│  │     INPUT:  energy_*, cost_*, hvac_pct_* (from step 1)           │   │
│  │     OUTPUT: hvac_energy_total_kbtu, hvac_cost_total_annual       │   │
│  │     WHY 3RD: For reporting (valuation recalculates internally)   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                    ┌───────────────┴───────────────┐                    │
│                    ▼                               ▼                    │
│  ┌─────────────────────────────┐   ┌─────────────────────────────┐     │
│  │  4. 04_carbon_by_city.py    │   │  5. 05_bps_fines.py         │     │
│  │  INPUT:  energy_*,          │   │  INPUT:  energy_*,          │     │
│  │          hvac_pct_* (1),    │   │          hvac_pct_* (1),    │     │
│  │          odcv_pct (2),      │   │          odcv_pct (2),      │     │
│  │          loc_city           │   │          loc_city           │     │
│  │  OUTPUT: carbon_*           │   │  OUTPUT: bps_fine_*,        │     │
│  │                             │   │          bps_law_name       │     │
│  │  (can run parallel w/ 5)    │   │  (can run parallel w/ 4)    │     │
│  └─────────────────────────────┘   └─────────────────────────────┘     │
│                                                   │                     │
│                                                   ▼                     │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  6. 06_valuation.py                                              │   │
│  │     INPUT:  cost_*, hvac_pct_* (1), odcv_hvac_savings_pct (2),   │   │
│  │             bps_fine_avoided_yr1_usd (5)  ← CRITICAL DEPENDENCY  │   │
│  │     OUTPUT: odcv_hvac_savings_annual_usd,                        │   │
│  │             savings_opex_avoided_annual_usd,                     │   │
│  │             val_odcv_impact_usd, val_current_usd, val_post_odcv  │   │
│  │     WHY 6TH: MUST have BPS fines to calculate total savings      │   │
│  │     NOTE:   Calculates dollar savings itself (not from hvac_tot) │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                                    ▼                                     │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  7. 07_nyc_update.py                    *** MUST BE LAST ***     │   │
│  │     INPUT:  /Users/forrestmiller/Desktop/ll97/                   │   │
│  │             10_year_savings_20241209.csv (1,119 NYC buildings)   │   │
│  │     OUTPUT: Overwrites MANY columns for NYC buildings with       │   │
│  │             fresh data from LL97 source file                     │   │
│  │     WHY LAST: If not last, other scripts overwrite NYC data!     │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Why This Exact Order?

| Step | Script | Depends On | Produces | Critical Note |
|------|--------|------------|----------|---------------|
| 1 | hvac_pct | Base data only | hvac_pct_* | Foundation for everything |
| 2 | odcv_savings | Base data only | odcv_hvac_savings_pct | Does NOT need hvac_pct! |
| 3 | hvac_totals | hvac_pct (1) | hvac_*_total | For reporting |
| 4 | carbon | hvac_pct (1), odcv_pct (2) | carbon_* | City-specific factors |
| 5 | bps_fines | hvac_pct (1), odcv_pct (2) | bps_fine_* | Valuation needs this |
| 6 | valuation | hvac_pct (1), odcv_pct (2), **bps_fine (5)** | val_*, savings_* | **AFTER BPS!** |
| 7 | nyc_update | LL97 source file | Overwrites NYC rows | **ABSOLUTELY LAST** |

### Key Insight
**Valuation script (step 6) calculates `odcv_hvac_savings_annual_usd` internally** - it doesn't read `hvac_cost_total_annual`. But it DOES read `bps_fine_avoided_yr1_usd`, so BPS must run first.

---

## ORCHESTRATION SCRIPT TEMPLATE

```python
#!/usr/bin/env python3
"""
Master Orchestration Script
============================
Runs all derived-column calculators in correct dependency order.

CRITICAL: This order is verified and must not change!
  1. hvac_pct      → hvac_pct_* columns
  2. odcv_savings  → odcv_hvac_savings_pct
  3. hvac_totals   → hvac_*_total columns
  4. carbon        → carbon_* columns (city-specific)
  5. bps_fines     → bps_* columns
  6. valuation     → val_*, savings_*, odcv_dollar (NEEDS BPS FIRST)
  7. nyc_update    → NYC overwrite (MUST BE LAST)

Usage: python3 orchestrate.py
"""

import subprocess
import sys
import shutil
import pandas as pd
from datetime import datetime
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_DIR = Path('/Users/forrestmiller/Desktop/nationwide-prospector')
MASTER_CSV = BASE_DIR / 'data/source/portfolio_data.csv'
BACKUP_DIR = BASE_DIR / 'BACKUPS_GO_HERE/csv_backups'
SCRIPTS_DIR = BASE_DIR / 'scripts/populate_master'

# Scripts in EXACT execution order - DO NOT CHANGE ORDER
SCRIPTS = [
    ('01_hvac_pct.py',      'HVAC percentages by fuel type'),
    ('02_odcv_savings.py',  'ODCV savings percentage'),
    ('03_hvac_totals.py',   'HVAC energy and cost totals'),
    ('04_carbon_by_city.py','Carbon emissions (city-specific)'),
    ('05_bps_fines.py',     'BPS fine avoidance'),
    ('06_valuation.py',     'Valuation impact (NEEDS BPS FIRST)'),
    ('07_nyc_update.py',    'NYC data refresh (MUST BE LAST)'),
]

CRITICAL_COLUMNS = [
    'hvac_pct_elec',
    'hvac_pct_gas',
    'hvac_cost_total_annual',
    'odcv_hvac_savings_pct',
    'odcv_hvac_savings_annual_usd',
    'carbon_emissions_total_mt',
    'bps_fine_avoided_yr1_usd',
    'savings_opex_avoided_annual_usd',
    'val_odcv_impact_usd',
]

EXPECTED_TOTALS = {
    'odcv_hvac_savings_annual_usd': (2_500_000_000, 3_200_000_000),  # $2.5-3.2B
    'bps_fine_avoided_yr1_usd': (700_000_000, 950_000_000),          # $700M-950M
    'val_odcv_impact_usd': (35_000_000_000, 45_000_000_000),         # $35-45B
}

# =============================================================================
# FUNCTIONS
# =============================================================================

def log(msg, level='INFO'):
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {level}: {msg}")

def create_backup():
    """Create timestamped backup before any changes."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = BACKUP_DIR / f'portfolio_data_backup_{timestamp}.csv'
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(MASTER_CSV, backup_path)
    log(f"Backup created: {backup_path.name}")
    return backup_path

def run_script(script_name, description):
    """Run a single script and return success/failure."""
    script_path = SCRIPTS_DIR / script_name

    if not script_path.exists():
        log(f"MISSING: {script_name}", 'ERROR')
        return False

    print(f"\n{'='*70}")
    print(f"  STEP: {script_name}")
    print(f"  {description}")
    print('='*70)

    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=False,
        cwd=str(BASE_DIR)
    )

    if result.returncode != 0:
        log(f"FAILED: {script_name}", 'ERROR')
        return False

    log(f"Completed: {script_name}", 'OK')
    return True

def validate_results():
    """Check for issues in critical columns."""
    log("Running validation...")
    df = pd.read_csv(MASTER_CSV, low_memory=False)

    issues = []

    # Check row count
    if len(df) != 23882:
        issues.append(f"Row count: {len(df)} (expected 23,882)")

    # Check for NaN in critical columns
    for col in CRITICAL_COLUMNS:
        if col not in df.columns:
            issues.append(f"MISSING COLUMN: {col}")
        else:
            nan_count = df[col].isna().sum()
            if nan_count > 100:  # Allow some NaN
                issues.append(f"{col}: {nan_count:,} NaN values")

    # Check totals are in expected range
    for col, (min_val, max_val) in EXPECTED_TOTALS.items():
        if col in df.columns:
            total = df[col].sum()
            if total < min_val or total > max_val:
                issues.append(f"{col} total: ${total:,.0f} (expected ${min_val:,.0f}-${max_val:,.0f})")

    # Check NYC buildings
    nyc_count = df['id_building'].str.startswith('NYC_').sum()
    if nyc_count < 2000:
        issues.append(f"NYC buildings: {nyc_count} (expected ~2,387)")

    return issues

def print_summary():
    """Print summary statistics."""
    df = pd.read_csv(MASTER_CSV, low_memory=False)

    print(f"\n{'='*70}")
    print("  SUMMARY")
    print('='*70)
    print(f"  Total buildings:        {len(df):,}")
    print(f"  ODCV savings/year:      ${df['odcv_hvac_savings_annual_usd'].sum():,.0f}")
    print(f"  BPS fines avoided/year: ${df['bps_fine_avoided_yr1_usd'].sum():,.0f}")
    print(f"  Valuation impact:       ${df['val_odcv_impact_usd'].sum():,.0f}")
    print(f"  NYC buildings:          {df['id_building'].str.startswith('NYC_').sum():,}")
    print('='*70)

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("\n" + "="*70)
    print("  MASTER ORCHESTRATION SCRIPT")
    print("  Running all calculators in dependency order")
    print("="*70)
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Master CSV: {MASTER_CSV}")
    print("="*70)

    # Step 0: Backup
    backup_path = create_backup()

    # Run each script in order
    for i, (script_name, description) in enumerate(SCRIPTS, 1):
        log(f"Starting step {i}/7: {script_name}")

        success = run_script(script_name, description)

        if not success:
            print(f"\n{'!'*70}")
            print(f"  FAILED AT STEP {i}: {script_name}")
            print(f"  Restore from backup: {backup_path}")
            print(f"{'!'*70}\n")
            sys.exit(1)

    # Validate results
    print(f"\n{'='*70}")
    print("  VALIDATION")
    print('='*70)

    issues = validate_results()

    if issues:
        print("\n  ISSUES FOUND:")
        for issue in issues:
            print(f"    - {issue}")
        print(f"\n  Review results carefully. Backup: {backup_path}")
    else:
        print("  All validations passed!")

    # Print summary
    print_summary()

    print(f"\n  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70 + "\n")

if __name__ == '__main__':
    main()
```

---

## ALL 70 COLUMNS (ACTIVE SCHEMA)

### Identifiers (id_)
| Column | Type | Description |
|--------|------|-------------|
| `id_building` | str | Unique ID: "NYC_1000160125", "BOS_100001" |
| `id_property_name` | str | Building name |
| `id_source_plant_id` | str | Original ID from source |
| `id_source_url` | str | URL to source data |

### Location (loc_)
| Column | Type | Description |
|--------|------|-------------|
| `loc_address` | str | Street address |
| `loc_city` | str | City (**used for emission factors**) |
| `loc_state` | str | State abbreviation |
| `loc_zip` | str | ZIP code |
| `loc_lat` | float | Latitude |
| `loc_lon` | float | Longitude |

### Building (bldg_)
| Column | Type | Description |
|--------|------|-------------|
| `bldg_type` | str | "Office", "Hotel", "K-12 School", etc. |
| `bldg_type_filter` | str | Simplified type for UI filtering |
| `bldg_type_benchmark` | str | Type for Energy Star benchmark |
| `bldg_vertical` | str | Market vertical |
| `bldg_sqft` | int | Gross square footage |
| `bldg_year_built` | int | Year constructed |

### Organizations (org_)
| Column | Type | Description |
|--------|------|-------------|
| `org_owner` | str | Building owner |
| `org_manager` | str | Property manager |
| `org_tenant` | str | Primary tenant |
| `org_tenant_subunit` | str | Tenant sub-organization |

### Energy (energy_)
| Column | Type | Description |
|--------|------|-------------|
| `energy_elec_kbtu` | float | Annual electricity (kBtu) |
| `energy_elec_kwh` | float | Annual electricity (kWh) |
| `energy_gas_kbtu` | float | Annual natural gas (kBtu) |
| `energy_steam_kbtu` | float | Annual district steam (kBtu) |
| `energy_fuel_oil_kbtu` | float | Annual fuel oil (kBtu) |
| `energy_total_kbtu` | float | Total site energy |
| `energy_site_eui` | float | Site EUI (kBtu/sqft) |
| `energy_eui_benchmark` | float | Median EUI for building type |
| `energy_star_score` | int | Energy Star score (1-100) |
| `energy_climate_zone` | str | ASHRAE climate zone |

### Costs (cost_)
| Column | Type | Description |
|--------|------|-------------|
| `cost_elec_rate_kwh` | float | Electricity rate ($/kWh) |
| `cost_elec_rate_demand_kw` | float | Demand charge ($/kW) |
| `cost_elec_peak_kw` | float | Estimated peak demand |
| `cost_elec_load_factor` | float | Load factor |
| `cost_elec_energy_annual` | float | Annual elec energy cost |
| `cost_elec_demand_annual` | float | Annual elec demand cost |
| `cost_elec_total_annual` | float | Total annual elec cost |
| `cost_gas_rate_therm` | float | Gas rate ($/therm) |
| `cost_gas_annual` | float | Annual gas cost |
| `cost_steam_rate_mlb` | float | Steam rate ($/Mlb) |
| `cost_steam_annual` | float | Annual steam cost |
| `cost_fuel_oil_rate_gal` | float | Fuel oil rate ($/gal) |
| `cost_fuel_oil_annual` | float | Annual fuel oil cost |
| `cost_utility_name` | str | Utility company |
| `cost_calc_notes` | str | Cost calculation notes |

### HVAC (hvac_) - **CALCULATED BY SCRIPT 1 & 3**
| Column | Type | Description |
|--------|------|-------------|
| `hvac_pct_elec` | float | % of elec for HVAC (0.0-1.0) |
| `hvac_pct_gas` | float | % of gas for HVAC |
| `hvac_pct_steam` | float | % of steam for HVAC (~0.92) |
| `hvac_pct_fuel_oil` | float | % of fuel oil for HVAC |
| `hvac_pct_method` | str | Calculation method |
| `hvac_energy_total_kbtu` | float | Total HVAC energy |
| `hvac_cost_total_annual` | float | Total HVAC cost |

### Carbon (carbon_) - **CALCULATED BY SCRIPT 4**
| Column | Type | Description |
|--------|------|-------------|
| `carbon_emissions_total_mt` | float | Annual GHG (metric tons CO2e) |

### Occupancy (occ_)
| Column | Type | Description |
|--------|------|-------------|
| `occ_vacancy_rate` | float | Vacancy rate (0.0-1.0) |
| `occ_utilization_rate` | float | Utilization rate |

### ODCV Savings (odcv_) - **CALCULATED BY SCRIPT 2 & 6**
| Column | Type | Description |
|--------|------|-------------|
| `odcv_hvac_savings_pct` | float | % HVAC cost saved (0.20-0.50) |
| `odcv_hvac_savings_annual_usd` | float | Annual $ saved |
| `odcv_carbon_reduction_yr1_mt` | float | Carbon reduction (MT CO2e) |

### BPS (bps_) - **CALCULATED BY SCRIPT 5**
| Column | Type | Description |
|--------|------|-------------|
| `bps_law_name` | str | "NYC LL97", "Boston BERDO", etc. |
| `bps_fine_avoided_yr1_usd` | float | Annual fine avoided |

### Combined Savings (savings_) - **CALCULATED BY SCRIPT 6**
| Column | Type | Description |
|--------|------|-------------|
| `savings_opex_avoided_annual_usd` | float | ODCV + BPS combined |
| `savings_pct_of_energy_cost` | float | Savings as % of energy |

### Valuation (val_) - **CALCULATED BY SCRIPT 6**
| Column | Type | Description |
|--------|------|-------------|
| `val_cap_rate_pct` | float | Cap rate for building type |
| `val_market_rent_sqft` | float | Market rent ($/sqft) |
| `val_opex_ratio` | float | Operating expense ratio |
| `val_current_usd` | float | Current building value |
| `val_odcv_impact_usd` | float | Value increase from ODCV |
| `val_post_odcv_usd` | float | Value after ODCV |

### Metadata (meta_)
| Column | Type | Description |
|--------|------|-------------|
| `meta_photo_url` | str | Building photo URL |

---

## ALL FORMULAS

### HVAC Percentages (Script 1)
```python
# From CBECS 2018 data, adjusted by building characteristics
hvac_pct_elec = base_pct × energy_star_modifier × year_modifier × eui_modifier
# Typical: 15-60% (higher in mild climates)

hvac_pct_gas = base_pct × modifiers  # Typical: 60-90% (most gas is heating)
hvac_pct_steam = ~0.92              # Steam is almost always HVAC
hvac_pct_fuel_oil = ~0.66           # Fuel oil is mostly heating
```

### ODCV Savings Percentage (Script 2)
```python
# Varies by building type:
#   Office: 20-40%
#   K-12 School: 20-45%
#   Hotel: 15-30%
#   Hospital: 5-15%
#   Data Center: 0% (can't reduce cooling)

odcv_hvac_savings_pct = (
    floor +
    (opportunity_score × automation_score × range) ×
    modifiers
)

# Where:
#   floor = minimum for building type
#   opportunity_score = f(vacancy_rate, utilization_rate)
#   automation_score = f(year_built, sqft)
#   modifiers = climate_zone adjustment
```

### HVAC Totals (Script 3)
```python
hvac_energy_total_kbtu = (
    energy_elec_kbtu × hvac_pct_elec +
    energy_gas_kbtu × hvac_pct_gas +
    energy_steam_kbtu × hvac_pct_steam +
    energy_fuel_oil_kbtu × hvac_pct_fuel_oil
)

hvac_cost_total_annual = (
    cost_elec_total_annual × hvac_pct_elec +
    cost_gas_annual × hvac_pct_gas +
    cost_steam_annual × hvac_pct_steam +
    cost_fuel_oil_annual × hvac_pct_fuel_oil
)
```

### Carbon Emissions (Script 4)
```python
# USE CITY-SPECIFIC FACTORS!
factors = get_emission_factors(loc_city)

carbon_emissions_total_mt = (
    energy_elec_kbtu × factors['electricity'] +
    energy_gas_kbtu × factors['gas'] +
    energy_steam_kbtu × factors['steam'] +
    energy_fuel_oil_kbtu × factors['fuel_oil']
)

odcv_carbon_reduction_yr1_mt = (
    energy_elec_kbtu × hvac_pct_elec × odcv_pct × factors['electricity'] +
    energy_gas_kbtu × hvac_pct_gas × odcv_pct × factors['gas'] +
    energy_steam_kbtu × hvac_pct_steam × odcv_pct × factors['steam'] +
    energy_fuel_oil_kbtu × hvac_pct_fuel_oil × odcv_pct × factors['fuel_oil']
)
```

### BPS Fines (Script 5)
```python
# Each city has different rules:
#   NYC LL97:      $268/tCO2e over emissions cap
#   Boston BERDO: $234/tCO2e over cap
#   DC BEPS:      $10/sqft if below Energy Star threshold
#   Denver:       $0.30/kBtu over EUI target
#   Seattle:      $10/sqft per 5-year cycle
#   St. Louis:    $500/day non-compliance

bps_fine_avoided_yr1_usd = fine_without_odcv - fine_with_odcv
```

### Valuation (Script 6)
```python
# Cap rates by building type:
#   Office: 7.5%
#   Retail: 6.25%
#   Hotel: 8.0%
#   Industrial: 6.5%

# VALUATION SCRIPT CALCULATES THIS INTERNALLY:
odcv_hvac_savings_annual_usd = (
    cost_elec × hvac_pct_elec × odcv_pct +
    cost_gas × hvac_pct_gas × odcv_pct +
    cost_steam × hvac_pct_steam × odcv_pct +
    cost_fuel_oil × hvac_pct_fuel_oil × odcv_pct
)

# Combined savings (NEEDS BPS FINE FROM SCRIPT 5!)
savings_opex_avoided_annual_usd = odcv_hvac_savings_annual_usd + bps_fine_avoided_yr1_usd

# Valuation impact
val_odcv_impact_usd = savings_opex_avoided_annual_usd / (val_cap_rate_pct / 100)

# Example: $100K savings / 7.5% cap rate = $1.33M value increase
```

---

## BPS CITIES DETAIL

| City | Law | Year | Penalty | Electricity Factor | Buildings |
|------|-----|------|---------|-------------------|-----------|
| NYC | Local Law 97 | 2024 | $268/tCO2e | 0.000084689 | 2,387 |
| Boston | BERDO 2.0 | 2025 | $234/tCO2e | 0.000084689 | ~300 |
| Cambridge | BEUDO | 2025 | $234/tCO2e | 0.000084689 | ~50 |
| Washington DC | BEPS | 2021 | $10/sqft | 0.000082 | ~200 |
| Denver | Energize Denver | 2024 | $0.30/kBtu | 0.000095 | ~100 |
| Seattle | BEPS | 2027 | $10/sqft | 0.000035 | ~150 |
| St. Louis | BEPS | 2025 | $500/day | 0.000090 | ~50 |
| San Francisco | EBEPO | TBD | Reporting | 0.000040 | ~200 |

---

## FILE LOCATIONS

### Data Files
| File | Path | Description |
|------|------|-------------|
| **Master CSV** | `data/source/portfolio_data.csv` | 23,882 buildings, 70 columns |
| Column Lookup | `data/source/column_rename_lookup.csv` | Old→new name mapping |
| NYC Source | `/Users/forrestmiller/Desktop/ll97/10_year_savings_20241209.csv` | 1,119 NYC LL97 buildings |

### Test/Backup
| Folder | Purpose |
|--------|---------|
| `TEST_SANDBOX/` | Copy files here to test scripts safely |
| `BACKUPS_GO_HERE/csv_backups/` | All backups go here |

---

## COMMON PITFALLS

```
┌─────────────────────────────────────────────────────────────────────────┐
│  DON'T DO THESE:                                                        │
├─────────────────────────────────────────────────────────────────────────┤
│  ✗ Use US average emission factors for BPS cities                       │
│  ✗ Run NYC script before valuation (NYC overwrites, must be last)       │
│  ✗ Run valuation before BPS (valuation needs bps_fine)                  │
│  ✗ Forget to handle NaN values (use pd.notna() or safe_float)           │
│  ✗ Hardcode paths that break after moves                                │
│  ✗ Create backups in data/source/ (use BACKUPS_GO_HERE/)                │
│  ✗ Modify master CSV directly (test in sandbox first)                   │
│  ✗ Make todo lists or ask questions (user hates this - just execute)    │
│  ✗ Continue after user says STOP                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## VERIFICATION

After running orchestrate.py, verify:

```python
import pandas as pd
df = pd.read_csv('data/source/portfolio_data.csv', low_memory=False)

# Row count
assert len(df) == 23882, f"Expected 23,882 rows, got {len(df)}"

# No NaN in critical columns
for col in ['hvac_pct_elec', 'odcv_hvac_savings_pct', 'val_odcv_impact_usd']:
    assert df[col].isna().sum() < 100, f"{col} has too many NaN"

# Totals in expected range
assert 2_500_000_000 < df['odcv_hvac_savings_annual_usd'].sum() < 3_200_000_000
assert 700_000_000 < df['bps_fine_avoided_yr1_usd'].sum() < 950_000_000
assert 35_000_000_000 < df['val_odcv_impact_usd'].sum() < 45_000_000_000

# NYC buildings present
assert df['id_building'].str.startswith('NYC_').sum() > 2000

print("All validations passed!")
```

---

## QUICK START

```bash
cd /Users/forrestmiller/Desktop/nationwide-prospector

# 1. See current state
ls -la scripts/data_updates/

# 2. Find all Python files
find . -name "*.py" -type f | grep -v __pycache__ | head -30

# 3. Check master CSV columns
head -1 data/source/portfolio_data.csv | tr ',' '\n' | head -20

# 4. Verify a sample building
python3 -c "
import pandas as pd
df = pd.read_csv('data/source/portfolio_data.csv')
row = df[df['id_building']=='NYC_1000160125'].iloc[0]
print(f\"Building: {row['id_building']}\")
print(f\"ODCV %: {row['odcv_hvac_savings_pct']:.2%}\")
print(f\"ODCV \$: \${row['odcv_hvac_savings_annual_usd']:,.0f}\")
print(f\"BPS Fine: \${row['bps_fine_avoided_yr1_usd']:,.0f}\")
print(f\"Val Impact: \${row['val_odcv_impact_usd']:,.0f}\")
"
```

---

## NOW DO THE 4 TASKS

1. **Reorganize files** → clean structure with `scripts/populate_master/`
2. **Delete broken scripts** → retail, old carbon, savings_pct
3. **Write city-specific carbon script** → use emission factors above
4. **Write orchestration script** → use template above

Don't discuss. Execute.
