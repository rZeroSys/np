#!/usr/bin/env python3
"""
================================================================================
                        MASTER ORCHESTRATION SCRIPT
================================================================================

THIS IS THE ONE SCRIPT THAT DOES EVERYTHING.

Run this to:
  1. Backup portfolio_data.csv
  2. Run all 12 data calculation scripts
  3. Regenerate the homepage
  4. Regenerate all building reports (including NYC special reports)
  5. Commit and push to GitHub

Usage:
    python3 scripts/MASTER_ORCHESTRATE.py "Your commit message"
    python3 scripts/MASTER_ORCHESTRATE.py  # uses default message

================================================================================
"""

import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path
import shutil

# =============================================================================
# CONFIGURATION
# =============================================================================

SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = SCRIPT_DIR.parent
POPULATE_MASTER_DIR = SCRIPT_DIR / 'populate_master'
EUI_SCRIPT = SCRIPT_DIR / 'data_updates' / 'calculate_new_eui.py'

# Add project root to path for imports
sys.path.insert(0, str(PROJECT_ROOT))
from src.config import PORTFOLIO_DATA_PATH, BACKUP_DIR

# Data scripts to run in order
DATA_SCRIPTS = [
    ('00_align_verticals.py',      'Align building types to verticals'),
    ('01_hvac_pct.py',             'HVAC % by fuel type'),
    ('02_energy_costs.py',         'Calculate energy costs from rates'),
    ('03_odcv_savings.py',         'ODCV savings percentage'),
    ('04_post_odcv_energy.py',     'Post-ODCV energy'),
    ('05_post_odcv_costs.py',      'Post-ODCV costs'),
    ('06_hvac_totals.py',          'HVAC energy and cost totals'),
    ('07_carbon_by_city.py',       'City-specific carbon emissions'),
    ('08_bps_fines.py',            'BPS fine avoidance'),
    ('09_valuation.py',            'Valuation impact'),
    ('10_energy_star_estimate.py', 'Energy Star score estimation'),
    ('11_nyc_update.py',           'NYC building overrides (LAST)'),
]

HTML_GENERATOR_MODULE = 'src.generators.html_generator'
BUILDING_REPORT_MODULE = 'src.generators.building_report'

# =============================================================================
# HELPERS
# =============================================================================

def print_banner(text):
    """Print a prominent banner."""
    width = 70
    print()
    print("=" * width)
    print(text.center(width))
    print("=" * width)


def print_step(step_num, total, description):
    """Print step header."""
    print()
    print("-" * 70)
    print(f"[{step_num}/{total}] {description}")
    print("-" * 70)


def run_command(cmd, description, cwd=None):
    """Run a command and return success status."""
    print(f"Running: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(
        cmd,
        cwd=cwd or PROJECT_ROOT,
        capture_output=False
    )
    if result.returncode != 0:
        print(f"FAILED: {description} (exit code {result.returncode})")
        return False
    return True


def create_backup():
    """Create timestamped backup of portfolio_data.csv."""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = BACKUP_DIR / f'portfolio_data_backup_{timestamp}.csv'
    shutil.copy2(PORTFOLIO_DATA_PATH, backup_path)
    print(f"Backup created: {backup_path}")
    return backup_path


# =============================================================================
# MAIN STEPS
# =============================================================================

def step_1_data_scripts():
    """Run all 12 data calculation scripts."""
    print(f"Running {len(DATA_SCRIPTS)} data scripts...")

    for script_name, description in DATA_SCRIPTS:
        script_path = POPULATE_MASTER_DIR / script_name

        if not script_path.exists():
            print(f"ERROR: Script not found: {script_path}")
            return False

        print(f"\n  [{script_name}] {description}")

        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=PROJECT_ROOT,
            capture_output=False
        )

        if result.returncode != 0:
            print(f"FAILED: {script_name} (exit code {result.returncode})")
            return False

    return True


def step_1b_update_eui_lookup():
    """Update eui_post_odcv.csv lookup file."""
    return run_command(
        [sys.executable, str(EUI_SCRIPT)],
        "EUI post-ODCV lookup update"
    )


def step_2_regenerate_homepage():
    """Regenerate the homepage."""
    return run_command(
        [sys.executable, '-m', HTML_GENERATOR_MODULE],
        "Homepage generation"
    )


def step_3_regenerate_building_reports():
    """Regenerate all building reports (includes NYC special reports)."""
    return run_command(
        [sys.executable, '-m', BUILDING_REPORT_MODULE],
        "Building reports generation"
    )


def step_4_git_push(commit_message):
    """Stage, commit, and push to GitHub."""
    # Stage all changes
    if not run_command(['git', 'add', '-A'], "Git add"):
        return False

    # Show what's staged
    subprocess.run(['git', 'status', '--short'], cwd=PROJECT_ROOT)

    # Commit
    full_message = f"""{commit_message}

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"""

    result = subprocess.run(
        ['git', 'commit', '-m', full_message],
        cwd=PROJECT_ROOT
    )
    if result.returncode != 0:
        print("Note: Commit may have failed if there were no changes")
        # Don't fail on empty commit

    # Push
    return run_command(['git', 'push'], "Git push")


# =============================================================================
# MAIN
# =============================================================================

def main():
    start_time = datetime.now()

    # Get commit message from args or use default
    commit_message = sys.argv[1] if len(sys.argv) > 1 else "Full data update, regenerate homepage and building reports"

    print_banner("MASTER ORCHESTRATION SCRIPT")
    print(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Project: {PROJECT_ROOT}")
    print(f"Commit message: {commit_message}")

    total_steps = 4

    # Step 0: Create backup
    print("\nCreating backup of portfolio_data.csv...")
    backup_path = create_backup()

    # Step 1: Run all 12 data scripts
    print_step(1, total_steps, "Running 12 data scripts...")
    if not step_1_data_scripts():
        print_banner("FAILED AT STEP 1: DATA SCRIPTS")
        print(f"Backup available at: {backup_path}")
        sys.exit(1)
    print("All data scripts complete.")

    # Step 1b: Update EUI lookup
    print("\nUpdating EUI post-ODCV lookup...")
    if not step_1b_update_eui_lookup():
        print_banner("FAILED: EUI LOOKUP UPDATE")
        sys.exit(1)
    print("EUI lookup updated.")

    # Step 2: Regenerate homepage
    print_step(2, total_steps, "Regenerating homepage...")
    if not step_2_regenerate_homepage():
        print_banner("FAILED AT STEP 2: HOMEPAGE GENERATION")
        sys.exit(1)
    print("Homepage regenerated.")

    # Step 3: Regenerate building reports (includes NYC special)
    print_step(3, total_steps, "Regenerating building reports (includes NYC special reports)...")
    if not step_3_regenerate_building_reports():
        print_banner("FAILED AT STEP 3: BUILDING REPORTS")
        sys.exit(1)
    print("Building reports regenerated.")

    # Step 4: Git push
    print_step(4, total_steps, "Committing and pushing to GitHub...")
    if not step_4_git_push(commit_message):
        print_banner("FAILED AT STEP 4: GIT PUSH")
        sys.exit(1)
    print("Pushed to GitHub.")

    # Done!
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print_banner("ALL STEPS COMPLETED SUCCESSFULLY")
    print(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
    print(f"Completed: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()


if __name__ == '__main__':
    main()
