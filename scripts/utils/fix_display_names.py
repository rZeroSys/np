#!/usr/bin/env python3
"""
Fix confusing display names - make government entities clear
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import PORTFOLIO_ORGS_PATH

CSV_PATH = str(PORTFOLIO_ORGS_PATH)

# Explicit mappings for cities/counties/districts
DISPLAY_NAME_FIXES = {
    # Cities - use "X City Gov" format
    'City Of New York': 'NYC Gov',
    'City Of Los Angeles': 'LA City Gov',
    'City Of Boston': 'Boston City Gov',
    'City Of Seattle': 'Seattle City Gov',
    'City Of Chicago': 'Chicago City Gov',
    'City Of Philadelphia': 'Philadelphia City Gov',
    'City Of Cambridge': 'Cambridge City Gov',
    'City Of Denver': 'Denver City Gov',
    'City Of Portland': 'Portland City Gov',
    'City Of Atlanta': 'Atlanta City Gov',
    'City Of St. Louis': 'St. Louis City Gov',
    'City Of Sacramento': 'Sacramento City Gov',
    'City Of San Diego': 'San Diego City Gov',
    'City Of Inglewood': 'Inglewood City Gov',
    'City Of San Jose': 'San Jose City Gov',
    'City Of Chula Vista': 'Chula Vista City Gov',

    # District of Columbia
    'District Of Columbia': 'DC Gov',
    # Keep DC Public Schools and DC International as-is (already clear)

    # Counties - use "X County Gov" format
    'Los Angeles County': 'LA County Gov',
    'Riverside County': 'Riverside County Gov',
    'Philadelphia County': 'Philadelphia County Gov',
    'Orange County': 'Orange County Gov',
    'Sacramento County': 'Sacramento County Gov',
    'San Bernardino County': 'San Bernardino County Gov',
    'Cook County': 'Cook County Gov',
    'Kings County': 'Kings County Gov',
    'Santa Clara County': 'Santa Clara County Gov',
    'Kern County': 'Kern County Gov',
    'Multnomah County': 'Multnomah County Gov',
    'Ventura County': 'Ventura County Gov',
    'King County': 'King County Gov',
    'Placer County': 'Placer County Gov',
    'Denver County': 'Denver County Gov',
    'San Diego County': 'San Diego County Gov',
    'Alameda County': 'Alameda County Gov',
    'Stanislaus County': 'Stanislaus County Gov',
    'Fresno County': 'Fresno County Gov',
    'Napa County': 'Napa County Gov',
    'Suffolk County': 'Suffolk County Gov',
    'Solano County': 'Solano County Gov',
    'Madera County': 'Madera County Gov',
    'Monterey County': 'Monterey County Gov',
    'Contra Costa County': 'Contra Costa County Gov',
    'Marin County': 'Marin County Gov',
    'Yuba County': 'Yuba County Gov',

    # NOT a government - it's a hospital/research center
    # 'City Of Hope': keep as 'Hope'

    # Confusing abbreviations - make clear
    'Los Angeles Unified School District': 'LA Public Schools',
    'University Of Denver': 'Denver University',
    'City University of New York (CUNY)': 'CUNY NYC University',
    'University Of San Francisco': 'San Francisco University',
    'University of Washington (UW)': 'U of Washington',
    'University Of The District Of Columbia': 'DC University',
    'Massachusetts College Of Pharmacy And Health Sciences': 'Mass Pharmacy College',
    'Amda College And Conservatory Of The Performing Arts': 'AMDA Performing Arts',
    'Savannah College Of Art And Design': 'Savannah Art & Design',

    # State governments
    'State Of New York': 'New York State Gov',
    'State of California': 'California State Gov',

    # NYC departments - make clear it's NYC
    'Department Of Citywide Administrative Services': 'NYC Citywide Admin Services',
    'Department Of Parks And Recreation': 'NYC Parks & Recreation',
    'Department Of Cultural Affairs': 'NYC Cultural Affairs',
    'Department Of Health & Mental Hygiene': 'NYC Health & Mental Hygiene',
    'Department Of Small Business Services': 'NYC Small Business Services',
    'Department Of Behavioral Health': 'DC Behavioral Health',
    'Human Resources Administration': 'NYC Human Resources Admin',

    # LA departments
    'Los Angeles Department Of Building And Safety': 'Los Angeles Building & Safety',

    # More state governments
    'Commonwealth Of Massachusetts': 'Massachusetts State Gov',
    'Commonwealth Of Pennsylvania': 'Pennsylvania State Gov',

    # Confusing agency names
    'Administration For Children\'s Services': 'NYC Children\'s Services',
    'Administration': 'GSA Administration',
    'Boston Redevelopment Authority': 'Boston Redevelopment Authority',

    # Single-word names - make two words for clarity
    'The Irvine Company': 'Irvine Company',
    'Hines': 'Hines Real Estate',
    'Kilroy Realty': 'Kilroy Realty',
    'Vornado Realty Trust': 'Vornado Realty',
    'Jamestown L.P.': 'Jamestown Properties',
    'Apollo Global Management': 'Apollo Capital',
    'Kaufman Organization': 'Kaufman Organization',
    'Newmark': 'Newmark Real Estate',
    'Colliers': 'Colliers Real Estate',
    'Transwestern': 'Transwestern Real Estate',
    'Cousins Properties': 'Cousins Properties',
    'Okada & Company': 'Okada Company',
    'Bernstein Real Estate': 'Bernstein Real Estate',

    # More single-word fixes
    'Hotel': 'Various Hotels',
    'Eastgate': 'Eastgate Properties',
    'CommonWealth Partners': 'CommonWealth Partners',
    'Knotel': 'Knotel Offices',
    'Watermark Retirement Communities': 'Watermark Retirement',
    'Windsor Mgmt': 'Windsor Management',
    'Wildflower Open Classroom District': 'Wildflower Schools',
    'ATCO': 'ATCO Properties',
    'Shriners Hospitals For Children': 'Shriners Hospitals',

    # Round 7 - more single-word fixes
    'Ross Stores': 'Ross Stores',
    'BJ\'s Wholesale Club': 'BJ\'s Wholesale',
    'Rockhill Management, L.L.C.': 'Rockhill Management',
    'Sobrato Organization': 'Sobrato Organization',
    'Edward J. Minskoff Equities': 'Minskoff Equities',
    'Hearst': 'Hearst Corporation',
    'Pembroke': 'Pembroke Properties',
    'Sprouts Farmers Market': 'Sprouts Market',
    'Vallarta Supermarkets': 'Vallarta Supermarkets',
    'The Pacifica Company, LP.': 'Pacifica Company',

    # Round 8 - top portfolios fixes
    'Adams & Company Real Estate': 'Adams & Company',
    'George Washington University': 'GW University',
    'Columbia University': 'Columbia University',
    'Northeastern University': 'Northeastern University',
    'Temple University': 'Temple University',
    'Cornell University': 'Cornell University',
    'Northwestern University': 'Northwestern University',
    'Emerson College': 'Emerson College',
    'Simmons University': 'Simmons University',
    'Lesley University': 'Lesley University',
    'Tufts University': 'Tufts University',

    # Round 9 - more fixes
    'Drexel University': 'Drexel University',
    'Howard University': 'Howard University',
    'Swig Company': 'Swig Company',
    'Himmel + Meringoff Properties LLC': 'Himmel + Meringoff',
    'Koeppel Rosen': 'Koeppel Rosen',
    'Portland Community College': 'Portland Community College',

    # Round 10 - more fixes
    'Berklee College Of Music': 'Berklee College',
    'Regal Entertainment': 'Regal Entertainment',
    'George Comfort & Sons': 'George Comfort & Sons',
    'Jack Resnick & Sons': 'Jack Resnick & Sons',
    'Walt Disney Imagineering': 'Disney Imagineering',
    'GH Palmer': 'GH Palmer Associates',

    # Round 11 - universities still showing single word
    'Emory University': 'Emory University',
    'Stanford University': 'Stanford University',
    'Georgetown University': 'Georgetown University',
    'DePaul University': 'DePaul University',
    'Wentworth Institute Of Technology': 'Wentworth Institute',

    # Final round - last fixes
    'Winco Foods': 'WinCo Foods',
}

# Read CSV
with open(CSV_PATH, 'r') as f:
    reader = csv.reader(f)
    rows = list(reader)

header = rows[0]
display_name_idx = header.index('display_name')

# Update display names
updated = 0
for row in rows[1:]:
    org_name = row[0]
    if org_name in DISPLAY_NAME_FIXES:
        old_display = row[display_name_idx]
        new_display = DISPLAY_NAME_FIXES[org_name]
        if old_display != new_display:
            print(f'{org_name}: "{old_display}" → "{new_display}"')
            row[display_name_idx] = new_display
            updated += 1

# Write back
with open(CSV_PATH, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerows(rows)

print(f'\nUpdated {updated} display names')
