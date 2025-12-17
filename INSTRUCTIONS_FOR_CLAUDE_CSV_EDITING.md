# Instructions for Claude: Editing portfolio_data.csv

## CRITICAL: ALWAYS USE PYTHON CSV MODULE

**NEVER use awk, sed, or bash to edit this CSV file.** The file has quoted fields containing commas, which awk cannot handle properly. Using awk WILL corrupt the file by dropping rows.

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
wc -l /tmp/portfolio_data_fixed.csv  # Should be 23164
cp /tmp/portfolio_data_fixed.csv /Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv
```

## BACKUP LOCATION
If you corrupt the file, restore from:
```
/Users/forrestmiller/Desktop/nationwide-prospector/BACKUPS_GO_HERE/csv_backups/portfolio_data_backup_20251216_220950.csv
```

## KEY COLUMNS
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

## CANONICAL ORG NAMES
Always use canonical names from:
```
/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_organizations.csv
```
First column is the canonical name. Check this before setting tenant/owner values.

## TENANT/SUBUNIT RELATIONSHIPS
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

## STANDALONE COMPANIES (no subunit needed)
- Victoria's Secret & Co.
- Sotheby's
- Trump Organization
- GoDaddy
- Hewlett Packard Enterprise

## FINDING MISSING TENANTS

### Strategy 1: Search for known brand patterns in property names
Be VERY careful with false positives. These patterns cause problems:
- "cisco" matches "San Francisco"
- "ea" matches "center", "east", "healthcare"
- "square" matches building names like "Union Square"
- "office" matches random buildings
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

## WHEN TO SET bldg_hq_org
Only set this when the building is a company's HEADQUARTERS:
- CHI_101736, CHI_160438 - Hyatt Center → hq: Hyatt (Hyatt's global HQ)

## FIXES ALREADY APPLIED (as of this writing)
- Bloomingdale's (8 rows) → Macy's / Bloomingdale's
- Marshalls DC_5486706 → TJX Companies / Marshalls
- Old Navy (3 rows) → Gap Inc. / Old Navy
- Whole Foods NYC_3023510006 → Amazon / Whole Foods Market
- Victoria's Secret CA_1166233 → Victoria's Secret & Co.
- Bergdorf Goodman NYC_1012730033 → Neiman Marcus Group / Bergdorf Goodman
- Fred Meyer PDX_Campus-24 → Kroger / Fred Meyer
- FoodMaxx SJ_761, SJ_877 → Save Mart Companies / FoodMaxx
- Gap INC. → Gap Inc. (standardized spelling)
- Hyatt Center CHI_101736, CHI_160438 → Hyatt + hq:Hyatt
- Sprouts LA_442662832744 → Sprouts Farmers Market
- Macy's SF_72950042024 → Macy's
- Sotheby's NYC_1014830001 → Sotheby's
- HP Moffett CA_6353422, CA_6353425 → Hewlett Packard Enterprise
- Chase Tower CHI_101739 → JPMorgan Chase (JPM)
- PwC DC_5480773 → PwC
- GitHub SF_37740732024 → Microsoft / GitHub
- Trump Building NYC_1000430002 → Trump Organization
- Adobe SF_37570672024 → Adobe (also fixed building type to Office)
- GoDaddy CA_16851978 → GoDaddy
- Beverly Center LA_447470850115 → Macy's / Bloomingdale's + owner Kimco
- Pier 57 NYC_1006620003 → Google
- Soldier Field CHI_103669 → Chicago Bears + owner City Of Chicago
- Xerox Centre CHI_101791 → Xerox

## VERIFYING CHANGES
Always verify after making changes:
```python
# Check specific IDs
for row in reader:
    if row[0] in ["ID1", "ID2"]:
        print(f"{row[0]} | tenant:{row[tenant_idx]} | subunit:{row[subunit_idx]}")
```

## ROW COUNT
The file should have **23164 rows** (including header). If you see fewer, YOU CORRUPTED THE FILE. Restore from backup immediately.
