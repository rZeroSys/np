#!/usr/bin/env python3
"""
Match ALL buildings to store locations using city + Haversine distance + address verification.
"""

import csv
import math
import re
from collections import defaultdict
from pathlib import Path

BUILDINGS_PATH = Path("/Users/forrestmiller/Desktop/nationwide-prospector/data/source/buildings_tab_data.csv")
STORES_PATH = Path("/Users/forrestmiller/Desktop/new data/all_stores.csv")
OUTPUT_PATH = Path("/Users/forrestmiller/Desktop/new data/matched_buildings.csv")

# Distance threshold in meters (tighter for high confidence)
MATCH_THRESHOLD_METERS = 50


def haversine(lat1, lon1, lat2, lon2):
    """Calculate great-circle distance in meters."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(delta_lambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def normalize_address(addr):
    """Extract key parts of address for comparison."""
    addr = addr.lower().strip()
    # Remove common suffixes
    addr = re.sub(r'\b(st|street|ave|avenue|blvd|boulevard|rd|road|dr|drive|ln|lane|ct|court|pl|place|way|pkwy|parkway|cir|circle)\b', '', addr)
    # Remove directionals
    addr = re.sub(r'\b(n|s|e|w|ne|nw|se|sw|north|south|east|west)\b', '', addr)
    # Extract just numbers and letters
    addr = re.sub(r'[^a-z0-9\s]', '', addr)
    # Collapse whitespace
    addr = ' '.join(addr.split())
    return addr


def extract_street_number(addr):
    """Extract the street number from address."""
    match = re.match(r'^(\d+)', addr.strip())
    return match.group(1) if match else ""


def address_similarity(addr1, addr2):
    """Calculate similarity between two addresses (0-1 score)."""
    num1 = extract_street_number(addr1)
    num2 = extract_street_number(addr2)

    # Street numbers must match
    if num1 and num2 and num1 != num2:
        return 0.0

    # Compare normalized addresses
    norm1 = normalize_address(addr1)
    norm2 = normalize_address(addr2)

    if not norm1 or not norm2:
        return 0.0

    # Check if one contains the other
    if norm1 in norm2 or norm2 in norm1:
        return 1.0

    # Word overlap
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    if not words1 or not words2:
        return 0.0

    overlap = len(words1 & words2)
    return overlap / max(len(words1), len(words2))


def normalize_city(city):
    """Normalize city name for matching."""
    city = city.strip().lower()
    # Handle NYC boroughs
    if city in {"manhattan", "brooklyn", "queens", "bronx", "staten island", "new york city"}:
        return "new york"
    return city


def load_stores():
    """Load stores grouped by city."""
    stores_by_city = defaultdict(list)

    with open(STORES_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lat = float(row["lat"])
                lon = float(row["lon"])
            except (ValueError, KeyError):
                continue

            city = normalize_city(row.get("city", ""))
            state = row.get("state", "").strip().upper()

            stores_by_city[(city, state)].append({
                "retailer": row.get("retailer", ""),
                "store_name": row.get("store_name", ""),
                "street": row.get("street", ""),
                "city": row.get("city", ""),
                "state": state,
                "lat": lat,
                "lon": lon,
            })

    return stores_by_city


def load_buildings():
    """Load ALL buildings grouped by city."""
    buildings_by_city = defaultdict(list)
    total = 0

    with open(BUILDINGS_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            try:
                lat = float(row.get("latitude", ""))
                lon = float(row.get("longitude", ""))
                sqft = float(row.get("square_footage", 0))
            except (ValueError, TypeError):
                continue

            city = normalize_city(row.get("city", ""))
            state = row.get("state", "").strip().upper()

            buildings_by_city[(city, state)].append({
                "building_id": row.get("building_id", ""),
                "address": row.get("address", ""),
                "building_type": row.get("building_type", ""),
                "tenant": row.get("tenant", "").strip(),
                "square_footage": sqft,
                "city": row.get("city", ""),
                "state": state,
                "lat": lat,
                "lon": lon,
            })

    print(f"[INFO] Loaded {total} buildings ({len(buildings_by_city)} unique city/state combos)")
    return buildings_by_city


def find_matches(buildings_by_city, stores_by_city):
    """Find buildings that match stores within threshold distance + address verification."""
    matches = []
    comparisons = 0

    for (city, state), buildings in buildings_by_city.items():
        stores = stores_by_city.get((city, state), [])
        if not stores:
            continue

        for building in buildings:
            best_match = None
            best_distance = float("inf")
            best_addr_score = 0

            for store in stores:
                comparisons += 1
                distance = haversine(
                    building["lat"], building["lon"],
                    store["lat"], store["lon"]
                )

                if distance < best_distance:
                    best_distance = distance
                    best_match = store
                    best_addr_score = address_similarity(building["address"], store["street"])

            # Must be within distance threshold
            if not best_match or best_distance > MATCH_THRESHOLD_METERS:
                continue

            # Calculate confidence score
            # - Distance < 10m = high confidence
            # - Address match = high confidence
            # - Both = very high confidence
            distance_score = max(0, 1 - (best_distance / MATCH_THRESHOLD_METERS))
            confidence = (distance_score * 0.6) + (best_addr_score * 0.4)

            # Require either very close distance OR good address match
            if best_distance > 25 and best_addr_score < 0.5:
                continue  # Skip low confidence matches

            current_tenant = building["tenant"]
            expected_retailer = best_match["retailer"]

            tenant_missing = not current_tenant
            tenant_mismatch = (
                current_tenant and
                expected_retailer.lower() not in current_tenant.lower() and
                current_tenant.lower() not in expected_retailer.lower()
            )

            matches.append({
                "building_id": building["building_id"],
                "building_address": building["address"],
                "building_type": building["building_type"],
                "square_footage": building["square_footage"],
                "building_lat": building["lat"],
                "building_lon": building["lon"],
                "current_tenant": current_tenant if current_tenant else "(MISSING)",
                "matched_retailer": expected_retailer,
                "store_name": best_match["store_name"],
                "store_address": best_match["street"],
                "store_lat": best_match["lat"],
                "store_lon": best_match["lon"],
                "distance_meters": round(best_distance, 2),
                "address_match_score": round(best_addr_score, 2),
                "confidence": round(confidence, 2),
                "issue": "MISSING_TENANT" if tenant_missing else ("WRONG_TENANT" if tenant_mismatch else "CORRECT"),
            })

    print(f"[INFO] Made {comparisons:,} distance comparisons")
    return matches


def write_output(matches):
    """Write matches to CSV."""
    if not matches:
        print("[WARN] No matches found")
        return

    fieldnames = [
        "building_id", "building_address", "building_type", "square_footage",
        "current_tenant", "matched_retailer", "store_name",
        "distance_meters", "address_match_score", "confidence", "issue",
        "building_lat", "building_lon", "store_lat", "store_lon", "store_address"
    ]

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for match in sorted(matches, key=lambda x: x["distance_meters"]):
            writer.writerow(match)

    print(f"[OK] Wrote {len(matches)} matches to {OUTPUT_PATH}")


def main():
    print("=" * 70)
    print("Matching ALL Buildings to Store Locations")
    print(f"Distance threshold: {MATCH_THRESHOLD_METERS} meters")
    print("=" * 70)

    print("\n[INFO] Loading stores...")
    stores_by_city = load_stores()
    print(f"[INFO] Loaded {sum(len(v) for v in stores_by_city.values())} stores in {len(stores_by_city)} cities")

    print("\n[INFO] Loading buildings...")
    buildings_by_city = load_buildings()

    print("\n[INFO] Finding matches...")
    matches = find_matches(buildings_by_city, stores_by_city)

    # Summary
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    missing = [m for m in matches if m["issue"] == "MISSING_TENANT"]
    wrong = [m for m in matches if m["issue"] == "WRONG_TENANT"]
    correct = [m for m in matches if m["issue"] == "CORRECT"]

    print(f"Buildings with MISSING tenant: {len(missing)}")
    print(f"Buildings with WRONG tenant:   {len(wrong)}")
    print(f"Buildings with CORRECT tenant: {len(correct)}")
    print(f"TOTAL matches:                 {len(matches)}")

    print("\nBy retailer:")
    by_retailer = defaultdict(int)
    for m in matches:
        by_retailer[m["matched_retailer"]] += 1
    for retailer, count in sorted(by_retailer.items(), key=lambda x: -x[1]):
        print(f"  {retailer}: {count}")

    print()
    write_output(matches)

    # Show samples
    if matches:
        print("\n" + "=" * 70)
        print("SAMPLE MATCHES (highest confidence first)")
        print("=" * 70)
        for m in sorted(matches, key=lambda x: -x["confidence"])[:15]:
            print(f"\n{m['building_id']}: {m['building_address']}")
            print(f"  Store addr: {m['store_address']}")
            print(f"  Type: {m['building_type']} | SqFt: {m['square_footage']:,.0f}")
            print(f"  Current tenant: {m['current_tenant']}")
            print(f"  Matched to: {m['matched_retailer']} ({m['store_name']})")
            print(f"  Distance: {m['distance_meters']}m | Addr match: {m['address_match_score']} | Confidence: {m['confidence']}")
            print(f"  Issue: {m['issue']}")


if __name__ == "__main__":
    main()
