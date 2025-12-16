#!/usr/bin/env python3
"""
API Data Validator - Research potential data issues using multiple APIs
Saves results incrementally to CSV

Usage:
  python3 scripts/api_data_validator.py --test-apis     # Test API connections
  python3 scripts/api_data_validator.py --validate      # Run validation
  python3 scripts/api_data_validator.py --validate --limit 10  # Test with 10 records
"""

import os
import sys
import csv
import json
import time
import argparse
import requests
from datetime import datetime

# API Keys - load from environment variables
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY", "")

# File paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
INPUT_CSV = os.path.join(PROJECT_DIR, "data/source/potential_issues.csv")
OUTPUT_CSV = os.path.join(PROJECT_DIR, "data/source/api_validation_results.csv")


def search_serpapi(query):
    """Search Google via SerpAPI"""
    try:
        url = "https://serpapi.com/search"
        params = {
            "q": query,
            "api_key": SERPAPI_KEY,
            "num": 5
        }
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            results = []
            for item in data.get("organic_results", [])[:3]:
                results.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "link": item.get("link", "")
                })
            return results
        return None
    except Exception as e:
        print(f"    SerpAPI error: {e}")
        return None


def search_google_places(query, location=None):
    """Search Google Places API"""
    try:
        url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
        params = {
            "input": query,
            "inputtype": "textquery",
            "fields": "name,formatted_address,types,business_status",
            "key": GOOGLE_KEY
        }
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("candidates"):
                return data["candidates"][0]
        return None
    except Exception as e:
        print(f"    Google Places error: {e}")
        return None


def analyze_with_openai(issue, search_results, places_result):
    """Use OpenAI to analyze results and make recommendation"""
    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_KEY)

        prompt = f"""Analyze this potential data issue and recommend action:

ISSUE TYPE: {issue.get('issue_type')}
BUILDING ID: {issue.get('id_building')}
PROPERTY NAME: {issue.get('property_name')}
ADDRESS: {issue.get('address')}
CURRENT VALUE: {issue.get('current_value')}
EXPECTED: {issue.get('expected')}
ORG: {issue.get('org')}

GOOGLE SEARCH RESULTS:
{json.dumps(search_results, indent=2) if search_results else 'None'}

GOOGLE PLACES RESULT:
{json.dumps(places_result, indent=2) if places_result else 'None'}

Based on the search results, provide a JSON response with:
1. "is_issue": true/false - Is this actually a data issue that needs fixing?
2. "recommendation": Brief recommendation (FIX, KEEP, DELETE, or INVESTIGATE)
3. "correct_value": If FIX, what should the correct value be?
4. "confidence": HIGH, MEDIUM, or LOW
5. "reasoning": One sentence explanation

Respond ONLY with valid JSON, no markdown."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )

        result_text = response.choices[0].message.content.strip()
        # Try to parse JSON
        try:
            return json.loads(result_text)
        except:
            return {"recommendation": "INVESTIGATE", "reasoning": result_text, "confidence": "LOW"}

    except Exception as e:
        print(f"    OpenAI error: {e}")
        return {"recommendation": "ERROR", "reasoning": str(e), "confidence": "LOW"}


def process_issue(issue, row_num, total):
    """Process a single issue"""
    print(f"\n[{row_num}/{total}] {issue.get('id_building')}: {issue.get('issue_type')}")

    # Build search query
    prop_name = issue.get('property_name', '')
    address = issue.get('address', '')
    org = issue.get('org', '')

    if prop_name and str(prop_name) != 'nan':
        query = f"{prop_name} {address}"
    else:
        query = f"{org} {address}"

    print(f"  Searching: {query[:60]}...")

    # Search APIs
    search_results = search_serpapi(query)
    time.sleep(0.5)  # Rate limit

    places_result = search_google_places(query)
    time.sleep(0.3)

    # Analyze with OpenAI
    analysis = analyze_with_openai(issue, search_results, places_result)

    # Build result
    result = {
        'id_building': issue.get('id_building'),
        'issue_type': issue.get('issue_type'),
        'property_name': prop_name,
        'address': address,
        'current_value': issue.get('current_value'),
        'expected': issue.get('expected'),
        'org': org,
        'recommendation': analysis.get('recommendation', 'UNKNOWN'),
        'correct_value': analysis.get('correct_value', ''),
        'confidence': analysis.get('confidence', 'LOW'),
        'reasoning': analysis.get('reasoning', ''),
        'is_issue': analysis.get('is_issue', None),
        'search_snippet': search_results[0].get('snippet', '')[:200] if search_results else '',
        'places_name': places_result.get('name', '') if places_result else '',
        'places_types': ','.join(places_result.get('types', [])) if places_result else '',
        'timestamp': datetime.now().isoformat()
    }

    print(f"  Result: {result['recommendation']} ({result['confidence']}) - {result['reasoning'][:60]}...")

    return result


def save_result(result, is_first=False):
    """Save a single result to CSV (incremental)"""
    mode = 'w' if is_first else 'a'
    with open(OUTPUT_CSV, mode, newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=result.keys())
        if is_first:
            writer.writeheader()
        writer.writerow(result)


def run_validation(limit=None):
    """Run validation on all issues"""
    import pandas as pd

    print(f"\nLoading issues from {INPUT_CSV}...")
    issues_df = pd.read_csv(INPUT_CSV)
    total = len(issues_df) if limit is None else min(limit, len(issues_df))

    print(f"Processing {total} issues...")
    print(f"Results will be saved to {OUTPUT_CSV}")

    for i, (_, issue) in enumerate(issues_df.head(total).iterrows()):
        try:
            result = process_issue(issue.to_dict(), i+1, total)
            save_result(result, is_first=(i==0))
        except KeyboardInterrupt:
            print("\n\nInterrupted! Results saved so far.")
            break
        except Exception as e:
            print(f"  ERROR: {e}")
            # Save error result
            error_result = {
                'id_building': issue.get('id_building'),
                'issue_type': issue.get('issue_type'),
                'recommendation': 'ERROR',
                'reasoning': str(e),
                'timestamp': datetime.now().isoformat()
            }
            save_result(error_result, is_first=(i==0))

    print(f"\n\nDone! Results saved to {OUTPUT_CSV}")


def test_apis():
    """Test all API connections"""
    print("\n=== TESTING API CONNECTIONS ===\n")

    # Test SerpAPI
    try:
        result = search_serpapi("Empire State Building NYC")
        if result:
            print(f"  SerpAPI: OK - Found {len(result)} results")
        else:
            print("  SerpAPI: FAILED")
    except Exception as e:
        print(f"  SerpAPI: FAILED - {e}")

    # Test Google Places
    try:
        result = search_google_places("Empire State Building")
        if result:
            print(f"  Google Places: OK - {result.get('name', 'Unknown')}")
        else:
            print("  Google Places: FAILED")
    except Exception as e:
        print(f"  Google Places: FAILED - {e}")

    # Test OpenAI
    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=20,
            messages=[{"role": "user", "content": "Say OK"}]
        )
        print(f"  OpenAI: OK - {response.choices[0].message.content.strip()}")
    except Exception as e:
        print(f"  OpenAI: FAILED - {e}")

    # Test Anthropic
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=20,
            messages=[{"role": "user", "content": "Say OK"}]
        )
        print(f"  Anthropic: OK - {response.content[0].text.strip()}")
    except Exception as e:
        print(f"  Anthropic: FAILED - {e}")


def main():
    parser = argparse.ArgumentParser(description="API Data Validator")
    parser.add_argument("--test-apis", action="store_true", help="Test API connections")
    parser.add_argument("--validate", action="store_true", help="Run validation")
    parser.add_argument("--limit", type=int, help="Limit number of records to process")

    args = parser.parse_args()

    if args.test_apis:
        test_apis()
    elif args.validate:
        run_validation(limit=args.limit)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
