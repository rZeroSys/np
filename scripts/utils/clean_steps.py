#!/usr/bin/env python3
import requests
import re
import sys
import os

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
INPUT_FILE = "/Users/forrestmiller/Desktop/convos/data_cleaning_steps.txt"
OUTPUT_FILE = "/Users/forrestmiller/Desktop/convos/clean_steps_final.txt"

def log(msg):
    print(msg, flush=True)
    with open(OUTPUT_FILE, 'a') as f:
        f.write(msg + '\n')

def verify_with_anthropic(openai_cleaned_steps, raw_steps):
    """Use Claude to verify and correct the OpenAI output"""
    prompt = f"""You are a data cleaning verification assistant.

OpenAI cleaned these raw steps and produced the output below. Your job is to VERIFY correctness and FIX any errors.

CRITICAL CHECKS:
1. Is the ACTION correct? (DELETE ROW vs CLEAR VALUE vs UPDATE VALUE - these are DIFFERENT!)
   - DELETE ROW = entire row removed, row count decreases
   - CLEAR VALUE = cell set to empty/blank, row stays, row count same
   - UPDATE VALUE = cell changed from X to Y
2. Are the file paths correct?
3. Are the column names correct?
4. Are the criteria/conditions accurate?
5. Were any steps incorrectly merged or removed?

RAW STEPS (original):
{raw_steps[:8000]}

OPENAI'S CLEANED OUTPUT:
{openai_cleaned_steps}

Your output: Return the CORRECTED version of the cleaned steps. If OpenAI got it right, return it unchanged. If there are errors, fix them. Keep the same format."""

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 2500,
            "messages": [{"role": "user", "content": prompt}]
        },
        timeout=120
    )
    if response.status_code == 200:
        return response.json()['content'][0]['text']
    return f"ANTHROPIC ERROR: {response.status_code} - {response.text[:200]}"

def extract_csv_paths(raw_steps, filename):
    prompt = """Extract ALL CSV file paths mentioned in these data cleaning steps.

Return ONLY a list of full file paths, one per line. Include:
- Input CSVs that were read
- Output CSVs that were modified/created
- Any backup CSVs mentioned

If a path is partial, try to reconstruct the full path based on context.
Do NOT include any other text, just the file paths.

Steps to extract from:
""" + raw_steps

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1000
        },
        timeout=120
    )
    if response.status_code == 200:
        return response.json()['choices'][0]['message']['content']
    return f"ERROR: {response.status_code}"

def clean_steps_with_openai(raw_steps, filename):
    prompt = """Review these data cleaning steps extracted from a conversation.
The conversation had trial-and-error, mistakes, and corrections.

Your job: Output ONLY the correct final steps that should be followed to replicate this cleaning.

CRITICAL - Be VERY CAREFUL to distinguish between these operations:
- DELETE ROW = remove entire row from CSV (row count decreases)
- CLEAR VALUE = set cell to empty/blank but KEEP the row (row count stays same)
- UPDATE VALUE = change cell from one value to another value
- ADD COLUMN = add new column to CSV
- ADD ROW = insert new row into CSV
- RENAME COLUMN = change column header name
- COPY FILE = duplicate a file
- FILTER ROWS = keep only rows matching criteria (delete non-matching)

Rules:
1. REMOVE any correction/undo steps (e.g., "Restored values that were incorrectly cleared")
2. MERGE mistake steps with their corrections into ONE correct step
3. REMOVE validation/checking steps that don't change data
4. Keep only ACTIONABLE steps that modify files
5. Be specific: include file paths, column names, exact criteria

Format each step as:
- ACTION: [DELETE ROW | CLEAR VALUE | UPDATE VALUE | ADD COLUMN | ADD ROW | RENAME COLUMN | COPY FILE | FILTER ROWS | other]
- FILE: exact path
- COLUMN(S): which column(s) affected
- CRITERIA: how to identify which rows (e.g., "where org_tenant = 'Kroger'")
- CHANGES: specific values (old -> new, or what to set)
- ROW COUNT: how many rows affected if known
- WHY: brief reason

Raw steps to clean:
""" + raw_steps

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000
        },
        timeout=120
    )
    if response.status_code == 200:
        return response.json()['choices'][0]['message']['content']
    return f"ERROR: {response.status_code}"

def parse_conversations(content):
    """Split the input file into individual conversation sections"""
    pattern = r'\[(\d+)/17\] ([^\n]+\.jsonl)\n={60}\n(.*?)(?=\[\d+/17\]|$)'
    matches = re.findall(pattern, content, re.DOTALL)
    return [(m[1], m[2]) for m in matches]

# Main
with open(OUTPUT_FILE, 'w') as f:
    f.write("CLEANED DATA CLEANING STEPS\n")
    f.write("=" * 60 + "\n\n")

log("Reading input file...")
with open(INPUT_FILE, 'r') as f:
    content = f.read()

conversations = parse_conversations(content)
log(f"Found {len(conversations)} conversations to clean\n")

all_csv_paths = set()

for i, (filename, raw_steps) in enumerate(conversations, 1):
    log(f"\n{'='*60}")
    log(f"[{i}/{len(conversations)}] {filename}")
    log('='*60)

    if "STEPS EXTRACTED:" not in raw_steps:
        log("  SKIP: No steps found")
        continue

    steps_section = raw_steps.split("STEPS EXTRACTED:")[-1].strip()
    log(f"  Processing {len(steps_section)} chars...")

    # Extract CSV paths
    log("  Extracting CSV paths...")
    csv_paths = extract_csv_paths(steps_section, filename)
    log("\nCSV FILES USED:")
    log(csv_paths)

    # Add to master list
    for line in csv_paths.split('\n'):
        line = line.strip()
        if line and '.csv' in line.lower() and not line.startswith('ERROR'):
            all_csv_paths.add(line)

    # Clean the steps with OpenAI
    log("\n  Cleaning steps with OpenAI...")
    openai_cleaned = clean_steps_with_openai(steps_section, filename)
    log("\nOPENAI CLEANED STEPS:")
    log(openai_cleaned)

    # Verify with Anthropic/Claude
    log("\n  Verifying with Claude...")
    verified = verify_with_anthropic(openai_cleaned, steps_section)
    log("\nCLAUDE VERIFIED STEPS:")
    log(verified)
    log("")

# Write master CSV list
log("\n" + "="*60)
log("ALL CSV FILES ACROSS ALL CONVERSATIONS:")
log("="*60)
for path in sorted(all_csv_paths):
    log(path)

# Also save to separate file
with open("/Users/forrestmiller/Desktop/convos/all_csv_paths.txt", 'w') as f:
    f.write("ALL CSV FILES USED IN DATA CLEANING\n")
    f.write("="*60 + "\n\n")
    for path in sorted(all_csv_paths):
        f.write(path + '\n')

log(f"\nTotal unique CSV files: {len(all_csv_paths)}")
log(f"CSV list saved to: /Users/forrestmiller/Desktop/convos/all_csv_paths.txt")

log("\n" + "="*60)
log("DONE!")
