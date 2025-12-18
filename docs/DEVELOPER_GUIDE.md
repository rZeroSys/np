# Nationwide Prospector Developer Guide

This document covers the project structure, data files, scripts, and AWS infrastructure.

---

## Quick Start

### Full Data Update & Regeneration

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

### Homepage Only (Fast)

```bash
python3 -m src.generators.html_generator
```

Use this when you've only changed CSS, layout, or JavaScript.

---

## Directory Structure

```
nationwide-prospector/
├── src/                          # Core application code
│   ├── config.py                 # Central configuration
│   ├── data/loader.py            # Data loading
│   └── generators/               # HTML generation
│       ├── html_generator.py     # Homepage generator
│       └── building_report.py    # Building report generator
│
├── scripts/                      # All runnable scripts
│   ├── MASTER_ORCHESTRATE.py     # Main orchestration script
│   ├── data_updates/             # Scripts that modify portfolio_data.csv
│   ├── populate_master/          # Calculation scripts (HVAC%, costs, savings)
│   ├── images/                   # Image fetching/upload
│   ├── logos/                    # Logo processing
│   ├── matching/                 # Building/tenant matching
│   ├── nyc/                      # NYC-specific scripts
│   └── utils/                    # Utility scripts
│
├── data/
│   ├── source/                   # Source data files
│   │   ├── portfolio_data.csv    # MAIN DATA FILE (~23k buildings)
│   │   └── portfolio_organizations.csv  # Org logos, classifications
│   ├── cbecs/                    # EIA CBECS 2018 data
│   ├── nyc/                      # NYC-specific data files
│   ├── city_benchmarking/        # City disclosure program data
│   └── reference_documents/      # Market reports, standards
│
├── output/html/                  # Generated HTML output
├── assets/                       # Images and logos
├── BACKUPS_GO_HERE/              # ALL BACKUPS HERE
└── docs/                         # Documentation
```

---

## Source CSV Files

### Primary Data Files

#### `portfolio_data.csv` (~23k rows)
The master building database with energy, location, organization, and calculated fields.
- **Key columns**: `id_building`, `id_property_name`, `loc_address`, `loc_city`, `bldg_sqft`, `bldg_type`, `org_owner`, `org_tenant`
- **Column prefixes**: `id_`, `loc_`, `bldg_`, `org_`, `energy_`, `cost_`, `hvac_`, `odcv_`, `bps_`, `savings_`, `val_`

#### `portfolio_organizations.csv` (~1,200 rows)
Master list of organizations with logos, classifications, and display info.
- **Columns**: `organization`, `logo_file`, `classification`, `display_name`, `aws_logo_url`, `search_aliases`, `vertical`, `org_type`

### Supporting Data Files

| File | Description | Rows |
|------|-------------|------|
| `building_type_to_vertical.csv` | Maps building types to verticals | 17 |
| `column_rename_lookup.csv` | Column naming definitions | 70 |
| `utility_logos.csv` | Utility company logo mappings | 21 |
| `leed_certified_buildings.csv` | Complete USGBC LEED database | ~33k |
| `leed_matches.csv` | Buildings matched to LEED certs | ~2k |
| `eui_post_odcv.csv` | Post-ODCV EUI calculations | ~24k |
| `market_vacancy_utilization_Q3_2025.csv` | Vacancy/utilization by city | 21 |
| `cbecs2018_final_public.csv` | EIA CBECS 2018 microdata | 6,436 |

---

## CSV Editing Rules

### ALWAYS USE PYTHON CSV MODULE

**NEVER use awk, sed, cut, or bash string manipulation on portfolio_data.csv.**

The file has quoted fields containing commas. Shell tools will corrupt the file.

```python
import csv

with open('data/source/portfolio_data.csv', 'r', newline='', encoding='utf-8') as f:
    reader = csv.reader(f)
    header = next(reader)
    rows = list(reader)

col_idx = {name: i for i, name in enumerate(header)}

# Make changes
for row in rows:
    if row[col_idx['id_building']] == "TARGET_ID":
        row[col_idx['org_tenant']] = "New Tenant"

with open('/tmp/portfolio_data_fixed.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(header)
    writer.writerows(rows)

# ALWAYS verify row count before replacing!
```

---

## Backup Policy

**ALL BACKUPS GO IN `BACKUPS_GO_HERE/` FOLDER**

```
BACKUPS_GO_HERE/
├── csv_backups/      <- CSV backups (portfolio_data_backup_*.csv)
└── script_backups/   <- Script backups (*_backup_*.py)
```

### Restore from backup:
```bash
ls -lt BACKUPS_GO_HERE/csv_backups/ | head -5
cp BACKUPS_GO_HERE/csv_backups/portfolio_data_backup_LATEST.csv data/source/portfolio_data.csv
```

---

## Tenant/Organization Data Rules

### Canonical Org Names
Always use names from `portfolio_organizations.csv` (first column).

### Tenant/Subunit Relationships
When a subsidiary brand is the tenant, set PARENT as `org_tenant` and SUBSIDIARY as `org_tenant_subunit`:

| org_tenant | org_tenant_subunit |
|------------|-------------------|
| Macy's | Bloomingdale's |
| TJX Companies | Marshalls, T.J. Maxx, HomeGoods |
| Gap Inc. | Old Navy, Banana Republic |
| Amazon | Whole Foods Market |
| Kroger | Fred Meyer, Ralphs, Food 4 Less |
| Microsoft | GitHub, LinkedIn |
| Hilton | Hampton Inn, DoubleTree, Embassy Suites |
| Marriott | Sheraton, Westin, Courtyard, Residence Inn |

### When to Set `bldg_hq_org`
Only when the building is a company's HEADQUARTERS.

---

## AWS S3 Bucket

### Overview

| Property | Value |
|----------|-------|
| **Bucket Name** | `nationwide-odcv-images` |
| **Region** | `us-east-2` (Ohio) |
| **Base URL** | `https://nationwide-odcv-images.s3.us-east-2.amazonaws.com` |
| **Access** | Public read |

### What's Stored

| Prefix | Content | Format |
|--------|---------|--------|
| `logos/` | Full-size organization logos | PNG |
| `logo-thumbnails/` | 64x64 logo thumbnails | PNG |
| `images/` | Building exterior photos | JPEG |
| `thumbnails/` | Building image thumbnails | JPEG |

### URL Patterns

```
# Logos
https://nationwide-odcv-images.s3.us-east-2.amazonaws.com/logos/{filename}.png
https://nationwide-odcv-images.s3.us-east-2.amazonaws.com/logo-thumbnails/{filename}.png

# Building Images
https://nationwide-odcv-images.s3.us-east-2.amazonaws.com/images/{filename}.jpg
https://nationwide-odcv-images.s3.us-east-2.amazonaws.com/thumbnails/{filename}.jpg
```

### Upload Scripts

| Script | Purpose |
|--------|---------|
| `scripts/images/upload_to_s3.py` | Upload all logos and images |
| `scripts/logos/fetch_validate_upload_logos.py` | Full logo pipeline (fetch, validate, upload) |
| `scripts/logos/create_logo_thumbnails.py` | Generate 64x64 thumbnails |
| `scripts/images/fetch_validate_upload.py` | Full building image pipeline |

### Adding a New Logo

1. Prepare PNG with transparent background (200-400px wide)
2. Upload to S3:
   ```bash
   aws s3 cp Logo_Name.png s3://nationwide-odcv-images/logos/Logo_Name.png \
       --content-type "image/png"
   ```
3. Create thumbnail:
   ```bash
   python3 scripts/logos/create_logo_thumbnails.py
   ```
4. Update `aws_logo_url` in `portfolio_organizations.csv`
5. Regenerate homepage:
   ```bash
   python3 -m src.generators.html_generator
   ```

### Checking Bucket Contents

```bash
aws s3 ls s3://nationwide-odcv-images/logos/ --summarize
aws s3 ls s3://nationwide-odcv-images/images/ --summarize
```

---

## Script Categories

### Data Calculation (`scripts/populate_master/`)

Run in order by `MASTER_ORCHESTRATE.py`:

| Script | Purpose |
|--------|---------|
| `00_align_verticals.py` | Ensure consistent vertical categorization |
| `01_hvac_pct.py` | Calculate HVAC energy percentages |
| `02_energy_costs.py` | Calculate energy costs from consumption |
| `03_odcv_savings.py` | Calculate ODCV savings percentages |
| `04_post_odcv_energy.py` | Calculate post-ODCV energy values |
| `05_post_odcv_costs.py` | Calculate post-ODCV costs |
| `06_hvac_totals.py` | Sum HVAC totals |
| `07_carbon_by_city.py` | Calculate carbon emissions by city |
| `08_bps_fines.py` | Calculate BPS fine avoidance |
| `09_valuation.py` | Calculate property value impact |
| `10_energy_star_estimate.py` | Estimate post-ODCV Energy Star scores |
| `11_nyc_update.py` | NYC-specific calculations |

### Data Updates (`scripts/data_updates/`)

Scripts for updating utilization rates by building type:
- `update_office_vacancy_rates.py`
- `update_hotel_utilization.py`
- `update_retail_utilization.py`
- `update_k12_utilization.py`
- `update_higher_ed_utilization.py`
- etc.

---

## Troubleshooting

### CSV Row Count Changed
File was corrupted. Restore from backup immediately.

### Images Not Updating
Check S3 cache headers. Clear browser cache or use incognito mode.

### boto3 Not Found
```bash
pip install boto3
```

### AWS Access Denied
Verify AWS credentials are configured via `aws configure` or environment variables.
