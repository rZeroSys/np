# Building Energy Data Dictionary

## File: `ANALYSIS STEP merged_property_matches_updated.csv`

**Location:** `/Users/forrestmiller/Desktop/analysis stage/ANALYSIS STEP merged_property_matches_updated.csv`

---

## Overview

| Metric | Value |
|--------|-------|
| Total Records | 26,648 buildings |
| Total Columns | 56 |
| Reporting Years | 2011-2024 (90% from 2023-2024) |
| Geographic Coverage | US commercial buildings |
| Primary Sources | ENERGY STAR Portfolio Manager, municipal benchmarking |

---

## Data Completeness

| Field | Coverage | Notes |
|-------|----------|-------|
| site_eui | 100% | All buildings have EUI |
| electricity_use_kbtu | 100% | All buildings have electricity data |
| natural_gas_use_kbtu | 68.1% | 18,142 buildings use gas |
| district_steam_use_kbtu | 5.1% | 1,357 buildings (mostly urban) |
| other_fuels_use_kbtu | 9.7% | 2,572 buildings (fuel oil) |
| energy_star_score | 70.0% | 18,641 buildings have scores |
| year_built | 93.0% | 24,780 buildings |
| valuation | 70.2% | 18,708 buildings |
| latitude/longitude | 100% | All geocoded |

---

## Column Definitions

### Building Identification

| Column | Type | Description |
|--------|------|-------------|
| `building_id` | string | Unique identifier for each building |
| `address` | string | Street address |
| `property_name` | string | Building/property name |
| `zip_code` | string | ZIP code |
| `latitude` | float | Latitude coordinate |
| `longitude` | float | Longitude coordinate |
| `building_url` | string | URL to building profile |
| `Property/Plant ID` | string | ENERGY STAR property ID |

### Building Characteristics

| Column | Type | Description | Stats |
|--------|------|-------------|-------|
| `building type` | string | Primary use type (32 categories) | See Building Types below |
| `vertical` | string | Sector: Commercial, Education, Healthcare, Government | |
| `square_footage` | int | Gross floor area | Min: 25,000 / Median: 89,000 / Max: 11.4M |
| `year_built` | int | Construction year | Min: 1800 / Median: 1982 / Max: 2025 |
| `reporting_year` | int | Year of energy data | 2011-2024 |

### Energy Metrics

| Column | Type | Description | Stats |
|--------|------|-------------|-------|
| `site_eui` | float | Site Energy Use Intensity (kBtu/sqft/yr) | Min: 5 / Median: 57 / Max: 3,088 |
| `total_site_energy_kbtu` | float | Total annual site energy (kBtu) | Median: 5.5M kBtu |
| `electricity_use_kbtu` | float | Annual electricity consumption (kBtu) | Median: 3.4M kBtu |
| `electricity_kwh` | float | Annual electricity (kWh) | = electricity_use_kbtu / 3.412 |
| `natural_gas_use_kbtu` | float | Annual natural gas (kBtu) | Median: 1.9M kBtu |
| `district_steam_use_kbtu` | float | Annual district steam (kBtu) | Median: 6.6M kBtu |
| `other_fuels_use_kbtu` | float | Annual fuel oil/other (kBtu) | Median: 893K kBtu |
| `energy_star_score` | int | ENERGY STAR score (1-100) | Median: 78 |

### Emissions

| Column | Type | Description | Stats |
|--------|------|-------------|-------|
| `total_ghg_emissions_mt_co2e` | float | Annual GHG emissions (metric tons CO2e) | Median: 377 MT |

### Energy Costs

| Column | Type | Description |
|--------|------|-------------|
| `annual_energy_cost` | float | Total annual energy cost ($) |
| `energy_rate_per_kwh` | float | Electricity rate ($/kWh) |
| `utility_name_used` | string | Electric utility name |
| `annual_demand_cost` | float | Demand charges ($) |
| `estimated_peak_kw` | float | Estimated peak demand (kW) |
| `demand_rate_per_kw` | float | Demand rate ($/kW) |
| `total_annual_electricity_cost` | float | Total electricity cost ($) |
| `annual_gas_cost` | float | Annual gas cost ($) |
| `gas_rate_per_therm` | float | Gas rate ($/therm) |
| `annual_steam_cost` | float | Annual steam cost ($) |
| `steam_rate_per_mlb` | float | Steam rate ($/Mlb) |
| `annual_fuel_oil_cost` | float | Annual fuel oil cost ($) |
| `fuel_oil_rate_per_gallon` | float | Fuel oil rate ($/gallon) |
| `load_factor_used` | float | Load factor for demand calculation |
| `cost_calculation_notes` | string | Notes on cost methodology |

### Ownership & Management

| Column | Type | Description |
|--------|------|-------------|
| `building_owner` | string | Building owner name (7,852 unique) |
| `property_manager` | string | Property manager name |
| `tenant` | string | Primary tenant |
| `tenant_sub_org` | string | Tenant sub-org |

### Location & Climate

| Column | Type | Description |
|--------|------|-------------|
| `ENERGY STAR Climate Zone` | string | Northern, North-Central, South-Central, Southern |
| `statec` | string | State code |

### Financial Metrics

| Column | Type | Description | Stats |
|--------|------|-------------|-------|
| `valuation` | float | Property valuation ($) | Median: $22.9M |
| `cap_rate` | float | Capitalization rate (%) | |
| `noi` | float | Net Operating Income ($) | |
| `market_rent_per_sqft` | float | Market rent ($/sqft) | |
| `operating_expense_ratio` | float | OpEx ratio (%) | |
| `vacancy_rate` | float | Vacancy rate (%) | |
| `utilization_rate` | float | Utilization rate (%) | |

### Media

| Column | Type | Description |
|--------|------|-------------|
| `photo_url` | string | Building photo URL |

### HVAC Energy Allocation

| Column | Type | Description | Stats |
|--------|------|-------------|-------|
| `pct_elec_hvac` | float | Percentage of electricity used for HVAC (0-1) | Varies by building type |
| `pct_gas_hvac` | float | Percentage of natural gas used for HVAC (0-1) | Typically 0.8-1.0 for heating |
| `pct_steam_hvac` | float | Percentage of district steam used for HVAC (0-1) | Typically 1.0 (heating only) |
| `pct_other_hvac` | float | Percentage of other fuels used for HVAC (0-1) | Typically 1.0 (heating only) |
| `method` | string | Methodology used for HVAC estimation | cbecs_adjusted, direct |

---

## Building Types (32 Categories)

| Building Type | Count | Vertical |
|---------------|-------|----------|
| Office | 9,714 | Commercial |
| K-12 School | 2,589 | Education |
| Hotel | 2,520 | Commercial |
| Retail Store | 1,898 | Commercial |
| Higher Ed | 1,316 | Education |
| Strip Mall | 1,027 | Commercial |
| Residential Care Facility | 948 | Healthcare |
| Medical Office | 800 | Healthcare |
| Supermarket/Grocery | 682 | Commercial |
| Specialty Hospital | 587 | Healthcare |
| Mixed Use | 495 | Commercial |
| Wholesale Club | 490 | Commercial |
| Laboratory | 461 | Commercial |
| Inpatient Hospital | 393 | Healthcare |
| Arts & Culture | 291 | Commercial |
| Gym | 278 | Commercial |
| Restaurant/Bar | 233 | Commercial |
| Vehicle Dealership | 224 | Commercial |
| Event Space | 209 | Commercial |
| Theater | 206 | Commercial |
| Public Service | 185 | Government |
| Police Station | 160 | Government |
| Data Center | 152 | Commercial |
| Enclosed Mall | 149 | Commercial |
| Courthouse | 134 | Government |
| Outpatient Clinic | 133 | Healthcare |
| Preschool/Daycare | 110 | Education |
| Library | 81 | Government |
| Public Transit | 57 | Government |
| Bank Branch | 46 | Commercial |
| Fire Station | 40 | Government |
| Sports/Gaming Center | 40 | Commercial |

---

## Climate Zone Distribution

| Climate Zone | Count | % | Description |
|--------------|-------|---|-------------|
| South-Central | 13,148 | 49.3% | Mixed-dry/Hot-dry (TX, AZ, NM, etc.) |
| North-Central | 8,049 | 30.2% | Mixed-humid (Mid-Atlantic, Midwest) |
| Northern | 5,271 | 19.8% | Cold/Very cold (Northeast, Upper Midwest) |
| Southern | 179 | 0.7% | Hot-humid (FL, Gulf Coast) |

---

## Vertical Distribution

| Vertical | Count | % |
|----------|-------|---|
| Commercial | 18,226 | 68.4% |
| Education | 4,117 | 15.5% |
| Healthcare | 3,322 | 12.5% |
| Government | 983 | 3.7% |

---

## Top Building Owners

| Owner | Count |
|-------|-------|
| City Of New York | 325 |
| Chicago Public Schools | 216 |
| Walmart | 199 |
| District Of Columbia Public Schools | 189 |
| The Irvine Company | 161 |
| Harvard University | 158 |
| District Of Columbia | 147 |
| Costco | 125 |
| Massachusetts Institute Of Technology | 124 |
| Boston Properties (BXP) | 119 |

*Total: 7,852 unique owners*

---

## Data Quality Notes

1. **Minimum Square Footage**: All buildings ≥25,000 sqft (large commercial threshold)

2. **EUI Outliers**: Max EUI of 3,088 kBtu/sqft indicates some data quality issues or special use cases (data centers, labs)

3. **Year Built Range**: 1800-2025 includes historic buildings and those under construction

4. **Gas Coverage**: 32% of buildings have no gas data - likely all-electric buildings

5. **Steam Coverage**: Only 5% have district steam - concentrated in dense urban areas (NYC, Boston, etc.)

6. **Fuel Oil Coverage**: 10% use fuel oil - primarily in Northeast for heating

7. **ENERGY STAR Score**: 30% missing scores - may be ineligible building types or incomplete data

---

## Fuel Type Summary

| Fuel | Buildings | % of Portfolio | Typical Use |
|------|-----------|----------------|-------------|
| Electricity | 26,648 | 100% | Cooling, lighting, equipment |
| Natural Gas | 18,142 | 68% | Heating, DHW, cooking |
| District Steam | 1,357 | 5% | Heating (urban buildings) |
| Fuel Oil | 2,572 | 10% | Heating (Northeast) |

---

## Related Files

| File | Description |
|------|-------------|
| `hvac_pct_ACCURATE.py` | Script to estimate HVAC % by fuel type |
| `buildings_hvac_pct_ACCURATE.csv` | Output with pct_elec_hvac, pct_gas_hvac, pct_steam_hvac, pct_other_hvac |
| `METHODOLOGY.md` | HVAC estimation methodology documentation |
