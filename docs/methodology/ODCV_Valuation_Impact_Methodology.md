# ODCV Valuation Impact Methodology

## Overview

This document describes the methodology used to calculate the property valuation impact of implementing Occupancy-Driven Control Ventilation (ODCV) systems in commercial buildings. The valuation methodology incorporates both utility cost savings and BPS (Building Performance Standards) fine avoidance, following the approach used in the NYC LL97 analysis.

## Scope

- **Buildings analyzed**: 26,648 commercial buildings
- **Building types included**: Office, Medical Office, Mixed Use, Retail Store, Strip Mall, Hotel, Supermarket/Grocery, Enclosed Mall, Restaurant/Bar, Gym, Vehicle Dealership, Wholesale Club, Bank Branch, Data Center
- **Data Centers**: Excluded from savings calculations ($0 impact) due to cooling-dominated loads with minimal ventilation-related savings opportunity
- **BPS Jurisdictions**: 7 cities with Building Performance Standards (NYC LL97, Boston BERDO, Cambridge BEUDO, DC BEPS, Denver Energize, Seattle BEPS, St. Louis BEPS)

## Calculation Methodology

### Step 1: Calculate Annual HVAC Costs by Fuel Type

For each building, we calculate the portion of energy costs attributable to HVAC:

```
Electricity HVAC Cost = total_annual_electricity_cost × pct_elec_hvac
Gas HVAC Cost = annual_gas_cost × pct_gas_hvac
Steam HVAC Cost = annual_steam_cost × pct_steam_hvac
Fuel Oil HVAC Cost = annual_fuel_oil_cost × pct_fuel_oil_hvac

Total HVAC Cost = Sum of all fuel HVAC costs
```

### Step 2: Calculate Annual ODCV Utility Savings

Annual energy savings from ODCV implementation:

```
odcv_dollar_savings = Total HVAC Cost × odcv_savings_pct
```

The `odcv_savings_pct` ranges from 20-40% for office buildings, with type-specific ranges for other building types based on:
- Vacancy rates (for multi-tenant buildings)
- Utilization rates (for owner-occupied buildings)
- Building age and size (automation likelihood proxy)
- Energy efficiency (Energy Star score or EUI)
- Climate zone (heating/cooling intensity)

### Step 3: Calculate Total Annual OpEx Avoidance (Including BPS Fine Avoidance)

For buildings in BPS jurisdictions, ODCV reduces carbon emissions, which can help avoid or reduce regulatory penalties. The total annual benefit combines utility savings with fine avoidance:

```
total_annual_opex_avoidance = odcv_dollar_savings + fine_avoidance_yr1
```

Where:
- `odcv_dollar_savings`: Annual utility cost savings from reduced HVAC energy
- `fine_avoidance_yr1`: Year 1 BPS penalty avoidance (calculated per city's BPS law, see NATIONAL_BPS_METHODOLOGY.md)

**Rationale**: Following the NYC LL97 methodology, both utility savings and regulatory penalty avoidance contribute to increased Net Operating Income (NOI). Both represent real dollar savings that improve building cash flow.

### Step 4: Calculate Valuation Impact (Income Capitalization Approach)

Commercial real estate is valued based on income-producing potential. Operating expense reductions directly increase NOI, which increases property value:

```
odcv_valuation_impact_usd = total_annual_opex_avoidance / (cap_rate / 100)
```

**IMPORTANT**: The `cap_rate` column stores values as whole numbers (e.g., 8 for 8%, 7.5 for 7.5%). For the valuation calculation, this must be converted to decimal form by dividing by 100.

**Rationale**: In income-producing properties, a $1 reduction in operating expenses (or avoided penalties) increases NOI by $1. The capitalization rate converts this income stream into property value. For example:
- $100,000 annual benefit / 0.07 (7% cap rate) = $1,428,571 valuation increase

**Value Multiplier by Cap Rate**:
| Cap Rate | Value Multiplier | Example Impact |
|----------|------------------|----------------|
| 6.00% | 16.67× | $100K savings → $1.67M value |
| 7.00% | 14.29× | $100K savings → $1.43M value |
| 8.00% | 12.50× | $100K savings → $1.25M value |
| 9.00% | 11.11× | $100K savings → $1.11M value |

### Step 5: Estimate Current and Post-ODCV Valuations

**Current Valuation** (estimated):
```
Estimated Gross Income = Total Energy Cost / 0.12
  (Energy typically ~12% of gross income for commercial properties)

Estimated NOI = Estimated Gross Income × 0.60
  (Operating expenses typically 35-45% of gross income)

current_valuation_usd = Estimated NOI / (cap_rate / 100)
```

**Note**: The `cap_rate` must be converted from percentage to decimal (divide by 100) for the valuation formula.

**Post-ODCV Valuation**:
```
post_odcv_valuation_usd = current_valuation_usd + odcv_valuation_impact_usd
```

## Data Sources and Assumptions

### Cap Rates by Building Type (Median Values)
| Building Type | Cap Rate |
|---------------|----------|
| Office | 7.50% |
| Medical Office | 7.50% |
| Mixed Use | 7.00% |
| Retail Store | 6.25% |
| Strip Mall | 6.75% |
| Hotel | 8.00% |
| Supermarket/Grocery | 6.00% |
| Enclosed Mall | 7.50% |
| Restaurant/Bar | 7.00% |
| Gym | 7.00% |
| Vehicle Dealership | 6.25% |
| Wholesale Club | 5.75% |
| Bank Branch | 6.50% |
| Data Center | 5.50% |

### HVAC Percentages (Median Values for Gap-Filling)
| Fuel Type | HVAC % of Total Use |
|-----------|---------------------|
| Natural Gas | 85% |
| District Steam | 99% |
| Fuel Oil | 78% |
| Electricity | Building-specific |

### Energy Cost Assumptions
- Energy costs represent approximately 12% of gross rental income
- Operating expense ratio: 40% of gross income (60% NOI margin)
- These are industry-standard benchmarks for commercial properties

## Output Columns

Four columns related to valuation in the dataset:

1. **odcv_dollar_savings**: Annual utility cost savings from ODCV ($)
2. **total_annual_opex_avoidance**: Combined utility savings + BPS fine avoidance ($)
3. **current_valuation_usd**: Estimated current property value based on energy costs and cap rate
4. **post_odcv_valuation_usd**: Estimated property value after ODCV implementation
5. **odcv_valuation_impact_usd**: Dollar increase in property value from total annual benefit

## Results Summary

| Metric | Value |
|--------|-------|
| Commercial Buildings | 26,429 |
| Buildings with Valuation Calculated | 18,625 |
| **Total Valuation Impact** | **$39,596,552,648** |
| Average Impact per Building | $2,126,000 |

### By Building Type (Top 10)
| Building Type | Buildings | Valuation Impact |
|---------------|-----------|------------------|
| Office | 9,763 | $26,281,439,514 |
| Hotel | 2,523 | $4,388,345,615 |
| Retail Store | 1,902 | $2,556,495,690 |
| Mixed Use | 496 | $1,429,066,137 |
| Strip Mall | 1,028 | $1,339,724,555 |
| Medical Office | 800 | $1,056,862,293 |
| Wholesale Club | 490 | $770,583,810 |
| Enclosed Mall | 150 | $529,875,699 |
| Supermarket/Grocery | 682 | $341,126,172 |
| Restaurant/Bar | 237 | $329,446,064 |

## Methodology Alignment with NYC LL97 Approach

This valuation methodology follows the same approach used in the NYC LL97 ODCV analysis:

1. **Combined Benefits**: Both utility savings and penalty avoidance contribute to NOI improvement
2. **Direct Capitalization**: Annual benefits are capitalized using property-specific cap rates
3. **Conservative Assumptions**: Year 1 fine avoidance is used for all BPS laws (no multi-year escalation)

The key formula matches the NYC approach:
```
Valuation Impact = (Utility Savings + Penalty Avoidance) / Cap Rate
```

## Limitations and Caveats

1. **Valuation estimates are indicative**: Actual property values depend on many factors beyond energy costs (location, condition, lease terms, etc.)

2. **Cap rates are market-dependent**: Actual cap rates vary by market, property class, and economic conditions

3. **ODCV savings are estimated**: Actual savings depend on existing HVAC systems, building controls, and implementation quality

4. **Data Center exclusion**: While Data Centers are included in the commercial count, they have $0 valuation impact because ODCV has minimal applicability to cooling-dominated data center loads

5. **Year 1 fine avoidance only**: BPS penalties may escalate in future compliance periods; this analysis uses Year 1 values as a conservative baseline

6. **BPS law changes**: Building Performance Standards are evolving; caps and penalties may change

## Files

- **Input**: `ANALYSIS STEP II merged_property_matches_updated.csv`
- **Output**: Same file, updated with valuation columns
- **Backup**: `backup/ANALYSIS STEP II merged_property_matches_updated_backup_[timestamp].csv`
- **Related**: `NATIONAL_BPS_METHODOLOGY.md` (details on fine avoidance calculations)

---

*Last Updated: December 2, 2025*
*Valuation calculation corrected: cap_rate must be converted from percentage to decimal (divide by 100)*
*This correction increased valuation impact values by 100× to align with NYC LL97 methodology*
