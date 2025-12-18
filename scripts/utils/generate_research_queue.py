#!/usr/bin/env python3
"""
Generate Research Queue - Find all data issues for API research
Polls for changes to portfolio data and regenerates queue when needed.

Run: python3 generate_research_queue.py
Fresh: python3 generate_research_queue.py --fresh
"""

import pandas as pd
import re
import os
import csv
import time
import subprocess
import signal
import atexit
from datetime import datetime
from collections import Counter

# Paths - everything saves to this folder
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = '/Users/forrestmiller/Desktop/nationwide-prospector'

PORTFOLIO_DATA = f'{PROJECT_DIR}/data/source/portfolio_data.csv'
PORTFOLIO_ORGS = f'{PROJECT_DIR}/data/source/portfolio_organizations.csv'

OUTPUT_QUEUE = f'{SCRIPT_DIR}/research_queue.csv'
PROGRESS_FILE = f'{SCRIPT_DIR}/generate_progress.txt'
LAST_HASH_FILE = f'{SCRIPT_DIR}/generate_last_hash.txt'

POLL_INTERVAL = 60  # Check for changes every 60 seconds

# Caffeinate process to prevent Mac sleep
caffeinate_proc = None

def start_caffeinate():
    global caffeinate_proc
    try:
        caffeinate_proc = subprocess.Popen(['caffeinate', '-dims'])
        log("[CAFFEINATE] Mac will not sleep during run")
    except Exception as e:
        log(f"[CAFFEINATE] Could not start: {e}")

def stop_caffeinate():
    global caffeinate_proc
    if caffeinate_proc:
        caffeinate_proc.terminate()
        log("[CAFFEINATE] Stopped")

def log(msg):
    """Verbose logging"""
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {msg}")

def save_progress(idx):
    """Save current progress"""
    with open(PROGRESS_FILE, 'w') as f:
        f.write(str(idx))

def load_progress():
    """Load last progress"""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return int(f.read().strip())
    return 0

def get_file_hash():
    """Get modification time + size as simple hash"""
    try:
        stat1 = os.stat(PORTFOLIO_DATA)
        stat2 = os.stat(PORTFOLIO_ORGS)
        return f"{stat1.st_mtime}_{stat1.st_size}_{stat2.st_mtime}_{stat2.st_size}"
    except:
        return None

def save_hash(h):
    with open(LAST_HASH_FILE, 'w') as f:
        f.write(h)

def load_hash():
    if os.path.exists(LAST_HASH_FILE):
        with open(LAST_HASH_FILE, 'r') as f:
            return f.read().strip()
    return None

def build_canonical_set(orgs_df):
    """Build set of all canonical names + aliases"""
    log("Building canonical org set...")
    canonical = {}
    for _, org in orgs_df.iterrows():
        name = org['organization']
        canonical[name.lower()] = name
        aliases = str(org.get('search_aliases', '')).split('|')
        for a in aliases:
            a = a.strip()
            if a and len(a) > 2:
                canonical[a.lower()] = name
    log(f"  {len(canonical)} canonical names/aliases loaded")
    return canonical

def get_fieldnames():
    return [
        'id_building', 'property_name', 'address', 'city', 'state',
        'current_owner', 'current_tenant', 'current_manager',
        'data_year', 'bldg_sqft', 'bldg_type',
        'issue_type', 'priority', 'research_query', 'expected_finding'
    ]

def append_issue(issue, is_first=False):
    """Append single issue to CSV (incremental save)"""
    mode = 'w' if is_first else 'a'
    with open(OUTPUT_QUEUE, mode, newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=get_fieldnames())
        if is_first:
            writer.writeheader()
        writer.writerow(issue)

def generate_queue(fresh=False):
    """Generate the research queue - returns total issues found"""
    log("=" * 60)
    log("GENERATE RESEARCH QUEUE")
    log("=" * 60)

    # Load data
    log(f"Loading portfolio data from {PORTFOLIO_DATA}...")
    df = pd.read_csv(PORTFOLIO_DATA, low_memory=False)
    log(f"  Loaded {len(df):,} buildings")

    log(f"Loading canonical orgs from {PORTFOLIO_ORGS}...")
    orgs_df = pd.read_csv(PORTFOLIO_ORGS)
    log(f"  Loaded {len(orgs_df)} portfolio orgs")

    canonical_set = build_canonical_set(orgs_df)
    canonical_lower = set(canonical_set.keys())

    # Count org occurrences
    log("Counting org occurrences...")
    all_orgs = []
    for col in ['org_owner', 'org_tenant', 'org_manager']:
        all_orgs.extend(df[col].dropna().tolist())
    org_counts = Counter(all_orgs)
    log(f"  {len(org_counts)} unique orgs found")

    # Check for resume
    start_idx = 0 if fresh else load_progress()
    if start_idx > 0 and start_idx < len(df):
        log(f"RESUMING from row {start_idx}")
    else:
        log("Starting fresh...")
        start_idx = 0

    # Track stats
    stats = {
        'OLD_DATA': 0,
        'SHELL_COMPANY': 0,
        'LARGE_NO_TENANT': 0,
        'ORPHAN': 0,
        'NON_CANONICAL_ORG': 0
    }
    total_issues = 0
    seen = set()  # Dedupe

    log("")
    log("Processing buildings...")
    log("-" * 60)

    for idx, row in df.iterrows():
        if idx < start_idx:
            continue

        if idx % 1000 == 0:
            save_progress(idx)
            log(f"Row {idx:,}/{len(df):,} | Issues: {total_issues:,} | "
                f"OLD:{stats['OLD_DATA']} SHELL:{stats['SHELL_COMPANY']} "
                f"NOTENANT:{stats['LARGE_NO_TENANT']} ORPHAN:{stats['ORPHAN']} "
                f"NONCANON:{stats['NON_CANONICAL_ORG']}")

        building_id = row['id_building']
        prop = str(row['id_property_name']) if pd.notna(row['id_property_name']) else ''
        addr = str(row['loc_address']) if pd.notna(row['loc_address']) else ''
        city = str(row['loc_city']) if pd.notna(row['loc_city']) else ''
        state = str(row['loc_state']) if pd.notna(row['loc_state']) else ''
        owner = str(row['org_owner']) if pd.notna(row['org_owner']) else ''
        tenant = str(row['org_tenant']) if pd.notna(row['org_tenant']) else ''
        manager = str(row['org_manager']) if pd.notna(row['org_manager']) else ''
        data_year = int(row['data_year']) if pd.notna(row['data_year']) else 0
        sqft = int(row['bldg_sqft']) if pd.notna(row['bldg_sqft']) else 0
        bldg_type = str(row['bldg_type']) if pd.notna(row['bldg_type']) else ''

        base = {
            'id_building': building_id,
            'property_name': prop,
            'address': addr,
            'city': city,
            'state': state,
            'current_owner': owner,
            'current_tenant': tenant,
            'current_manager': manager,
            'data_year': data_year if data_year else '',
            'bldg_sqft': sqft if sqft else '',
            'bldg_type': bldg_type
        }

        issues_for_building = []

        # Priority 1: OLD_DATA (pre-2016)
        if data_year and data_year < 2016:
            key = (building_id, 'OLD_DATA')
            if key not in seen:
                seen.add(key)
                issues_for_building.append({**base,
                    'issue_type': 'OLD_DATA',
                    'priority': 1,
                    'research_query': f'"{prop}" {city} sold acquired owner 2020 2021 2022 2023 2024',
                    'expected_finding': f'Check if ownership changed since {data_year}'
                })
                stats['OLD_DATA'] += 1

        # Priority 2: SHELL_COMPANY
        if owner and re.search(r'\b(llc|lp|inc|trust|holdings|properties)\s*$', owner, re.I):
            if org_counts.get(owner, 0) < 3:
                key = (building_id, 'SHELL_COMPANY')
                if key not in seen:
                    seen.add(key)
                    issues_for_building.append({**base,
                        'issue_type': 'SHELL_COMPANY',
                        'priority': 2,
                        'research_query': f'"{owner}" real estate investor parent company',
                        'expected_finding': 'Find real owner behind shell company'
                    })
                    stats['SHELL_COMPANY'] += 1

        # Priority 3: LARGE_NO_TENANT
        if sqft and sqft > 100000 and not tenant and owner:
            key = (building_id, 'LARGE_NO_TENANT')
            if key not in seen:
                seen.add(key)
                issues_for_building.append({**base,
                    'issue_type': 'LARGE_NO_TENANT',
                    'priority': 3,
                    'research_query': f'"{prop}" {city} major tenants list',
                    'expected_finding': 'Find major tenant for large building'
                })
                stats['LARGE_NO_TENANT'] += 1

        # Priority 4: ORPHAN
        if not owner and not tenant and not manager:
            key = (building_id, 'ORPHAN')
            if key not in seen:
                seen.add(key)
                query = f'"{prop}" {city} owner' if prop else f'{addr} {city} building owner'
                issues_for_building.append({**base,
                    'issue_type': 'ORPHAN',
                    'priority': 4,
                    'research_query': query,
                    'expected_finding': 'Find owner for orphan building'
                })
                stats['ORPHAN'] += 1

        # Priority 5: NON_CANONICAL_ORG
        for org, col_name in [(owner, 'owner'), (tenant, 'tenant'), (manager, 'manager')]:
            if org and org.lower() not in canonical_lower:
                if org_counts.get(org, 0) >= 3:  # Only potential portfolios
                    key = (building_id, 'NON_CANONICAL_ORG')
                    if key not in seen:
                        seen.add(key)
                        issues_for_building.append({**base,
                            'issue_type': 'NON_CANONICAL_ORG',
                            'priority': 5,
                            'research_query': f'"{org}" company headquarters',
                            'expected_finding': f'Normalize {col_name}: {org}'
                        })
                        stats['NON_CANONICAL_ORG'] += 1
                    break

        # Save issues incrementally
        for issue in issues_for_building:
            is_first = (total_issues == 0 and start_idx == 0)
            append_issue(issue, is_first=is_first)
            total_issues += 1

    # Final save
    save_progress(len(df))

    log("")
    log("=" * 60)
    log("COMPLETE!")
    log("=" * 60)
    log(f"Total issues: {total_issues:,}")
    log("")
    for issue_type, count in sorted(stats.items(), key=lambda x: -x[1]):
        log(f"  {issue_type}: {count:,}")
    log("")
    log(f"Output saved to: {OUTPUT_QUEUE}")
    log("=" * 60)

    return total_issues

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--fresh', action='store_true', help='Start fresh, ignore progress')
    args = parser.parse_args()

    # Setup
    start_caffeinate()
    atexit.register(stop_caffeinate)

    def handle_signal(sig, frame):
        log("\n[INTERRUPTED] Shutting down...")
        stop_caffeinate()
        exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Initial run
    if args.fresh:
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
        if os.path.exists(LAST_HASH_FILE):
            os.remove(LAST_HASH_FILE)

    generate_queue(fresh=args.fresh)
    current_hash = get_file_hash()
    if current_hash:
        save_hash(current_hash)

    # Poll for changes
    log("")
    log(f"[LISTENING] Polling for changes every {POLL_INTERVAL}s...")
    log("           Press Ctrl+C to stop")
    log("")

    while True:
        time.sleep(POLL_INTERVAL)

        new_hash = get_file_hash()
        if new_hash and new_hash != current_hash:
            log("")
            log("[CHANGE DETECTED] Source files modified, regenerating queue...")
            log("")

            # Reset progress for fresh regeneration
            if os.path.exists(PROGRESS_FILE):
                os.remove(PROGRESS_FILE)

            generate_queue(fresh=True)
            current_hash = new_hash
            save_hash(current_hash)

            log("")
            log(f"[LISTENING] Polling for changes every {POLL_INTERVAL}s...")
            log("")
        else:
            # Silent poll - just show a dot every 5 minutes
            pass

if __name__ == "__main__":
    main()
