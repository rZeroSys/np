# Data Dictionary for portfolio_data.csv

This document defines all 70 columns in `portfolio_data.csv`, organized by category prefix.

**Naming Convention:**
- `id_` - Identifiers
- `loc_` - Location data
- `bldg_` - Building characteristics
- `data_` - Data metadata
- `org_` - Organization names
- `energy_` - Energy consumption
- `cost_` - Utility costs
- `hvac_` - HVAC-specific data
- `carbon_` - Carbon emissions
- `occ_` - Occupancy data
- `odcv_` - ODCV savings (HVAC-related)
- `bps_` - Building Performance Standards
- `savings_` - Combined savings totals
- `val_` - Valuation data
- `meta_` - Metadata

---

## Identifiers (`id_`)

| Column | Definition |
|--------|------------|
| `id_building` | Unique identifier for each building (format: CITY_NUMBER, e.g. NYC_1000160125) |
| `id_property_name` | Common name of property (e.g. '2 World Financial Center') |
| `id_source_plant_id` | Original ID from source database |
| `id_source_url` | URL to original data source (e.g. Energy Star Portfolio Manager) |

---

## Location (`loc_`)

| Column | Definition |
|--------|------------|
| `loc_address` | Street address of building |
| `loc_city` | City name extracted from address |
| `loc_state` | Two-letter state abbreviation |
| `loc_zip` | 5-digit ZIP code |
| `loc_lat` | Geographic latitude coordinate |
| `loc_lon` | Geographic longitude coordinate |

---

## Building Characteristics (`bldg_`)

| Column | Definition |
|--------|------------|
| `bldg_type` | Building use type (e.g. Office, Hotel, K-12 School) |
| `bldg_type_filter` | Simplified building type for UI filtering |
| `bldg_type_benchmark` | Building type used for EUI benchmarking |
| `bldg_vertical` | Market vertical: Commercial, Education, Healthcare, or Government |
| `bldg_year_built` | Year building was constructed |
| `bldg_sqft` | Gross floor area in square feet |

---

## Data Metadata (`data_`)

| Column | Definition |
|--------|------------|
| `data_year` | Year the energy data was reported |

---

## Organizations (`org_`)

| Column | Definition |
|--------|------------|
| `org_owner` | Legal owner of the building |
| `org_manager` | Property management company |
| `org_tenant` | Primary tenant organization |
| `org_tenant_subunit` | Sub-unit or department within tenant organization |

---

## Energy Consumption (`energy_`)

| Column | Definition |
|--------|------------|
| `energy_site_eui` | Site Energy Use Intensity in kBtu per square foot per year |
| `energy_eui_benchmark` | Median EUI for this building type (for comparison) |
| `energy_total_kbtu` | Total annual site energy consumption in kBtu |
| `energy_elec_kbtu` | Annual electricity consumption in kBtu |
| `energy_elec_kwh` | Annual electricity consumption in kWh |
| `energy_gas_kbtu` | Annual natural gas consumption in kBtu |
| `energy_steam_kbtu` | Annual district steam consumption in kBtu |
| `energy_fuel_oil_kbtu` | Annual fuel oil consumption in kBtu |
| `energy_star_score` | EPA Energy Star score (1-100, higher = more efficient) |
| `energy_climate_zone` | Climate zone for Energy Star calculations (Northern, South-Central, etc.) |

---

## Utility Costs (`cost_`)

| Column | Definition |
|--------|------------|
| `cost_elec_rate_kwh` | Electricity rate in dollars per kWh |
| `cost_elec_rate_demand_kw` | Electricity demand charge in dollars per kW |
| `cost_elec_load_factor` | Load factor used to estimate peak demand (0-1) |
| `cost_elec_peak_kw` | Estimated peak electricity demand in kW |
| `cost_elec_energy_annual` | Annual electricity energy charges (usage only) in USD |
| `cost_elec_demand_annual` | Annual electricity demand charges in USD |
| `cost_elec_total_annual` | Total annual electricity cost (energy + demand) in USD |
| `cost_gas_rate_therm` | Natural gas rate in dollars per therm |
| `cost_gas_annual` | Annual natural gas cost in USD |
| `cost_steam_rate_mlb` | District steam rate in dollars per thousand pounds |
| `cost_steam_annual` | Annual district steam cost in USD |
| `cost_fuel_oil_rate_gal` | Fuel oil rate in dollars per gallon |
| `cost_fuel_oil_annual` | Annual fuel oil cost in USD |
| `cost_utility_name` | Name of electric utility used for rate lookup |
| `cost_calc_notes` | Notes on how costs were calculated or estimated |

---

## HVAC Data (`hvac_`)

| Column | Definition |
|--------|------------|
| `hvac_pct_elec` | Fraction of electricity used for HVAC (0-1), from CBECS data |
| `hvac_pct_gas` | Fraction of natural gas used for HVAC (0-1), from CBECS data |
| `hvac_pct_steam` | Fraction of district steam used for HVAC (0-1), from CBECS data |
| `hvac_pct_fuel_oil` | Fraction of fuel oil used for HVAC (0-1), from CBECS data |
| `hvac_energy_total_kbtu` | Total annual HVAC energy in kBtu = sum of (fuel_kbtu × hvac_pct) for each fuel |
| `hvac_cost_total_annual` | Total annual HVAC cost in USD = sum of (fuel_cost × hvac_pct) for each fuel |
| `hvac_pct_method` | Method used to determine HVAC percentages (CBECS lookup key) |

---

## Carbon Emissions (`carbon_`)

| Column | Definition |
|--------|------------|
| `carbon_emissions_total_mt` | Total annual GHG emissions in metric tons CO2 equivalent |

---

## Occupancy Data (`occ_`)

| Column | Definition |
|--------|------------|
| `occ_vacancy_rate` | Fraction of rentable space currently vacant (0-1) |
| `occ_utilization_rate` | Fraction of occupied space actually in use during business hours (0-1) |

---

## ODCV Savings (`odcv_`)

These columns represent savings from **Occupancy-Driven Control Ventilation** applied to **HVAC systems only**.

| Column | Definition |
|--------|------------|
| `odcv_hvac_savings_pct` | Percentage of HVAC costs saved by ODCV (0.20-0.50). Derived from: opportunity score (vacancy + utilization) × automation score (year + sqft) × efficiency modifier × climate modifier, clamped to building type bounds |
| `odcv_hvac_savings_annual_usd` | Annual HVAC utility cost savings from ODCV in USD = `hvac_cost_total_annual` × `odcv_hvac_savings_pct` |
| `odcv_carbon_reduction_yr1_mt` | Year 1 carbon emissions reduction from ODCV in metric tons CO2e. Calculated from energy reduction × emission factors per fuel type |

---

## Building Performance Standards (`bps_`)

| Column | Definition |
|--------|------------|
| `bps_law_name` | Name of Building Performance Standard law (e.g. 'NYC LL97', 'Boston BERDO') |
| `bps_fine_avoided_yr1_usd` | Year 1 BPS penalty avoided by implementing ODCV in USD. Calculation varies by city law type (emission cap, EUI target, or Energy Star based) |

---

## Combined Savings (`savings_`)

| Column | Definition |
|--------|------------|
| `savings_opex_avoided_annual_usd` | Total annual operating expense savings in USD = `odcv_hvac_savings_annual_usd` + `bps_fine_avoided_yr1_usd` |
| `savings_pct_of_energy_cost` | ODCV savings as percentage of total annual energy cost = `odcv_hvac_savings_annual_usd` / (`cost_elec_total_annual` + `cost_gas_annual` + `cost_steam_annual` + `cost_fuel_oil_annual`) |

---

## Valuation (`val_`)

| Column | Definition |
|--------|------------|
| `val_cap_rate_pct` | Capitalization rate for property valuation (stored as percentage, e.g. 7.5 means 7.5%) |
| `val_market_rent_sqft` | Market rent in dollars per square foot per year |
| `val_opex_ratio` | Operating expenses as fraction of gross income (0-1) |
| `val_current_usd` | Estimated current property value in USD = (energy_cost / 0.12 × 0.60) / (cap_rate / 100) |
| `val_post_odcv_usd` | Estimated property value after ODCV in USD = `val_current_usd` + `val_odcv_impact_usd` |
| `val_odcv_impact_usd` | Property value increase from ODCV in USD = `savings_opex_avoided_annual_usd` / (`val_cap_rate_pct` / 100) |

---

## Metadata (`meta_`)

| Column | Definition |
|--------|------------|
| `meta_photo_url` | URL to building photo image |

---

## Column Rename Lookup

For reference, the mapping from old to new column names is stored in:
`/data/source/column_rename_lookup.csv`
