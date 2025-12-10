# CLAUDE INSTRUCTIONS FOR THIS PROJECT

## BACKUP POLICY - READ THIS FIRST

**ALL BACKUPS GO IN `BACKUPS_GO_HERE/` FOLDER**

```
BACKUPS_GO_HERE/
├── csv_backups/      <- CSV backups (portfolio_data_backup_*.csv)
├── script_backups/   <- Script backups (*_backup_*.py)
└── legacy_archive/   <- Old archived files
```

### When creating backups:
- CSV files: `BACKUPS_GO_HERE/csv_backups/filename_backup_YYYYMMDD_HHMMSS.csv`
- Python scripts: `BACKUPS_GO_HERE/script_backups/filename_backup_YYYYMMDD_HHMMSS.py`

### NEVER create backups in:
- `data/source/` (only live data)
- `scripts/` (only active scripts)
- `src/` (only active code)
- Root directory

---

## Directory Structure

```
nationwide-prospector/
├── src/                          # Core application code
│   ├── config.py                 # Central configuration
│   ├── data/loader.py            # Data loading
│   └── generators/               # HTML generation
│       ├── html_generator.py
│       └── building_report.py
│
├── scripts/                      # All runnable scripts
│   ├── data_updates/             # Scripts that modify portfolio_data.csv
│   │   ├── update_nyc_buildings.py
│   │   ├── calculate_odcv_savings.py
│   │   ├── calculate_valuation_impact.py
│   │   └── national_bps_calculator.py
│   ├── images/                   # Image fetching/upload
│   ├── logos/                    # Logo processing
│   └── utils/                    # Utility scripts
│
├── data/source/                  # Source data files
│   ├── portfolio_data.csv        # MAIN DATA FILE (23,882 buildings)
│   ├── portfolio_organizations.csv
│   └── column_rename_lookup.csv  # Column name mapping
│
├── docs/methodology/             # Methodology documentation
├── assets/                       # Images and logos
├── output/                       # Generated HTML output
├── BACKUPS_GO_HERE/              # ALL BACKUPS HERE
└── staging/                      # Temporary staging
```

---

## Column Naming Convention

All columns in `portfolio_data.csv` use prefixes:
- `id_` - Identifiers
- `loc_` - Location
- `bldg_` - Building characteristics
- `org_` - Organizations
- `energy_` - Energy consumption
- `cost_` - Utility costs
- `hvac_` - HVAC data
- `odcv_` - ODCV savings (HVAC-only)
- `bps_` - Building Performance Standards
- `savings_` - Combined savings
- `val_` - Valuation

See `docs/methodology/DATA_DICTIONARY.md` for full definitions.

---

## CRITICAL - DO NOT CHANGE THESE VALUES

### Button/Layout Alignment - LOCKED IN

These values are carefully calibrated to align the UI elements. DO NOT MODIFY:

#### 1. `.vertical-filter-inner` (line ~374)
```css
max-width: 1272px;
padding: 0;
```

#### 2. Map button container (line ~2365)
```css
margin-right: 85px;
```

#### 3. Filter drawer close button (line ~2341)
```html
<button class="filter-drawer-close" onclick="toggleFilterDrawer()">&times;</button>
```

### If alignment breaks
Restore from backup:
```bash
cp BACKUPS_GO_HERE/script_backups/html_generator_WORKING_20251208_161703.py src/generators/html_generator.py
```

### DO NOT
- Change max-width values without checking alignment
- Change margin-right on the Map button container
- Remove the filter drawer close button

---

## Useful Commands

### Regenerate & Push to GitHub
```bash
./scripts/regenerate_and_push.sh "Your commit message"
```

### Manual Commands
```bash
# Regenerate homepage only
python3 -m src.generators.html_generator

# Regenerate building reports only
python3 -m src.generators.building_report

# Update NYC buildings
python3 scripts/data_updates/update_nyc_buildings.py

# Recalculate ODCV savings
python3 scripts/data_updates/calculate_odcv_savings.py

# Recalculate valuation impact
python3 scripts/data_updates/calculate_valuation_impact.py

# Recalculate BPS fines
python3 scripts/data_updates/national_bps_calculator.py
```
