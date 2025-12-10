# Estimated Post-ODCV Energy Star Score Methodology

## Overview

This document describes the methodology for estimating a building's new Energy Star score after applying ODCV (Optimized Decarbonization through Controlled Ventilation) HVAC savings.

**Output Column:** `energy_star_score_post_odcv`

---

## How Energy Star Scores Work

### The Core Formula

Energy Star scores are based on an **efficiency ratio**:

```
Efficiency Ratio = Actual Source EUI / Predicted Source EUI
```

- **Lower ratio** = More efficient = Higher score
- **Score of 50** = Median performer (ratio ≈ 1.0)
- **Score of 75** = Top 25% (ratio ≈ 0.60 for offices)
- **Score of 99** = Top 1% (ratio ≈ 0.25)

### Percentile Mapping

EPA uses a **gamma distribution** to map efficiency ratios to percentile scores. Each building type has specific gamma parameters (shape α, scale θ) derived from CBECS survey data.

The score represents what percentage of peer buildings a given building outperforms.

---

## Estimation Method

### Step 1: Calculate Weighted HVAC Percentage

ODCV savings affect HVAC energy consumption. We calculate the weighted average HVAC percentage across all fuel types:

```python
hvac_total_pct = (
    (hvac_pct_elec × energy_elec_kbtu) +
    (hvac_pct_gas × energy_gas_kbtu) +
    (hvac_pct_steam × energy_steam_kbtu) +
    (hvac_pct_fuel_oil × energy_fuel_oil_kbtu)
) / total_energy_kbtu
```

### Step 2: Calculate Energy Reduction

ODCV savings (typically 26%) apply to the HVAC portion of energy:

```python
total_energy_reduction = odcv_hvac_savings_pct × hvac_total_pct
```

**Example:** If ODCV saves 26% of HVAC and HVAC is 45% of total energy:
- Total energy reduction = 0.26 × 0.45 = **11.7%**

### Step 3: Calculate New EUI

```python
new_eui = current_eui × (1 - total_energy_reduction)
```

### Step 4: Convert Current Score to Efficiency Ratio

Using the inverse gamma CDF (percent point function):

```python
percentile = (100 - current_score) / 100
current_ratio = gamma.ppf(percentile, shape, scale)
```

### Step 5: Calculate New Efficiency Ratio

Since efficiency ratio is proportional to EUI:

```python
new_ratio = current_ratio × (new_eui / current_eui)
```

### Step 6: Convert New Ratio to Score

Using the gamma CDF:

```python
cdf = gamma.cdf(new_ratio, shape, scale)
new_score = (1 - cdf) × 100
```

---

## Gamma Distribution Parameters

| Building Type | Shape (α) | Scale (θ) | Score 75 Ratio |
|---------------|-----------|-----------|----------------|
| Office | 2.0 | 0.42 | ~0.60 |
| Medical Office | 2.1 | 0.40 | ~0.58 |
| Hotel | 1.8 | 0.48 | ~0.65 |
| K-12 School | 2.2 | 0.38 | ~0.55 |
| Higher Ed | 2.0 | 0.45 | ~0.63 |
| Retail Store | 1.9 | 0.45 | ~0.63 |
| Inpatient Hospital | 2.3 | 0.38 | ~0.55 |
| Data Center | 1.5 | 0.55 | ~0.70 |
| DEFAULT | 2.0 | 0.43 | ~0.61 |

Parameters are approximations based on EPA technical reference documents and CBECS data distributions.

---

## Example Calculation

**Building:** Office in New York
- Current Energy Star Score: 65
- Current Site EUI: 85 kBtu/sqft
- HVAC Percentages: 45% elec, 85% gas, 90% steam
- Weighted HVAC %: 48%
- ODCV Savings: 26%

**Calculation:**
1. Energy reduction = 0.26 × 0.48 = **12.5%**
2. New EUI = 85 × (1 - 0.125) = **74.4 kBtu/sqft**
3. Current ratio (score 65) ≈ **0.72**
4. EUI factor = 74.4 / 85 = **0.875**
5. New ratio = 0.72 × 0.875 = **0.63**
6. New score (ratio 0.63) ≈ **73**

**Result:** Score improves from 65 → 73 (+8 points)

---

## Limitations

1. **Approximation**: Gamma parameters are approximations; actual EPA calculations use proprietary lookup tables specific to each building type.

2. **Predicted EUI assumption**: We assume ODCV changes do not affect the predicted EUI (which depends on business activity, not efficiency measures).

3. **Source vs Site EUI**: Energy Star uses source EUI; we use site EUI as a proxy. This introduces minor error (~5-10%).

4. **Building type coverage**: Not all building types have Energy Star scores. Buildings without scores will not receive estimates.

5. **Score ceiling**: Scores are capped at 99 (top 1%).

---

## Data Requirements

The estimation requires these columns in `portfolio_data.csv`:

| Column | Description | Required |
|--------|-------------|----------|
| `energy_star_score` | Current Energy Star score (1-100) | Yes |
| `energy_site_eui` | Current site EUI (kBtu/sqft) | Yes |
| `odcv_hvac_savings_pct` | ODCV savings percentage (decimal) | Yes |
| `hvac_pct_elec` | % of electricity used for HVAC | Recommended |
| `hvac_pct_gas` | % of gas used for HVAC | Recommended |
| `hvac_pct_steam` | % of steam used for HVAC | Recommended |
| `hvac_pct_fuel_oil` | % of fuel oil used for HVAC | Recommended |
| `energy_elec_kbtu` | Electricity consumption (kBtu) | Recommended |
| `energy_gas_kbtu` | Gas consumption (kBtu) | Recommended |
| `energy_steam_kbtu` | Steam consumption (kBtu) | Recommended |
| `bldg_type` | Building type for gamma params | Recommended |

---

## Sources

- [EPA: How the 1-100 ENERGY STAR Score is Calculated](https://www.energystar.gov/buildings/benchmark/understand-metrics/how-score-calculated)
- [Portfolio Manager Technical Reference: ENERGY STAR Score](https://portfoliomanager.energystar.gov/pdf/reference/ENERGY%20STAR%20Score.pdf)
- [ENERGY STAR Score for Offices](https://www.energystar.gov/sites/default/files/tools/Office_August_2019_508.pdf)
- [U.S. National Median EUI Table (Aug 2024)](https://portfoliomanager.energystar.gov/pdf/reference/US%20National%20Median%20Table.pdf)
- [What is EUI?](https://www.energystar.gov/buildings/benchmark/understand-metrics/what-eui)

---

## Script Location

```
scripts/populate_master/08_energy_star_estimate.py
```

## Execution Order

Run after ODCV savings have been calculated (after 02_odcv_savings.py):

```
01_hvac_pct.py          → hvac_pct_*
02_odcv_savings.py      → odcv_hvac_savings_pct
03_hvac_totals.py
04_carbon_by_city.py
05_bps_fines.py
06_valuation.py
07_nyc_update.py
08_energy_star_estimate.py → energy_star_score_post_odcv (NEW)
```
