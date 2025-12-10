#!/usr/bin/env python3
"""
Master Orchestration Script
============================
Runs all populate_master scripts in correct dependency order.

Execution Order:
  1. 01_hvac_pct.py       - Base data only
  2. 02_odcv_savings.py   - Base data only
  3. 03_hvac_totals.py    - Needs hvac_pct (1)
  4. 04_carbon_by_city.py - Needs hvac_pct (1), odcv_pct (2)
  5. 05_bps_fines.py      - Needs hvac_pct (1), odcv_pct (2)
  6. 06_valuation.py      - Needs (1), (2), bps_fine (5)
  7. 07_nyc_update.py     - MUST BE LAST (overwrites NYC data)

Usage: python3 orchestrate.py
"""

import subprocess
import sys
import os
from datetime import datetime
import shutil

# =============================================================================
# CONFIGURATION
# =============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = '/Users/forrestmiller/Desktop/nationwide-prospector/data/source/portfolio_data.csv'
BACKUP_DIR = '/Users/forrestmiller/Desktop/nationwide-prospector/BACKUPS_GO_HERE/csv_backups'

SCRIPTS = [
    ('01_hvac_pct.py',       'HVAC percentages by fuel type'),
    ('02_odcv_savings.py',   'ODCV savings percentage'),
    ('03_hvac_totals.py',    'HVAC energy and cost totals'),
    ('04_carbon_by_city.py', 'City-specific carbon emissions'),
    ('05_bps_fines.py',      'BPS fine avoidance'),
    ('06_valuation.py',      'Valuation impact'),
    ('07_nyc_update.py',     'NYC building overrides (LAST)'),
]

# =============================================================================
# FUNCTIONS
# =============================================================================

def create_backup():
    """Create timestamped backup of portfolio_data.csv."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f'portfolio_data_backup_{timestamp}.csv')
    shutil.copy2(DATA_FILE, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path


def run_script(script_name, description):
    """Run a single script and return success status."""
    script_path = os.path.join(SCRIPT_DIR, script_name)

    if not os.path.exists(script_path):
        print(f"ERROR: Script not found: {script_path}")
        return False

    print(f"\n{'='*70}")
    print(f"Running: {script_name}")
    print(f"Purpose: {description}")
    print('='*70)

    result = subprocess.run(
        [sys.executable, script_path],
        capture_output=False
    )

    if result.returncode != 0:
        print(f"\nFAILED: {script_name} (exit code {result.returncode})")
        return False

    return True


# =============================================================================
# MAIN
# =============================================================================

def main():
    start_time = datetime.now()

    print("="*70)
    print("MASTER ORCHESTRATION SCRIPT")
    print("="*70)
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Data file: {DATA_FILE}")
    print(f"Scripts to run: {len(SCRIPTS)}")

    # Create backup
    print("\n" + "-"*70)
    print("Creating backup...")
    backup_path = create_backup()

    # Run each script in order
    completed = 0
    for script_name, description in SCRIPTS:
        if not run_script(script_name, description):
            print("\n" + "!"*70)
            print("ORCHESTRATION FAILED")
            print(f"Script: {script_name}")
            print(f"Backup available at: {backup_path}")
            print("!"*70)
            sys.exit(1)
        completed += 1

    # Summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print("\n" + "="*70)
    print("ALL SCRIPTS COMPLETED SUCCESSFULLY")
    print("="*70)
    print(f"Scripts run: {completed}/{len(SCRIPTS)}")
    print(f"Duration: {duration:.1f} seconds")
    print(f"Backup: {backup_path}")
    print(f"Completed: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)


if __name__ == '__main__':
    main()
