#!/usr/bin/env python3
"""
Org URL Enricher v5 - UNKNOWN URLs FOCUS
- Input: UNKNOWN_urls.csv (496 hard cases)
- 190+ known URLs
- SerpAPI search for all failures
- 100 parallel workers
"""

import re
import time
import os
import concurrent.futures
from threading import Lock
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ======================================================================================
# CONFIG
# ======================================================================================

PORTFOLIO_CSV = "/Users/forrestmiller/Desktop/websites final/UNKNOWN_urls.csv"
FORTUNE_2024 = "/Users/forrestmiller/Desktop/websites/fortune1000_2024.csv"
OUTPUT_CSV = "/Users/forrestmiller/Desktop/websites final/UNKNOWN_urls_FOUND.csv"

# API Keys
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")

MAX_WORKERS = 100
TIMEOUT = 6

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}

# Known URLs - TRUSTED, NO VERIFICATION NEEDED
KNOWN_URLS = {
    # Major retailers
    'marriott': 'https://www.marriott.com',
    'hilton': 'https://www.hilton.com',
    'target': 'https://www.target.com',
    'walmart': 'https://www.walmart.com',
    'costco': 'https://www.costco.com',
    'the home depot': 'https://www.homedepot.com',
    'home depot': 'https://www.homedepot.com',
    'amazon': 'https://www.amazon.com',
    'best buy': 'https://www.bestbuy.com',
    "lowe's": 'https://www.lowes.com',
    'lowes': 'https://www.lowes.com',
    'kroger': 'https://www.kroger.com',
    'walgreens': 'https://www.walgreens.com',
    'cvs': 'https://www.cvs.com',
    'cvs health': 'https://www.cvshealth.com',
    'nordstrom': 'https://www.nordstrom.com',
    "macy's": 'https://www.macys.com',
    'macys': 'https://www.macys.com',
    'jcpenney': 'https://www.jcpenney.com',
    'extended stay america': 'https://www.extendedstayamerica.com',
    'tjx companies': 'https://www.tjx.com',
    'ross stores': 'https://www.rossstores.com',
    'dollar general': 'https://www.dollargeneral.com',
    'dollar tree': 'https://www.dollartree.com',
    # Hotels
    'wyndham': 'https://www.wyndhamhotels.com',
    'choice hotels': 'https://www.choicehotels.com',
    'best western': 'https://www.bestwestern.com',
    'intercontinental hotels group (ihg)': 'https://www.ihg.com',
    'ihg': 'https://www.ihg.com',
    'hyatt': 'https://www.hyatt.com',
    # Tech
    'adobe': 'https://www.adobe.com',
    'apple': 'https://www.apple.com',
    'apple inc': 'https://www.apple.com',
    'microsoft': 'https://www.microsoft.com',
    'google': 'https://www.google.com',
    'alphabet': 'https://abc.xyz',
    'meta': 'https://www.meta.com',
    'facebook': 'https://www.facebook.com',
    'tesla': 'https://www.tesla.com',
    'nvidia': 'https://www.nvidia.com',
    'oracle': 'https://www.oracle.com',
    'salesforce': 'https://www.salesforce.com',
    'ibm': 'https://www.ibm.com',
    # Banks
    'jpmorgan chase': 'https://www.jpmorganchase.com',
    'bank of america': 'https://www.bankofamerica.com',
    'wells fargo': 'https://www.wellsfargo.com',
    'citigroup': 'https://www.citigroup.com',
    'goldman sachs': 'https://www.goldmansachs.com',
    'morgan stanley': 'https://www.morganstanley.com',
    # Real estate
    'cbre group (cbre)': 'https://www.cbre.com',
    'cbre': 'https://www.cbre.com',
    'jones lang lasalle (jll)': 'https://www.jll.com',
    'jll': 'https://www.jll.com',
    'boston properties (bxp)': 'https://www.bxp.com',
    'boston properties': 'https://www.bxp.com',
    'newmark': 'https://www.nmrk.com',
    'cushman & wakefield': 'https://www.cushmanwakefield.com',
    'lincoln property company': 'https://www.lpc.com',
    'related companies': 'https://www.related.com',
    'principal real estate investors': 'https://www.principalglobal.com',
    'brookfield': 'https://www.brookfield.com',
    'blackstone': 'https://www.blackstone.com',
    'the irvine company': 'https://www.irvinecompany.com',
    'hines': 'https://www.hines.com',
    'vornado realty trust': 'https://www.vno.com',
    'kilroy realty': 'https://www.kilroyrealty.com',
    'sl green': 'https://www.slgreen.com',
    'douglas emmett': 'https://www.douglasemmett.com',
    'beacon capital partners': 'https://www.beaconcapital.com',
    'cerberus capital': 'https://www.cerberus.com',
    'gfp real estate': 'https://www.gfpre.com',
    'kaufman organization': 'https://www.kaufmanorganization.com',
    'avison young': 'https://www.avisonyoung.com',
    'shorenstein properties': 'https://www.shorenstein.com',
    'jamestown l.p.': 'https://www.jamestownlp.com',
    'douglas development': 'https://www.douglasdevelopment.com',
    'tishman speyer': 'https://www.tishmanspeyer.com',
    'wework': 'https://www.wework.com',
    'healthcare realty': 'https://www.healthcarerealty.com',
    # Healthcare
    'kaiser permanente': 'https://www.kaiserpermanente.org',
    'sutter health': 'https://www.sutterhealth.org',
    'providence health': 'https://www.providence.org',
    'sunrise senior living': 'https://www.sunriseseniorliving.com',
    'oakmont senior living': 'https://www.oakmontseniorliving.com',
    # Universities
    'harvard university': 'https://www.harvard.edu',
    'california state university': 'https://www.calstate.edu',
    'depaul university': 'https://www.depaul.edu',
    'new york university (nyu)': 'https://www.nyu.edu',
    'nyu': 'https://www.nyu.edu',
    'columbia university': 'https://www.columbia.edu',
    'stanford university': 'https://www.stanford.edu',
    'mit': 'https://www.mit.edu',
    'yale university': 'https://www.yale.edu',
    'princeton university': 'https://www.princeton.edu',
    'university of southern california': 'https://www.usc.edu',
    'usc': 'https://www.usc.edu',
    'ucla': 'https://www.ucla.edu',
    'city university of new york (cuny)': 'https://www.cuny.edu',
    'cuny': 'https://www.cuny.edu',
    'georgetown university': 'https://www.georgetown.edu',
    # School districts
    'chicago public schools': 'https://www.cps.edu',
    'los angeles unified school district': 'https://www.lausd.org',
    'new york city public schools': 'https://www.schools.nyc.gov',
    'district of columbia public schools': 'https://dcps.dc.gov',
    'fresno unified school district': 'https://www.fresnounified.org',
    'long beach unified school district': 'https://www.lbusd.org',
    'san diego unified school district': 'https://www.sandiegounified.org',
    'san bernardino city unified school district': 'https://www.sbcusd.com',
    'corona-norco unified school district': 'https://www.cnusd.k12.ca.us',
    'temecula valley unified school district': 'https://www.tvusd.k12.ca.us',
    'capistrano unified school district': 'https://www.capousd.org',
    'elk grove unified school district': 'https://www.egusd.net',
    'desert sands unified school district': 'https://www.dsusd.us',
    'kansas city public schools': 'https://www.kcpublicschools.org',
    # Government
    'city of new york': 'https://www.nyc.gov',
    'city of los angeles': 'https://www.lacity.org',
    'city of chicago': 'https://www.chicago.gov',
    'city of houston': 'https://www.houstontx.gov',
    'city of seattle': 'https://www.seattle.gov',
    'city of denver': 'https://www.denvergov.org',
    'city of boston': 'https://www.boston.gov',
    'los angeles county': 'https://www.lacounty.gov',
    'riverside county': 'https://www.rivco.org',
    'general services administration (gsa)': 'https://www.gsa.gov',
    'gsa': 'https://www.gsa.gov',
    'district of columbia': 'https://dc.gov',
    'state of new york': 'https://www.ny.gov',
    'los angeles world airports': 'https://www.flylax.com',
    'dormitory authority of the state of new york': 'https://www.dasny.org',
    'new york city police department (nypd)': 'https://www.nyc.gov/nypd',
    'los angeles police department (lapd)': 'https://www.lapdonline.org',
    'philadelphia county': 'https://www.phila.gov',
    # Other
    'roman catholic church': 'https://www.vatican.va',
    'starbucks': 'https://www.starbucks.com',
    "mcdonald's": 'https://www.mcdonalds.com',
    'mcdonalds': 'https://www.mcdonalds.com',
    'ahold delhaize': 'https://www.aholddelhaize.com',
    'verizon': 'https://www.verizon.com',
    'at&t': 'https://www.att.com',
    'comcast': 'https://www.comcast.com',
    # From UNKNOWN list
    'fresno unified school district': 'https://www.fresnounified.org',
    "young men's christian association (ymca)": 'https://www.ymca.org',
    'ymca': 'https://www.ymca.org',
    'highwoods properties': 'https://www.highwoods.com',
    'philadelphia county': 'https://www.phila.gov',
    'staples': 'https://www.staples.com',
    'brandywine realty trust': 'https://www.brandywinerealty.com',
    'city of cambridge': 'https://www.cambridgema.gov',
    'piedmont office realty trust': 'https://www.piedmontreit.com',
    'rudin management co. inc.': 'https://www.rudin.com',
    'rudin management': 'https://www.rudin.com',
    'carr properties': 'https://www.carrprop.com',
    'fontana unified school district': 'https://www.fusd.net',
    'colton joint unified school district': 'https://www.colton.k12.ca.us',
    'akridge': 'https://www.akridge.com',
    'rexford industrial': 'https://www.rexfordindustrial.com',
    'eastdil secured': 'https://www.eastdilsecured.com',
    'paramount group': 'https://www.paramount-group.com',
    'alexandria real estate equities': 'https://www.are.com',
    'equity residential': 'https://www.equityapartments.com',
    'essex property trust': 'https://www.essex.com',
    'prologis': 'https://www.prologis.com',
    'simon property group': 'https://www.simon.com',
    'duke realty': 'https://www.dukerealty.com',
    'kimco realty': 'https://www.kimcorealty.com',
    'regency centers': 'https://www.regencycenters.com',
    'federal realty': 'https://www.federalrealty.com',
    'welltower': 'https://www.welltower.com',
    'ventas': 'https://www.ventasreit.com',
    'medical properties trust': 'https://www.medicalpropertiestrust.com',
    'healthpeak properties': 'https://www.healthpeak.com',
    'american tower': 'https://www.americantower.com',
    'crown castle': 'https://www.crowncastle.com',
    'digital realty': 'https://www.digitalrealty.com',
    'equinix': 'https://www.equinix.com',
    'iron mountain': 'https://www.ironmountain.com',
    'public storage': 'https://www.publicstorage.com',
    'extra space storage': 'https://www.extraspace.com',
    'cubesmart': 'https://www.cubesmart.com',
    'life storage': 'https://www.lifestorage.com',
    'apartment investment and management': 'https://www.aimco.com',
    'aimco': 'https://www.aimco.com',
    'mid-america apartment communities': 'https://www.maac.com',
    'camden property trust': 'https://www.camdenliving.com',
    'udr': 'https://www.udr.com',
    'avalonbay communities': 'https://www.avaloncommunities.com',
}

BAD_PATTERNS = ['ww25.', 'ww1.', 'ww38.', 'parked', 'domain for sale', 'sedoparking',
                'hugedomains', 'godaddy', 'dan.com', '/blocked', '.mx/', '/es-mx']

# Thread-safe globals
print_lock = Lock()
verified_count = 0
failed_count = 0

# ======================================================================================
# Helpers
# ======================================================================================

def normalize(s):
    return str(s).lower().strip() if s else ""

def normalize_for_match(s):
    if not s: return ""
    s = str(s).lower()
    s = re.sub(r'\s*\([^)]*\)\s*', '', s)
    for suf in ['inc', 'llc', 'corp', 'corporation', 'company', 'co', 'ltd', 'the', 'group', 'holdings']:
        s = re.sub(rf'\b{suf}\b\.?', '', s)
    s = re.sub(r'[^a-z0-9\s]', '', s)
    return ' '.join(s.split())

def get_acronym(org):
    m = re.search(r'\(([A-Z]{2,10})\)', org)
    return m.group(1).lower() if m else None

def get_initials(name):
    words = name.split()
    return ''.join(w[0] for w in words if w).lower()

def generate_domains(org_name):
    org_lower = org_name.lower().strip()
    acronym = get_acronym(org_name)
    name_clean = re.sub(r'\s*\([^)]*\)\s*', '', org_lower)
    name_clean = re.sub(r'[^a-z0-9\s]', ' ', name_clean)
    name_clean = ' '.join(name_clean.split())

    name_no_suffix = name_clean
    for suf in ['inc', 'llc', 'corp', 'corporation', 'co', 'ltd', 'group', 'holdings', 'the',
                'unified school district', 'school district', 'public schools']:
        name_no_suffix = re.sub(rf'\b{suf}\b', '', name_no_suffix)
    name_no_suffix = ' '.join(name_no_suffix.split())

    base = re.sub(r'[^a-z0-9]', '', name_no_suffix)
    initials = get_initials(name_no_suffix)

    domains = []

    # NYC special
    if 'new york' in org_lower and 'city' in org_lower:
        domains.append('nyc.gov')

    # Cities
    if 'city of ' in org_lower:
        city = re.sub(r'[^a-z]', '', org_lower.split('city of ')[1].split()[0] if 'city of ' in org_lower else '')
        if city:
            domains.extend([f"{city}.gov", f"cityof{city}.gov", f"{city}.org"])

    # Government with acronym
    if acronym and any(x in org_lower for x in ['administration', 'agency', 'department', 'federal']):
        domains.insert(0, f"{acronym}.gov")

    # Schools
    if 'public school' in org_lower or 'school district' in org_lower or 'unified' in org_lower:
        if initials:
            domains.extend([f"{initials}.org", f"{initials}.edu", f"{initials}.k12.ca.us", f"{initials}usd.org"])
        if base:
            domains.extend([f"{base}.org", f"{base}unified.org", f"{base}.k12.ca.us"])

    # Universities
    elif 'university' in org_lower or 'college' in org_lower:
        if acronym:
            domains.insert(0, f"{acronym}.edu")
        if base:
            domains.extend([f"{base}.edu", f"{base}.org"])

    # Default commercial
    if base:
        domains.append(f"{base}.com")
        domains.append(f"{base}.org")
    if acronym:
        domains.append(f"{acronym}.com")

    # Dedupe
    seen = set()
    return [d for d in domains if d and len(d) > 4 and d not in seen and not seen.add(d)][:8]


def create_session():
    session = requests.Session()
    retry = Retry(total=1, backoff_factor=0.1)
    adapter = HTTPAdapter(pool_connections=150, pool_maxsize=150, max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session


def is_bad_url(url):
    url_lower = url.lower()
    for p in BAD_PATTERNS:
        if p in url_lower:
            return True
    return False


def quick_verify(session, url):
    """Quick verification - just check it loads and isn't parked."""
    try:
        resp = session.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True, verify=False)
        if resp.status_code >= 400:
            return None
        final_url = str(resp.url)
        if is_bad_url(final_url):
            return None
        content = resp.text or ""
        if len(content) < 500:
            return None
        for p in BAD_PATTERNS:
            if p in content.lower()[:3000]:
                return None
        return final_url
    except:
        return None


def search_serpapi(org_name):
    """Use SerpAPI to find official website."""
    try:
        query = f"{org_name} official website"
        url = "https://serpapi.com/search"
        params = {
            "q": query,
            "api_key": SERPAPI_KEY,
            "num": 3,
            "gl": "us",
            "hl": "en"
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()

        # Check organic results
        for result in data.get("organic_results", [])[:3]:
            link = result.get("link", "")
            if link and not is_bad_url(link):
                # Skip Wikipedia, LinkedIn, etc.
                skip = ['wikipedia.org', 'linkedin.com', 'facebook.com', 'twitter.com',
                        'instagram.com', 'youtube.com', 'yelp.com', 'bloomberg.com']
                if not any(s in link.lower() for s in skip):
                    return link
        return None
    except:
        return None


def process_org(args):
    """Process single org."""
    idx, total, org, fortune_lookup, fortune_first_word, session = args
    global verified_count, failed_count

    org_lower = normalize(org)
    org_norm = normalize_for_match(org)
    found_url = None
    source = ""

    # TIER 0: Known URLs (TRUST - no verification)
    if org_lower in KNOWN_URLS:
        found_url = KNOWN_URLS[org_lower]
        source = "known"

    # TIER 1: Fortune lookup (TRUST - no verification)
    if not found_url:
        if org_norm in fortune_lookup:
            found_url = fortune_lookup[org_norm]
            source = "fortune"
        else:
            words = org_norm.split()
            if len(words) == 1 and words[0] in fortune_first_word:
                found_url = fortune_first_word[words[0]]
                source = "fortune"

    # TIER 2: Try domains with quick verify
    if not found_url:
        for domain in generate_domains(org):
            for prefix in ['https://www.', 'https://']:
                url = f"{prefix}{domain}"
                result = quick_verify(session, url)
                if result:
                    found_url = result
                    source = "guessed"
                    break
            if found_url:
                break

    # TIER 3: SerpAPI search (for failures)
    if not found_url and SERPAPI_KEY:
        serp_url = search_serpapi(org)
        if serp_url:
            # Quick verify the SerpAPI result
            verified = quick_verify(session, serp_url)
            if verified:
                found_url = verified
                source = "serpapi"

    # Output
    with print_lock:
        if found_url:
            verified_count += 1
            print(f"[{idx:4d}/{total}] ✓ {org[:38]:<38} → {found_url[:50]} ({source})")
        else:
            failed_count += 1
            print(f"[{idx:4d}/{total}] ✗ {org[:38]:<38}")

    return {
        'organization': org,
        'website_url': found_url or '',
        'source': source,
        'verified': 'yes' if found_url else 'no'
    }


# ======================================================================================
# MAIN
# ======================================================================================

def main():
    global verified_count, failed_count

    portfolio_path = Path(PORTFOLIO_CSV)
    if not portfolio_path.exists():
        raise SystemExit(f"Portfolio not found: {portfolio_path}")

    df = pd.read_csv(portfolio_path)
    orgs = df['organization'].tolist()
    total = len(orgs)

    print("=" * 75)
    print(f"URL ENRICHER v4 - {MAX_WORKERS} workers + SerpAPI")
    print(f"Portfolio: {total} organizations")
    print(f"Known URLs: {len(KNOWN_URLS)}")
    print("=" * 75)

    # Fortune lookup (TRUSTED)
    fortune_lookup = {}
    fortune_first_word = {}
    fortune_first_word_len = {}
    fortune_path = Path(FORTUNE_2024)
    if fortune_path.exists():
        fdf = pd.read_csv(fortune_path)
        for _, r in fdf.iterrows():
            name = normalize_for_match(r.get('Company', ''))
            url = r.get('Website', '')
            if name and url and pd.notna(url) and 'blocked' not in str(url).lower():
                fortune_lookup[name] = url
                first = name.split()[0] if name.split() else ""
                if first and len(first) >= 4:
                    if len(name) < fortune_first_word_len.get(first, 999):
                        fortune_first_word[first] = url
                        fortune_first_word_len[first] = len(name)
        print(f"Fortune URLs: {len(fortune_lookup)}")

    # Check for existing output to resume
    out_path = Path(OUTPUT_CSV)
    existing = {}
    if out_path.exists():
        try:
            edf = pd.read_csv(out_path)
            if 'organization' in edf.columns:
                for _, r in edf.iterrows():
                    existing[str(r['organization'])] = dict(r)
            print(f"[resume] Found {len(existing)} already processed")
        except:
            pass

    # Filter unprocessed
    work_orgs = [org for org in orgs if org not in existing]
    rows_out = list(existing.values())
    verified_count = sum(1 for r in existing.values() if r.get('verified') == 'yes')
    failed_count = sum(1 for r in existing.values() if r.get('verified') == 'no')

    if not work_orgs:
        print("All orgs already processed!")
        return

    print(f"[work] {len(work_orgs)} orgs to process")
    print("=" * 75)

    start = time.time()
    session = create_session()

    work_items = [(i, total, org, fortune_lookup, fortune_first_word, session)
                  for i, org in enumerate(work_orgs, len(existing) + 1)]

    save_lock = Lock()
    save_counter = [0]

    def process_and_save(args):
        result = process_org(args)
        with save_lock:
            rows_out.append(result)
            save_counter[0] += 1
            if save_counter[0] % 50 == 0:
                pd.DataFrame(rows_out).to_csv(out_path, index=False)
                print(f"[save] {save_counter[0]} saved")
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        list(executor.map(process_and_save, work_items))

    # Final save
    pd.DataFrame(rows_out).to_csv(out_path, index=False)

    elapsed = time.time() - start
    print()
    print("=" * 75)
    print(f"DONE in {elapsed:.1f}s")
    print(f"Verified: {verified_count}/{total} ({100*verified_count/total:.1f}%)")
    print(f"Output: {out_path}")
    print("=" * 75)


if __name__ == "__main__":
    main()
