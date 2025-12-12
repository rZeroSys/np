# HANDOFF NOTES FOR NEXT CLAUDE SESSION

## CRITICAL UNDERSTANDING - READ THIS FIRST

### Building Report Structure (MUST BE CRYSTAL CLEAR)

**ENERGY SECTION** = HOW MUCH SAVINGS
- Shows electricity, gas, fuel oil, steam consumption
- Shows Current vs New vs Change
- Explains HOW we calculate the HVAC savings percentage
- Methodology link goes to `methodology.html#energy`

**IMPACT SECTION** = VALUE OF THOSE SAVINGS
- Shows Utility Cost savings ($)
- Shows Property Value increase
- Shows Energy Star Score improvement
- Shows BPS Fine Avoidance
- Shows Carbon Emissions reduction
- Methodology link goes to `methodology.html#opex`

---

## BUGS FOUND THIS SESSION

### 1. hvac_pct_gas is 0/missing for 6,897 buildings
- 522 hotels affected
- Causes tooltips to say "0% of gas is HVAC" which is WRONG
- Need to populate from BUILDING_TYPE_CONFIG values in building_report.py
- Hotels should be ~20% (gas_hvac_typical: 0.197)

### 2. Logo filename hyphen bug - FIXED
- `get_logo_filename()` wasn't removing hyphens
- "Ritz-Carlton" became "Ritz-Carlton.png" but S3 has "RitzCarlton.png"
- Added `name = name.replace('-', '')` to fix

### 3. Purple color - FIXED
- Replaced `#6366f1` (purple/indigo) with `#3b82f6` (blue)

---

## CHANGES MADE THIS SESSION

### building_report.py
1. Separated "Energy & Impact" into two sections: "Energy" and "Impact"
2. Added Methodology links next to both h2 headers (NOT far away, RIGHT NEXT TO)
3. Moved building data source link from header to "Property" section as "More Info"
4. Fixed logo filename generation to remove hyphens
5. Changed purple to blue color

### methodology.html
1. Removed giant header "Nationwide Prospector - Definitive Technical Guide..."
2. Removed Table of Contents
3. Removed Section 1 "What Nationwide Prospector Produces"
4. Renumbered all sections and subsections
5. Removed duplicate "Sources & References" section at end

---

## FILES INVOLVED

- `/Users/forrestmiller/Desktop/nationwide-prospector/src/generators/building_report.py` - Main report generator
- `/Users/forrestmiller/Desktop/nationwide-prospector/output/html/methodology.html` - Methodology page
- `/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv` - 23,698 buildings

---

## REGENERATE COMMANDS

```bash
# Single building report
python3 -c "
from src.generators.building_report import generate_html_report
from src.data.loader import load_portfolio_data
df = load_portfolio_data()
row = df[df['id_building'] == 'ATL_179'].iloc[0]
html = generate_html_report(row)
with open('output/html/buildings/ATL_179.html', 'w') as f:
    f.write(html)"

# All building reports
python3 -m src.generators.building_report
```

---

## STILL TODO

1. **FIX hvac_pct_gas in CSV** - 6,897 buildings need this populated
2. **Verify methodology.html deep links work** - #energy and #opex anchors
3. **Regenerate ALL building reports** after CSV fix
4. **Hotel savings tooltip** - User asked about this, needs verification

---

## BUILDING TYPE CONFIG (for reference)

Hotels:
- gas_hvac_typical: 0.197 (only 20% of gas is HVAC)
- elec_hvac_typical: 0.47 (47% of electricity is HVAC)
- Rest of gas: 42% hot water, 33% cooking

The ODCV methodology tooltip for hotels should say:
```
Hotels save 15-35% on HVAC.
Room-level controls adjust to actual guests -
typically 65-75% occupancy. Note: only 20%
of gas is HVAC here. Rest is hot water (42%)
and kitchen (33%).
```

---

## USER FRUSTRATIONS TO AVOID

1. DON'T put methodology link far from section header - put it RIGHT NEXT TO
2. DON'T gut content without asking
3. DON'T mess up numbering
4. DO verify changes by opening the actual HTML file
5. DO use Python for CSV analysis, not bash
