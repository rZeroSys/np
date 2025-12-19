#!/usr/bin/env python3
"""
Update tenant data in portfolio and buildings CSVs based on high-confidence store matches.
"""

import csv
from pathlib import Path

MATCHES_PATH = Path("/Users/forrestmiller/Desktop/new data/matched_buildings.csv")
PORTFOLIO_PATH = Path("../data/source/portfolio_data.csv")
BUILDINGS_PATH = Path("../data/source/buildings_tab_data.csv")

# Only update high-confidence matches
MIN_CONFIDENCE = 0.7
MIN_ADDRESS_SCORE = 0.9


def load_updates():
    """Load high-confidence matches that need tenant updates."""
    updates = {}

    with open(MATCHES_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Only process missing or wrong tenant
            if row["issue"] not in ("MISSING_TENANT", "WRONG_TENANT"):
                continue

            # Check confidence thresholds
            confidence = float(row.get("confidence", 0))
            addr_score = float(row.get("address_match_score", 0))

            if confidence >= MIN_CONFIDENCE and addr_score >= MIN_ADDRESS_SCORE:
                building_id = row["building_id"]
                updates[building_id] = {
                    "new_tenant": row["matched_retailer"],
                    "store_name": row["store_name"],
                    "old_tenant": row["current_tenant"],
                    "confidence": confidence,
                    "address_score": addr_score,
                }

    return updates


def update_csv(filepath, updates, dry_run=False):
    """Update tenant column in CSV file."""
    if not filepath.exists():
        print(f"[WARN] File not found: {filepath}")
        return 0

    # Read all rows
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if "tenant" not in fieldnames:
        print(f"[WARN] No 'tenant' column in {filepath.name}")
        return 0

    # Update matching rows
    updated_count = 0
    for row in rows:
        building_id = row.get("building_id", "")
        if building_id in updates:
            update = updates[building_id]
            old_val = row.get("tenant", "")
            new_val = update["new_tenant"]

            if old_val != new_val:
                print(f"  {building_id}: '{old_val}' -> '{new_val}' (conf: {update['confidence']})")
                if not dry_run:
                    row["tenant"] = new_val
                updated_count += 1

    # Write back
    if not dry_run and updated_count > 0:
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    return updated_count


def main():
    print("=" * 70)
    print("Updating Tenant Data from Store Matches")
    print(f"Min confidence: {MIN_CONFIDENCE} | Min address score: {MIN_ADDRESS_SCORE}")
    print("=" * 70)

    # Load updates
    print("\n[INFO] Loading high-confidence matches...")
    updates = load_updates()
    print(f"[INFO] Found {len(updates)} buildings to update")

    if not updates:
        print("[INFO] No updates needed")
        return

    # Show what will be updated
    print("\n[INFO] Updates to apply:")
    for bid, upd in updates.items():
        print(f"  {bid}: '{upd['old_tenant']}' -> '{upd['new_tenant']}'")

    # Update portfolio_data.csv
    print(f"\n[INFO] Updating {PORTFOLIO_PATH.name}...")
    count1 = update_csv(PORTFOLIO_PATH, updates)
    print(f"[OK] Updated {count1} rows in {PORTFOLIO_PATH.name}")

    # Update buildings_tab_data.csv
    print(f"\n[INFO] Updating {BUILDINGS_PATH.name}...")
    count2 = update_csv(BUILDINGS_PATH, updates)
    print(f"[OK] Updated {count2} rows in {BUILDINGS_PATH.name}")

    print("\n" + "=" * 70)
    print(f"DONE - Updated {count1 + count2} total rows")
    print("=" * 70)


if __name__ == "__main__":
    main()
