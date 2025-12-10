# National Building Performance Standards (BPS) Calculator
## Methodology Documentation

**Date:** December 1, 2025
**Script:** `national_bps_calculator.py`
**Input:** `ANALYSIS STEP II merged_property_matches_updated.csv`

---

## Executive Summary

This document describes the methodology for calculating carbon emissions reduction and fine avoidance potential for commercial buildings in U.S. cities with Building Performance Standards (BPS). The calculator uses the **cap-based methodology** from the NYC LL97 calculator as the model for all emission-based BPS laws.

### Key Results (Year 1)
- **Total Buildings:** 26,648
- **Total Emissions:** 26,869,259 tCO2e
- **Total Carbon Reduction:** 3,962,911 tCO2e
- **Total Fine Avoidance:** $833,938,936
- **BPS Cities Covered:** 7 jurisdictions (NYC, Boston, Cambridge, DC, Denver, Seattle, St. Louis)

---

## 1. Output Columns Added to CSV

| Column | Description | Data Type |
|--------|-------------|-----------|
| `loc_city` | City name extracted from address | String |
| `bps_law_name` | Name of applicable BPS law (Commercial only) | String |
| `carbon_emissions_total_mt` | Baseline building emissions (city-specific factors) | Float |
| `odcv_carbon_reduction_yr1_mt` | tCO2e reduced via ODCV in Year 1 | Float |
| `bps_fine_avoided_yr1_usd` | $ saved by avoiding BPS fines in Year 1 | Float |

---

## 2. Core Methodology: Emissions from Raw Energy Data

**CRITICAL:** Emissions are calculated from **raw energy data** (kBtu), NOT from pre-calculated emissions columns. This matches the methodology used in the original NYC LL97 HTML calculator.

### 2.1 City-Specific Emission Factors (tCO2e per kBtu)

Emissions are calculated using **city-specific electricity emission factors** based on local grid characteristics and BPS law definitions. Gas and steam factors are standard combustion factors.

| City | Electricity | Gas | Steam | Source |
|------|-------------|-----|-------|--------|
| New York | 0.0000847 | 0.00005311 | 0.00004493 | NYC LL97 (2024-2029) |
| Seattle | 0.0000029 | 0.000053 | 0.000081 | Seattle BEPS (98% hydro) |
| Boston | 0.0000717 | 0.00005311 | 0.00004493 | EPA eGRID NEWE |
| Washington DC | 0.0000794 | 0.00005311 | 0.00004493 | EPA eGRID RFCE |
| Denver | 0.0001378 | 0.00005311 | 0.00004493 | EPA eGRID RMPA |
| San Francisco | 0.0000570 | 0.00005311 | 0.00004493 | EPA eGRID CAMX |
| St. Louis | 0.0001649 | 0.00005311 | 0.00004493 | EPA eGRID SRMW |
| Los Angeles | 0.0000570 | 0.00005311 | 0.00004493 | EPA eGRID CAMX |
| Chicago | 0.0001649 | 0.00005311 | 0.00004493 | EPA eGRID SRMW |
| Portland | 0.0000595 | 0.00005311 | 0.00004493 | EPA eGRID NWPP |
| Atlanta | 0.0000988 | 0.00005311 | 0.00004493 | EPA eGRID SRSO |
| **Default** | 0.0000922 | 0.00005311 | 0.00004493 | US National Average |

**Key Observations:**
- Seattle's grid is **29x cleaner** than NYC (Seattle City Light is ~98% hydroelectric)
- Chicago/St. Louis grids are **2x dirtier** than NYC (coal-heavy SRMW region)
- California cities have cleaner grids than the US average

### 2.2 Baseline Emissions Calculation

```python
# Get city-specific factors
factors = get_emission_factors(city)

baseline_emissions = (
    electricity_use_kbtu × factors['elec'] +
    natural_gas_use_kbtu × factors['gas'] +
    district_steam_use_kbtu × factors['steam']
)
```

### 2.3 ODCV Reduction Applied Per Fuel Type

ODCV savings are applied **per fuel type** based on HVAC percentages:

```python
# Calculate energy reduction per fuel
elec_reduction = electricity_use_kbtu × pct_elec_hvac × odcv_savings_pct
gas_reduction = natural_gas_use_kbtu × pct_gas_hvac × odcv_savings_pct
steam_reduction = district_steam_use_kbtu × pct_steam_hvac × odcv_savings_pct

# Net energy after ODCV
net_elec = electricity_use_kbtu - elec_reduction
net_gas = natural_gas_use_kbtu - gas_reduction
net_steam = district_steam_use_kbtu - steam_reduction

# Carbon reduction (using city-specific factors)
carbon_emissions_reduction_yr1 = (
    elec_reduction × factors['elec'] +
    gas_reduction × factors['gas'] +
    steam_reduction × factors['steam']
)
```

### 2.4 NaN Handling

**Key Rule:** If energy is 0 or NaN for a fuel type, its contribution is 0 regardless of HVAC percentage.

```python
# Safe reduction calculation
elec_reduction = elec × elec_hvac × odcv_pct if elec > 0 else 0
gas_reduction = gas × gas_hvac × odcv_pct if gas > 0 else 0
steam_reduction = steam × steam_hvac × odcv_pct if steam > 0 else 0
```

---

## 3. City Extraction Methodology

Cities are extracted from the `loc_address` field using regex pattern matching:

### Primary Pattern
```
"Street Address, City, STATE, ZIP"
or
"Street Address, City STATE ZIP"
```

### Fallback Strategies
1. **Denver ZIP codes:** 802xx patterns → Denver, CO
2. **ZIP code lookup:** Known edge cases (e.g., 92108 → San Diego)
3. **Embedded state pattern:** "City STATE ZIP" without comma

### Success Rate
- **26,647 / 26,648 rows** (99.996%)

---

## 4. BPS Laws Covered

### Summary Table

| City | Law Name | Fine Type | Fine Rate | Emission/EUI Cap | Min Sqft | Penalty Start |
|------|----------|-----------|-----------|------------------|----------|---------------|
| New York, NY | Local Law 97 | $/tCO2e | $268 | 0.00758 tCO2e/sqft | 25,000 | 2026 |
| Boston, MA | BERDO 2.0 | $/tCO2e | $234 | 0.0053 tCO2e/sqft | 20,000 | 2025 |
| Washington, DC | DC BEPS | $/sqft | $10 (max $7.5M) | ENERGY STAR median | 50,000 | 2026 |
| Denver, CO | Energize Denver | $/kBtu | $0.30 | 48.3 kBtu/sqft | 25,000 | 2028 |
| Seattle, WA | Seattle BEPS | $/sqft | $10 per cycle | 0.00081 tCO2e/sqft | 20,000 | 2031 |
| San Francisco, CA | EBEPO | Daily | $100/day | None (reporting only) | 10,000 | N/A |
| St. Louis, MO | St. Louis BEPS | Daily | $500/day | ~65 kBtu/sqft | 50,000 | 2025 |

---

## 5. Fine Avoidance Calculation by City

### 5.1 NYC Local Law 97 (LL97)

**Law Details:**
- Penalty: $268 per metric ton CO2e over cap
- Cap (2024-2029): 0.00758 tCO2e/sqft for office/commercial
- Minimum building size: 25,000 sqft

**Formula:**
```python
cap = square_footage × 0.00758
baseline_overage = max(0, baseline_emissions - cap)
with_odcv_overage = max(0, with_odcv_emissions - cap)
fine_avoidance = (baseline_overage - with_odcv_overage) × $268
```

**Source:** [NYC LL97](https://www.nyc.gov/site/buildings/codes/ll97-greenhouse-gas-emissions-reductions.page)

---

### 5.2 Boston BERDO 2.0

**Law Details:**
- Penalty: $234/tCO2e Alternative Compliance Payment (ACP)
- Cap (2025-2029): 0.0053 tCO2e/sqft (5.3 kgCO2e/sqft)
- Minimum building size: 20,000 sqft

**Formula:**
```python
cap = square_footage × 0.0053  # tCO2e
baseline_overage = max(0, baseline_emissions - cap)
with_odcv_overage = max(0, with_odcv_emissions - cap)
fine_avoidance = (baseline_overage - with_odcv_overage) × $234
```

**Source:** [Boston BERDO](https://www.boston.gov/departments/environment/berdo)

---

### 5.3 Cambridge BEUDO

**Law Details:**
- Penalty: $234/tCO2e Alternative Compliance Payment (same as Boston BERDO)
- Cap (2025-2029): 0.0053 tCO2e/sqft (5.3 kgCO2e/sqft)
- Minimum building size: 25,000 sqft

**Formula:**
```python
cap = square_footage × 0.0053  # tCO2e
baseline_overage = max(0, baseline_emissions - cap)
with_odcv_overage = max(0, with_odcv_emissions - cap)
fine_avoidance = (baseline_overage - with_odcv_overage) × $234
```

**Source:** [Cambridge BEUDO](https://www.cambridgema.gov/CDD/zoninganddevelopment/sustainablebldgs/beudo)

---

### 5.4 Washington DC BEPS

**Law Details:**
- Penalty: $10/sqft (max $7.5M per property), prorated by compliance gap
- Metric: ENERGY STAR score (office median target = 71)
- Minimum building size: 50,000 sqft

**Formula (using energy_star_score column):**
```python
target_score = 71
current_score = energy_star_score

if current_score >= target_score:
    fine_avoidance = 0  # Already compliant
else:
    gap = target_score - current_score
    odcv_score_improvement = 7  # ~15-30% energy reduction ≈ 7 point improvement
    new_score = min(100, current_score + odcv_score_improvement)

    if new_score >= target_score:
        # ODCV brings building to full compliance
        fine_avoidance = square_footage × $10
    else:
        # Partial improvement - prorated by gap reduction
        fine_avoidance = square_footage × $10 × (odcv_score_improvement / gap)
```

**Source:** [DC BEPS](https://doee.dc.gov/service/building-energy-performance-standards-beps)

---

### 5.4 Denver Energize Denver

**Law Details:**
- Penalty: $0.30/kBtu above EUI target
- Target EUI (Office): 48.3 kBtu/sqft
- Minimum building size: 25,000 sqft

**Formula:**
```python
target_eui = 48.3

# Calculate energy reduction from ODCV (per fuel type)
energy_reduction = (
    elec × elec_hvac × odcv_pct +
    gas × gas_hvac × odcv_pct +
    steam × steam_hvac × odcv_pct
)

# EUI after ODCV
eui_reduction = energy_reduction / square_footage
with_odcv_eui = max(0, site_eui - eui_reduction)

# Fine calculation
baseline_overage_kbtu = max(0, site_eui - target_eui) × square_footage
with_odcv_overage_kbtu = max(0, with_odcv_eui - target_eui) × square_footage
fine_avoidance = (baseline_overage_kbtu - with_odcv_overage_kbtu) × $0.30
```

**Source:** [Denver Energize](https://denvergov.org/Government/Agencies-Departments-Offices/Agencies-Departments-Offices-Directory/Climate-Action-Sustainability-and-Resiliency/Energize-Denver)

---

### 5.5 Seattle BEPS

**Law Details:**
- Penalty: $10/sqft per 5-year compliance cycle
- Cap (2031-2035): 0.00081 tCO2e/sqft (0.81 kgCO2e/sqft)
- Minimum building size: 20,000 sqft
- Uses Seattle-specific emission factors (cleaner grid)

**Seattle Emission Factors (tCO2e/kBtu):**
- Electricity: 0.0000029 (Seattle City Light - very clean)
- Gas: 0.000053
- Steam: 0.000081

**Formula:**
```python
baseline_intensity = baseline_emissions / square_footage
with_odcv_intensity = with_odcv_emissions / square_footage
cap = 0.00081

# Binary: either over cap or not
if baseline_intensity > cap and with_odcv_intensity <= cap:
    fine_avoidance = square_footage × $10 / 5  # Annualized
else:
    fine_avoidance = 0
```

**Source:** [Seattle BEPS](https://www.seattle.gov/environment/climate-change/buildings-and-energy/building-emissions-performance-standard)

---

### 5.6 San Francisco EBEPO

**Law Details:**
- Fine: $100/day (>50k sqft), $50/day (<50k sqft), max 25 days
- **Status: No emission performance standard yet** - reporting ordinance only

**Calculation:**
```python
fine_avoidance = 0  # No cap to exceed
```

**Note:** Carbon reduction is still calculated for SF buildings.

**Source:** [SF EBEPO](https://www.sfenvironment.org/existing-buildings-energy-performance-ordinance)

---

### 5.7 St. Louis BEPS

**Law Details:**
- Penalty: $500/day for non-compliance
- Target EUI: ~65 kBtu/sqft (35th percentile local benchmark)
- Minimum building size: 50,000 sqft

**Formula:**
```python
target_eui = 65

# Calculate EUI after ODCV (same as Denver)
energy_reduction = calc_energy_reduction(elec, gas, steam, odcv_pct, hvac_pcts)
eui_reduction = energy_reduction / square_footage
with_odcv_eui = max(0, site_eui - eui_reduction)

# Binary compliance
if site_eui > target_eui and with_odcv_eui <= target_eui:
    fine_avoidance = $500 × 365  # $182,500/year
else:
    fine_avoidance = 0
```

**Source:** [St. Louis BEPS](https://www.stlouis-mo.gov/government/departments/public-safety/building/building-performance/index.cfm)

---

## 6. Data Quality Fixes Applied

### 6.1 Gas/Steam Energy Edge Cases

**Issue:** 249 buildings had cost > 0 but energy (kBtu) = NaN or 0
- 242 gas records
- 7 steam records

**Fix:** Back-calculated energy from cost using median rates from the dataset:
- Gas: $1.727/therm (1 therm = 100 kBtu)
- Steam: $33.60/Mlb (1 Mlb = 1000 kBtu)

```python
# Gas: energy = cost / rate × 100
natural_gas_use_kbtu = annual_gas_cost / 1.727 × 100

# Steam: energy = cost / rate × 1000
district_steam_use_kbtu = annual_steam_cost / 33.60 × 1000
```

### 6.2 Missing HVAC Percentages

For fixed records, HVAC percentages were set to dataset medians:
- `hvac_pct_gas`: 0.844
- `hvac_pct_steam`: 0.9667

### 6.3 Columns Updated for Fixed Rows

After fixing energy values, these columns were recalculated:
- `energy_total_kbtu`
- `hvac_energy_total_kbtu`
- `hvac_cost_total_annual`
- `odcv_hvac_savings_annual_usd`
- `carbon_emissions_total_mt`
- `odcv_carbon_reduction_yr1_mt`
- `bps_fine_avoided_yr1_usd`

---

## 7. Results Summary

### By BPS Law (Commercial Buildings Only)

| Law | City | Buildings | Over Cap | Fine Avoidance | Carbon Reduction |
|-----|------|-----------|----------|----------------|------------------|
| DC BEPS | Washington, DC | 1,093 | 553 (51%) | $482,086,231 | 105,238 tCO2e |
| Energize Denver | Denver, CO | 739 | 603 (82%) | $273,554,378 | 127,674 tCO2e |
| NYC LL97 | New York, NY | 3,580 | 627 (18%) | $42,302,614 | 715,047 tCO2e |
| Seattle BEPS | Seattle, WA | 731 | 63 (9%) | $24,460,962 | 39,747 tCO2e |
| Boston BERDO 2.0 | Boston, MA | 521 | 141 (27%) | $6,534,078 | 93,762 tCO2e |
| Cambridge BEUDO | Cambridge, MA | 139 | 58 (42%) | $4,453,173 | 31,432 tCO2e |
| St. Louis BEPS | St. Louis, MO | 73 | 3 (4%) | $547,500 | 7,771 tCO2e |
| **BPS Total** | | **6,876** | **2,048** | **$833,938,936** | **1,120,671 tCO2e** |

### Partial vs Full Fine Avoidance

Buildings with fine avoidance include both:
- **Partial avoidance**: Building remains over cap but reduces overage (gets proportional credit)
- **Full avoidance**: Building goes from over cap to under cap (avoids entire fine)

| Law | Partial (still over) | Full (to compliance) |
|-----|---------------------|---------------------|
| NYC LL97 | 437 | 190 |
| Boston BERDO | 97 | 44 |
| Cambridge BEUDO | 39 | 19 |
| DC BEPS | 444 | 109 |
| Denver | 504 | 99 |
| Seattle BEPS | 0 | 63 (binary penalty) |
| St. Louis BEPS | 0 | 3 (binary penalty) |

### Non-BPS Cities
- Buildings: 19,772
- Fine avoidance: $0
- Carbon reduction calculated with regional eGRID factors

### Grand Total
- **Total Buildings:** 26,648
- **Total Emissions:** 26,869,259 tCO2e
- **Total Carbon Reduction:** 3,962,911 tCO2e
- **Total Fine Avoidance:** $833,938,936

---

## 8. Input CSV Columns Used

| Column | Description |
|--------|-------------|
| `loc_address` | Building address (for city extraction) |
| `loc_state` | State abbreviation |
| `bldg_vertical` | Building type (filtered to "Commercial") |
| `bldg_sqft` | Building size in sqft |
| `energy_site_eui` | Site Energy Use Intensity (kBtu/sqft) |
| `energy_elec_kbtu` | Annual electricity consumption |
| `energy_gas_kbtu` | Annual gas consumption |
| `energy_steam_kbtu` | Annual steam consumption |
| `odcv_hvac_savings_pct` | ODCV savings potential (0.15-0.33) |
| `hvac_pct_elec` | % of electricity used for HVAC |
| `hvac_pct_gas` | % of gas used for HVAC |
| `hvac_pct_steam` | % of steam used for HVAC |
| `cost_gas_annual` | Annual gas cost ($) |
| `cost_steam_annual` | Annual steam cost ($) |
| `cost_gas_rate_therm` | Gas rate ($/therm) |
| `cost_steam_rate_mlb` | Steam rate ($/Mlb) |

---

## 9. Official Sources

### BPS Law Sources
1. **NYC Local Law 97:** https://www.nyc.gov/site/buildings/codes/ll97-greenhouse-gas-emissions-reductions.page
2. **Boston BERDO:** https://www.boston.gov/departments/environment/berdo
3. **DC BEPS:** https://doee.dc.gov/service/building-energy-performance-standards-beps
4. **Denver Energize:** https://denvergov.org/Government/Agencies-Departments-Offices/Agencies-Departments-Offices-Directory/Climate-Action-Sustainability-and-Resiliency/Energize-Denver
5. **Seattle BEPS:** https://www.seattle.gov/environment/climate-change/buildings-and-energy/building-emissions-performance-standard
6. **San Francisco EBEPO:** https://www.sfenvironment.org/existing-buildings-energy-performance-ordinance
7. **St. Louis BEPS:** https://www.stlouis-mo.gov/government/departments/public-safety/building/building-performance/index.cfm

### Emission Factor Sources
8. **EPA eGRID 2023:** https://www.epa.gov/egrid/summary-data (Regional electricity emission factors)
9. **Seattle GHGI Targets:** https://www.seattle.gov/documents/Departments/OSE/Building%20Energy/BEPS-GHGI-Targets.pdf
10. **EPA GHG Emission Factors Hub:** https://www.epa.gov/climateleadership/ghg-emission-factors-hub (Natural gas: 53.06 kgCO2/MMBtu)

---

## 10. Limitations

1. **DC BEPS:** Uses `energy_star_score` column with target of 71; buildings without scores excluded from fine calculation
2. **San Francisco:** No emission caps to calculate fine avoidance (EBEPO is reporting-only)
3. **Building Type Assumptions:** All buildings treated as Office/Commercial
4. **Future Period Caps:** Only Year 1 caps used; stricter future caps not modeled
5. **Data Quality:** 249 records had energy back-calculated from cost using median rates
6. **Emission Factors:** Non-BPS cities use EPA eGRID regional averages; actual utility-specific factors may vary

---

*Generated by national_bps_calculator.py on 2025-12-01*
