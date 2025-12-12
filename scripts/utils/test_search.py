#!/usr/bin/env python3
"""
TEST the search functionality to make sure it ACTUALLY WORKS!
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import DATA_OUTPUT_DIR

# Load the generated portfolio_cards.js
portfolio_cards_path = DATA_OUTPUT_DIR / 'portfolio_cards.js'
with open(str(portfolio_cards_path), 'r') as f:
    content = f.read()

# Extract the JSON array
match = re.search(r'const PORTFOLIO_CARDS = (\[.*\]);', content, re.DOTALL)
if not match:
    print("ERROR: Could not parse portfolio_cards.js")
    exit(1)

cards = json.loads(match.group(1))
print(f"Loaded {len(cards)} portfolio cards\n")

# Simulate the JavaScript globalSearch function
def search(query):
    """Simulate the globalSearch function"""
    query = query.lower().strip()
    matches = []

    for p in cards:
        org_match = query in (p.get('org_name') or '').lower()
        display_match = query in (p.get('display_name') or '').lower()
        tenant_match = any(query in t.lower() for t in (p.get('tenants') or []))
        sub_org_match = any(query in s.lower() for s in (p.get('tenant_sub_orgs') or []))
        owner_match = any(query in o.lower() for o in (p.get('owners') or []))
        manager_match = any(query in m.lower() for m in (p.get('managers') or []))

        # Check search_aliases
        alias_match = False
        for alias in (p.get('search_aliases') or []):
            a = alias.lower()
            if query in a or a in query or a == query:
                alias_match = True
                break

        if org_match or display_match or tenant_match or sub_org_match or owner_match or manager_match or alias_match:
            matches.append({
                'org_name': p['org_name'],
                'display_name': p['display_name'],
                'aliases': p.get('search_aliases', [])
            })

    return matches

# Test cases - THE ONES THE USER SPECIFICALLY ASKED FOR
TEST_CASES = [
    # Universities - CRITICAL
    ("cal", ["University of California", "California State University"]),
    ("usc", ["University Of Southern California"]),
    ("u of c", ["University of California", "University Of Chicago"]),
    ("mit", ["Massachusetts Institute Of Technology"]),
    ("ucla", ["University of California"]),
    ("nyu", ["New York University"]),
    ("berkeley", ["University of California"]),
    ("stanford", ["Stanford University"]),
    ("harvard", ["Harvard University"]),
    ("usc trojans", ["University Of Southern California"]),
    ("cal state", ["California State University"]),
    ("csu", ["California State University"]),

    # Cities
    ("nyc", ["City Of New York"]),
    ("la", ["City Of Los Angeles"]),
    ("sf", ["University Of San Francisco"]),  # No "City Of San Francisco" in data
    ("chicago", ["City Of Chicago", "Chicago Public Schools"]),
    ("dc", ["District Of Columbia"]),
    ("boston", ["City Of Boston"]),
    ("seattle", ["City Of Seattle"]),

    # Federal agencies
    ("gsa", ["General Services Administration"]),
    # NYPD/LAPD exist in CSV but not in portfolios (filtered out)

    # Real estate companies
    ("jll", ["Jones Lang LaSalle"]),
    ("cbre", ["CBRE Group"]),
    ("c&w", ["Cushman & Wakefield"]),
    ("cushman", ["Cushman & Wakefield"]),

    # Hotels
    ("ihg", ["InterContinental Hotels Group"]),
    ("marriott", ["Marriott"]),
    ("hilton", ["Hilton"]),

    # Other common searches
    ("walmart", ["Walmart"]),
    ("target", ["Target"]),
    ("costco", ["Costco"]),
    ("home depot", ["The Home Depot"]),
    ("kaiser", ["Kaiser Permanente"]),
    ("ymca", ["Young Men's Christian Association"]),
]

print("=" * 80)
print("SEARCH FUNCTIONALITY TEST")
print("=" * 80)
print()

passed = 0
failed = 0
partial = 0

for query, expected_matches in TEST_CASES:
    results = search(query)
    result_names = [r['org_name'] for r in results]

    # Check if all expected matches are found
    all_found = True
    found_expected = []
    missing = []

    for expected in expected_matches:
        found = any(expected.lower() in name.lower() for name in result_names)
        if found:
            found_expected.append(expected)
        else:
            missing.append(expected)
            all_found = False

    if all_found:
        status = "✅ PASS"
        passed += 1
    elif found_expected:
        status = "⚠️  PARTIAL"
        partial += 1
    else:
        status = "❌ FAIL"
        failed += 1

    print(f"{status} | Query: '{query}'")
    print(f"       Expected: {expected_matches}")
    print(f"       Found ({len(results)}): {result_names[:5]}{'...' if len(results) > 5 else ''}")
    if missing:
        print(f"       MISSING: {missing}")
    print()

print("=" * 80)
print(f"RESULTS: {passed} passed, {partial} partial, {failed} failed out of {len(TEST_CASES)} tests")
print("=" * 80)

if failed > 0:
    print("\n❌ SOME TESTS FAILED - SEARCH NEEDS MORE WORK!")
    exit(1)
elif partial > 0:
    print("\n⚠️  SOME TESTS PARTIAL - CHECK ALIASES")
else:
    print("\n✅ ALL TESTS PASSED!")
