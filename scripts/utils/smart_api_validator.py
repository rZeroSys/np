#!/usr/bin/env python3
"""
Smart API Validator - Research issues using APIs
Saves results incrementally, can resume if interrupted

Run: python3 smart_api_validator.py
     python3 smart_api_validator.py --limit 100  # Test with 100 issues
"""

import pandas as pd
import requests
import json
import csv
import os
import time
import argparse
import re
import subprocess
import signal
import atexit
from datetime import datetime
from urllib.parse import urlparse

# Caffeinate process to prevent Mac sleep
caffeinate_proc = None

def start_caffeinate():
    global caffeinate_proc
    caffeinate_proc = subprocess.Popen(['caffeinate', '-dims'])
    print("[CAFFEINATE] Mac will not sleep during run")

def stop_caffeinate():
    global caffeinate_proc
    if caffeinate_proc:
        caffeinate_proc.terminate()
        print("[CAFFEINATE] Stopped")

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = '/Users/forrestmiller/Desktop/nationwide-prospector'

INPUT_QUEUE = f'{SCRIPT_DIR}/research_queue.csv'
OUTPUT_RESULTS = f'{SCRIPT_DIR}/research_results.csv'
PROGRESS_FILE = f'{SCRIPT_DIR}/validate_progress.txt'
PORTFOLIO_ORGS = f'{PROJECT_DIR}/data/source/portfolio_organizations.csv'
PORTFOLIO_DATA = f'{PROJECT_DIR}/data/source/portfolio_data.csv'

# API Keys
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY", "")

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {msg}")

def calculate_priority_score(row):
    """Calculate smart priority score based on value, sqft, issue type, and likelihood of success"""
    score = 0

    # Factor 1: Building value (0-50 points)
    val = row.get('val_current_usd', 0) or 0
    if val > 500e6:
        score += 50
    elif val > 100e6:
        score += 40
    elif val > 50e6:
        score += 30
    elif val > 10e6:
        score += 20
    elif val > 1e6:
        score += 10

    # Factor 2: Building size (0-30 points)
    sqft = row.get('bldg_sqft', 0) or 0
    if sqft > 1000000:
        score += 30
    elif sqft > 500000:
        score += 25
    elif sqft > 200000:
        score += 20
    elif sqft > 100000:
        score += 15
    elif sqft > 50000:
        score += 10

    # Factor 3: Issue type - BASED ON ACTUAL SUCCESS RATES
    # SHELL_COMPANY: 0% LOW confidence (best!)
    # ORPHAN: 0% LOW confidence (best!)
    # LARGE_NO_TENANT: 23% LOW confidence (good)
    # NON_CANONICAL_ORG: 50% LOW confidence (deprioritize)
    # OLD_DATA: harder to find (deprioritize)
    issue_type = row.get('issue_type', '')
    if issue_type == 'SHELL_COMPANY':
        score += 25  # 0% LOW - highest priority!
    elif issue_type == 'ORPHAN':
        score += 22  # 0% LOW - very reliable
    elif issue_type == 'LARGE_NO_TENANT':
        score += 18  # 23% LOW - still good
    elif issue_type == 'NON_CANONICAL_ORG':
        score += 5   # 50% LOW - deprioritize significantly
    elif issue_type == 'OLD_DATA':
        score += 3   # Historical, hardest to research

    # Factor 4: Building type - based on research success
    bldg_type = str(row.get('bldg_type', '')).lower()
    if 'office' in bldg_type:
        score += 12  # Office tenants well documented
    elif 'hotel' in bldg_type:
        score += 10  # Hotel brands/owners easy to find
    elif 'mall' in bldg_type or 'enclosed' in bldg_type:
        score += 10  # Malls have public tenant lists
    elif 'medical' in bldg_type or 'hospital' in bldg_type:
        score += 9   # Healthcare well documented
    elif 'higher ed' in bldg_type or 'university' in bldg_type:
        score += 8   # Universities are public
    elif 'retail' in bldg_type or 'supermarket' in bldg_type:
        score += 6   # Retail varies
    elif 'residential care' in bldg_type:
        score -= 5   # Nursing homes - hard to research
    elif 'k-12' in bldg_type or 'school' in bldg_type:
        score -= 3   # Schools - usually govt, known
    elif 'library' in bldg_type or 'museum' in bldg_type:
        score -= 3   # Usually govt owned
    elif 'theater' in bldg_type or 'venue' in bldg_type:
        score -= 2   # Entertainment venues harder

    # Factor 5: CRITICAL - Property name availability (big impact on search success)
    # 68% of queue missing names, but named buildings search much better
    prop_name = row.get('property_name')
    if prop_name and pd.notna(prop_name) and str(prop_name).strip():
        score += 15  # Has name - much easier to search!
    else:
        score -= 10  # No name - harder to search, deprioritize

    # Factor 6: Data recency - newer data more likely accurate
    data_year = row.get('data_year', 2020)
    if pd.notna(data_year):
        if data_year >= 2023:
            score += 5
        elif data_year >= 2020:
            score += 2
        elif data_year < 2016:
            score -= 5  # Very old data

    return max(score, 1)  # Minimum score of 1

def enrich_queue_with_portfolio(queue_df, portfolio_df):
    """Merge queue with portfolio data for extra context and smart prioritization"""
    # Select useful columns from portfolio
    context_cols = ['id_building', 'bldg_sqft', 'bldg_type', 'bldg_vertical', 'bldg_year_built',
                    'val_current_usd', 'energy_star_score', 'leed_certification_level', 'loc_zip']

    # Only include columns that exist
    available_cols = [c for c in context_cols if c in portfolio_df.columns]

    # Merge - left join to keep all queue items
    enriched = queue_df.merge(
        portfolio_df[available_cols],
        on='id_building',
        how='left',
        suffixes=('', '_pf')
    )

    # Calculate priority score
    enriched['priority_score'] = enriched.apply(calculate_priority_score, axis=1)

    # Sort by priority score descending (highest value/sqft first)
    enriched = enriched.sort_values('priority_score', ascending=False).reset_index(drop=True)

    return enriched

def save_progress(idx):
    with open(PROGRESS_FILE, 'w') as f:
        f.write(str(idx))

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return int(f.read().strip())
    return 0

def build_canonical_lookup(orgs_df):
    """Build alias -> canonical name lookup"""
    # Skip city/location names that cause false matches
    skip_words = {'atlanta', 'chicago', 'boston', 'new york', 'los angeles', 'washington',
                  'seattle', 'denver', 'portland', 'san francisco', 'miami', 'dallas',
                  'district', 'federal', 'the', 'city', 'metro', 'capital', 'state',
                  'american', 'national', 'university', 'center', 'building'}
    lookup = {}
    for _, org in orgs_df.iterrows():
        name = org['organization']
        name_lower = name.lower()
        if name_lower not in skip_words and len(name) > 5:
            lookup[name_lower] = name
        aliases = str(org.get('search_aliases', '')).split('|')
        for a in aliases:
            a = a.strip().lower()
            if a and len(a) > 5 and a not in skip_words:
                lookup[a] = name
    return lookup

def match_canonical(text, lookup):
    """Find canonical org in text"""
    text_lower = text.lower()
    for alias, canonical in sorted(lookup.items(), key=lambda x: -len(x[0])):
        if len(alias) > 4 and re.search(r'\b' + re.escape(alias) + r'\b', text_lower):
            return canonical
    return None

def extract_domain(url):
    """Extract domain from URL for source quality scoring"""
    try:
        return urlparse(url).netloc.replace('www.', '')
    except:
        return ''

def score_source_quality(domain):
    """Score domain reliability 1-10"""
    tier1 = ['sec.gov', 'edgar', 'bloomberg.com', 'wsj.com', 'nytimes.com', 'reuters.com',
             'businesswire.com', 'prnewswire.com', 'globenewswire.com']
    tier2 = ['costar.com', 'loopnet.com', 'commercialcafe.com', 'bizjournals.com',
             'commercialobserver.com', 'therealdeal.com', 'bisnow.com']
    tier3 = ['linkedin.com', 'dnb.com', 'zoominfo.com', 'crunchbase.com', 'glassdoor.com',
             'wikipedia.org', 'forbes.com']

    domain_lower = domain.lower()
    if any(t in domain_lower for t in tier1) or '.gov' in domain_lower:
        return 10
    elif any(t in domain_lower for t in tier2):
        return 7
    elif any(t in domain_lower for t in tier3):
        return 5
    else:
        return 3

def build_search_queries(issue):
    """Generate multiple search queries based on issue type"""
    issue_type = issue['issue_type']
    prop = str(issue.get('property_name', '') or '').strip()
    addr = str(issue.get('address', '') or '').strip()
    city = str(issue.get('city', '') or '').strip()
    owner = str(issue.get('current_owner', '') or '').strip()
    tenant = str(issue.get('current_tenant', '') or '').strip()

    queries = []

    if issue_type == 'SHELL_COMPANY':
        queries = [
            f'"{owner}" real estate investor parent company',
            f'"{owner}" acquired by bought merger subsidiary',
            f'"{prop}" {city} building owner REIT investment trust' if prop else f'{addr} {city} building owner'
        ]
    elif issue_type == 'LARGE_NO_TENANT':
        queries = [
            f'"{prop}" {city} major tenants list occupants' if prop else f'{addr} {city} tenants',
            f'"{prop}" {city} office space lease companies' if prop else f'{addr} {city} office tenants',
            f'{addr} {city} headquarters tenants businesses'
        ]
    elif issue_type == 'ORPHAN':
        base = f'"{prop}"' if prop else addr
        queries = [
            f'{base} {city} owner building',
            f'{addr} {city} property records owner deed',
            f'{base} {city} sold purchased acquired'
        ]
    elif issue_type == 'NON_CANONICAL_ORG':
        org = owner or tenant
        queries = [
            f'"{org}" company headquarters official',
            f'"{org}" official website about company'
        ]
    elif issue_type == 'OLD_DATA':
        queries = [
            f'"{prop}" {city} sold acquired owner 2020 2021 2022 2023 2024' if prop else f'{addr} {city} sold owner',
            f'"{prop}" {city} new owner recent transaction sale' if prop else f'{addr} {city} new owner'
        ]
    else:
        # Default fallback
        queries = [issue.get('research_query', f'{prop} {city} owner')]

    # Filter out empty queries and limit to 3
    return [q for q in queries if q.strip()][:3]

def search_serpapi(query):
    """Google search via SerpAPI - returns structured results with URLs"""
    try:
        r = requests.get("https://serpapi.com/search",
            params={"q": query, "api_key": SERPAPI_KEY, "num": 10}, timeout=30)
        if r.status_code == 200:
            data = r.json()
            results = data.get("organic_results", [])
            # Return list of dicts with text, URL, domain, and quality score
            structured = []
            for res in results[:10]:
                url = res.get('link', '')
                domain = extract_domain(url)
                structured.append({
                    'text': (res.get('snippet', '') + ' ' + res.get('title', '')).strip(),
                    'url': url,
                    'domain': domain,
                    'quality': score_source_quality(domain)
                })
            return structured
        return []
    except Exception as e:
        log(f"    SerpAPI error: {e}")
        return []

def search_serpapi_with_retry(query, max_retries=3):
    """Search with exponential backoff retry"""
    for attempt in range(max_retries):
        result = search_serpapi(query)
        if result:
            return result
        if attempt < max_retries - 1:
            wait_time = 2 ** attempt  # 1, 2, 4 seconds
            log(f"    Retry {attempt + 1}/{max_retries} in {wait_time}s...")
            time.sleep(wait_time)
    return []

def search_places(query):
    """Google Places search"""
    try:
        r = requests.get("https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
            params={"input": query, "inputtype": "textquery",
                    "fields": "name,formatted_address,types", "key": GOOGLE_KEY}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get("candidates"):
                c = data["candidates"][0]
                return f"{c.get('name', '')} | {','.join(c.get('types', []))}"
        return None
    except Exception as e:
        log(f"    Places error: {e}")
        return None

def verify_finding(finding_type, found_value, building_info):
    """Verify a finding with an independent search"""
    if not found_value or found_value == 'null':
        return False, 0

    prop = building_info.get('property_name', '')
    city = building_info.get('city', '')

    # Build verification query based on what we found
    if finding_type == 'owner':
        query = f'"{found_value}" owns "{prop}" {city}' if prop else f'"{found_value}" real estate owner'
    elif finding_type == 'tenant':
        query = f'"{found_value}" {city} office location headquarters'
    else:
        query = f'"{found_value}" real estate company'

    results = search_serpapi(query)
    if not results:
        return False, 0

    # Check if the found value appears in verification results
    found_value_lower = found_value.lower()

    # Count corroborating sources
    corroborating = sum(1 for r in results if found_value_lower in r['text'].lower())

    return corroborating >= 2, corroborating

def compute_confidence(sources, verification_passed, verification_count, gpt_confidence):
    """Compute confidence score from multiple factors"""
    score = 0

    # Factor 1: Number of sources with results
    source_count = len(sources)
    if source_count >= 15:
        score += 3
    elif source_count >= 8:
        score += 2
    elif source_count >= 3:
        score += 1

    # Factor 2: Source quality average
    if sources:
        avg_quality = sum(s.get('quality', 3) for s in sources) / len(sources)
        if avg_quality >= 7:
            score += 3
        elif avg_quality >= 5:
            score += 2
        elif avg_quality >= 3:
            score += 1

    # Factor 3: Verification
    if verification_passed:
        score += 2
    elif verification_count >= 1:
        score += 1

    # Factor 4: GPT confidence
    gpt_conf = str(gpt_confidence).upper()
    if gpt_conf == 'HIGH':
        score += 2
    elif gpt_conf == 'MEDIUM':
        score += 1

    # Convert to HIGH/MEDIUM/LOW
    if score >= 8:
        return 'HIGH'
    elif score >= 5:
        return 'MEDIUM'
    else:
        return 'LOW'

def parse_gpt_json(gpt_result):
    """Parse GPT JSON response with error handling"""
    if not gpt_result:
        return {}

    gpt_clean = gpt_result.replace('```json', '').replace('```', '').strip()
    # Find JSON object in text
    start = gpt_clean.find('{')
    end = gpt_clean.rfind('}') + 1
    if start >= 0 and end > start:
        gpt_clean = gpt_clean[start:end]
    return json.loads(gpt_clean)

def analyze_with_gpt(issue_type, building_info, search_text, issue=None):
    """Use GPT to analyze search results with chain-of-thought reasoning"""
    import openai
    client = openai.OpenAI(api_key=OPENAI_KEY)

    # Get additional context from issue if available
    current_owner = issue.get('current_owner', '') if issue else ''
    current_tenant = issue.get('current_tenant', '') if issue else ''

    # Build rich context string with all available building data
    context_parts = [building_info]

    if issue:
        sqft = issue.get('bldg_sqft')
        if sqft and pd.notna(sqft):
            context_parts.append(f"Size: {int(sqft):,} sqft")

        bldg_type = issue.get('bldg_type')
        if bldg_type and pd.notna(bldg_type):
            context_parts.append(f"Type: {bldg_type}")

        vertical = issue.get('bldg_vertical')
        if vertical and pd.notna(vertical):
            context_parts.append(f"Sector: {vertical}")

        year_built = issue.get('bldg_year_built')
        if year_built and pd.notna(year_built):
            context_parts.append(f"Built: {int(year_built)}")

        val = issue.get('val_current_usd')
        if val and pd.notna(val) and val > 0:
            context_parts.append(f"Value: ${val/1e6:.1f}M")

        leed = issue.get('leed_certification_level')
        if leed and pd.notna(leed):
            context_parts.append(f"LEED: {leed}")

        zipcode = issue.get('loc_zip')
        if zipcode and pd.notna(zipcode):
            context_parts.append(f"ZIP: {zipcode}")

    building_context = " | ".join(context_parts)

    prompts = {
        'OLD_DATA': f"""Analyze if this building has been SOLD or changed ownership since the data was recorded.

TASK: Determine if ownership has changed and identify the new owner if applicable.

Building: {building_context}

SEARCH RESULTS:
{search_text[:2500]}

REASONING STEPS:
1. Look for any mentions of "sold", "acquired", "purchased", "transferred" related to this property
2. Identify any dates of ownership changes (especially 2020-2024)
3. Find the new owner's name if a sale occurred
4. Assess how confident you are based on the evidence quality

Return JSON: {{
  "reasoning": "brief explanation of your analysis",
  "sold": true/false,
  "new_owner": "company name or null",
  "year_sold": year or null,
  "confidence": "HIGH/MEDIUM/LOW"
}}""",

        'SHELL_COMPANY': f"""Analyze this shell company to find the REAL OWNER behind it.

TASK: Identify who actually owns/controls this LLC/LP/Trust entity.
Look for: parent companies, REITs, investment firms, private equity firms, family trusts, institutional investors.

Building: {building_context}
Current Owner Listed: {current_owner}

SEARCH RESULTS:
{search_text[:2500]}

REASONING STEPS:
1. What type of entity is the current owner (LLC, LP, Trust, Holdings, etc.)?
2. Is there a parent company, REIT, or investment firm mentioned in connection with this entity?
3. Are there any merger/acquisition/subsidiary references?
4. Is this a single-purpose entity created for this specific property?
5. What is your confidence level based on evidence quality?

Return JSON: {{
  "reasoning": "brief explanation of how you determined the real owner",
  "real_owner": "company name or null",
  "parent_company": "name or null",
  "entity_type": "REIT/Private Equity/Family Trust/Institutional/Corp/Unknown",
  "confidence": "HIGH/MEDIUM/LOW"
}}""",

        'LARGE_NO_TENANT': f"""Identify the major TENANTS occupying this building.

TASK: Find actual business tenants (not property managers or the building name itself).

Building: {building_context}

CRITICAL RULES:
- DO NOT return the building name itself as a tenant
- DO NOT return property managers as tenants: CBRE, Cushman & Wakefield, JLL, Newmark, Colliers, Savills, Marcus & Millichap
- ONLY return actual business tenants: law firms, banks, tech companies, insurance, accounting firms, corporate headquarters, retailers, etc.
- If you see a "tenant list" or "occupants", extract the company names

SEARCH RESULTS:
{search_text[:2500]}

REASONING STEPS:
1. Look for phrases like "tenants include", "occupied by", "leased to", "headquarters at"
2. Identify actual business names (not property management companies)
3. Determine the largest/anchor tenant if multiple are found
4. Note if a property manager is mentioned separately
5. Check if the building has a different/correct name than listed

Return JSON: {{
  "reasoning": "brief explanation of tenant findings",
  "tenants": ["company1", "company2", "company3"],
  "largest_tenant": "name or null",
  "property_manager": "name or null",
  "correct_property_name": "real name if current is wrong/missing, else null",
  "confidence": "HIGH/MEDIUM/LOW"
}}""",

        'ORPHAN': f"""Identify the OWNER of this building that currently has no ownership records.

TASK: Find who owns this building (and optionally major tenants).

Building: {building_context}

SEARCH RESULTS:
{search_text[:2500]}

REASONING STEPS:
1. Look for ownership indicators: "owned by", "property of", "belongs to", "developed by"
2. Check for institutional owners: universities, hospitals, government, REITs
3. Look for any tenant information that could help identify the building
4. Consider if this could be a campus building (university/hospital/corporate)
5. Assess confidence based on how directly the ownership is stated

Return JSON: {{
  "reasoning": "brief explanation of ownership finding",
  "owner": "company name or null",
  "owner_type": "University/Hospital/Government/REIT/Private/Corp/Unknown",
  "tenant": "name or null",
  "confidence": "HIGH/MEDIUM/LOW"
}}""",

        'NON_CANONICAL_ORG': f"""Verify if this is a real company and determine its official/canonical name.

TASK: Confirm the organization exists and find its proper official name.

Organization to verify: {current_owner or current_tenant}
Building: {building_context}

SEARCH RESULTS:
{search_text[:2500]}

REASONING STEPS:
1. Is this a real company with a website, news mentions, or business presence?
2. What is the official/legal name (check for Inc, LLC, Corp suffixes)?
3. Is this a subsidiary of a larger company?
4. Could this be a misspelling or variant of a known company?
5. Assess confidence based on evidence quality

Return JSON: {{
  "reasoning": "brief explanation of verification",
  "official_name": "canonical company name",
  "is_real_company": true/false,
  "parent_company": "if any or null",
  "confidence": "HIGH/MEDIUM/LOW"
}}"""
    }

    prompt = prompts.get(issue_type, prompts['ORPHAN'])

    try:
        response = client.chat.completions.create(
            model="gpt-4o", max_tokens=500,
            messages=[{"role": "user", "content": prompt}])
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f'{{"error": "{str(e)}"}}'

def get_result_fieldnames():
    return [
        # Original columns (for backward compatibility)
        'id_building', 'issue_type', 'priority',
        'property_name', 'address', 'city',
        'current_owner', 'current_tenant', 'current_manager',
        'search_query', 'search_snippet', 'places_result',
        'gpt_analysis', 'found_owner', 'found_tenant', 'found_manager',
        'correct_property_name', 'canonical_match',
        'recommendation', 'confidence', 'timestamp',
        # NEW columns for enhanced tracking
        'source_urls',           # Pipe-delimited list of source URLs
        'source_count',          # Number of sources searched
        'avg_source_quality',    # Average source quality score (1-10)
        'gpt_reasoning',         # GPT's reasoning explanation
        'verified',              # True/False - did verification pass
        'verification_sources',  # Number of corroborating sources
        'computed_confidence',   # Confidence computed from factors
        'queries_used',          # Number of queries executed
        'processing_time_sec'    # Time taken to process this issue
    ]

def append_result(result, is_first=False):
    mode = 'w' if is_first else 'a'
    with open(OUTPUT_RESULTS, mode, newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=get_result_fieldnames())
        if is_first:
            writer.writeheader()
        writer.writerow(result)

def process_issue(issue, canonical_lookup):
    """Process a single issue with enhanced accuracy using multi-query search and verification"""
    start_time = time.time()
    issue_type = issue['issue_type']
    building_info = {
        'property_name': str(issue.get('property_name', '') or ''),
        'address': str(issue.get('address', '') or ''),
        'city': str(issue.get('city', '') or ''),
        'current_owner': str(issue.get('current_owner', '') or '')
    }
    building_info_str = f"{building_info['property_name']} at {building_info['address']}, {building_info['city']}"

    # Step 1: Multi-query search
    queries = build_search_queries(issue)
    all_results = []
    all_urls = []

    for query in queries:
        results = search_serpapi_with_retry(query)
        for r in results:
            all_results.append(r)
            if r.get('url'):
                all_urls.append(r['url'])
        time.sleep(0.5)

    # Step 2: Prepare search text for GPT (combine all results)
    search_text = ' '.join([r.get('text', '') for r in all_results])

    # Skip Places search - was returning bad results
    places_result = None

    # Step 3: GPT analysis with improved prompts
    gpt_result = ""
    if search_text:
        gpt_result = analyze_with_gpt(issue_type, building_info_str, search_text, issue)
        time.sleep(0.5)

    # Step 4: Parse GPT result with proper error handling
    found_owner = None
    found_tenant = None
    found_manager = None
    correct_property_name = None
    gpt_confidence = "LOW"
    gpt_reasoning = ""
    recommendation = "INVESTIGATE"

    try:
        gpt_data = parse_gpt_json(gpt_result)
        gpt_confidence = gpt_data.get('confidence', 'LOW')
        gpt_reasoning = gpt_data.get('reasoning', '')

        if issue_type == 'OLD_DATA':
            if gpt_data.get('sold'):
                found_owner = gpt_data.get('new_owner')
                recommendation = 'UPDATE_OWNER' if found_owner else 'INVESTIGATE'
            else:
                recommendation = 'KEEP'

        elif issue_type == 'SHELL_COMPANY':
            found_owner = gpt_data.get('real_owner') or gpt_data.get('parent_company')
            recommendation = 'UPDATE_OWNER' if found_owner else 'INVESTIGATE'

        elif issue_type == 'LARGE_NO_TENANT':
            # Handle "null" string as None
            largest = gpt_data.get('largest_tenant')
            found_tenant = largest if largest and largest != 'null' else None

            # If no largest but we have a tenants list, use first one
            if not found_tenant:
                tenants_list = gpt_data.get('tenants', [])
                if tenants_list and len(tenants_list) > 0:
                    # Filter out null/None values
                    valid_tenants = [t for t in tenants_list if t and t != 'null']
                    if valid_tenants:
                        found_tenant = valid_tenants[0]

            mgr = gpt_data.get('property_manager')
            found_manager = mgr if mgr and mgr != 'null' else None
            cpn = gpt_data.get('correct_property_name')
            correct_property_name = cpn if cpn and cpn != 'null' else None
            recommendation = 'ADD_TENANT' if found_tenant else 'INVESTIGATE'

        elif issue_type == 'ORPHAN':
            owner = gpt_data.get('owner')
            found_owner = owner if owner and owner != 'null' else None
            tenant = gpt_data.get('tenant')
            found_tenant = tenant if tenant and tenant != 'null' else None
            recommendation = 'ADD_OWNER' if found_owner else 'INVESTIGATE'

        elif issue_type == 'NON_CANONICAL_ORG':
            official = gpt_data.get('official_name')
            found_owner = official if official and official != 'null' else None
            recommendation = 'NORMALIZE' if found_owner else 'ADD_TO_ORGS'

    except json.JSONDecodeError as e:
        log(f"    JSON parse error: {e}")
        log(f"    Raw GPT response: {gpt_result[:200]}")
    except KeyError as e:
        log(f"    Missing key in GPT response: {e}")
    except Exception as e:
        log(f"    Unexpected error: {type(e).__name__}: {e}")

    # Step 5: Verification step
    verified = False
    verification_count = 0
    if found_owner or found_tenant:
        finding_type = 'owner' if found_owner else 'tenant'
        finding_value = found_owner or found_tenant
        verified, verification_count = verify_finding(finding_type, finding_value, building_info)
        time.sleep(0.3)

    # Step 6: Compute confidence from multiple factors
    computed_confidence = compute_confidence(all_results, verified, verification_count, gpt_confidence)

    # Step 7: Canonical matching (try search text first, then found values)
    canonical_match = None
    if search_text:
        canonical_match = match_canonical(search_text, canonical_lookup)
    if not canonical_match and found_owner:
        canonical_match = match_canonical(found_owner, canonical_lookup)
    if not canonical_match and found_tenant:
        canonical_match = match_canonical(found_tenant, canonical_lookup)

    # Calculate processing time and source quality
    processing_time = time.time() - start_time
    avg_quality = sum(r.get('quality', 3) for r in all_results) / len(all_results) if all_results else 0

    # Build search snippet from first query results for backward compatibility
    first_query = queries[0] if queries else issue.get('research_query', '')
    search_snippet = ' '.join([r.get('text', '') for r in all_results[:4]])[:300]

    return {
        # Original columns
        'id_building': issue['id_building'],
        'issue_type': issue_type,
        'priority': issue['priority'],
        'property_name': issue.get('property_name', ''),
        'address': issue.get('address', ''),
        'city': issue.get('city', ''),
        'current_owner': issue.get('current_owner', ''),
        'current_tenant': issue.get('current_tenant', ''),
        'current_manager': issue.get('current_manager', ''),
        'search_query': first_query[:200],
        'search_snippet': search_snippet,
        'places_result': places_result or '',
        'gpt_analysis': gpt_result[:500],
        'found_owner': found_owner or '',
        'found_tenant': found_tenant or '',
        'found_manager': found_manager or '',
        'correct_property_name': correct_property_name or '',
        'canonical_match': canonical_match or '',
        'recommendation': recommendation,
        'confidence': gpt_confidence,
        'timestamp': datetime.now().isoformat(),
        # NEW columns
        'source_urls': '|'.join(all_urls[:10]),
        'source_count': len(all_results),
        'avg_source_quality': round(avg_quality, 2),
        'gpt_reasoning': (gpt_reasoning or '')[:200],
        'verified': str(verified),
        'verification_sources': verification_count,
        'computed_confidence': computed_confidence,
        'queries_used': len(queries),
        'processing_time_sec': round(processing_time, 1)
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, help='Limit number of issues to process')
    parser.add_argument('--fresh', action='store_true', help='Start fresh, ignore progress')
    args = parser.parse_args()

    # Start caffeinate and register cleanup
    start_caffeinate()
    atexit.register(stop_caffeinate)

    log("=" * 60)
    log("SMART API VALIDATOR")
    log("=" * 60)

    # Check input exists
    if not os.path.exists(INPUT_QUEUE):
        log(f"ERROR: {INPUT_QUEUE} not found!")
        log("Run generate_research_queue.py first")
        return

    # Load queue
    log(f"Loading research queue from {INPUT_QUEUE}...")
    queue_df = pd.read_csv(INPUT_QUEUE)
    log(f"  {len(queue_df):,} issues to research")

    # Load portfolio data for context and smart prioritization
    log(f"Loading portfolio data for context...")
    portfolio_df = pd.read_csv(PORTFOLIO_DATA, low_memory=False)
    log(f"  {len(portfolio_df):,} buildings loaded")

    # Enrich queue with portfolio data and sort by priority
    log(f"Smart prioritization by value/sqft...")
    queue_df = enrich_queue_with_portfolio(queue_df, portfolio_df)
    top_score = queue_df['priority_score'].max()
    log(f"  Priority scores: {queue_df['priority_score'].min():.0f} - {top_score:.0f}")
    log(f"  Top building: {queue_df.iloc[0]['property_name'] or queue_df.iloc[0]['address']}")
    if queue_df.iloc[0].get('val_current_usd'):
        log(f"    Value: ${queue_df.iloc[0]['val_current_usd']/1e6:.1f}M")

    total = len(queue_df)
    if args.limit:
        total = min(args.limit, total)
        log(f"  Limited to {total} issues")

    # Load canonical orgs
    log(f"Loading canonical orgs...")
    orgs_df = pd.read_csv(PORTFOLIO_ORGS)
    canonical_lookup = build_canonical_lookup(orgs_df)
    log(f"  {len(canonical_lookup)} aliases loaded")

    # Check progress
    start_idx = 0 if args.fresh else load_progress()
    if start_idx > 0:
        log(f"RESUMING from issue {start_idx}")

    log("")
    log("Processing issues...")
    log("-" * 60)

    stats = {'UPDATE_OWNER': 0, 'ADD_TENANT': 0, 'ADD_OWNER': 0, 'NORMALIZE': 0, 'KEEP': 0, 'INVESTIGATE': 0}
    processed = 0

    for idx, row in queue_df.head(total).iterrows():
        if idx < start_idx:
            continue

        issue = row.to_dict()
        processed += 1

        prop_display = str(issue['property_name'])[:25] if pd.notna(issue['property_name']) else str(issue['address'])[:25]
        priority = issue.get('priority_score', 0)
        val = issue.get('val_current_usd', 0)
        val_str = f" ${val/1e6:.0f}M" if val and val > 0 else ""
        log(f"[{processed}/{total}] P{priority:.0f}{val_str} {issue['issue_type']}: {prop_display}")

        try:
            result = process_issue(issue, canonical_lookup)
            is_first = (processed == 1 and start_idx == 0)
            append_result(result, is_first=is_first)

            rec = result['recommendation']
            stats[rec] = stats.get(rec, 0) + 1

            found_info = result['found_owner'] or result['found_tenant'] or result['found_manager'] or ''
            extra = f" | PropName: {result['correct_property_name']}" if result['correct_property_name'] else ''
            log(f"    -> {rec} ({result['confidence']}) {found_info}{extra}")

        except KeyboardInterrupt:
            log("\n\nINTERRUPTED! Progress saved.")
            save_progress(idx)
            break
        except Exception as e:
            log(f"    ERROR: {e}")

        save_progress(idx + 1)

        # Rate limiting
        if processed % 10 == 0:
            time.sleep(1)

    log("")
    log("=" * 60)
    log("COMPLETE!")
    log("=" * 60)
    log(f"Processed: {processed:,}")
    log("")
    for rec, count in sorted(stats.items(), key=lambda x: -x[1]):
        if count > 0:
            log(f"  {rec}: {count}")
    log("")
    log(f"Results saved to: {OUTPUT_RESULTS}")

if __name__ == "__main__":
    main()
