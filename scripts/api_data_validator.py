#!/usr/bin/env python3
"""
Data Validator - Uses multiple APIs to verify and fix org/building data
Run with: python3 scripts/api_data_validator.py --test-apis
"""

import os
import sys
import csv
import json
import time
import argparse
from datetime import datetime

# API Keys
ANTHROPIC_KEY = "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"
SERPAPI_KEY = "***REMOVED***"
OPENAI_KEY = "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"
GOOGLE_KEY = "AIzaSyA-De5e-LfLN4_mrcgTnufcRjmiX0o1dQY"
YELP_KEY = "T-ehGPV5rpTT6KHJQyGL6Y-RC5sRLJsoK7VEKjUGbWq-XpzohwXKx8F18-D7N1nsIg6qRD2npjrtD8MI4ZgThO9lHAeKBCdxogNeE_I_LYQcxN3deD9em0agfl0UhaXYx"
TRIPADVISOR_KEY = "CE660D5D434F4F0A89852BF0C838BAC1"

OUTPUT_CSV = "data/source/api_validation_results.csv"

def test_anthropic():
    """Test Anthropic API"""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=50,
            messages=[{"role": "user", "content": "Say 'API working' in 2 words"}]
        )
        print(f"  Anthropic: OK - {response.content[0].text.strip()}")
        return True
    except Exception as e:
        print(f"  Anthropic: FAILED - {e}")
        return False

def test_serpapi():
    """Test SerpAPI"""
    try:
        import requests
        url = "https://serpapi.com/search"
        params = {"q": "test", "api_key": SERPAPI_KEY, "num": 1}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            print(f"  SerpAPI: OK")
            return True
        else:
            print(f"  SerpAPI: FAILED - Status {r.status_code}")
            return False
    except Exception as e:
        print(f"  SerpAPI: FAILED - {e}")
        return False

def test_openai():
    """Test OpenAI API"""
    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=20,
            messages=[{"role": "user", "content": "Say OK"}]
        )
        print(f"  OpenAI: OK - {response.choices[0].message.content.strip()}")
        return True
    except Exception as e:
        print(f"  OpenAI: FAILED - {e}")
        return False

def test_google():
    """Test Google Places API"""
    try:
        import requests
        url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
        params = {"input": "Empire State Building", "inputtype": "textquery", "key": GOOGLE_KEY}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data.get("status") in ["OK", "ZERO_RESULTS"]:
            print(f"  Google Places: OK")
            return True
        else:
            print(f"  Google Places: FAILED - {data.get('status')}")
            return False
    except Exception as e:
        print(f"  Google Places: FAILED - {e}")
        return False

def test_yelp():
    """Test Yelp API"""
    try:
        import requests
        url = "https://api.yelp.com/v3/businesses/search"
        headers = {"Authorization": f"Bearer {YELP_KEY}"}
        params = {"term": "restaurant", "location": "NYC", "limit": 1}
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            print(f"  Yelp: OK")
            return True
        else:
            print(f"  Yelp: FAILED - Status {r.status_code}")
            return False
    except Exception as e:
        print(f"  Yelp: FAILED - {e}")
        return False

def test_all_apis():
    """Test all API connections"""
    print("\n=== TESTING API CONNECTIONS ===\n")

    results = {
        "Anthropic": test_anthropic(),
        "SerpAPI": test_serpapi(),
        "OpenAI": test_openai(),
        "Google": test_google(),
        "Yelp": test_yelp(),
    }

    print("\n=== SUMMARY ===")
    working = sum(1 for v in results.values() if v)
    print(f"{working}/{len(results)} APIs working\n")

    return results

def main():
    parser = argparse.ArgumentParser(description="Data Validator using multiple APIs")
    parser.add_argument("--test-apis", action="store_true", help="Test all API connections")
    parser.add_argument("--validate", action="store_true", help="Run validation on data")

    args = parser.parse_args()

    if args.test_apis:
        test_all_apis()
    elif args.validate:
        print("Validation mode not yet implemented")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
