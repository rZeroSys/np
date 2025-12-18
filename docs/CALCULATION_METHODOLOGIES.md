# Calculation Methodologies

This document describes the methodology used in each data calculation script run by `MASTER_ORCHESTRATE.py`.

---

## 01_hvac_pct.py — HVAC Percentage Calculator

**Purpose:** Calculates the percentage of each fuel type used for HVAC (heating, ventilation, air conditioning).

### Output Columns
| Column | Description |
|--------|-------------|
| `hvac_pct_elec` | % of electricity used for HVAC |
| `hvac_pct_gas` | % of natural gas used for HVAC |
| `hvac_pct_steam` | % of district steam used for HVAC |
| `hvac_pct_fuel_oil` | % of fuel oil used for HVAC (fixed at 93%) |
| `hvac_pct_method` | `cbecs_adjusted` or `data_center` |

### Methodology

1. **Base Benchmarks:** Uses EIA CBECS 2018 (Commercial Buildings Energy Consumption Survey) data to compute baseline HVAC percentages by building type (PBA code) and climate zone.

2. **Building-Specific Adjustments:** Applies three adjustment factors (capped at ±12% combined):

   | Factor | Adjustment Range | Logic |
   |--------|------------------|-------|
   | Energy Star Score | -5% (90+) to +5% (<50) | Efficient buildings use less HVAC |
   | Year Built | -3% (2010+) to +4% (<1970) | Newer buildings have more efficient HVAC |
   | EUI vs Peer Median | -4% (<0.7x) to +6% (>1.5x) | High EUI = likely higher HVAC % |

3. **Special Cases:**
   - **Data Centers:** Fixed at 42% electric, 0% gas/steam/fuel oil
   - **All-Electric Buildings:** +8-15% electric HVAC (climate-dependent)
   - **Hotels:** Gas HVAC 12-28% based on intensity
   - **Restaurants:** Gas HVAC ~18%

4. **Bounds:** Electric 15-70%, Gas 40-98%, Steam 50-100%

### Data Sources
- EIA CBECS 2018: https://www.eia.gov/consumption/commercial/

---

## 02_energy_costs.py — Energy Cost Calculator

**Purpose:** Calculates annual energy costs from energy usage and utility rates.

### Output Columns
| Column | Description |
|--------|-------------|
| `cost_elec_peak_kw` | Peak demand in kW |
| `cost_elec_energy_annual` | Annual electricity energy charges ($) |
| `cost_elec_demand_annual` | Annual electricity demand charges ($) |
| `cost_elec_total_annual` | Total annual electricity cost ($) |
| `cost_gas_annual` | Annual natural gas cost ($) |
| `cost_steam_annual` | Annual district steam cost ($) |
| `cost_fuel_oil_annual` | Annual fuel oil cost ($) |

### Formulas

**Electricity:**
```
peak_kw = energy_elec_kwh / (8760 × load_factor)
energy_annual = energy_elec_kwh × rate_kwh × 1.10
demand_annual = peak_kw × rate_demand_kw × 12 × 1.265
total = energy_annual + demand_annual
```

**Natural Gas:**
```
therms = energy_gas_kbtu / 100
cost = therms × rate_therm × 1.10
```

**District Steam:**
```
mlb = energy_steam_kbtu / 909
cost = mlb × rate_mlb
```

**Fuel Oil:**
```
mmbtu = energy_fuel_oil_kbtu / 1000
cost = mmbtu × rate_mmbtu × 1.10
```

### Multipliers
| Multiplier | Value | Purpose |
|------------|-------|---------|
| Energy Charge | 1.10 | Taxes, fees, distribution charges |
| Demand Charge | 1.265 | Ratchet clauses, seasonal peaks |
| Default Load Factor | 0.45 | Used when not specified |

### Conversion Factors
- 100 kBtu = 1 therm
- 909 kBtu = 1 Mlb steam
- 1000 kBtu = 1 MMBtu

---

## 03_odcv_savings.py — ODCV Savings Percentage Calculator

**Purpose:** Calculates per-building ODCV (Occupancy-Driven Demand Control Ventilation) savings percentage.

### Output Column
| Column | Description |
|--------|-------------|
| `odcv_hvac_savings_pct` | Expected HVAC savings from ODCV (20-50%) |

### Methodology

ODCV savings are calculated based on multiple factors:

**1. Opportunity Score (0-1):**
- **Office/Medical Office/Mixed Use:** `vacancy + (1-vacancy) × (1-utilization)`
- **Low Opportunity Types (Residential Care, Lab, etc.):** `(1-utilization) × 0.3`
- **Data Centers:** 0 (no opportunity)
- **All Other Types:** `1 - utilization`

**2. Automation Score (0-1):**
Average of:
- Year Built Score: 0 (<1970) to 1.0 (2015+)
- Size Score: 0.25 (<50k sqft) to 1.0 (250k+ sqft)

**3. Efficiency Modifier:**
Based on Energy Star score (preferred) or EUI vs peer median:
- 90+ score: 0.85 (less waste to capture)
- <25 score: 1.10 (more waste to capture)

**4. Climate Modifier:**
- Northern: 1.10 (more heating penalty per CFM)
- Southern: 0.95

**5. Final Calculation:**
```
base_odcv = floor + (opportunity × automation × range)
final_odcv = base_odcv × efficiency_modifier × climate_modifier × 1.20
```

### Building Type Bounds

| Building Type | Floor | Ceiling |
|---------------|-------|---------|
| Office | 20% | 40% |
| K-12 School | 20% | 45% |
| Higher Ed | 20% | 45% |
| Event Space / Venue | 20% | 45% |
| Hotel | 15% | 35% |
| Retail | 15% | 35% |
| Supermarket | 10% | 25% |
| Restaurant/Bar | 10% | 25% |
| Residential Care | 5% | 15% |
| Data Center | 0% | 0% |

**Global bounds:** Never below 20%, never above 50%

---

## 04_post_odcv_energy.py — Post-ODCV Energy Calculator

**Purpose:** Calculates energy usage after applying ODCV savings to each fuel type.

### Output Columns
| Column | Description |
|--------|-------------|
| `energy_elec_kwh_post_odcv` | Electricity after ODCV (kWh) |
| `energy_elec_kbtu_post_odcv` | Electricity after ODCV (kBtu) |
| `energy_gas_kbtu_post_odcv` | Natural gas after ODCV (kBtu) |
| `energy_steam_kbtu_post_odcv` | District steam after ODCV (kBtu) |
| `energy_fuel_oil_kbtu_post_odcv` | Fuel oil after ODCV (kBtu) |
| `energy_total_kbtu_post_odcv` | Total energy after ODCV (kBtu) |
| `carbon_emissions_post_odcv_mt` | Carbon emissions after ODCV (metric tons) |

### Formula

For each fuel type:
```
post_odcv_energy = current_energy × (1 - hvac_pct × odcv_hvac_savings_pct)
```

### Dependencies
- `hvac_pct_*` columns from 01_hvac_pct.py
- `odcv_hvac_savings_pct` from 03_odcv_savings.py

---

## 05_post_odcv_costs.py — Post-ODCV Energy Cost Calculator

**Purpose:** Calculates energy costs using post-ODCV energy values.

### Output Columns
| Column | Description |
|--------|-------------|
| `cost_elec_energy_annual_post_odcv` | Electricity energy charges after ODCV ($) |
| `cost_elec_demand_annual_post_odcv` | Electricity demand charges after ODCV ($) |
| `cost_elec_total_annual_post_odcv` | Total electricity cost after ODCV ($) |
| `cost_gas_annual_post_odcv` | Natural gas cost after ODCV ($) |
| `cost_steam_annual_post_odcv` | District steam cost after ODCV ($) |
| `cost_fuel_oil_annual_post_odcv` | Fuel oil cost after ODCV ($) |

### Methodology
Uses the same formulas as 02_energy_costs.py but with post-ODCV energy values.

---

## 06_hvac_totals.py — HVAC Totals Calculator

**Purpose:** Calculates total HVAC energy and cost across all fuel types.

### Output Columns
| Column | Description |
|--------|-------------|
| `hvac_energy_total_kbtu` | Total HVAC energy consumption (kBtu) |
| `hvac_cost_total_annual` | Total annual HVAC cost ($) |

### Formulas

```
hvac_energy_total_kbtu = (energy_elec_kbtu × hvac_pct_elec)
                       + (energy_gas_kbtu × hvac_pct_gas)
                       + (energy_steam_kbtu × hvac_pct_steam)
                       + (energy_fuel_oil_kbtu × hvac_pct_fuel_oil)

hvac_cost_total_annual = (cost_elec_total_annual × hvac_pct_elec)
                       + (cost_gas_annual × hvac_pct_gas)
                       + (cost_steam_annual × hvac_pct_steam)
                       + (cost_fuel_oil_annual × hvac_pct_fuel_oil)
```

---

## 07_carbon_by_city.py — City-Specific Carbon Emissions Calculator

**Purpose:** Calculates carbon emissions using city-specific emission factors.

### Output Columns
| Column | Description |
|--------|-------------|
| `carbon_emissions_total_mt` | Total carbon emissions (metric tons CO2e) |
| `odcv_carbon_reduction_yr1_mt` | Carbon reduction from ODCV (metric tons CO2e) |

### City Emission Factors (tCO2e per kBtu)

| City | Electricity | Gas | Steam | Fuel Oil |
|------|-------------|-----|-------|----------|
| New York | 0.0000847 | 0.00005311 | 0.00004493 | 0.00007315 |
| Boston | 0.0000717 | 0.00005311 | 0.00004493 | 0.00007315 |
| Seattle | 0.0000029 | 0.000053 | 0.000081 | 0.00007315 |
| Denver | 0.0001378 | 0.00005311 | 0.00004493 | 0.00007315 |
| Chicago | 0.0001649 | 0.00005311 | 0.00004493 | 0.00007315 |
| San Francisco | 0.0000570 | 0.00005311 | 0.00004493 | 0.00007315 |
| DEFAULT | 0.0000922 | 0.00005311 | 0.00004493 | 0.00007315 |

**Source:** EPA eGRID 2023

### Formulas

```
carbon_emissions_total_mt = (energy_elec_kbtu × elec_factor)
                          + (energy_gas_kbtu × gas_factor)
                          + (energy_steam_kbtu × steam_factor)
                          + (energy_fuel_oil_kbtu × fuel_oil_factor)

odcv_carbon_reduction = emissions_total - emissions_post_odcv
```

---

## 08_bps_fines.py — BPS (Building Performance Standards) Fines Calculator

**Purpose:** Calculates potential BPS fine avoidance for buildings in cities with building performance standards.

### Output Columns
| Column | Description |
|--------|-------------|
| `bps_fine_baseline_yr1_usd` | Baseline annual fine without ODCV ($) |
| `bps_fine_post_odcv_yr1_usd` | Annual fine with ODCV ($) |
| `bps_fine_avoided_yr1_usd` | Fine avoided due to ODCV ($) |

### BPS Laws by City

| City | Law | Type | Fine Rate | Threshold |
|------|-----|------|-----------|-----------|
| New York | LL97 | Emission | $268/tCO2e over cap | 25k sqft |
| Boston | BERDO 2.0 | Emission | $234/tCO2e over cap | 20k sqft |
| Cambridge | BEUDO | Emission | $234/tCO2e (20% from baseline) | 25k sqft |
| Washington DC | BEPS | Energy Star | $10/sqft (prorated by gap) | 50k sqft |
| Denver | Energize Denver | EUI | $0.15/kBtu over target | 25k sqft |
| Seattle | Seattle BEPS | Emission | $10/sqft per 5-year cycle | 20k sqft |
| St. Louis | STL BEPS | EUI | $500/day if non-compliant | 50k sqft |
| San Francisco | EBEPO | None yet | N/A | 10k sqft |

### NYC LL97 Emission Caps (2024-2029)
- Default: 0.00758 tCO2e/sqft

### Boston BERDO Emission Caps by Building Type (tCO2e/sqft)

| Building Type | Cap |
|---------------|-----|
| Office | 0.0053 |
| Higher Ed | 0.0102 |
| Hotel | 0.0074 |
| Inpatient Hospital | 0.0165 |
| Supermarket | 0.0200 |
| Restaurant/Bar | 0.0240 |

### Denver EUI Targets (kBtu/sqft) — 2030 Targets

| Building Type | Target |
|---------------|--------|
| Office | 48.3 |
| Hotel | 61.1 |
| Retail | 43.5 |
| Restaurant/Bar | 194.1 |
| Supermarket | 164.4 |
| Inpatient Hospital | 165.2 |

### Exemptions
- NYC & Denver: K-12 schools have alternative compliance
- Cambridge: Multifamily buildings report only (no fines)

---

## 09_valuation.py — ODCV Valuation Impact Calculator

**Purpose:** Calculates the property valuation impact from ODCV energy savings using income capitalization approach.

### Output Columns
| Column | Description |
|--------|-------------|
| `val_current_usd` | Estimated current property value |
| `val_post_odcv_usd` | Estimated value after ODCV |
| `val_odcv_impact_usd` | Dollar increase in property value |
| `savings_opex_avoided_annual_usd` | ODCV savings + fine avoidance |
| `odcv_hvac_savings_annual_usd` | Annual HVAC cost savings |

### Methodology

**1. Calculate HVAC Cost by Fuel Type:**
```
elec_hvac_cost = cost_elec_total_annual × hvac_pct_elec
gas_hvac_cost = cost_gas_annual × hvac_pct_gas
(etc. for steam and fuel oil)
```

**2. Calculate ODCV Dollar Savings:**
```
odcv_dollar_savings = total_hvac_cost × odcv_hvac_savings_pct
```

**3. Calculate Total OpEx Avoidance:**
```
total_opex_avoidance = odcv_dollar_savings + bps_fine_avoided_yr1_usd
```

**4. Calculate Valuation Impact (commercial only):**
```
valuation_impact = total_opex_avoidance / cap_rate
```

**5. Estimate Current Valuation:**
```
estimated_gross_income = total_energy_cost / 0.12
estimated_noi = estimated_gross_income × 0.60
current_valuation = estimated_noi / cap_rate
```

### Commercial Building Types
Office, Medical Office, Mixed Use, Retail, Hotel, Supermarket, Restaurant/Bar, Gym, Vehicle Dealership, Wholesale Club, Bank Branch, Venue, Theater, Sports/Gaming Center

---

## 10_energy_star_estimate.py — Estimated Energy Star Score After ODCV

**Purpose:** Estimates the new Energy Star score after ODCV implementation using EPA's efficiency ratio methodology.

### Output Column
| Column | Description |
|--------|-------------|
| `energy_star_score_post_odcv` | Estimated Energy Star score after ODCV |

### Methodology

Based on EPA Portfolio Manager methodology:
- Efficiency Ratio = Actual Source EUI / Predicted Source EUI
- Score maps to percentile via gamma distribution
- Lower EUI = lower ratio = higher score

**Steps:**

1. **Calculate weighted HVAC percentage** across all fuel types (weighted by energy consumption)

2. **Calculate energy reduction:**
   ```
   total_energy_reduction = odcv_savings_pct × weighted_hvac_pct
   new_eui = current_eui × (1 - total_energy_reduction)
   ```

3. **Convert current score to efficiency ratio** using inverse gamma CDF

4. **Adjust ratio based on EUI change:**
   ```
   new_ratio = current_ratio × (new_eui / current_eui)
   ```

5. **Convert new ratio back to score** using gamma CDF

### Gamma Distribution Parameters by Building Type

| Building Type | Shape | Scale |
|---------------|-------|-------|
| Office | 2.0 | 0.42 |
| Hotel | 1.8 | 0.48 |
| K-12 School | 2.2 | 0.38 |
| Inpatient Hospital | 2.3 | 0.38 |
| Supermarket | 1.8 | 0.50 |
| Data Center | 1.5 | 0.55 |
| DEFAULT | 2.0 | 0.43 |

### Score Interpretation
- Score of 75 = better than 75% of peers = 25th percentile of efficiency ratios
- Score of 50 = median performer

---

## Script Execution Order

The scripts MUST run in this order due to dependencies:

```
01_hvac_pct.py          → hvac_pct_* columns
02_energy_costs.py      → cost_*_annual columns
03_odcv_savings.py      → odcv_hvac_savings_pct
04_post_odcv_energy.py  → energy_*_post_odcv columns (needs 01, 03)
05_post_odcv_costs.py   → cost_*_post_odcv columns (needs 04)
06_hvac_totals.py       → hvac_*_total columns (needs 01, 02)
07_carbon_by_city.py    → carbon_* columns (needs 01, 03)
08_bps_fines.py         → bps_fine_* columns (needs 01, 03)
09_valuation.py         → val_* columns (needs all above)
10_energy_star_estimate.py → energy_star_score_post_odcv (needs 01, 03)
```

---

## Data Sources

| Source | Used For |
|--------|----------|
| EIA CBECS 2018 | HVAC percentages by building type |
| EPA eGRID 2023 | City-specific emission factors |
| EPA Portfolio Manager | Energy Star score methodology |
| NYC LL97 | NYC emission caps and fine rates |
| Boston BERDO 2.0 | Boston emission caps by building type |
| Denver Energize Denver | Denver EUI targets |
| Seattle BEPS | Seattle emission caps |
| DC BEPS | DC Energy Star targets |
| St. Louis BEPS | St. Louis EUI targets |
