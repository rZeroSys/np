#!/usr/bin/env python3
"""
Align Building Types to Verticals
=================================
Updates bldg_vertical column based on bldg_type using the mapping file.

This script MUST run FIRST before any other populate_master scripts
because other scripts may depend on the vertical classification.

Input:
- portfolio_data.csv (bldg_type column)
- building_type_to_vertical.csv (mapping file)

Output:
- Updates bldg_vertical column in portfolio_data.csv
"""

import pandas as pd
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import PORTFOLIO_DATA_PATH, SOURCE_DATA_DIR

# =============================================================================
# CONFIGURATION
# =============================================================================

INPUT_FILE = str(PORTFOLIO_DATA_PATH)
MAPPING_FILE = str(SOURCE_DATA_DIR / 'building_type_to_vertical.csv')

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("Align Building Types to Verticals")
    print("=" * 60)

    # Load mapping file
    print(f"\nLoading mapping file: {MAPPING_FILE}")
    mapping_df = pd.read_csv(MAPPING_FILE)
    type_to_vertical = dict(zip(mapping_df['building_type'], mapping_df['vertical']))
    print(f"  Loaded {len(type_to_vertical)} building type mappings")

    # Load portfolio data
    print(f"\nLoading portfolio data: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"  Loaded {len(df)} buildings")

    # Track changes
    original_verticals = df['bldg_vertical'].copy()
    updated_count = 0
    missing_types = set()

    # Update bldg_vertical based on bldg_type
    for idx, row in df.iterrows():
        bldg_type = row.get('bldg_type')
        if pd.notna(bldg_type) and bldg_type in type_to_vertical:
            new_vertical = type_to_vertical[bldg_type]
            if row.get('bldg_vertical') != new_vertical:
                df.at[idx, 'bldg_vertical'] = new_vertical
                updated_count += 1
        elif pd.notna(bldg_type) and bldg_type not in type_to_vertical:
            missing_types.add(bldg_type)

    # Report
    print(f"\nResults:")
    print(f"  Buildings updated: {updated_count}")

    if missing_types:
        print(f"\n  WARNING: {len(missing_types)} building types not in mapping:")
        for t in sorted(missing_types)[:10]:
            print(f"    - {t}")
        if len(missing_types) > 10:
            print(f"    ... and {len(missing_types) - 10} more")

    # Save
    print(f"\nSaving updated data to: {INPUT_FILE}")
    df.to_csv(INPUT_FILE, index=False)
    print("  Done!")

    # Summary by vertical
    print(f"\nVertical distribution:")
    vertical_counts = df['bldg_vertical'].value_counts()
    for vertical, count in vertical_counts.items():
        print(f"  {vertical}: {count:,}")

    print("\n" + "=" * 60)


if __name__ == '__main__':
    main()
