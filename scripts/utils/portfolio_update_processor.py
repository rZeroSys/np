#!/usr/bin/env python3
"""
Portfolio Update Processor

Processes verified findings from claude_findings_verifier.py and generates
a ready-to-implement CSV of portfolio updates with canonical org name matching.

Usage:
    python3 portfolio_update_processor.py

Features:
- Processes existing verified findings on startup
- Watches for new entries continuously
- Matches orgs to canonical names with 100% accuracy (exact matching only)
- Outputs ready_to_implement.csv with all pending updates
"""

import os
import re
import csv
import time
import subprocess
from datetime import datetime
from pathlib import Path

# File paths
API_RESEARCH_DIR = Path("/Users/forrestmiller/Desktop/api_research")
PROSPECTOR_DIR = Path("/Users/forrestmiller/Desktop/nationwide-prospector/data/source")

VERIFIED_FINDINGS_PATH = API_RESEARCH_DIR / "verified_findings.csv"
RESEARCH_RESULTS_PATH = API_RESEARCH_DIR / "research_results.csv"
PORTFOLIO_ORGS_PATH = PROSPECTOR_DIR / "portfolio_organizations.csv"
PORTFOLIO_DATA_PATH = PROSPECTOR_DIR / "portfolio_data.csv"
OUTPUT_PATH = API_RESEARCH_DIR / "ready_to_implement.csv"
PROGRESS_PATH = API_RESEARCH_DIR / "update_processor_progress.txt"

# Recommendation type to field mapping
RECOMMENDATION_FIELD_MAP = {
    "UPDATE_OWNER": "org_owner",
    "ADD_OWNER": "org_owner",
    "UPDATE_TENANT": "org_tenant",
    "ADD_TENANT": "org_tenant",
    "UPDATE_MANAGER": "org_manager",
    "ADD_MANAGER": "org_manager",
}

# Poll interval for file watcher (seconds)
POLL_INTERVAL = 2


def log(message):
    """Log with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")


def enable_caffeinate():
    """Prevent Mac from sleeping during long runs."""
    try:
        subprocess.Popen(
            ["caffeinate", "-dims", "-w", str(os.getpid())],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        log("[CAFFEINATE] Mac will not sleep during run")
    except Exception:
        pass


def build_canonical_org_lookup():
    """
    Build lookup dict mapping org names and aliases to canonical names.
    Uses exact case-insensitive matching for 100% accuracy.

    Returns:
        dict: {lowercase_name_or_alias: canonical_org_name}
    """
    lookup = {}

    log(f"Loading canonical orgs from {PORTFOLIO_ORGS_PATH}...")

    with open(PORTFOLIO_ORGS_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        org_count = 0
        alias_count = 0

        for row in reader:
            canonical_name = row.get('organization', '').strip()
            if not canonical_name:
                continue

            org_count += 1

            # Add the canonical name itself (lowercase for matching)
            lookup[canonical_name.lower()] = canonical_name

            # Add all aliases from search_aliases (pipe-separated)
            aliases_str = row.get('search_aliases', '')
            if aliases_str:
                aliases = [a.strip() for a in aliases_str.split('|') if a.strip()]
                for alias in aliases:
                    lookup[alias.lower()] = canonical_name
                    alias_count += 1

    log(f"  Loaded {org_count} organizations with {alias_count} aliases")
    return lookup


def find_canonical_org(found_name, org_lookup):
    """
    Find canonical org name for a found organization.
    Uses EXACT full-string matching only for 100% accuracy.

    Args:
        found_name: The organization name found in research
        org_lookup: Dict mapping lowercase names/aliases to canonical names

    Returns:
        tuple: (canonical_name, matched_on) or (None, None) if no match
    """
    if not found_name or str(found_name).lower() == 'nan':
        return None, None

    found_lower = str(found_name).strip().lower()

    # EXACT full-string match only - no partial/word-boundary matching
    # This ensures 100% accuracy as requested
    if found_lower in org_lookup:
        return org_lookup[found_lower], "exact"

    return None, None


def load_research_results():
    """
    Load research results into a dict keyed by id_building.

    Returns:
        dict: {id_building: {found_owner, found_tenant, found_manager, ...}}
    """
    log(f"Loading research results from {RESEARCH_RESULTS_PATH}...")

    results = {}
    with open(RESEARCH_RESULTS_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            building_id = row.get('id_building', '')
            if building_id:
                results[building_id] = row

    log(f"  Loaded {len(results)} research results")
    return results


def load_portfolio_data():
    """
    Load portfolio data into a dict keyed by id_building.

    Returns:
        dict: {id_building: {org_owner, org_tenant, org_manager, ...}}
    """
    log(f"Loading portfolio data from {PORTFOLIO_DATA_PATH}...")

    portfolio = {}
    with open(PORTFOLIO_DATA_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            building_id = row.get('id_building', '')
            if building_id:
                portfolio[building_id] = row

    log(f"  Loaded {len(portfolio)} buildings")
    return portfolio


def load_last_processed_count():
    """Load the last processed row count from progress file."""
    if PROGRESS_PATH.exists():
        try:
            return int(PROGRESS_PATH.read_text().strip())
        except (ValueError, IOError):
            pass
    return 0


def save_processed_count(count):
    """Save the processed row count to progress file."""
    PROGRESS_PATH.write_text(str(count))


def get_verified_findings_count():
    """Get current row count of verified findings file."""
    if not VERIFIED_FINDINGS_PATH.exists():
        return 0

    with open(VERIFIED_FINDINGS_PATH, 'r', encoding='utf-8') as f:
        return sum(1 for _ in f) - 1  # Subtract header


def read_verified_findings(start_row=0):
    """
    Read verified findings from CSV, optionally starting from a specific row.

    Args:
        start_row: Row index to start from (0-based, after header)

    Yields:
        dict: Each verified finding row
    """
    with open(VERIFIED_FINDINGS_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= start_row:
                yield row


def process_finding(finding, research_results, portfolio_data, org_lookup):
    """
    Process a single verified finding and return update record if applicable.

    Args:
        finding: Dict from verified_findings.csv
        research_results: Dict of research results keyed by id_building
        portfolio_data: Dict of portfolio data keyed by id_building
        org_lookup: Canonical org lookup dict

    Returns:
        dict: Update record or None if not applicable
    """
    # Only process verified findings
    claude_verified = str(finding.get('claude_verified', '')).lower()
    if claude_verified != 'true':
        return None

    building_id = finding.get('id_building', '')
    if not building_id:
        return None

    # Get recommendation type
    recommendation = finding.get('original_recommendation', '')
    field_to_update = RECOMMENDATION_FIELD_MAP.get(recommendation)
    if not field_to_update:
        return None

    # Get research result for this building
    research = research_results.get(building_id, {})

    # Determine which found value to use based on recommendation
    if 'OWNER' in recommendation:
        found_value = research.get('found_owner', '')
    elif 'TENANT' in recommendation:
        found_value = research.get('found_tenant', '')
    elif 'MANAGER' in recommendation:
        found_value = research.get('found_manager', '')
    else:
        found_value = finding.get('original_finding', '')

    # Clean the found value
    if not found_value or str(found_value).lower() == 'nan':
        # Fall back to original_finding from verified_findings
        found_value = finding.get('original_finding', '')

    if not found_value or str(found_value).lower() == 'nan':
        return None

    # Check for canonical org match
    canonical_name, match_type = find_canonical_org(found_value, org_lookup)

    # Get current value from portfolio
    portfolio_record = portfolio_data.get(building_id, {})
    current_value = portfolio_record.get(field_to_update, '')
    if str(current_value).lower() == 'nan':
        current_value = ''

    # Determine final new value
    new_value = canonical_name if canonical_name else found_value

    # Build update record
    return {
        'id_building': building_id,
        'property_name': finding.get('property_name', ''),
        'address': finding.get('address', ''),
        'city': finding.get('city', ''),
        'field_to_update': field_to_update,
        'current_value': current_value,
        'new_value': new_value,
        'original_found_value': found_value,
        'is_canonical_org': 'Yes' if canonical_name else 'No',
        'canonical_match_type': match_type if match_type else '',
        'recommendation_type': recommendation,
        'issue_type': finding.get('issue_type', ''),
        'confidence': finding.get('claude_confidence', ''),
        'claude_reasoning': finding.get('claude_reasoning', ''),
        'timestamp': datetime.now().isoformat()
    }


def write_output_header():
    """Write header to output CSV if it doesn't exist."""
    if not OUTPUT_PATH.exists():
        fieldnames = [
            'id_building', 'property_name', 'address', 'city',
            'field_to_update', 'current_value', 'new_value', 'original_found_value',
            'is_canonical_org', 'canonical_match_type', 'recommendation_type',
            'issue_type', 'confidence', 'claude_reasoning', 'timestamp'
        ]
        with open(OUTPUT_PATH, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
        log(f"Created output file: {OUTPUT_PATH}")


def append_update(update_record):
    """Append a single update record to the output CSV."""
    fieldnames = [
        'id_building', 'property_name', 'address', 'city',
        'field_to_update', 'current_value', 'new_value', 'original_found_value',
        'is_canonical_org', 'canonical_match_type', 'recommendation_type',
        'issue_type', 'confidence', 'claude_reasoning', 'timestamp'
    ]
    with open(OUTPUT_PATH, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writerow(update_record)


def process_batch(findings, research_results, portfolio_data, org_lookup):
    """
    Process a batch of findings and write updates.

    Returns:
        int: Number of updates written
    """
    updates_written = 0

    for finding in findings:
        update = process_finding(finding, research_results, portfolio_data, org_lookup)
        if update:
            append_update(update)
            updates_written += 1
            log(f"  UPDATE: {update['id_building']} | {update['field_to_update']} | "
                f"'{update['current_value']}' -> '{update['new_value']}' "
                f"({'canonical' if update['is_canonical_org'] == 'Yes' else 'as-is'})")

    return updates_written


def main():
    """Main entry point."""
    enable_caffeinate()

    log("=" * 60)
    log("PORTFOLIO UPDATE PROCESSOR")
    log("=" * 60)

    # Load all reference data
    org_lookup = build_canonical_org_lookup()
    research_results = load_research_results()
    portfolio_data = load_portfolio_data()

    # Initialize output file
    write_output_header()

    # Load progress
    last_processed = load_last_processed_count()
    log(f"Last processed row: {last_processed}")

    # Process existing verified findings
    current_count = get_verified_findings_count()
    log(f"Verified findings available: {current_count}")

    if current_count > last_processed:
        log(f"Processing {current_count - last_processed} new/existing verified findings...")
        findings = list(read_verified_findings(start_row=last_processed))
        updates = process_batch(findings, research_results, portfolio_data, org_lookup)
        log(f"Wrote {updates} updates to {OUTPUT_PATH}")
        save_processed_count(current_count)
        last_processed = current_count

    # Enter file watcher mode
    log("")
    log("=" * 60)
    log("WATCHING FOR NEW VERIFIED FINDINGS...")
    log(f"Polling every {POLL_INTERVAL} seconds. Press Ctrl+C to stop.")
    log("=" * 60)

    try:
        while True:
            time.sleep(POLL_INTERVAL)

            new_count = get_verified_findings_count()
            if new_count > last_processed:
                log(f"Detected {new_count - last_processed} new verified finding(s)")

                # Reload research results in case new ones were added
                research_results = load_research_results()

                findings = list(read_verified_findings(start_row=last_processed))
                updates = process_batch(findings, research_results, portfolio_data, org_lookup)

                if updates > 0:
                    log(f"Wrote {updates} new update(s)")

                save_processed_count(new_count)
                last_processed = new_count

    except KeyboardInterrupt:
        log("")
        log("Stopped by user")
        log(f"Total processed: {last_processed} findings")
        log(f"Output file: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
