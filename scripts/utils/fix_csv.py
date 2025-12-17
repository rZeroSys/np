import pandas as pd
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import BUILDING_DATA_PATH

CSV_PATH = str(BUILDING_DATA_PATH)

# Load CSV
df = pd.read_csv(CSV_PATH, low_memory=False)
print(f"Loaded {len(df)} rows")

fixes = 0

# Building type to correct vertical mapping
TYPE_TO_VERTICAL = {
    # Education
    'K-12 School': 'Education',
    'Preschool/Daycare': 'Education', 
    'Higher Ed': 'Education',
    
    # Healthcare
    'Hospital': 'Healthcare',
    'Inpatient Hospital': 'Healthcare',
    'Outpatient Clinic': 'Healthcare',
    'Specialty Hospital': 'Healthcare',
    'Medical Office': 'Healthcare',
    'Residential Care': 'Healthcare',

    # Government
    'Courthouse': 'Government',
    'Fire Station': 'Government',
    'Police Station': 'Government',

    # Commercial (everything else)
    'Office': 'Commercial',
    'Hotel': 'Commercial',
    'Retail': 'Commercial',
    'Restaurant/Bar': 'Commercial',
    'Bank Branch': 'Commercial',
    'Supermarket': 'Commercial',
    'Wholesale Club': 'Commercial',
    'Library/Museum': 'Commercial',
    'Theater': 'Commercial',
    'Venue': 'Commercial',
    'Mixed Use': 'Commercial',
    'Worship Facility': 'Commercial',
    'Vehicle Dealership': 'Commercial',
    'Entertainment Venue': 'Commercial',
}

# Fix building types based on property name
def fix_building_type(row):
    global fixes
    name = str(row.get('id_property_name', '')).lower()
    tenant = str(row.get('org_tenant', '')).lower()
    current_type = row.get('bldg_type', '')
    
    combined = name + ' ' + tenant
    
    # Libraries
    if 'library' in combined and current_type == 'Office':
        fixes += 1
        return 'Library/Museum'
    
    # Hotels
    if any(h in combined for h in ['hotel', 'marriott', 'hilton', 'hyatt', 'sheraton', 'westin', 'ritz', 'holiday inn', 'hampton inn', 'courtyard']) and current_type == 'Office':
        fixes += 1
        return 'Hotel'
    
    # Schools
    if any(s in combined for s in ['school', 'academy', 'elementary', 'middle school', 'high school']) and current_type == 'Office':
        fixes += 1
        return 'K-12 School'
    
    # Hospitals
    if any(h in combined for h in ['hospital', 'medical center']) and current_type == 'Office':
        fixes += 1
        return 'Inpatient Hospital'
    
    # Clinics
    if 'clinic' in combined and current_type == 'Office':
        fixes += 1
        return 'Outpatient Clinic'
    
    # Churches
    if any(c in combined for c in ['church', 'cathedral', 'temple', 'synagogue', 'mosque', 'chapel']) and current_type == 'Office':
        fixes += 1
        return 'Worship Facility'
    
    return current_type

# Fix building types
df['bldg_type'] = df.apply(fix_building_type, axis=1)
print(f"Fixed {fixes} building types")

# Now fix verticals to match building types
vertical_fixes = 0
for idx, row in df.iterrows():
    btype = row.get('bldg_type', '')
    current_vertical = row.get('bldg_vertical', '')
    correct_vertical = TYPE_TO_VERTICAL.get(btype, 'Commercial')

    if current_vertical != correct_vertical:
        df.at[idx, 'bldg_vertical'] = correct_vertical
        vertical_fixes += 1

print(f"Fixed {vertical_fixes} verticals")

# Save
df.to_csv(CSV_PATH, index=False)
print(f"Saved to {CSV_PATH}")
