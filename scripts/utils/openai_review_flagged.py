#!/usr/bin/env python3
"""Use OpenAI to review flagged logos - remove ones that are actually fine."""

import os
import csv
import base64
import time
from openai import OpenAI

# Paths
FLAGGED_DIR = "/Users/forrestmiller/Desktop/downloaded_logos/all_flagged"
OUTPUT_DIR = "/Users/forrestmiller/Desktop/downloaded_logos"
ACTUALLY_BAD_CSV = os.path.join(OUTPUT_DIR, "actually_bad_logos.csv")
PROGRESS_CSV = os.path.join(OUTPUT_DIR, "review_progress.csv")

# API
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))


def get_image_base64(filepath):
    with open(filepath, 'rb') as f:
        return base64.standard_b64encode(f.read()).decode('utf-8')


def extract_org_name(filename):
    name = os.path.splitext(filename)[0]
    return name.replace('_', ' ')


def review_logo(filepath, org_name):
    """Ask OpenAI if logo is bad or fine."""
    try:
        img_data = get_image_base64(filepath)

        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=100,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_data}"}},
                    {"type": "text", "text": f"""Is this a usable logo for "{org_name}"?

Reply ONLY with:
GOOD - if it's a real logo that matches or could be for this org
BAD - if it's wrong org, error page, corrupted, or not a logo

Then 5 words max why."""}
                ]
            }]
        )

        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"ERROR: {e}"


def get_already_reviewed():
    """Get set of already reviewed filenames."""
    reviewed = {}
    if os.path.exists(PROGRESS_CSV):
        with open(PROGRESS_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                reviewed[row['filename']] = row['verdict']
    return reviewed


def main():
    # Get all flagged images
    image_files = sorted([
        f for f in os.listdir(FLAGGED_DIR)
        if f.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
    ])

    total = len(image_files)
    print(f"Found {total} flagged logos to review\n")

    # Get already reviewed
    reviewed = get_already_reviewed()
    print(f"Already reviewed: {len(reviewed)}\n")

    # Setup CSVs
    fieldnames = ['filename', 'org_name', 'verdict', 'reason']

    progress_file = open(PROGRESS_CSV, 'a', newline='', encoding='utf-8')
    progress_writer = csv.DictWriter(progress_file, fieldnames=fieldnames)
    if os.path.getsize(PROGRESS_CSV) == 0 if os.path.exists(PROGRESS_CSV) else True:
        progress_writer.writeheader()

    good_count = 0
    bad_count = 0

    try:
        for i, filename in enumerate(image_files, 1):
            if filename in reviewed:
                if 'GOOD' in reviewed[filename].upper():
                    good_count += 1
                else:
                    bad_count += 1
                continue

            filepath = os.path.join(FLAGGED_DIR, filename)
            org_name = extract_org_name(filename)

            print(f"[{i}/{total}] {org_name}...", end=" ", flush=True)

            result = review_logo(filepath, org_name)

            if result.startswith("ERROR"):
                print(f"ERROR")
                verdict = "ERROR"
                reason = result
            elif result.upper().startswith("GOOD"):
                print(f"GOOD")
                verdict = "GOOD"
                reason = result.replace("GOOD", "").strip(" -")
                good_count += 1
            else:
                print(f"BAD")
                verdict = "BAD"
                reason = result.replace("BAD", "").strip(" -")
                bad_count += 1

            progress_writer.writerow({
                'filename': filename,
                'org_name': org_name,
                'verdict': verdict,
                'reason': reason
            })
            progress_file.flush()

            time.sleep(0.3)

    except KeyboardInterrupt:
        print("\n\nStopped. Progress saved.")

    finally:
        progress_file.close()

    # Write final bad logos list
    print(f"\nWriting actually bad logos...")
    with open(ACTUALLY_BAD_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        with open(PROGRESS_CSV, 'r', encoding='utf-8') as pf:
            reader = csv.DictReader(pf)
            for row in reader:
                if 'BAD' in row['verdict'].upper():
                    writer.writerow(row)

    print(f"\n{'='*50}")
    print(f"DONE")
    print(f"  GOOD (keep): {good_count}")
    print(f"  BAD (replace): {bad_count}")
    print(f"\nBad logos saved to: {ACTUALLY_BAD_CSV}")


if __name__ == '__main__':
    main()
