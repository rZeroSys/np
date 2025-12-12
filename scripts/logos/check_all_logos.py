#!/usr/bin/env python3
"""
Check ALL logos for wrong colors using OpenAI Vision API.
Saves results to CSV as it goes.
"""

import os
import sys
import csv
import base64
import time
from pathlib import Path
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import LOGOS_DIR as CONFIG_LOGOS_DIR

# CONFIG
LOGOS_DIR = str(CONFIG_LOGOS_DIR)
# Output folder is external to project - intentionally hardcoded
OUTPUT_DIR = "/Users/forrestmiller/Desktop/new logos"
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "bad_logos.csv")
PROGRESS_CSV = os.path.join(OUTPUT_DIR, "check_progress.csv")

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")

client = OpenAI(api_key=OPENAI_KEY)

def get_company_name(filename):
    """Convert filename to company name."""
    name = filename.replace('.png', '').replace('_', ' ')
    return name

def check_logo(image_path, company_name):
    """Use OpenAI Vision to check if logo has correct colors."""
    with open(image_path, 'rb') as f:
        image_bytes = f.read()

    b64_image = base64.standard_b64encode(image_bytes).decode('utf-8')

    prompt = f"""Look at this logo for "{company_name}".

Check if this logo has the CORRECT official brand colors for this company.

Common issues to look for:
- Wrong color (e.g., Hilton should be blue not orange)
- Inverted colors
- Faded/washed out colors
- Completely wrong color scheme

If you're not sure what company this is or what their official colors should be, say UNKNOWN.

Respond in this EXACT format:
STATUS: GOOD or BAD or UNKNOWN
COLORS_FOUND: [describe the colors you see]
EXPECTED_COLORS: [what colors should this brand have, if known]
ISSUE: [if BAD, explain what's wrong]"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}", "detail": "low"}}
                ]
            }],
            max_tokens=300
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"ERROR: {e}"

def parse_response(response):
    """Parse the OpenAI response."""
    status = "UNKNOWN"
    colors_found = ""
    expected_colors = ""
    issue = ""

    for line in response.split('\n'):
        line = line.strip()
        if line.startswith('STATUS:'):
            status = line.replace('STATUS:', '').strip()
        elif line.startswith('COLORS_FOUND:'):
            colors_found = line.replace('COLORS_FOUND:', '').strip()
        elif line.startswith('EXPECTED_COLORS:'):
            expected_colors = line.replace('EXPECTED_COLORS:', '').strip()
        elif line.startswith('ISSUE:'):
            issue = line.replace('ISSUE:', '').strip()

    return status, colors_found, expected_colors, issue

def load_progress():
    """Load already checked logos."""
    checked = set()
    if os.path.exists(PROGRESS_CSV):
        with open(PROGRESS_CSV, 'r') as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            for row in reader:
                if row:
                    checked.add(row[0])
    return checked

def save_progress(filename, status):
    """Save progress."""
    file_exists = os.path.exists(PROGRESS_CSV)
    with open(PROGRESS_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['filename', 'status'])
        writer.writerow([filename, status])

def save_bad_logo(filename, company, colors_found, expected_colors, issue):
    """Save bad logo to CSV."""
    file_exists = os.path.exists(OUTPUT_CSV)
    with open(OUTPUT_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['filename', 'company', 'colors_found', 'expected_colors', 'issue'])
        writer.writerow([filename, company, colors_found, expected_colors, issue])

def main():
    print("=" * 70)
    print("LOGO COLOR CHECKER - OpenAI Vision")
    print("=" * 70)

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Get all logo files
    logo_files = sorted([f for f in os.listdir(LOGOS_DIR) if f.endswith('.png') and not f.endswith('.py')])
    total = len(logo_files)

    print(f"\nLogos directory: {LOGOS_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Total logos to check: {total}")

    # Load progress
    checked = load_progress()
    print(f"Already checked: {len(checked)}")
    print(f"Remaining: {total - len(checked)}")
    print("\n" + "=" * 70 + "\n")

    # Stats
    good = 0
    bad = 0
    unknown = 0
    errors = 0

    start_time = time.time()

    for i, filename in enumerate(logo_files, 1):
        if filename in checked:
            continue

        company = get_company_name(filename)
        logo_path = os.path.join(LOGOS_DIR, filename)

        print(f"[{i}/{total}] {filename}")
        print(f"         Company: {company}")

        # Check logo
        response = check_logo(logo_path, company)

        if response.startswith("ERROR:"):
            print(f"         ERROR: {response}")
            errors += 1
            save_progress(filename, "ERROR")
            time.sleep(1)
            continue

        # Parse response
        status, colors_found, expected_colors, issue = parse_response(response)

        if "GOOD" in status.upper():
            print(f"         ✅ GOOD - {colors_found}")
            good += 1
            save_progress(filename, "GOOD")
        elif "BAD" in status.upper():
            print(f"         ❌ BAD - {issue}")
            print(f"         Found: {colors_found}")
            print(f"         Expected: {expected_colors}")
            bad += 1
            save_progress(filename, "BAD")
            save_bad_logo(filename, company, colors_found, expected_colors, issue)
        else:
            print(f"         ⚠️  UNKNOWN - {colors_found}")
            unknown += 1
            save_progress(filename, "UNKNOWN")

        # Progress stats every 25
        if i % 25 == 0:
            elapsed = time.time() - start_time
            rate = i / elapsed * 60
            print(f"\n{'=' * 70}")
            print(f"PROGRESS: {i}/{total} ({i/total*100:.1f}%)")
            print(f"✅ Good: {good} | ❌ Bad: {bad} | ⚠️ Unknown: {unknown} | Errors: {errors}")
            print(f"Rate: {rate:.0f}/hour | Elapsed: {elapsed/60:.1f} min")
            print(f"{'=' * 70}\n")

        # Small delay to avoid rate limits
        time.sleep(0.5)

    # Final summary
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(f"Total checked: {good + bad + unknown + errors}")
    print(f"✅ Good: {good}")
    print(f"❌ Bad: {bad}")
    print(f"⚠️  Unknown: {unknown}")
    print(f"Errors: {errors}")
    print(f"\nBad logos saved to: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
