#!/usr/bin/env python3
"""
Apply Verified Updates - Final step in the research pipeline
Applies verified research findings to portfolio_data.csv

Run: python3 apply_verified_updates.py
High-only: python3 apply_verified_updates.py --high-only
Dry-run: python3 apply_verified_updates.py --dry-run
Fresh: python3 apply_verified_updates.py --fresh
"""

import pandas as pd
import csv
import os
import shutil
import time
import argparse
import subprocess
import signal
import atexit
from datetime import datetime
from pathlib import Path

# Paths
SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = Path('/Users/forrestmiller/Desktop/nationwide-prospector')

READY_TO_IMPLEMENT = SCRIPT_DIR / 'ready_to_implement.csv'
PORTFOLIO_DATA = PROJECT_DIR / 'data/source/portfolio_data.csv'
BACKUP_DIR = PROJECT_DIR / 'BACKUPS_GO_HERE/csv_backups'
APPLIED_UPDATES = SCRIPT_DIR / 'applied_updates.csv'
CHANGE_LOG = SCRIPT_DIR / 'portfolio_change_log.csv'
PROGRESS_FILE = SCRIPT_DIR / 'apply_progress.txt'

# Config
POLL_INTERVAL = 5  # seconds
MAX_BACKUPS = 10
AUTO_APPLY_CONFIDENCE = ['HIGH', 'MEDIUM']

# Retail-only tenants - these should NOT appear in pure "Office" buildings
# (They can appear in Retail, Mixed Use, etc.)
RETAIL_ONLY_TENANTS = {
    # Big box / department stores
    'walmart', 'target', 'costco', 'sams club', "sam's club", 'bjs',
    "macy's", 'macys', 'nordstrom', "bloomingdale's", 'bloomingdales',
    'neiman marcus', 'saks fifth avenue', 'jcpenney', "j.c. penney",
    'kohls', "kohl's", 'dillards', "dillard's", 'belk',
    # Grocery
    'whole foods', 'trader joes', "trader joe's", 'safeway', 'kroger',
    'publix', 'wegmans', 'aldi', 'lidl', 'food lion', 'giant',
    'shoprite', 'stop & shop', 'albertsons', 'vons', 'ralphs',
    # Home improvement
    'home depot', 'lowes', "lowe's", 'menards', 'ace hardware',
    # Discount/variety
    'dollar general', 'dollar tree', 'family dollar', 'five below',
    'burlington', 'ross', 'tjmaxx', 't.j. maxx', 'marshalls', 'homegoods',
    # Drugstore
    'cvs', 'walgreens', 'rite aid',
    # Electronics
    'best buy', 'micro center',
    # Furniture
    'ikea', 'rooms to go', 'ashley furniture',
    # Sporting goods
    "dick's sporting goods", 'academy sports', 'bass pro shops', 'cabelas',
    # Clothing retail (store operations, not HQ)
    'gap', 'old navy', 'banana republic', 'h&m', 'zara', 'forever 21',
    'aeropostale', 'american eagle', 'hollister', 'abercrombie',
    # Pet
    'petco', 'petsmart',
    # Craft
    'michaels', 'joann', 'hobby lobby',
    # Office supply retail
    'staples', 'office depot', 'office max',
}

# Column names for ready_to_implement.csv (no header in file)
INPUT_COLUMNS = [
    'id_building', 'property_name', 'address', 'city',
    'field_to_update', 'current_value', 'new_value', 'original_found_value',
    'is_canonical_org', 'canonical_match_type', 'recommendation_type',
    'issue_type', 'confidence', 'claude_reasoning', 'timestamp'
]

def is_tenant_building_mismatch(tenant_name, building_type):
    """
    Check if tenant is a retail-only business being placed in an Office building.
    Returns True if this is a mismatch that should be rejected.
    """
    if not tenant_name or not building_type:
        return False

    # Only check for pure "Office" buildings
    btype_lower = str(building_type).lower().strip()
    if btype_lower != 'office':
        return False  # Mixed Use, Retail, etc. are OK

    # Check if tenant is a retail-only business
    tenant_lower = str(tenant_name).lower().strip()
    for retail in RETAIL_ONLY_TENANTS:
        if retail in tenant_lower or tenant_lower in retail:
            return True  # Mismatch: retail tenant in office building

    return False

# Caffeinate
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
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {msg}")

def save_progress(idx):
    with open(PROGRESS_FILE, 'w') as f:
        f.write(str(idx))

def load_progress():
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, 'r') as f:
            content = f.read().strip()
            return int(content) if content else 0
    return 0

def count_input_rows():
    """Count rows in ready_to_implement.csv"""
    if not READY_TO_IMPLEMENT.exists():
        return 0
    with open(READY_TO_IMPLEMENT, 'r') as f:
        return sum(1 for _ in f)

def create_backup():
    """Create timestamped backup of portfolio_data.csv"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"portfolio_data_backup_{timestamp}.csv"
    shutil.copy2(PORTFOLIO_DATA, backup_path)
    log(f"  Backup created: {backup_path.name}")

    # Prune old backups
    backups = sorted(BACKUP_DIR.glob("portfolio_data_backup_*.csv"),
                    key=lambda x: x.stat().st_mtime, reverse=True)
    for old in backups[MAX_BACKUPS:]:
        old.unlink()
        log(f"  Pruned old backup: {old.name}")

    return backup_path

def load_applied_set():
    """Load set of already-applied updates"""
    applied = set()
    if APPLIED_UPDATES.exists():
        with open(APPLIED_UPDATES, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row['id_building'], row['field_to_update'], row['new_value'])
                applied.add(key)
    return applied

def record_applied(updates, batch_id, backup_file):
    """Record applied updates"""
    is_new = not APPLIED_UPDATES.exists()
    with open(APPLIED_UPDATES, 'a', newline='', encoding='utf-8') as f:
        fieldnames = ['id_building', 'field_to_update', 'new_value', 'applied_at', 'batch_id', 'backup_file']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if is_new:
            writer.writeheader()
        for u in updates:
            writer.writerow({
                'id_building': u['id_building'],
                'field_to_update': u['field_to_update'],
                'new_value': u['new_value'],
                'applied_at': datetime.now().isoformat(),
                'batch_id': batch_id,
                'backup_file': backup_file.name if backup_file else ''
            })

def log_changes(changes, batch_id, backup_file):
    """Write to change log"""
    is_new = not CHANGE_LOG.exists()
    with open(CHANGE_LOG, 'a', newline='', encoding='utf-8') as f:
        fieldnames = [
            'timestamp', 'batch_id', 'id_building', 'property_name',
            'field_updated', 'old_value', 'new_value', 'confidence',
            'issue_type', 'recommendation_type', 'is_canonical_org', 'backup_file'
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if is_new:
            writer.writeheader()
        for c in changes:
            writer.writerow({
                'timestamp': datetime.now().isoformat(),
                'batch_id': batch_id,
                'id_building': c['id_building'],
                'property_name': c['property_name'],
                'field_updated': c['field_to_update'],
                'old_value': c['old_value'],
                'new_value': c['new_value'],
                'confidence': c['confidence'],
                'issue_type': c['issue_type'],
                'recommendation_type': c['recommendation_type'],
                'is_canonical_org': c['is_canonical_org'],
                'backup_file': backup_file.name if backup_file else ''
            })

def read_updates(start_row=0):
    """Read updates from ready_to_implement.csv starting at row"""
    if not READY_TO_IMPLEMENT.exists():
        return []

    updates = []
    with open(READY_TO_IMPLEMENT, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if i < start_row:
                continue
            if len(row) >= len(INPUT_COLUMNS):
                update = dict(zip(INPUT_COLUMNS, row[:len(INPUT_COLUMNS)]))
                updates.append(update)
    return updates

def apply_updates(updates, confidence_filter, dry_run=False):
    """Apply updates to portfolio_data.csv"""
    if not updates:
        return 0, {'skipped_confidence': 0, 'skipped_duplicate': 0, 'skipped_current': 0, 'skipped_flip': 0, 'skipped_mismatch': 0}

    # Load data
    log("Loading portfolio data...")
    portfolio_df = pd.read_csv(PORTFOLIO_DATA, low_memory=False)
    portfolio_df.set_index('id_building', inplace=True)
    applied_set = load_applied_set()

    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = None

    changes = []
    skipped = {'skipped_confidence': 0, 'skipped_duplicate': 0, 'skipped_current': 0, 'skipped_flip': 0, 'skipped_mismatch': 0}

    # Track building+field combos seen in this batch to prevent flip-flops
    seen_in_batch = set()

    for update in updates:
        # Filter by confidence
        if update['confidence'] not in confidence_filter:
            skipped['skipped_confidence'] += 1
            continue

        # Prevent flip-flops: only apply FIRST update per building+field in batch
        batch_key = (update['id_building'], update['field_to_update'])
        if batch_key in seen_in_batch:
            skipped['skipped_flip'] += 1
            continue
        seen_in_batch.add(batch_key)

        # Check duplicate (already applied in previous run)
        key = (update['id_building'], update['field_to_update'], update['new_value'])
        if key in applied_set:
            skipped['skipped_duplicate'] += 1
            continue

        # Check if building exists
        if update['id_building'] not in portfolio_df.index:
            log(f"  WARNING: Building not found: {update['id_building']}")
            continue

        # Check for tenant/building type mismatch (retail tenant in Office building)
        if update['field_to_update'] == 'org_tenant':
            bldg_type = portfolio_df.loc[update['id_building'], 'bldg_type'] if 'bldg_type' in portfolio_df.columns else None
            if is_tenant_building_mismatch(update['new_value'], bldg_type):
                log(f"  SKIP MISMATCH: {update['id_building']} | retail tenant '{update['new_value'][:25]}' in {bldg_type} building")
                skipped['skipped_mismatch'] += 1
                continue

        # Get current value
        field = update['field_to_update']
        if field not in portfolio_df.columns:
            log(f"  WARNING: Field not found: {field}")
            continue

        current_val = portfolio_df.loc[update['id_building'], field]
        if pd.isna(current_val):
            current_val = ''
        else:
            current_val = str(current_val)

        # Skip if already matches
        if current_val == update['new_value']:
            skipped['skipped_current'] += 1
            continue

        # Create backup on first actual change
        if not dry_run and not backup_file and changes == []:
            backup_file = create_backup()

        # Apply
        if not dry_run:
            portfolio_df.loc[update['id_building'], field] = update['new_value']

        changes.append({
            'id_building': update['id_building'],
            'property_name': update['property_name'],
            'field_to_update': field,
            'old_value': current_val,
            'new_value': update['new_value'],
            'confidence': update['confidence'],
            'issue_type': update['issue_type'],
            'recommendation_type': update['recommendation_type'],
            'is_canonical_org': update['is_canonical_org']
        })

        prefix = "[DRY-RUN] " if dry_run else ""
        log(f"  {prefix}UPDATE {update['id_building']} | {field} | "
            f"'{current_val[:30]}...' -> '{update['new_value'][:30]}...' | {update['confidence']}")

    # Save
    if not dry_run and changes:
        portfolio_df.reset_index(inplace=True)
        portfolio_df.to_csv(PORTFOLIO_DATA, index=False)
        log(f"  Saved {len(changes)} updates to portfolio_data.csv")

        record_applied(changes, batch_id, backup_file)
        log_changes(changes, batch_id, backup_file)

    return len(changes), skipped

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    parser.add_argument('--high-only', action='store_true', help='Only apply HIGH confidence')
    parser.add_argument('--all', action='store_true', help='Apply all including LOW')
    parser.add_argument('--fresh', action='store_true', help='Ignore progress, start fresh')
    args = parser.parse_args()

    # Determine confidence filter
    if args.high_only:
        confidence_filter = ['HIGH']
    elif args.all:
        confidence_filter = ['HIGH', 'MEDIUM', 'LOW']
    else:
        confidence_filter = AUTO_APPLY_CONFIDENCE

    # Setup
    start_caffeinate()
    atexit.register(stop_caffeinate)

    def handle_signal(sig, frame):
        log("\n[INTERRUPTED] Shutting down...")
        stop_caffeinate()
        exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    log("=" * 60)
    log("APPLY VERIFIED UPDATES")
    log("=" * 60)
    log(f"Confidence filter: {confidence_filter}")
    log(f"Dry run: {args.dry_run}")
    log("")

    # Get starting position
    if args.fresh:
        start_row = 0
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
    else:
        start_row = load_progress()

    total_rows = count_input_rows()
    log(f"Input file: {total_rows} rows")
    log(f"Starting from row: {start_row}")
    log("")

    # Initial batch
    if start_row < total_rows:
        log("Processing pending updates...")
        updates = read_updates(start_row)
        applied, skipped = apply_updates(updates, confidence_filter, args.dry_run)
        log(f"Applied: {applied} | Skipped: {skipped}")
        if not args.dry_run:
            save_progress(total_rows)
    else:
        log("No pending updates.")

    # Exit after dry-run
    if args.dry_run:
        log("")
        log("Dry-run complete. No changes made.")
        return

    # Poll for new
    log("")
    log(f"[LISTENING] Polling for new updates every {POLL_INTERVAL}s...")
    log("           Press Ctrl+C to stop")
    log("")

    last_count = total_rows

    while True:
        time.sleep(POLL_INTERVAL)

        current_count = count_input_rows()
        if current_count > last_count:
            new_count = current_count - last_count
            log(f"Detected {new_count} new update(s)")

            updates = read_updates(last_count)
            applied, skipped = apply_updates(updates, confidence_filter, args.dry_run)
            log(f"Applied: {applied} | Skipped: {skipped}")

            if not args.dry_run:
                save_progress(current_count)
            last_count = current_count

            log("")
            log(f"[LISTENING] Polling for new updates every {POLL_INTERVAL}s...")
            log("")

if __name__ == "__main__":
    main()
