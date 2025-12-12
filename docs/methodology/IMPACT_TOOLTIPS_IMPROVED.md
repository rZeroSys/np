# Impact Section Tooltips - Improved with Methodology & Data Sources

These tooltips explain HOW we calculated each Impact metric and WHERE the data comes from.

---

## Utility Cost Savings

**Current tooltip (too generic):**
"Savings from not heating and cooling empty space..."

**IMPROVED:**
"Annual dollar savings from reducing HVAC energy waste. We calculate this by: (1) taking your actual energy costs from city benchmarking disclosure filings, (2) applying CBECS (Commercial Buildings Energy Consumption Survey) data to determine what percentage goes to HVAC by building type—offices average 44% of electricity and 60% of gas to HVAC, hotels just 20% of gas due to hot water and kitchen loads, (3) multiplying by your building's ODCV savings percentage, which accounts for vacancy (CBRE/Cushman & Wakefield data) and utilization (Kastle Systems badge swipes for offices, STR data for hotels, NCES for schools). The result: exactly how much you're spending to heat and cool empty space right now."

---

## Fine Avoidance (by city)

### New York City
**Current:** "NYC Local Law 97 sets a carbon cap..."

**IMPROVED:**
"NYC Local Law 97 (2019) sets annual carbon emission limits for buildings over 25,000 sqft, with penalties of $268 per metric ton over the cap. We calculate your exposure using: (1) your building's actual emissions from city benchmarking data (LL84/LL33), (2) the carbon coefficient for your building type from the law's Table 2, (3) your building's gross floor area. The 2024 limits are strict—most office buildings can emit only 8.46 kgCO2e/sqft before fines kick in. Source: NYC Mayor's Office of Climate & Environmental Justice, Local Law 97 of 2019 as amended."

### Boston
**IMPROVED:**
"Boston's BERDO 2.0 (Building Emissions Reduction and Disclosure Ordinance) sets emissions limits starting at 0.0053 metric tons CO2e per square foot for offices, declining to net-zero by 2050. Penalties are $234 per excess metric ton annually. We calculate your baseline emissions from your Boston benchmarking disclosure, apply the current year's emissions standard by building type, and determine excess tons. ODCV reduces emissions by cutting the electricity and gas that generate them. Source: City of Boston Environment Department, BERDO 2.0 emissions standards tables."

### Cambridge
**IMPROVED:**
"Cambridge BEUDO (Building Energy Use Disclosure Ordinance) mirrors Boston's BERDO framework—buildings over 25,000 sqft face emissions caps with $234/ton penalties for excess emissions. We use your Cambridge benchmarking disclosure to calculate current emissions, compare against the city's published emissions factors by building type, and determine fine exposure. ODCV reduces emissions proportionally to energy savings. Source: Cambridge Community Development Department, BEUDO regulations."

### Washington DC
**IMPROVED:**
"DC's BEPS (Building Energy Performance Standards) requires buildings to meet an ENERGY STAR score of 71 or higher, with alternative compliance pathways for buildings that can't reach the target. Non-compliant buildings face fines up to $10 per square foot per year. We calculate your score from DC benchmarking data (using the ENERGY STAR Portfolio Manager methodology), estimate post-ODCV score improvement based on reduced energy consumption, and determine compliance status. Source: DC Department of Energy & Environment, Clean Energy DC Omnibus Act."

### Denver
**IMPROVED:**
"Energize Denver sets site EUI targets by building type—offices must hit 48.3 kBtu/sqft or face fines of $0.30 per kBtu over the threshold per square foot. We calculate your current site EUI from Denver benchmarking disclosure (total source energy divided by gross floor area), project post-ODCV EUI based on energy reduction, and determine fine exposure. Every 1% reduction in HVAC energy lowers your EUI proportionally. Source: City of Denver Office of Climate Action, Energize Denver Benchmarking Ordinance."

### Seattle
**IMPROVED:**
"Seattle's BEPS requires buildings to meet emissions intensity targets, with compliance assessments every 5 years. Buildings that fail to meet targets or show adequate progress face penalties up to $10/sqft. We calculate your emissions intensity from Seattle benchmarking data (using Washington's grid emissions factors), compare against published targets by building type, and estimate penalty exposure. Source: Seattle Office of Sustainability & Environment, Building Emissions Performance Standard rules."

### St. Louis
**IMPROVED:**
"St. Louis BEPS (Building Energy Performance Standard) sets EUI targets by building type, with daily fines of $500 for non-compliance after the grace period. We calculate your current EUI from St. Louis benchmarking data, compare against the city's target for your building type, and determine compliance status. ODCV directly reduces your EUI by cutting HVAC energy waste. Source: City of St. Louis Building Division, BEPS Ordinance."

---

## Property Value Increase

**Current tooltip (too generic):**
"Lower operating costs mean higher building value. Every dollar you stop spending on wasted energy goes straight to NOI..."

**IMPROVED:**
"Commercial property values are determined by Net Operating Income (NOI) divided by capitalization rate. Every dollar of annual operating cost savings—like HVAC energy—flows directly to NOI. We calculate value impact using: (1) your annual utility cost savings from ODCV, (2) a capitalization rate based on your building type and market (we use CBRE Cap Rate Survey data: 7.0% average for offices, 7.5% for hotels, 6.5% for medical). At a 7% cap rate, $100,000 in annual savings adds $1.43M to property value. For buildings with fine avoidance, we also capitalize the avoided penalties. Source: CBRE Cap Rate Survey Q4 2024, income capitalization methodology per Appraisal Institute standards."

---

## Energy Star Score

**Current tooltip (too generic):**
"How this building ranks against peers nationwide..."

**IMPROVED:**
"ENERGY STAR score ranks your building from 1-100 against similar buildings nationwide—a score of 50 means median performance, 75+ earns certification. EPA calculates this using source energy (not site energy), normalized for weather, hours of operation, and other factors. We project post-ODCV score improvement using EPA's published regression equations for your building type: for offices, the primary driver is source EUI, which drops proportionally with HVAC savings. Reducing electricity by 10% typically improves score by 3-5 points depending on starting position. Source: EPA ENERGY STAR Portfolio Manager Technical Reference, regression coefficients by building type."

---

## Carbon Reduction

**Current tooltip (too generic):**
"Less energy used means less carbon emitted..."

**IMPROVED:**
"Carbon emissions calculated from your actual fuel consumption using EPA eGRID emission factors for electricity (varies by grid region—California at 0.21 kg CO2/kWh vs Midwest at 0.41 kg CO2/kWh) and standard combustion factors for natural gas (5.3 kg CO2 per therm), fuel oil (10.2 kg CO2 per gallon), and district steam (varies by plant, typically 30-60 kg CO2/MMBtu). We calculate post-ODCV emissions by reducing each fuel type proportionally to HVAC savings. For buildings in carbon-capped cities (NYC, Boston, DC), this directly affects fine exposure. Source: EPA eGRID 2022, EIA emission factors, city-specific steam plant data."

---

## ODCV Savings Percentage (by building type)

The ODCV % tooltip is already dynamic but here are improved versions with full methodology:

### Office
"This office building can save {X}% of HVAC energy by ventilating based on actual occupancy. We calculate this using: (1) vacancy rate of {Y}% from CBRE/Cushman & Wakefield Q4 2024 market data for {city}, (2) utilization rate of {Z}% from Kastle Systems Back to Work Barometer showing {city} at {Z}% of pre-pandemic badge swipes, (3) your building's year built ({year}) and size ({sqft} sqft) as proxies for BMS sophistication. Formula: floor + (vacancy + (1-vacancy) × (1-utilization)) × automation_score × (ceiling - floor), modified by efficiency (Energy Star score) and climate zone. Bounds: 20-40% for offices. Sources: CBRE Office Vacancy Index, Kastle Systems weekly barometer, CBECS building age/automation correlations."

### Hotel
"This hotel can save {X}% of HVAC energy by conditioning rooms based on actual guest presence. We calculate this using: (1) market occupancy rate from STR/CoStar data showing {city} hotels at {Y}% average occupancy, (2) guest presence factor of 45%—guests spend ~11 hours/day out of their room (meetings, sightseeing, dining), giving true utilization of {Z}%. Note: only ~20% of hotel gas goes to HVAC (per CBECS); 42% is hot water, 33% is kitchen. Formula: 1 - utilization, bounded at 15-35%. Sources: STR Global occupancy reports, CBECS hotel energy end-use breakdown."

### K-12 School
"This school can save {X}% of HVAC energy—the highest potential of any building type. We calculate this using: (1) instructional days from NCES data showing {state} schools operate {Y} days/year, (2) school hours of 7am-4pm, (3) summer, weekend, and holiday closures. Total: buildings occupied just 22-28% of annual hours depending on state calendar. California's year-round programs push higher; traditional calendar states run lower. Formula: 1 - utilization, bounded at 20-45%. Sources: NCES instructional time requirements, state education agency academic calendars."

### Hospital (Inpatient/Specialty)
"This hospital can save {X}% of HVAC energy—a constrained opportunity due to infection control codes. ASHRAE 170 mandates 15-25 air changes per hour in clinical areas regardless of occupancy. But hospitals have large non-clinical areas over-ventilated at medical-grade rates: waiting rooms (empty overnight), exam rooms (35% occupied), admin offices (business hours only), cafeterias (meal peaks only). We weight these zones: patient rooms 40% × 70% occupancy, clinical 20% × 85%, support areas 40% × 35% = ~56% building-wide utilization. Sources: AHA Hospital Statistics 2024 (bed occupancy), ASHRAE 170-2021 (ventilation requirements), hospital space planning guides (zone percentages)."

---

## Electricity (kWh) Savings

"Your building uses {current_kwh} kWh/year of electricity per {city} benchmarking disclosure. We calculate HVAC's share using CBECS data: {bldg_type}s average {hvac_pct}% of electricity to cooling and ventilation. Applying your {odcv_pct}% ODCV savings gives {delta_kwh} kWh reduction. Post-ODCV consumption: {post_kwh} kWh/year. The savings come from running fans and chillers less when spaces are unoccupied—ventilation is typically 30-40% of HVAC electricity, cooling is 60-70%. Sources: City benchmarking disclosure ({law_name}), CBECS 2018 Table E1 (electricity end uses by building type)."

---

## Natural Gas (therms) Savings

"Your building uses {current_therms} therms/year of natural gas per {city} benchmarking disclosure. We calculate HVAC's share using CBECS data: {bldg_type}s average {hvac_pct}% of gas to heating. Note: this varies dramatically—offices use 60% for HVAC, hotels only 20% (rest is hot water and kitchen), restaurants just 18% (72% is cooking). Applying your {odcv_pct}% ODCV savings gives {delta_therms} therm reduction. The savings come from not heating outdoor air for empty spaces—every CFM of ventilation in winter requires heating from outdoor temp to 70°F. Sources: City benchmarking disclosure ({law_name}), CBECS 2018 Table E3 (natural gas end uses by building type)."

---

## Site EUI

"Site EUI (Energy Use Intensity) measures total energy consumption per square foot—{eui} kBtu/sqft for this building versus a {bldg_type} median of {benchmark} kBtu/sqft. We calculate this from your {city} benchmarking disclosure: (electricity kWh × 3.412 + gas therms × 100 + steam MMBtu × 1000 + fuel oil gallons × 138.5) ÷ gross floor area. Buildings above the median have more waste to capture; buildings below are already efficient. Post-ODCV EUI: {post_eui} kBtu/sqft. Sources: City benchmarking disclosure ({law_name}), ENERGY STAR median EUI by building type."

---

## Load Factor

"Load factor measures how evenly your building uses electricity throughout the month—calculated as average demand ÷ peak demand. Your building's {load_factor}% load factor is {comparison} for {bldg_type}s (typical: 50-70%). A low load factor means sharp demand spikes that utilities penalize; a high load factor means steady, predictable consumption. ODCV can improve load factor by reducing ventilation during unoccupied periods instead of running at full capacity then shutting down. Source: Calculated from your utility bill structure using standard utility rate analysis methodology."

---

## Total GHG Emissions

"Total greenhouse gas emissions of {ghg} metric tons CO2e/year, calculated from your actual fuel consumption: electricity at {elec_kwh} kWh × {grid_factor} kg CO2/kWh (EPA eGRID {region} factor) + natural gas at {gas_therms} therms × 5.3 kg CO2/therm + steam at {steam_mmbtu} MMBtu × {steam_factor} kg CO2/MMBtu. Post-ODCV emissions: {post_ghg} metric tons—a reduction of {delta_ghg} metric tons ({pct_reduction}%). For context, one metric ton CO2 equals driving 2,500 miles or powering a home for 1.2 months. Sources: EPA eGRID 2022, EIA combustion emission factors, city steam plant disclosures where available."
