# How We Estimate Energy Savings from Occupancy-Driven Ventilation
## A Complete Methodology Guide

---

# Part 1: The Problem We're Solving

## Buildings Waste Energy Ventilating Empty Space

Every commercial building has a ventilation system that brings in fresh outdoor air. This is essential—people need oxygen, and indoor air quality matters. Building codes specify exactly how much fresh air each space needs, typically measured in cubic feet per minute (CFM) per person.

Here's the problem: **most buildings ventilate based on how many people the space was *designed* for, not how many people are actually there.**

Consider a typical office floor designed for 200 people:
- The ventilation system delivers fresh air for 200 people
- But on any given Tuesday, only 120 people show up (hybrid work)
- And 3 floors are completely vacant (no tenant)
- The building is pumping in fresh air for 800 people who don't exist

That fresh outdoor air isn't free. In winter, it's 20°F outside and 70°F inside—every cubic foot of outdoor air needs to be heated. In summer, it's 95°F and humid outside, 72°F and dry inside—every cubic foot needs to be cooled and dehumidified.

**Ventilating empty space is pure waste.**

---

## What Occupancy-Driven Demand Control Ventilation (O-DCV) Does

O-DCV uses real-time occupancy sensors to answer a simple question: *How many people are actually in this zone right now?*

Then it adjusts ventilation to match:
- Conference room designed for 20 people but only 4 are there? Deliver air for 4.
- Entire floor is empty at 6pm? Reduce to minimum setback.
- Big meeting happening? Ramp up for actual headcount.

The savings come from three places:
1. **Fan energy** — fans run slower when less air is needed
2. **Heating energy** — less cold outdoor air to heat in winter
3. **Cooling energy** — less hot/humid outdoor air to cool in summer

---

# Part 2: Our Estimation Approach

## The Core Question

We have data on 26,648 commercial buildings. For each one, we need to estimate: **What percentage of HVAC energy could O-DCV save?**

We don't have occupancy sensor data for these buildings (if we did, they'd already have O-DCV). So we use available data to estimate the *opportunity* for savings.

## The Factors That Matter

After analyzing what drives O-DCV savings potential, we identified five key factors:

| Factor | What It Tells Us |
|--------|------------------|
| **Vacancy Rate** | How much space has no tenant at all? |
| **Utilization Rate** | When space is leased, how fully is it actually used? |
| **Building Type** | Does this type of building have variable occupancy? |
| **Year Built** | Does the building likely have controls that can implement O-DCV? |
| **Square Footage** | Larger buildings typically have more sophisticated systems |

Plus two modifiers:
- **Energy Efficiency** (Energy Star score or EUI) — inefficient buildings have more waste to capture
- **Climate Zone** — colder climates have higher heating penalties per CFM of outdoor air

---

# Part 3: The Formula

## Basic Structure

```
ODCV Savings % = Floor + (Opportunity × Automation × Range) × Modifiers
```

Where:
- **Floor** = Minimum savings even in worst case (building type specific)
- **Ceiling** = Maximum realistic savings (building type specific)
- **Range** = Ceiling - Floor
- **Opportunity** = How much empty/underutilized space exists (0 to 1)
- **Automation** = How likely the building can implement O-DCV (0 to 1)
- **Modifiers** = Adjustments for efficiency and climate

---

## Opportunity Score: The Heart of the Calculation

### Why Building Type Determines the Formula

Not all buildings work the same way. The critical question is: **When space is empty, is it still being ventilated?**

#### Multi-Tenant Commercial Buildings (Office, Medical Office, Mixed Use, Strip Mall)

These buildings have **centralized HVAC systems controlled by the landlord**, not individual tenants.

When a floor is vacant (no tenant), the landlord typically can't just shut off that floor's ventilation because:
- Fire code often requires minimum ventilation in all occupied buildings
- The building management system treats "unoccupied" as "nighttime setback," not "zero"
- Vacant floors often get shown to prospective tenants (need to be comfortable)
- Systems are interconnected—you can't always isolate one floor

**Result: Vacant space in these buildings is often ventilated at or near design capacity for people who don't exist.**

On top of that, the *leased* space has its own utilization problem. With hybrid work, a floor leased for 100 people might only have 60 people on any given day.

**Formula for these building types:**
```
Opportunity = Vacancy + (1 - Vacancy) × (1 - Utilization)
```

**Example:** 25% vacancy, 55% utilization
- 25% of building is vacant but still ventilated → 25% waste
- 75% is leased, but only 55% utilized → 75% × 45% = 34% waste
- **Total opportunity: 59%**

#### Single-Tenant / Owner-Occupied Buildings (Schools, Hotels, Retail, etc.)

These buildings don't have "vacancy" in the traditional sense. A school district owns the school. A hotel operates all its rooms. A retailer controls its store.

For these, the opportunity is driven purely by **utilization**—how much of the operating time the space is actually occupied.

**Formula:**
```
Opportunity = 1 - Utilization
```

**Examples:**
- K-12 School at 45% utilization (empty summers, after 3pm, holidays) → 55% opportunity
- Retail store at 60% utilization (empty before open, after close, slow periods) → 40% opportunity

#### 24/7 and High-Ventilation-Requirement Buildings (Hospitals, Labs, etc.)

Some buildings simply can't reduce ventilation much, regardless of occupancy:

- **Hospitals** must maintain high air change rates for infection control
- **Laboratories** have fume hoods and safety requirements mandating high outdoor air
- **Police/Fire stations** operate 24/7 with limited downtime

For these, we apply a **0.3 multiplier** to the opportunity score, reflecting that only about 30% of the theoretical savings are actually capturable.

**Formula:**
```
Opportunity = (1 - Utilization) × 0.3
```

#### Data Centers

Data centers ventilate to remove heat from equipment, not to provide fresh air for people. Occupancy is irrelevant.

**Formula:**
```
Opportunity = 0
```

---

## Automation Score: Can the Building Actually Do This?

Having opportunity is only half the equation. The building needs controls sophisticated enough to implement O-DCV.

### Year Built Score

Newer buildings are far more likely to have:
- Building Management Systems (BMS) with BACnet/IP connectivity
- Variable Air Volume (VAV) systems with DDC controls
- Network infrastructure to support occupancy sensors
- Modern damper actuators that can modulate smoothly

| Construction Era | Typical Systems | Score |
|------------------|-----------------|-------|
| Before 1970 | Pneumatic controls, constant volume | 0.00 |
| 1970-1989 | Early electronic, limited DDC | 0.25 |
| 1990-2004 | DDC becoming standard, basic BMS | 0.50 |
| 2005-2014 | Modern BMS, IP-based controls | 0.75 |
| 2015+ | Smart building ready, integrated systems | 1.00 |

### Size Score

Larger buildings justify more sophisticated systems:
- Higher energy costs = faster payback on controls investment
- More likely to have dedicated facilities staff
- More likely to have been commissioned properly
- Manufacturers target large buildings for advanced systems

| Square Footage | Typical Sophistication | Score |
|----------------|------------------------|-------|
| Under 50,000 | Rooftop units, simple thermostats | 0.25 |
| 50,000-100,000 | Basic BMS, some VAV | 0.50 |
| 100,000-250,000 | Full BMS, VAV throughout | 0.75 |
| Over 250,000 | Advanced BMS, multiple AHUs, sophisticated zoning | 1.00 |

### Combined Automation Score

```
Automation Score = (Year Score + Size Score) / 2
```

A 2018 building of 300,000 sqft: (1.0 + 1.0) / 2 = **1.0**
A 1975 building of 60,000 sqft: (0.25 + 0.5) / 2 = **0.375**

---

## Efficiency Modifier: Where Is the Waste?

Buildings that are already efficient have less waste to capture. Buildings that are inefficient have more.

### Using Energy Star Score (When Available)

Energy Star scores compare a building's energy use to similar buildings nationwide. A score of 50 is median; higher is better.

| Energy Star Score | What It Means | Modifier |
|-------------------|---------------|----------|
| 90+ | Top 10% efficiency | 0.85 (less waste to find) |
| 75-89 | Better than 75% | 0.95 |
| 50-74 | Average | 1.00 |
| 25-49 | Below average | 1.05 |
| Below 25 | Bottom quartile | 1.10 (lots of waste) |

### Using EUI as Fallback (When Energy Star Missing)

When Energy Star score isn't available, we compare the building's Energy Use Intensity (EUI = kBtu per square foot per year) to the median EUI for its building type.

| EUI vs. Peer Median | Modifier |
|---------------------|----------|
| More than 1.5× median | 1.10 |
| 1.2× to 1.5× median | 1.05 |
| 0.85× to 1.2× median | 1.00 |
| 0.7× to 0.85× median | 0.95 |
| Less than 0.7× median | 0.90 |

---

## Climate Modifier: The Cost of Outdoor Air

Every cubic foot of outdoor air that enters a building must be conditioned to indoor temperature and humidity. This "penalty" varies by climate:

| Climate Zone | Heating Degree Days | Cooling Degree Days | Modifier |
|--------------|--------------------|--------------------|----------|
| Northern | 6,000+ | 500-1,500 | 1.10 |
| North-Central | 4,000-6,000 | 1,000-2,000 | 1.05 |
| South-Central | 2,000-4,000 | 2,000-3,000 | 1.00 |
| Southern | Under 2,000 | 3,000+ | 0.95 |

In Northern climates, reducing 1 CFM of outdoor air saves more energy because the temperature differential is larger and the heating season is longer.

---

# Part 4: Building Type Specific Ranges

## Why Different Buildings Get Different Ranges

A hospital at 100% opportunity still can't achieve the same savings as an office at 100% opportunity—the physics and code requirements are different.

We set **floor** (minimum) and **ceiling** (maximum) values for each building type based on:
1. Operating hours and patterns
2. Code-mandated ventilation requirements
3. Occupancy variability
4. System configurability
5. Industry benchmarks and case studies

---

## High-Opportunity Building Types (20%+ Ceiling)

### Office (20% - 40%)

**Why this range makes sense:**

Offices have the ideal O-DCV profile:
- Clear "occupied" vs. "unoccupied" hours (roughly 7am-7pm weekdays)
- High design occupancy rarely achieved (conference rooms, open floor plans)
- Massive impact from hybrid work (40-50% of desks empty on any given day)
- Significant current vacancy in many markets (20-30%)
- Centralized VAV systems that respond well to zone-level control

Industry case studies consistently show 25-35% HVAC savings from O-DCV in offices. Our 20-40% range captures this, with the actual value depending on vacancy, utilization, automation capability, and climate.

**Floor of 20%:** Even a fully-occupied, fully-utilized office has weekends, holidays, and evening hours where O-DCV provides savings over fixed schedules.

**Ceiling of 40%:** Represents a high-vacancy building in a cold climate with good controls and low utilization—the ideal case.

### K-12 School (20% - 45%)

**Why this range makes sense:**

Schools have extreme schedule-driven vacancy:
- Empty every day after 3pm (25% of weekday hours)
- Empty every weekend (29% of week)
- Empty for summer break (typically 10-12 weeks = 20-25% of year)
- Empty for winter break, spring break, holidays
- Many classrooms underutilized even during school hours

Total "empty" time often exceeds 50% of the year.

**Floor of 20%:** Even when school is in session, occupancy varies by room and period.

**Ceiling of 45%:** Higher than office because of the extreme empty periods (summer, nights, weekends). A school with good controls can capture significant savings.

### Higher Education (20% - 45%)

**Why this range makes sense:**

Similar to K-12, but with even more variability:
- Semester breaks (winter, spring, summer)
- Variable class schedules (some rooms used twice a week)
- Evening/weekend classes in some buildings, empty in others
- Labs and libraries with different patterns than classrooms

### Event Space (20% - 45%)

**Why this range makes sense:**

Convention centers, banquet halls, and event venues have the most extreme occupancy variability:
- Completely empty for days or weeks
- Then full capacity for a single event
- Fixed schedule ventilation makes no sense here

O-DCV is almost essential for these buildings to avoid massive waste during empty periods.

---

## Medium-Opportunity Building Types (15% - 35%)

### Retail Store (15% - 35%)

**Why this range makes sense:**

Retail stores have significant intra-day variability:
- Opening/closing: staff only (maybe 5% of design occupancy)
- Mid-morning lull: 15-20% capacity
- Lunch/evening rushes: 60-80% capacity
- After close: 0% (but systems may run for overnight stocking)

The opportunity comes from modulating to actual customer traffic, not from vacant/unoccupied calculations.

**Floor of 15%:** Stores operate on fairly predictable schedules; baseline savings from proper scheduling.

**Ceiling of 35%:** Stores with high traffic variability (busy weekends, dead weekdays) can capture significant savings.

### Hotel (15% - 35%)

**Why this range makes sense:**

Hotels have unique room-by-room variability:
- Occupancy rates typically 60-80% (20-40% of rooms empty nightly)
- Occupied rooms have variable actual presence (guests out during day)
- Common areas (lobby, restaurant, conference) follow different patterns

Many hotels already have room-level occupancy sensing (keycard, motion) integrated with HVAC, so O-DCV improvement is incremental.

### Gym / Fitness Center (15% - 35%)

**Why this range makes sense:**

Gyms have extreme peak/off-peak patterns:
- 6-8am: packed (morning workout crowd)
- 10am-4pm: relatively empty
- 5-7pm: packed again
- 8pm-5am: empty or minimal

Ventilating a gym at peak capacity during dead hours is pure waste.

---

## Lower-Opportunity Building Types (10% - 25%)

### Supermarket / Grocery (10% - 25%)

**Why this range makes sense:**

Supermarkets operate long hours (often 6am-midnight or 24/7) with steadier traffic than typical retail. The building is actively used for a larger portion of the day, reducing empty-space opportunity.

Additionally, refrigeration cases and kitchen/deli areas have specific ventilation requirements less dependent on customer count.

### Restaurant / Bar (10% - 25%)

**Why this range makes sense:**

Restaurants have predictable meal-time peaks, but the kitchen runs at relatively constant ventilation regardless of dining room occupancy (cooking exhaust requirements). Savings are primarily in the dining area, which is often a smaller portion of total ventilation load.

### Library / Bank Branch / Courthouse (10% - 28%)

**Why this range makes sense:**

These are public-facing buildings with:
- Fixed operating hours
- Relatively steady occupancy during open hours
- Limited extreme peaks or valleys

Savings come primarily from nights/weekends, with modest intra-day optimization opportunity.

---

## Limited-Opportunity Building Types (5% - 15%)

### Inpatient Hospital (5% - 15%)

**Why this range makes sense:**

Hospitals face fundamental constraints on ventilation reduction:
- **Infection control:** Many areas require high air change rates (15-25 ACH for ORs, isolation rooms)
- **24/7 operation:** Hospitals don't close
- **Code requirements:** ASHRAE 170 specifies minimum ventilation that can't be reduced regardless of occupancy
- **Pressure relationships:** Maintaining positive/negative pressure between zones is critical

O-DCV can help in some areas (waiting rooms, administrative areas, non-clinical spaces) but the core clinical areas have limited flexibility.

**Floor of 5%:** Even limited implementation in non-clinical areas provides some savings.

**Ceiling of 15%:** Represents maximum achievable with aggressive implementation in appropriate zones.

### Laboratory (5% - 15%)

**Why this range makes sense:**

Labs have high outdoor air requirements for safety:
- Fume hoods require constant exhaust (and makeup air)
- Many labs maintain negative pressure
- Chemical/biological safety requirements override occupancy

Some savings possible in office/administrative areas within lab buildings, and in labs with VAV fume hoods, but overall opportunity is constrained.

### Police Station / Fire Station (5% - 15%)

**Why this range makes sense:**

These buildings operate 24/7 with:
- Staff present at all times (shift work)
- Readiness requirements that limit setback
- Vehicle bays with specific ventilation needs

Limited opportunity, but some savings possible in administrative areas and during lower-activity periods.

### Residential Care Facility (5% - 15%)

**Why this range makes sense:**

Residents live there 24/7. Unlike an office that empties at night, a nursing home or assisted living facility has constant occupancy in resident rooms. Common areas have some variability, but the overall building load is relatively constant.

---

## Zero-Opportunity Building Type

### Data Center (0%)

**Why this range makes sense:**

Data centers ventilate to remove heat from servers, not to provide fresh air for people. A data center at 3am with one technician and a data center at 3pm with the same one technician have identical cooling loads—it's about the equipment, not the people.

Occupancy-driven ventilation is simply not applicable.

---

# Part 5: Putting It All Together

## Complete Calculation Example

**Building:** 350,000 sqft Class A office in Chicago
- Vacancy: 28%
- Utilization: 52%
- Built: 2008
- Energy Star: 68
- Climate: North-Central

### Step 1: Opportunity Score
```
Opportunity = Vacancy + (1 - Vacancy) × (1 - Utilization)
Opportunity = 0.28 + (0.72 × 0.48)
Opportunity = 0.28 + 0.346
Opportunity = 0.626
```

### Step 2: Automation Score
```
Year Score: 2008 → 0.75
Size Score: 350,000 sqft → 1.0
Automation = (0.75 + 1.0) / 2 = 0.875
```

### Step 3: Efficiency Modifier
```
Energy Star 68 → 1.00 (average efficiency)
```

### Step 4: Climate Modifier
```
North-Central → 1.05
```

### Step 5: Calculate Savings
```
Floor = 20%, Ceiling = 40%, Range = 20%

Base ODCV = 0.20 + (0.626 × 0.875 × 0.20)
Base ODCV = 0.20 + 0.110
Base ODCV = 0.310

Final ODCV = 0.310 × 1.00 × 1.05
Final ODCV = 0.326 = 32.6%
```

**This building could save approximately 32.6% of its HVAC energy through O-DCV implementation.**

---

## Applying Savings to Energy Consumption

Once we have the O-DCV savings percentage, we apply it to the HVAC portion of each fuel type:

```
Electricity HVAC Savings = Electricity Use × % Electric HVAC × ODCV Savings %
Natural Gas HVAC Savings = Gas Use × % Gas HVAC × ODCV Savings %
Steam HVAC Savings = Steam Use × % Steam HVAC × ODCV Savings %
Fuel Oil HVAC Savings = Fuel Oil Use × % Fuel Oil HVAC × ODCV Savings %
```

The HVAC percentages by fuel type are calculated separately based on building type, climate zone, and energy patterns (documented in separate methodology).

---

# Part 6: Validation and Limitations

## What Makes This Methodology Defensible

1. **Grounded in physics:** Ventilation energy is proportional to airflow and temperature differential. Reducing airflow for unoccupied spaces directly reduces energy.

2. **Consistent with industry benchmarks:** Our 20-40% range for offices aligns with documented O-DCV case studies showing 25-35% HVAC savings.

3. **Building-type specific:** Rather than one-size-fits-all, we account for the real operational differences between building types.

4. **Uses available data appropriately:** Vacancy, utilization, building characteristics, and efficiency metrics are reasonable proxies for O-DCV opportunity.

5. **Conservative by design:** Our ranges cap savings at realistic maximums. We don't promise 60% savings that can't be delivered.

## Known Limitations

1. **No actual occupancy data:** We're estimating opportunity from vacancy/utilization, not measuring real occupancy patterns.

2. **Automation assumptions:** Year built and size are proxies for system sophistication, not direct assessments.

3. **Building type averages:** Individual buildings may vary significantly from type averages.

4. **No system-specific analysis:** We don't know if a specific building has VAV vs. constant volume, or the actual control capabilities.

5. **Utility rates not considered:** Savings in kBtu don't account for time-of-use rates, demand charges, or fuel cost differences.

## Recommended Use

These estimates are appropriate for:
- Portfolio-level screening and prioritization
- Initial savings projections for prospect identification
- Benchmarking relative opportunity across buildings

For individual building proposals, these estimates should be validated with:
- On-site assessment of HVAC systems
- Actual occupancy data collection
- Detailed energy modeling

---

# Appendix: Complete Building Type Reference

| Building Type | Floor | Ceiling | Primary Driver | Formula |
|---------------|-------|---------|----------------|---------|
| Office | 20% | 40% | Vacancy + Utilization | V + (1-V)(1-U) |
| Medical Office | 20% | 40% | Vacancy + Utilization | V + (1-V)(1-U) |
| Mixed Use | 18% | 38% | Vacancy + Utilization | V + (1-V)(1-U) |
| Strip Mall | 15% | 35% | Vacancy + Utilization | V + (1-V)(1-U) |
| K-12 School | 20% | 45% | Utilization | 1 - U |
| Higher Ed | 20% | 45% | Utilization | 1 - U |
| Preschool/Daycare | 18% | 38% | Utilization | 1 - U |
| Retail Store | 15% | 35% | Utilization | 1 - U |
| Supermarket/Grocery | 10% | 25% | Utilization | 1 - U |
| Wholesale Club | 10% | 25% | Utilization | 1 - U |
| Enclosed Mall | 12% | 30% | Utilization | 1 - U |
| Hotel | 15% | 35% | Utilization | 1 - U |
| Restaurant/Bar | 10% | 25% | Utilization | 1 - U |
| Gym | 15% | 35% | Utilization | 1 - U |
| Event Space | 20% | 45% | Utilization | 1 - U |
| Theater | 18% | 40% | Utilization | 1 - U |
| Arts & Culture | 15% | 35% | Utilization | 1 - U |
| Library | 12% | 28% | Utilization | 1 - U |
| Bank Branch | 12% | 28% | Utilization | 1 - U |
| Vehicle Dealership | 15% | 35% | Utilization | 1 - U |
| Courthouse | 10% | 25% | Utilization | 1 - U |
| Public Service | 10% | 25% | Utilization | 1 - U |
| Outpatient Clinic | 15% | 32% | Utilization | 1 - U |
| Sports/Gaming Center | 18% | 40% | Utilization | 1 - U |
| Inpatient Hospital | 5% | 15% | Utilization (capped) | (1-U) × 0.3 |
| Specialty Hospital | 5% | 15% | Utilization (capped) | (1-U) × 0.3 |
| Residential Care Facility | 5% | 15% | Utilization (capped) | (1-U) × 0.3 |
| Laboratory | 5% | 15% | Utilization (capped) | (1-U) × 0.3 |
| Police Station | 5% | 15% | Utilization (capped) | (1-U) × 0.3 |
| Fire Station | 5% | 15% | Utilization (capped) | (1-U) × 0.3 |
| Public Transit | 5% | 15% | Utilization (capped) | (1-U) × 0.3 |
| Data Center | 0% | 0% | N/A | 0 |

---

*Methodology Version: 2.0*
*December 2025*
*R-Zero Systems*
