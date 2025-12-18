#!/usr/bin/env python3
"""
Process Store Location Data from Kaggle Downloads
Filters to target cities and creates normalized CSVs.
"""

import csv
import json
from pathlib import Path

DOWNLOAD_DIR = Path("/Users/forrestmiller/Desktop/new data/kaggle_downloads")
OUTPUT_DIR = Path("/Users/forrestmiller/Desktop/new data")

# Target cities
TARGET_CITIES = {
    ("san francisco", "ca"), ("san diego", "ca"), ("los angeles", "ca"),
    ("san jose", "ca"), ("sacramento", "ca"), ("portland", "or"),
    ("new york", "ny"), ("washington", "dc"), ("boston", "ma"),
    ("atlanta", "ga"), ("denver", "co"), ("seattle", "wa"),
    ("chicago", "il"), ("philadelphia", "pa"),
    ("kansas city", "mo"), ("kansas city", "ks"),
}

# NYC boroughs map to New York
NYC_BOROUGHS = {"manhattan", "brooklyn", "queens", "bronx", "staten island", "new york city", "nyc"}

OUTPUT_COLS = ["retailer", "store_name", "street", "city", "state", "zip", "phone", "lat", "lon"]


def normalize_state(s):
    """Convert state name to 2-letter code."""
    s = s.strip().upper()
    mapping = {
        "CALIFORNIA": "CA", "OREGON": "OR", "NEW YORK": "NY",
        "DISTRICT OF COLUMBIA": "DC", "MASSACHUSETTS": "MA",
        "GEORGIA": "GA", "COLORADO": "CO", "WASHINGTON": "WA",
        "ILLINOIS": "IL", "PENNSYLVANIA": "PA", "MISSOURI": "MO", "KANSAS": "KS",
    }
    return mapping.get(s, s[:2] if len(s) > 2 else s)


def city_matches(city, state):
    """Check if city/state is in target list."""
    city = city.strip().lower()
    state = normalize_state(state).lower()

    # Handle NYC boroughs
    if city in NYC_BOROUGHS:
        city = "new york"

    return (city, state) in TARGET_CITIES


def process_walmart():
    """Process Walmart CSV."""
    records = []
    csv_path = DOWNLOAD_DIR / "walmart" / "Walmart_Locations.csv"

    if not csv_path.exists():
        print(f"[WARN] Walmart CSV not found: {csv_path}")
        return records

    print(f"[INFO] Processing Walmart from {csv_path}")
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # City_and_State is "City, ST" format
            city_state = row.get("City_and_State", "")
            if ", " in city_state:
                city, state = city_state.rsplit(", ", 1)
            else:
                continue

            if not city_matches(city, state):
                continue

            records.append({
                "retailer": "Walmart",
                "store_name": row.get("Store_Name", "").strip(),
                "street": row.get("Address", "").strip(),
                "city": city.strip(),
                "state": normalize_state(state),
                "zip": row.get("Zipcode", "").strip(),
                "phone": row.get("Phone_Number", "").strip(),
                "lat": "",  # Not in dataset
                "lon": "",
            })

    print(f"[INFO] Found {len(records)} Walmart stores")
    return records


def process_target():
    """Process Target CSV."""
    records = []

    # Try both possible filenames
    for filename in ["target.csv", "targets.csv"]:
        csv_path = DOWNLOAD_DIR / "target" / filename
        if csv_path.exists():
            print(f"[INFO] Processing Target from {csv_path}")
            with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    city = row.get("Address.City", "").strip()
                    state = row.get("Address.Subdivision", "").strip()

                    if not city_matches(city, state):
                        continue

                    records.append({
                        "retailer": "Target",
                        "store_name": row.get("Name", "").strip(),
                        "street": row.get("Address.AddressLine1", "").strip(),
                        "city": city,
                        "state": normalize_state(state),
                        "zip": row.get("Address.PostalCode", "").strip(),
                        "phone": row.get("PhoneNumber", "").strip(),
                        "lat": row.get("Address.Latitude", "").strip(),
                        "lon": row.get("Address.Longitude", "").strip(),
                    })
            break

    print(f"[INFO] Found {len(records)} Target stores")
    return records


def process_costco():
    """Process Costco JSON."""
    records = []
    json_path = DOWNLOAD_DIR / "costco" / "costco_warehouses.json"

    if not json_path.exists():
        print(f"[WARN] Costco JSON not found: {json_path}")
        return records

    print(f"[INFO] Processing Costco from {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for warehouse in data:
        city = warehouse.get("city", "").strip()
        state = warehouse.get("state", "").strip()

        if not city_matches(city, state):
            continue

        records.append({
            "retailer": "Costco",
            "store_name": f"Costco #{warehouse.get('identifier', '')} - {warehouse.get('locationName', '')}",
            "street": warehouse.get("address1", "").strip(),
            "city": city,
            "state": normalize_state(state),
            "zip": warehouse.get("zipCode", "").strip(),
            "phone": warehouse.get("phone", "").strip(),
            "lat": str(warehouse.get("latitude", "")),
            "lon": str(warehouse.get("longitude", "")),
        })

    print(f"[INFO] Found {len(records)} Costco warehouses")
    return records


def process_home_improvement():
    """Process Home Depot and Lowe's from entry.csv."""
    hd_records = []
    lowes_records = []

    csv_path = DOWNLOAD_DIR / "home_improvement" / "entry.csv"

    if not csv_path.exists():
        print(f"[WARN] Home improvement CSV not found: {csv_path}")
        return hd_records, lowes_records

    print(f"[INFO] Processing Home Depot/Lowe's from {csv_path}")
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            city = row.get("city", "").strip()
            state = row.get("state", "").strip()
            store_type = row.get("store", "").strip().upper()

            if not city_matches(city, state):
                continue

            record = {
                "store_name": f"{store_type} - {city}",
                "street": row.get("address", "").strip(),
                "city": city,
                "state": normalize_state(state),
                "zip": row.get("zipcode", "").strip(),
                "phone": "",  # Not in dataset
                "lat": "",    # Not in this file
                "lon": "",
            }

            if store_type == "HD":
                record["retailer"] = "Home Depot"
                hd_records.append(record)
            elif store_type == "LOW":
                record["retailer"] = "Lowe's"
                lowes_records.append(record)

    print(f"[INFO] Found {len(hd_records)} Home Depot stores")
    print(f"[INFO] Found {len(lowes_records)} Lowe's stores")
    return hd_records, lowes_records


def write_csv(records, output_path):
    """Write records to CSV."""
    if not records:
        print(f"[WARN] No records to write for {output_path.name}")
        return

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLS)
        writer.writeheader()
        for rec in records:
            writer.writerow({col: rec.get(col, "") for col in OUTPUT_COLS})

    print(f"[OK] Wrote {len(records)} records to {output_path.name}")


def main():
    print("=" * 60)
    print("Processing Store Location Data")
    print("=" * 60)

    # Process each retailer
    walmart = process_walmart()
    target = process_target()
    costco = process_costco()
    hd, lowes = process_home_improvement()

    # Write individual CSVs
    write_csv(walmart, OUTPUT_DIR / "walmart_stores.csv")
    write_csv(target, OUTPUT_DIR / "target_stores.csv")
    write_csv(costco, OUTPUT_DIR / "costco_stores.csv")
    write_csv(hd, OUTPUT_DIR / "homedepot_stores.csv")
    write_csv(lowes, OUTPUT_DIR / "lowes_stores.csv")

    # Combined CSV
    all_records = walmart + target + costco + hd + lowes
    write_csv(all_records, OUTPUT_DIR / "all_stores.csv")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Walmart:    {len(walmart)} stores")
    print(f"Target:     {len(target)} stores")
    print(f"Costco:     {len(costco)} warehouses")
    print(f"Home Depot: {len(hd)} stores")
    print(f"Lowe's:     {len(lowes)} stores")
    print(f"TOTAL:      {len(all_records)} locations")
    print(f"\nOutput: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
