# HVAC Percentage by Fuel Type - Methodology Documentation (v3)

## Goal
Estimate the percentage of each fuel type that goes to HVAC for 26,648 commercial buildings:
- `pct_elec_hvac` - % of electricity used for HVAC
- `pct_gas_hvac` - % of natural gas used for HVAC
- `pct_steam_hvac` - % of district steam used for HVAC
- `pct_other_hvac` - % of fuel oil used for HVAC

## Final Script
**`hvac_pct_ACCURATE.py`** (v3) - Generates `buildings_hvac_pct_ACCURATE.csv`

---

## What's New in v3

Incorporated refinements from `HVAC_ELECTRICITY_DISAGGREGATION_METHODOLOGY.md`:

### 1. ENERGY STAR Score (Absolute Thresholds)

| Score | Adjustment | Rationale |
|-------|------------|-----------|
| 90+ | -5% | Very efficient |
| 75-89 | 0% | Good performance |
| 50-74 | +3% | Below average |
| <50 | +5% | Poor efficiency |

*Changed from peer-relative (P25/P75) to absolute thresholds for consistency.*

### 2. Electric HVAC 15% Minimum Floor

Ventilation fans, pumps, and controls run 24/7:

| Component | % of Electric |
|-----------|---------------|
| Ventilation fans | 8-12% |
| Chilled water pumps | 2-4% |
| Condenser water pumps | 1-3% |
| Controls & sensors | 1-2% |
| **Total minimum** | **15%** |

### 3. Fuel-Heated vs Electric-Heated Buildings

| Building Type | Cold Climate Elec HVAC |
|---------------|------------------------|
| Has gas/steam (fuel-heated) | Base CBECS value |
| All-electric, Northern | +15% (electric heat) |
| All-electric, South-Central | +8% (some electric heat) |
| All-electric, Southern | Base value (cooling only) |

---

## v2 Features (Retained)

### Year Built Adjustment

| Year | Adjustment |
|------|------------|
| < 1970 | +4% |
| 1970-1989 | +2% |
| 1990-2009 | 0% |
| 2010+ | -3% |

### EUI vs Peer Median

| EUI Ratio | Adjustment |
|-----------|------------|
| > 1.5× median | +6% |
| 1.2-1.5× median | +3% |
| 0.85-1.2× median | 0% |
| 0.7-0.85× median | -2% |
| < 0.7× median | -4% |

### Combined Adjustment Cap: ±12%

---

## Data Sources

| Source | File | Records |
|--------|------|---------|
| Building portfolio | `merged_property_matches_updated.csv` | 26,648 buildings |
| CBECS 2018 microdata | `cbecs2018_final_public.csv` | 6,436 survey responses |
| Methodology reference | `HVAC_ELECTRICITY_DISAGGREGATION_METHODOLOGY.md` | NYC validation |

---

## Output Summary (v3)

| Metric | Electric | Gas | Steam | Fuel Oil |
|--------|----------|-----|-------|----------|
| Mean | 45.1% | 75.9% | 92.1% | 65.7% |
| Median | 45.6% | 84.4% | 96.7% | 79.5% |
| P10 | 33.0% | 29.5% | 81.3% | 29.4% |
| P90 | 57.0% | 98.0% | 100.0% | 93.2% |

### Adjustment Impact Examples

| Building Type | Lowest HVAC % | Highest HVAC % |
|---------------|---------------|----------------|
| Office (gas) | 76.7% (score=93, yr=2018) | 98.0% (score=15, yr=2008) |
| Hotel (gas) | 8.0% (score=100) | 34.0% (score=32, yr=1907) |
| K-12 School (gas) | 51.0% (score=92, yr=2012) | 96.2% (score=31, yr=1914) |

---

## Special Cases

### Hotels
Only 19.7% of gas → HVAC (41.6% DHW, 33.1% cooking):
- Gas intensity < 15 kBtu/sqft: 12%
- Gas intensity 15-30: 18%
- Gas intensity 30-50: 22%
- Gas intensity > 50: 28%

### Restaurants
Only 17.6% gas HVAC (72.3% cooking):
- Fixed at 18% with dampened adjustments

### Data Centers
No CBECS category:
- 42% electric (cooling + ventilation)
- 0% gas/steam/oil HVAC

### Fuel Oil by Building Type
| Type | Oil HVAC % |
|------|------------|
| Laboratory | 12.5% |
| Mixed Use | 9.1% |
| Nursing | 41.9% |
| Retail | 97.4% |

---

## Building Type Mapping

| Portfolio Type | CBECS PBA | Base Gas HVAC % |
|----------------|-----------|-----------------|
| Office | 2 | 87.5% |
| K-12 School, Higher Ed | 14 | 79.6% |
| Hotel | 18 | 19.7% (special) |
| Restaurant/Bar | 15 | 17.6% (special) |
| Retail Store | 25 | 77.7% |
| Medical Office | 8 | 84.8% |
| Hospital | 16 | 60.3% |
| Laboratory | 4 | 82.5% |
| Data Center | DC | 0% (special) |

---

## Climate Zone Integration

Base CBECS lookup by (building type × climate zone):

| Climate Zone | Gas HVAC % | Notes |
|--------------|------------|-------|
| Northern | 67.9% | More heating |
| North-Central | 78.6% | Balanced |
| South-Central | 76.4% | Balanced |
| Southern | 59.4% | Less heating, -15% adjustment |

---

## Output File

**`buildings_hvac_pct_ACCURATE.csv`** - 26,648 rows:

| Column | Description |
|--------|-------------|
| building_id | Unique building identifier |
| pct_elec_hvac | % of electricity → HVAC (min 15%) |
| pct_gas_hvac | % of natural gas → HVAC |
| pct_steam_hvac | % of district steam → HVAC |
| pct_other_hvac | % of fuel oil → HVAC |
| method | cbecs_adjusted or data_center |

---

## References

1. EIA CBECS 2018: https://www.eia.gov/consumption/commercial/
2. HVAC_ELECTRICITY_DISAGGREGATION_METHODOLOGY.md (NYC validation)
3. LBNL 2024 Data Center Report
