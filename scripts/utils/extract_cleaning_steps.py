#!/usr/bin/env python3
import json
import requests
import os
from pathlib import Path
import sys

API_KEY = os.environ.get("OPENAI_API_KEY", "")
convos_dir = Path("/Users/forrestmiller/Desktop/convos")
output_file = convos_dir / "data_cleaning_steps.txt"

DATA_CLEANING_FILES = [
    "04c92094-1c55-45d0-8712-4ebd84da20c6.jsonl",
    "0fcf5fba-a518-44f6-b858-9ed92d4a5ef8.jsonl",
    "17bf2dee-1fb9-4c31-a694-d3dbf61605cf.jsonl",
    "23758767-9492-41ea-bf01-b357f5559527.jsonl",
    "42513c59-06b0-41be-a71d-7d6fd24a459c.jsonl",
    "503219a1-b650-4226-97da-924e88a9867d.jsonl",
    "739dd4e5-6492-40c1-937a-9d4c7971c57d.jsonl",
    "78ab4f94-a3fe-4de1-90fe-3f937d94eeaa.jsonl",
    "969d6039-bf01-4772-9571-56faf9ba0e5c.jsonl",
    "9cdff6b7-e38e-45e6-b493-c08ff70ed1eb.jsonl",
    "a93bbeff-fd80-4624-9ea4-e3ddd5255cfc.jsonl",
    "b23f4585-d771-46d0-8f15-fa2ff0503598.jsonl",
    "c2fc29cf-2d8b-4ea1-9a67-333126921a95.jsonl",
    "d9447358-aa23-413e-994a-b96741a4ba9c.jsonl",
    "eabc803b-745a-4777-87c2-66398b4785ac.jsonl",
    "f7cec90b-b63f-4d1c-92ee-17e28c2deecb.jsonl",
    "fc3155c4-fcb0-4132-85e8-189c6b82655f.jsonl",
]

def log(msg):
    print(msg, flush=True)
    with open(output_file, 'a') as f:
        f.write(msg + '\n')

def extract_conversation(jsonl_file):
    convo = []
    with open(jsonl_file, 'r') as f:
        for line in f:
            try:
                d = json.loads(line)
                msg_type = d.get('type')
                if msg_type in ['user', 'assistant'] and 'message' in d:
                    msg = d['message']
                    role = msg.get('role', msg_type)
                    content = msg.get('content', '')
                    if isinstance(content, list):
                        text_parts = []
                        for item in content:
                            if isinstance(item, dict) and item.get('type') == 'text':
                                text_parts.append(item.get('text', '')[:1000])
                        content = ' '.join(text_parts)
                    if content and isinstance(content, str):
                        convo.append(f"{role.upper()}: {content[:1500]}")
            except:
                pass
    return convo

def get_detailed_steps(convo_text):
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": """Analyze this data cleaning conversation and extract ALL specific data cleaning steps that were performed.
For each step, include:
- What action was taken (e.g., "deleted rows", "updated column", "changed value")
- Which file/CSV was modified
- What specific changes were made (column names, values changed, rows affected)
- Any criteria used for the changes

Format as a numbered list. Be specific about column names, file paths, and values."""},
                {"role": "user", "content": convo_text}
            ],
            "max_tokens": 2000
        },
        timeout=120
    )
    if response.status_code == 200:
        return response.json()['choices'][0]['message']['content']
    return f"ERROR: {response.status_code} - {response.text[:200]}"

# Clear output file
with open(output_file, 'w') as f:
    f.write("DATA CLEANING STEPS EXTRACTION\n")
    f.write("=" * 60 + "\n\n")

log(f"Processing {len(DATA_CLEANING_FILES)} data cleaning conversations...\n")

for i, filename in enumerate(DATA_CLEANING_FILES, 1):
    filepath = convos_dir / filename

    log(f"\n{'='*60}")
    log(f"[{i}/{len(DATA_CLEANING_FILES)}] {filename}")
    log('='*60)

    if not filepath.exists():
        log(f"  SKIP: file not found")
        continue

    log("  Extracting conversation...")
    convo = extract_conversation(filepath)

    if not convo:
        log("  SKIP: no content")
        continue

    log(f"  Found {len(convo)} messages")

    convo_text = "\n".join(convo)[:15000]
    log(f"  Sending {len(convo_text)} chars to OpenAI...")

    steps = get_detailed_steps(convo_text)
    log("\nSTEPS EXTRACTED:")
    log(steps)
    log("\n")

log("\n" + "="*60)
log("DONE!")
log(f"Results saved to: {output_file}")
