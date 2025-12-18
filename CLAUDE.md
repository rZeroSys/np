# CLAUDE INSTRUCTIONS FOR THIS PROJECT

================================================================================
##            THE ONE SCRIPT TO RULE THEM ALL
================================================================================

**TO UPDATE DATA AND REGENERATE EVERYTHING, RUN THIS:**

```bash
python3 scripts/MASTER_ORCHESTRATE.py "Your commit message"
```

This single script does EVERYTHING:
1. Backs up portfolio_data.csv
2. Runs all data calculation scripts
3. Regenerates the homepage
4. Regenerates all building reports (including NYC special reports)
5. Commits and pushes to GitHub

**DO NOT run individual scripts unless you know what you're doing.**
**DO NOT create new orchestration scripts - use MASTER_ORCHESTRATE.py.**

================================================================================
##            HOMEPAGE ONLY (NO BUILDING REPORTS)
================================================================================

**TO REGENERATE JUST THE HOMEPAGE (fast, ~10 seconds):**

```bash
./regen_homepage.sh
```

OR:

```bash
python3 -m src.generators.html_generator
```

Use this when you've only changed:
- CSS styles in html_generator.py
- Homepage layout/UI
- Filter logic
- JavaScript functionality

This does NOT regenerate building report HTML files.

================================================================================

---

## BACKUP POLICY - READ THIS FIRST

**ALL BACKUPS GO IN `BACKUPS_GO_HERE/` FOLDER**

```
BACKUPS_GO_HERE/
├── csv_backups/      <- CSV backups (portfolio_data_backup_*.csv)
└── script_backups/   <- Script backups (*_backup_*.py)
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
│   │   └── update_*_utilization.py  # Building type utilization updates
│   ├── images/                   # Image fetching/upload
│   ├── logos/                    # Logo processing
│   ├── nyc/                      # NYC-specific scripts
│   └── utils/                    # Utility scripts
│
├── data/source/                  # Source data files (see detailed list below)
│   ├── portfolio_data.csv        # MAIN DATA FILE (~23k buildings)
│   ├── portfolio_organizations.csv  # Org logos, classifications, aliases
│   └── [other CSVs...]           # Supporting data files
│
├── docs/methodology/             # Methodology documentation
├── assets/                       # Images and logos
├── output/                       # Generated HTML output
├── BACKUPS_GO_HERE/              # ALL BACKUPS HERE
└── staging/                      # Temporary staging
```

---

## Source CSV Files (data/source/)

### PRIMARY DATA FILES

#### `portfolio_data.csv` (~23k rows) - THE MAIN DATA FILE
The master building database. Contains all building records with energy, location, organization, and calculated fields.
- **Used by**: `src/data/loader.py`, `src/generators/html_generator.py`, `src/generators/building_report.py`
- **Modified by**: Most scripts in `scripts/data_updates/`, `scripts/populate_master/`
- **Key columns**: See "KEY COLUMNS" section below

#### `portfolio_organizations.csv` (~1,200 rows) - ORG METADATA
Master list of organizations (owners, tenants) with their logos, classifications, and display info.
- **Columns**: `organization`, `row_count`, `logo_file`, `classification`, `display_name`, `aws_logo_url`, `search_aliases`, `vertical`, `org_type`, `logo_url`, `org_url`, `primary_building_type`
- **Used by**: `src/data/loader.py` (loads logo mappings, classifications, search aliases)
- **Modified by**: `scripts/logos/fetch_validate_upload_logos.py`, `scripts/utils/add_search_aliases.py`
- **Purpose**: Provides logo URLs, display names, and search aliases for the UI

### LOOKUP/MAPPING FILES

#### `building_type_to_vertical.csv` (17 rows) - TYPE-TO-VERTICAL MAPPING
Maps `bldg_type` values to `bldg_vertical` categories (e.g., "Office" -> "Commercial").
- **Columns**: `building_type`, `vertical`
- **Used by**: `scripts/populate_master/00_align_verticals.py`
- **Purpose**: Ensures consistent vertical categorization across all buildings

#### `column_rename_lookup.csv` (70 rows) - COLUMN NAME DEFINITIONS
Documents column naming: old names, new prefixed names, and definitions.
- **Columns**: `old_name`, `new_name`, `definition`
- **Purpose**: Reference for understanding column naming convention

#### `utility_logos.csv` (21 rows) - UTILITY COMPANY LOGOS
Maps utility companies to their logo files.
- **Columns**: `utility_name`, `logo_file`, `aws_logo_url`
- **Used by**: `src/generators/building_report.py` (displays utility logos on building pages)

### LEED CERTIFICATION DATA

#### `leed_certified_buildings.csv` (~33k rows) - RAW LEED DATABASE
Complete USGBC LEED certification database.
- **Purpose**: Source data for matching buildings to LEED certifications

#### `leed_matches.csv` (~2k rows) - MATCHED LEED RECORDS
Buildings matched to LEED certifications by address proximity.
- **Columns**: `zip_idx`, `portfolio_idx`, `leed_idx`, `portfolio_address`, `leed_address`, `distance_m`, `leed_certification_level`, `leed_certification_date`, `leed_rating_system`, `leed_project_url`, `leed_project_id`
- **Used by**: `src/generators/building_report.py` (shows LEED badge on certified buildings)

#### `leed_property_names.csv` (~1,100 rows) - LEED PROPERTY NAMES
Property names fetched from LEED project pages for manual review.
- **Created by**: `scripts/data_updates/fetch_leed_property_names.py`
- **Purpose**: Helps identify building names from LEED records

### CALCULATED/DERIVED DATA

#### `eui_post_odcv.csv` (~24k rows) - POST-ODCV EUI VALUES
Pre-calculated EUI (Energy Use Intensity) values after ODCV adjustments.
- **Columns**: `id_building`, `energy_site_eui_post_odcv`
- **Used by**: Referenced in `src/config.py` as `EUI_POST_ODCV_PATH`

### DATA QUALITY FILES

#### `correction_log.csv` (~1,100 rows) - AUTOMATED CORRECTIONS
Log of automated data corrections (e.g., invalid Energy Star scores removed).
- **Columns**: `id_building`, `column`, `old_value`, `new_value`, `reason`, `timestamp`
- **Purpose**: Audit trail for automated data cleanup

#### `potential_issues.csv` (~400 rows) - DATA QUALITY FLAGS
Flagged records that may need manual review (e.g., tenant/building type mismatches).
- **Columns**: `id_building`, `property_name`, `address`, `issue_type`, `current_value`, `expected`, `org`
- **Used by**: `scripts/api_data_validator.py`
- **Purpose**: Identifies records like "Marriott tenant but Office type" that may need fixing

#### `recommended_tenant_changes.csv` (~30 rows) - SUGGESTED FIXES
Suggested tenant corrections for manual review.
- **Purpose**: Queue of potential tenant data fixes

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

## CSV EDITING RULES - CRITICAL

================================================================================
###        ALWAYS USE PYTHON CSV MODULE - NO EXCEPTIONS
================================================================================

**NEVER use awk, sed, cut, or bash string manipulation on portfolio_data.csv.**

The file has quoted fields containing commas. Tools like awk see commas inside quotes as delimiters and WILL corrupt the file by:
- Dropping rows
- Shifting columns
- Truncating data

**Claude has corrupted this file multiple times using awk. Claude also reports WRONG DATA when reading/analyzing with awk or cut instead of Python. ONLY use Python's csv module for BOTH reading and writing.**

### Correct approach:
```python
import csv

input_file = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv'
output_file = '/tmp/portfolio_data_fixed.csv'

with open(input_file, 'r', newline='', encoding='utf-8') as f:
    reader = csv.reader(f)
    header = next(reader)
    rows = list(reader)

col_idx = {name: i for i, name in enumerate(header)}
tenant_idx = col_idx['org_tenant']
subunit_idx = col_idx['org_tenant_subunit']
owner_idx = col_idx['org_owner']
hq_idx = col_idx['bldg_hq_org']

# Make changes to rows here
for row in rows:
    if row[0] == "BUILDING_ID":
        row[tenant_idx] = "New Tenant"
        # etc.

with open(output_file, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(header)
    writer.writerows(rows)

# VERIFY row count before replacing
print(f"Rows: {len(rows) + 1}")
```

### Then verify and copy:
```bash
wc -l /tmp/portfolio_data_fixed.csv
wc -l /Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv
# Row counts should match!
cp /tmp/portfolio_data_fixed.csv /Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv
```

### KEY COLUMNS (with indexes)
- `id_building` (0) - unique ID
- `id_property_name` (1) - building name
- `loc_address` (4) - address
- `loc_city` (5) - city
- `bldg_sqft` (10) - square footage
- `bldg_type` (11) - building type (Office, Hotel, Retail Store, etc.)
- `bldg_type_benchmark` (12)
- `bldg_type_filter` (13)
- `bldg_vertical` (14)
- `org_owner` (18) - owner organization
- `org_tenant` (19) - tenant organization
- `org_tenant_subunit` (20) - tenant sub-brand (e.g., Bloomingdale's under Macy's)
- `bldg_hq_org` (90) - headquarters organization

### VERIFYING CHANGES
Always verify row count matches before and after changes. If you see fewer rows, YOU CORRUPTED THE FILE. Restore from backup immediately:
```bash
ls -lt BACKUPS_GO_HERE/csv_backups/ | head -5  # Find most recent backup
cp BACKUPS_GO_HERE/csv_backups/portfolio_data_backup_LATEST.csv data/source/portfolio_data.csv
```

---

## TENANT/ORG DATA RULES

### CANONICAL ORG NAMES
Always use canonical names from:
```
/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_organizations.csv
```
First column is the canonical name. Check this before setting tenant/owner values.

### TENANT/SUBUNIT RELATIONSHIPS
When a subsidiary brand is the tenant, set PARENT as org_tenant and SUBSIDIARY as org_tenant_subunit:

| org_tenant | org_tenant_subunit |
|------------|-------------------|
| Macy's | Bloomingdale's |
| TJX Companies | Marshalls |
| TJX Companies | T.J. Maxx |
| TJX Companies | HomeGoods |
| Gap Inc. | Old Navy |
| Gap Inc. | Banana Republic |
| Amazon | Whole Foods Market |
| Kroger | Fred Meyer |
| Kroger | Ralphs |
| Kroger | Food 4 Less |
| Albertsons Companies | Safeway |
| Albertsons Companies | Vons |
| Ross Stores | dd's DISCOUNTS |
| Neiman Marcus Group | Bergdorf Goodman |
| Save Mart Companies | FoodMaxx |
| Microsoft | GitHub |
| Microsoft | LinkedIn |
| Walmart | Sam's Club |
| Nordstrom | Nordstrom Rack |
| Hilton | Hampton Inn |
| Hilton | DoubleTree |
| Hilton | Embassy Suites |
| Marriott | Sheraton |
| Marriott | Westin |
| Marriott | Courtyard |
| Marriott | Residence Inn |

### STANDALONE COMPANIES (no subunit needed)
- Victoria's Secret & Co.
- Sotheby's
- Trump Organization
- GoDaddy
- Hewlett Packard Enterprise

### WHEN TO SET bldg_hq_org
Only set this when the building is a company's HEADQUARTERS (e.g., Hyatt Center in Chicago is Hyatt's global HQ).

---

## FINDING MISSING TENANTS

### Strategy 1: Search for known brand patterns in property names
Be VERY careful with false positives. These patterns cause problems:
- "cisco" matches "San Francisco"
- "ea" matches "center", "east", "healthcare"
- "square" matches building names like "Union Square"
- City names match county/city organizations

Only use very specific brand names.

### Strategy 2: Look at largest buildings missing both owner AND tenant
```python
# Sort by sqft descending, filter where owner=='' and tenant==''
# Manually identify recognizable buildings
```

### Strategy 3: Owner-occupied buildings
If owner is a known tenant-type company (retailer, tech, etc.) and tenant is empty, they're likely the tenant too.

### Strategy 4: Match property name exactly to canonical org name
Low yield but high confidence.

### Strategy 5: Use your knowledge
Look at building names and addresses. Many are recognizable:
- Named buildings (e.g. "Salesforce Tower" -> tenant: Salesforce)
- Stadium/arena names (e.g. "Chase Center" -> could be Golden State Warriors)
- Hotels (Hilton, Marriott, Hyatt buildings -> those are tenants)
- Retail (Target, Walmart, Costco in name -> those are tenants)
- Tech campuses (Apple, Google, Meta, etc.)

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
cp BACKUPS_GO_HERE/script_backups/html_generator_WORKING_*.py src/generators/html_generator.py
```

### DO NOT
- Change max-width values without checking alignment
- Change margin-right on the Map button container
- Remove the filter drawer close button

---

## Useful Commands

### FULL UPDATE - Use This!
```bash
python3 scripts/MASTER_ORCHESTRATE.py "Your commit message"
```

### Manual Commands (only if you need individual steps)
```bash
# Regenerate homepage only
python3 -m src.generators.html_generator

# Regenerate building reports only
python3 -m src.generators.building_report
```
