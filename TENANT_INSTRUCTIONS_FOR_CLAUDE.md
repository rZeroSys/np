# Instructions: Find Missing TENANTS

## YOUR TASK
Look at biggest buildings MISSING TENANT (column 19) and use your knowledge to identify tenants.

## FILE
`/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv`

## ALWAYS USE PYTHON CSV MODULE
```python
import csv

with open('/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv', 'r') as f:
    reader = csv.reader(f)
    header = next(reader)
    rows = list(reader)

# Column indexes:
# 0: id_building
# 1: id_property_name  
# 4: loc_address
# 5: loc_city
# 10: bldg_sqft
# 11: bldg_type
# 18: org_owner
# 19: org_tenant
# 20: org_tenant_subunit
```

## FIND MISSING TENANTS
```python
def get_sqft(val):
    try:
        return int(float(val)) if val else 0
    except:
        return 0

missing = []
for row in rows:
    if row[19] == '':  # tenant empty
        sqft = get_sqft(row[10])
        if sqft > 100000:
            missing.append((row[0], row[1], row[4], row[5], sqft, row[11], row[18]))

missing.sort(key=lambda x: x[4], reverse=True)

for bid, name, addr, city, sqft, btype, owner in missing[:100]:
    print(f"{bid} | {name} | {city} | {sqft:,} | {btype} | owner: {owner}")
```

## USE YOUR KNOWLEDGE
Look at building names and addresses. You KNOW many of these:
- Named buildings (e.g. "Salesforce Tower" → tenant: Salesforce)
- Stadium/arena names (e.g. "Chase Center" → tenant could be Golden State Warriors)
- Hotels (Hilton, Marriott, Hyatt buildings → those are tenants)
- Retail (Target, Walmart, Costco in name → those are tenants)
- Tech campuses (Apple, Google, Meta, etc.)

## CHECK CANONICAL ORG NAMES FIRST
Before setting tenant, check if org exists in:
`/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_organizations.csv`

Column 0 is the canonical name. Use EXACTLY that spelling.

## FIX TEMPLATE
```python
fixes = [
    ('BUILDING_ID', 'Tenant Name'),
]

for bid, tenant in fixes:
    for row in rows:
        if row[0] == bid:
            print(f"BEFORE: {row[0]} | {row[1]} | tenant: {row[19]}")
            row[19] = tenant
            print(f"AFTER: {row[0]} | {row[1]} | tenant: {row[19]}")

with open('/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(header)
    writer.writerows(rows)

print(f"Written: {len(rows) + 1} rows")  # Should be 23164
```

## VERIFY ROW COUNT
Always verify 23164 rows after writing. If less, YOU CORRUPTED THE FILE.

## TENANT vs SUBUNIT
- org_tenant = parent company (e.g., Macy's, Marriott, Amazon)
- org_tenant_subunit = subsidiary brand ONLY (e.g., Bloomingdale's under Macy's)
- Do NOT put unrelated co-tenants in subunit
