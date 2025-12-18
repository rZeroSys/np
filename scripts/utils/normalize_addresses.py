#!/usr/bin/env python3
"""
Normalize address columns across multiple CSV files to match MASTER format.
Target format: 'address' column with pattern: "street, city, STATE, ZIP"
"""

import pandas as pd
import os
import re
from pathlib import Path

# Base directory
ORIGINALS_DIR = "/Users/forrestmiller/Desktop/Originals"


def title_case(text):
    """Convert text to title case, preserving certain patterns."""
    if pd.isna(text) or text == '':
        return ''

    text = str(text).strip()

    # Common street suffix abbreviations that should stay capitalized
    abbreviations = {
        'NE': 'NE', 'NW': 'NW', 'SE': 'SE', 'SW': 'SW',
        'N': 'N', 'S': 'S', 'E': 'E', 'W': 'W'
    }

    # Title case the text
    words = text.split()
    result = []

    for word in words:
        # Check if it's a directional abbreviation
        if word.upper() in abbreviations:
            result.append(abbreviations[word.upper()])
        else:
            # Standard title case
            result.append(word.title())

    return ' '.join(result)


def normalize_state(state):
    """Ensure state is 2-letter uppercase abbreviation."""
    if pd.isna(state) or state == '':
        return ''

    state = str(state).strip().upper()

    # Handle common state name to abbreviation conversions
    state_map = {
        'CALIFORNIA': 'CA', 'NEW YORK': 'NY', 'MASSACHUSETTS': 'MA',
        'PENNSYLVANIA': 'PA', 'ILLINOIS': 'IL', 'TEXAS': 'TX',
        'WASHINGTON': 'WA', 'OREGON': 'OR', 'COLORADO': 'CO',
        'MISSOURI': 'MO', 'FLORIDA': 'FL', 'GEORGIA': 'GA',
        'DISTRICT OF COLUMBIA': 'DC'
    }

    if state in state_map:
        return state_map[state]

    # If already 2 letters, return as-is
    if len(state) == 2:
        return state

    return state


def normalize_zip(zip_code):
    """Ensure ZIP code is 5 digits."""
    if pd.isna(zip_code) or zip_code == '':
        return ''

    # Convert to string and remove any non-digit characters
    zip_str = str(zip_code).strip()

    # Remove decimal point if present (from float conversion)
    if '.' in zip_str:
        zip_str = zip_str.split('.')[0]

    # Extract first 5 digits
    digits = re.sub(r'\D', '', zip_str)

    if len(digits) >= 5:
        return digits[:5]
    elif len(digits) > 0:
        # Pad with leading zeros if needed
        return digits.zfill(5)

    return ''


def parse_full_address(address_str):
    """
    Parse a full address string into components.
    Expected formats:
    - "street, city, state, zip"
    - "street, city, state zip"
    - etc.
    """
    if pd.isna(address_str) or address_str == '':
        return {'street': '', 'city': '', 'state': '', 'zip': ''}

    address_str = str(address_str).strip()

    # Split by comma
    parts = [p.strip() for p in address_str.split(',')]

    result = {'street': '', 'city': '', 'state': '', 'zip': ''}

    if len(parts) >= 1:
        result['street'] = parts[0]

    if len(parts) >= 2:
        result['city'] = parts[1]

    if len(parts) >= 3:
        # Third part might be just state or "state zip"
        state_zip = parts[2].strip()

        # Check if there's a separate 4th part for ZIP
        if len(parts) >= 4:
            result['state'] = state_zip
            result['zip'] = parts[3].strip()
        else:
            # Try to split state and ZIP from the same part
            state_zip_parts = state_zip.split()
            if len(state_zip_parts) >= 2:
                result['state'] = state_zip_parts[0]
                result['zip'] = state_zip_parts[1]
            else:
                result['state'] = state_zip

    return result


def create_address(street, city='', state='', zip_code=''):
    """Create formatted address string: 'street, city, STATE, ZIP'"""
    components = []

    # Street (required)
    if street and str(street).strip():
        components.append(title_case(str(street)))

    # City (optional)
    if city and str(city).strip():
        components.append(title_case(str(city)))

    # State (optional, uppercase)
    if state and str(state).strip():
        components.append(normalize_state(str(state)))

    # ZIP (optional, 5 digits)
    if zip_code and str(zip_code).strip():
        normalized_zip = normalize_zip(str(zip_code))
        if normalized_zip:
            components.append(normalized_zip)

    return ', '.join(components)


# File-specific processing configurations
FILE_CONFIGS = {
    # GROUP 1: Full address - rename & reformat
    "ATL.csv": {
        "type": "reformat_full",
        "source_column": "Match_addr",
        "remove_columns": ["Match_addr"]
    },
    "BOS.csv": {
        "type": "reformat_full",
        "source_column": "Full Address",
        "remove_columns": ["Full Address"]
    },
    "KC.csv": {
        "type": "reformat_full",
        "source_column": "address",
        "remove_columns": []  # Already named correctly
    },
    "NYC_with_property_id_cleaned.csv": {
        "type": "reformat_full",
        "source_column": "address",
        "remove_columns": []  # Already named correctly
    },

    # GROUP 2: Split components - combine
    "CA_final_deduplicated_with_costar.csv": {
        "type": "combine_split",
        "street_column": "Address 1",
        "city_column": "City",
        "state_column": "State/Province",
        "zip_column": "Postal Code",
        "remove_columns": ["Address 1", "City", "State/Province", "Postal Code",
                          "norm_address_line_1", "norm_full_address"]
    },
    "CHI.csv": {
        "type": "combine_split",
        "street_column": "Address",
        "city_column": None,
        "state_column": None,
        "zip_column": "ZIP Code",
        "remove_columns": ["Address", "ZIP Code"]
    },
    "DC.csv": {
        "type": "combine_split",
        "street_column": "address",
        "city_column": "city",
        "state_column": "state",
        "zip_column": None,
        "remove_columns": ["ADDRESSOFRECORD", "REPORTEDADDRESS", "address", "city", "state"]
    },
    "DEN.csv": {
        "type": "combine_split",
        "street_column": "Street",
        "city_column": None,
        "state_column": None,
        "zip_column": "Zipcode",
        "remove_columns": ["Street", "Zipcode"]
    },
    "PHL_filtered_with_sqft_enhanced.csv": {
        "type": "combine_split",
        "street_column": "street_address",
        "city_column": None,
        "state_column": None,
        "zip_column": "postal_code",
        "remove_columns": ["street_address", "postal_code"]
    },
    "SD.csv": {
        "type": "combine_split",
        "street_column": "PropertyAddress",
        "city_column": None,
        "state_column": None,
        "zip_column": "ZipCode",
        "remove_columns": ["PropertyAddress", "ZipCode", "ZipFull"]
    },
    "SEA_cleaned.csv": {
        "type": "combine_split",
        "street_column": "Address",
        "city_column": "City",
        "state_column": "State",
        "zip_column": "ZipCode",
        "remove_columns": ["Address", "City", "State", "ZipCode",
                          "address", "city", "state", "zip_code"]
    },
    "SF_with_portfolio_id_latest.csv": {
        "type": "reformat_full",
        "source_column": "address",
        "remove_columns": ["norm_address_line_1", "norm_address_line_2", "norm_city",
                          "norm_state", "norm_zip", "norm_zip5", "norm_zip4", "norm_full_address"]
    },
    "SJ_normalized.csv": {
        "type": "combine_split",
        "street_column": "STREET",
        "city_column": "CITY",
        "state_column": "STATE",
        "zip_column": "ZIP CODE",
        "remove_columns": ["STREET", "CITY", "STATE", "ZIP CODE", "Full Address",
                          "norm_address_line_1", "norm_address_line_2", "norm_city",
                          "norm_state", "norm_zip", "norm_zip5", "norm_zip4", "norm_full_address"]
    },
    "LA_filtered_normalized.csv": {
        "type": "combine_split",
        "street_column": "BUILDING ADDRESS",
        "city_column": None,
        "state_column": None,
        "zip_column": "POSTAL CODE",
        "remove_columns": ["BUILDING ADDRESS", "POSTAL CODE", "Full Address", "norm_full_address"]
    },

    # GROUP 3: Street only - rename
    "CAM.csv": {
        "type": "street_only",
        "street_column": "Address",
        "remove_columns": ["Address"]
    },
    "ORL.csv": {
        "type": "street_only",
        "street_column": "Property Address",
        "remove_columns": ["Property Address"]
    },
    "PDX.csv": {
        "type": "street_only",
        "street_column": "Site Address",
        "remove_columns": ["Site Address"]
    },
    "STL.csv": {
        "type": "street_only",
        "street_column": "Address",
        "remove_columns": ["Address"]
    }
}


def process_file(file_path, filename, config):
    """Process a single CSV file according to its configuration."""
    print(f"\nProcessing {filename}...")

    try:
        # Read CSV
        df = pd.read_csv(file_path, low_memory=False, keep_default_na=False)
        original_shape = df.shape
        original_columns = df.columns.tolist()

        # Create address column based on type
        if config["type"] == "reformat_full":
            # Parse existing full address and reformat
            source_col = config["source_column"]
            if source_col not in df.columns:
                return {
                    "file": filename,
                    "status": "ERROR",
                    "message": f"Source column '{source_col}' not found"
                }

            # Parse and reformat each address
            addresses = []
            for addr in df[source_col]:
                parsed = parse_full_address(addr)
                new_addr = create_address(
                    parsed['street'],
                    parsed['city'],
                    parsed['state'],
                    parsed['zip']
                )
                addresses.append(new_addr)

            df['address'] = addresses

        elif config["type"] == "combine_split":
            # Combine split components
            street_col = config.get("street_column")
            city_col = config.get("city_column")
            state_col = config.get("state_column")
            zip_col = config.get("zip_column")

            # Check if required street column exists
            if street_col and street_col not in df.columns:
                return {
                    "file": filename,
                    "status": "ERROR",
                    "message": f"Street column '{street_col}' not found"
                }

            # Create address from components
            addresses = []
            for idx, row in df.iterrows():
                street = row[street_col] if street_col else ''
                city = row[city_col] if city_col and city_col in df.columns else ''
                state = row[state_col] if state_col and state_col in df.columns else ''
                zip_code = row[zip_col] if zip_col and zip_col in df.columns else ''

                new_addr = create_address(street, city, state, zip_code)
                addresses.append(new_addr)

            df['address'] = addresses

        elif config["type"] == "street_only":
            # Just rename and title case the street
            street_col = config["street_column"]
            if street_col not in df.columns:
                return {
                    "file": filename,
                    "status": "ERROR",
                    "message": f"Street column '{street_col}' not found"
                }

            df['address'] = df[street_col].apply(lambda x: title_case(str(x)) if x else '')

        # Remove specified columns (only if they exist and aren't the new address column)
        columns_to_remove = [col for col in config["remove_columns"]
                           if col in df.columns and col != 'address']
        if columns_to_remove:
            df.drop(columns=columns_to_remove, inplace=True)

        # Get statistics
        total_rows = len(df)
        non_empty = (df['address'] != '').sum()

        # Save back to file
        df.to_csv(file_path, index=False)

        return {
            "file": filename,
            "status": "SUCCESS",
            "type": config["type"],
            "original_shape": original_shape,
            "new_shape": df.shape,
            "columns_removed": columns_to_remove,
            "non_empty_addresses": f"{non_empty}/{total_rows} ({100*non_empty/total_rows:.1f}%)"
        }

    except Exception as e:
        return {
            "file": filename,
            "status": "ERROR",
            "message": str(e)
        }


def main():
    """Main processing function."""
    print("=" * 80)
    print("ADDRESS NORMALIZATION SCRIPT")
    print("=" * 80)
    print(f"Processing directory: {ORIGINALS_DIR}")
    print(f"Total files to process: {len(FILE_CONFIGS)}")
    print(f"\nTarget format: 'address' column = 'Street, City, STATE, ZIP'")

    results = []

    # Process each file
    for filename, config in FILE_CONFIGS.items():
        file_path = os.path.join(ORIGINALS_DIR, filename)

        if not os.path.exists(file_path):
            results.append({
                "file": filename,
                "status": "ERROR",
                "message": "File not found"
            })
            continue

        result = process_file(file_path, filename, config)
        results.append(result)

    # Print summary
    print("\n" + "=" * 80)
    print("PROCESSING SUMMARY")
    print("=" * 80)

    success_count = sum(1 for r in results if r["status"] == "SUCCESS")
    error_count = sum(1 for r in results if r["status"] == "ERROR")

    for result in results:
        print(f"\n📄 {result['file']}")
        print(f"   Status: {result['status']}")

        if result["status"] == "SUCCESS":
            print(f"   Type: {result.get('type', 'unknown')}")
            print(f"   Shape: {result['original_shape']} → {result['new_shape']}")
            print(f"   Non-empty addresses: {result['non_empty_addresses']}")
            if result.get('columns_removed'):
                print(f"   Removed columns: {', '.join(result['columns_removed'])}")
        else:
            print(f"   Error: {result.get('message', 'Unknown error')}")

    print("\n" + "=" * 80)
    print(f"✅ Successful: {success_count}/{len(results)}")
    print(f"❌ Errors: {error_count}/{len(results)}")
    print("=" * 80)


if __name__ == "__main__":
    main()
