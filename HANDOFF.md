# Handoff Notes for Next Claude

## Critical: Always Make Backups First

**BEFORE editing any file, create backups:**

```bash
# Backup CSV data
cp data/source/portfolio_data.csv data/source/portfolio_data_backup_$(date +%Y%m%d_%H%M%S).csv

# Backup Python generators
cp src/generators/html_generator.py backup/html_generator_backup_$(date +%Y%m%d_%H%M%S).py
cp src/generators/building_report.py backup/building_report_backup_$(date +%Y%m%d_%H%M%S).py
```

---

## Project Structure

```
/Users/forrestmiller/Desktop/nationwide-prospector/
├── data/source/
│   ├── portfolio_data.csv          # Main building data (23,882 rows)
│   └── portfolio_organizations.csv # Logo mappings, classifications
├── src/
│   ├── data/loader.py              # Data loading, portfolio aggregation
│   └── generators/
│       ├── html_generator.py       # Homepage (index.html)
│       └── building_report.py      # Individual building pages
├── output/html/
│   ├── index.html                  # Generated homepage
│   ├── data/                       # JS data files for lazy loading
│   │   ├── portfolio_cards.js      # All portfolio card data
│   │   ├── filter_data.js          # Filter aggregations
│   │   └── portfolios/p_*.js       # Per-portfolio building data
│   └── buildings/                  # 23,881 building HTML files
└── backup/                         # Code backups
```

---

## Regeneration Commands

```bash
# Regenerate homepage only (~30 seconds)
python3 -m src.generators.html_generator

# Regenerate all building reports (~5 minutes, 23,881 files)
python3 -m src.generators.building_report

# Regenerate everything and push to GitHub
./scripts/regenerate_and_push.sh "Your commit message"
```

---

## Key Files & What They Control

### html_generator.py (~6000 lines)

| Lines | Section |
|-------|---------|
| 1-300 | Data preparation, PORTFOLIO_CARDS, FILTER_DATA |
| 300-1400 | CSS styles |
| 1400-2700 | More CSS |
| 2700-3600 | HTML structure, portfolio cards |
| 3600-4800 | JavaScript functions |
| 4800-6000 | More JS, infinite scroll, filtering |

**Important patterns:**
- Pre-rendered cards (first 100): `_render_portfolio_card()` at ~line 3520
- Lazy-loaded cards: `renderPortfolioCard()` JS function at ~line 5888
- Portfolio column headers: `.sort-col` CSS at ~line 1870
- Buildings tab: `.cities-header` CSS at ~line 1181

### building_report.py (~1400 lines)

| Lines | Section |
|-------|---------|
| 1-100 | Imports, constants, AWS bucket URL |
| 100-500 | Hero section, image handling |
| 500-700 | Property section (formerly "Building & Property") |
| 700-1000 | Energy section (electricity, gas/fuel oil merged) |
| 1000-1200 | ODCV Savings section |
| 1200-1400 | Main generation logic |

**Important patterns:**
- Gas + Fuel Oil merged into single row: `generate_energy_section()` ~line 893
- Tenant + sub-org with logos: lines 528-577
- Owner/Occupier display logic: lines 549-577

---

## Data Flow

1. **portfolio_data.csv** → `loader.py` → `html_generator.py` → **index.html**
2. **portfolio_data.csv** → `building_report.py` → **buildings/*.html**

### Portfolio Classification Types
- `owner` - Building owner
- `tenant` - Primary tenant
- `tenant_sub_org` - Sub-brand (e.g., Sheraton under Marriott)
- `property manager` - Property management company
- `owner/occupier` - Owner-occupied buildings

### Tenant Sub-Org Display
- Homepage: Shows "Radisson (Choice Hotels Owned)" on two lines
- Building report: Shows "Wyndham [logo] (La Quinta [logo])"

---

## Recent Changes (Dec 2024)

1. **Fuel Oil HVAC %** - Fixed pct_fuel_oil_hvac to use gas HVAC % when both present
2. **Merged Gas/Fuel Oil Row** - Energy section shows single "Natural Gas & Fuel Oil" row
3. **Tenant Sub-Org Logos** - Building reports show both tenant and sub-org logos
4. **Parent Owned Display** - Portfolio cards show "(Parent Owned)" on second line
5. **Hover Effects** - Portfolio column headers now have hover visual cue

---

## Common Tasks

### Add/Change Column Header Text
Edit HTML in `_generate_portfolio_section()` around line 3348

### Change Portfolio Card Layout
- Pre-rendered: `_render_portfolio_card()` ~line 3520
- Lazy-loaded: `renderPortfolioCard()` JS ~line 5888
- CSS: `.portfolio-header` ~line 1852

### Change Building Report Section
Functions in building_report.py:
- `generate_hero()` - Top section with name, address
- `generate_building_info()` - Property table
- `generate_energy_section()` - Energy usage table
- `generate_odcv_section()` - Savings table

### Add New Data Field
1. Add column to portfolio_data.csv
2. Add to loader.py data extraction
3. Add to html_generator.py or building_report.py display

---

## Debugging Tips

```python
# Check specific building data
python3 -c "
import csv
with open('data/source/portfolio_data.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['building_id'] == 'BOS_100093':
            print(row)
            break
"

# Check portfolio card data
python3 -c "
import json, re
with open('output/html/data/portfolio_cards.js', 'r') as f:
    content = f.read()
    match = re.search(r'const PORTFOLIO_CARDS = (\[.*\]);', content, re.DOTALL)
    cards = json.loads(match.group(1))
    for c in cards:
        if c['org_name'] == 'Radisson':
            print(c)
"
```

---

## DO NOT CHANGE (per CLAUDE.md)

- `.vertical-filter-inner` max-width: 1272px
- Map button container margin-right: 85px
- Filter drawer close button structure

---

## Quick Reference

| Task | Command |
|------|---------|
| Regenerate homepage | `python3 -m src.generators.html_generator` |
| Regenerate buildings | `python3 -m src.generators.building_report` |
| Open specific building | `open output/html/buildings/BOS_100093.html` |
| Search in generated HTML | `grep "pattern" output/html/index.html` |
| Count portfolios | `grep -c 'portfolio-card' output/html/index.html` |
