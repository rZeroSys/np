"""
Data loading and processing for Nationwide ODCV Prospector Homepage
===================================================================
Loads 26,648 buildings across Commercial, Education, Healthcare, and Government verticals.
Aggregates portfolio data by organization for expandable portfolio cards.
"""

import os
import re
import pandas as pd
import math
import statistics
from collections import defaultdict
from src.data.helpers import safe_float, safe_int, safe_str, normalize_building_type

# =============================================================================
# UTILITY FUNCTIONS FOR BUILDING REPORTS
# =============================================================================

def load_csv(csv_path):
    """Load CSV for building reports, handle encoding, data types"""
    import sys
    try:
        df = pd.read_csv(csv_path, encoding='utf-8')
        print(f"✓ Loaded {len(df)} buildings from CSV")
    except Exception as e:
        print(f"✗ Error loading CSV: {e}")
        sys.exit(1)

    # Convert numeric columns, coerce errors to NaN
    numeric_columns = [
        'square_footage', 'site_eui', 'latitude', 'longitude',
        'odcv_dollar_savings', 'fine_avoidance_yr1', 'total_annual_opex_avoidance',
        'odcv_valuation_impact_usd', 'carbon_emissions_reduction_yr1'
    ]

    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Fill NaN values with 0 for financial columns
    financial_cols = ['odcv_dollar_savings', 'fine_avoidance_yr1', 'total_annual_opex_avoidance',
                      'odcv_valuation_impact_usd', 'carbon_emissions_reduction_yr1']
    for col in financial_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0)

    return df

def extract_filename(photo_url):
    """Extract filename from photo URL"""
    if pd.isna(photo_url) or not photo_url:
        return ""
    if '/' not in str(photo_url):
        return str(photo_url)
    return str(photo_url).split('/')[-1]

# =============================================================================
# CONFIGURATION - Import from centralized config
# =============================================================================

from src.config import (
    BUILDING_DATA_PATH as CONFIG_BUILDING_DATA_PATH,
    PORTFOLIO_DATA_PATH as CONFIG_PORTFOLIO_DATA_PATH,
    BUILDINGS_TAB_DATA_PATH as CONFIG_BUILDINGS_TAB_DATA_PATH,
    PORTFOLIO_ORGS_PATH as CONFIG_PORTFOLIO_ORGS_PATH,
    IMAGES_DIR as CONFIG_IMAGES_DIR,
    LOGOS_DIR as CONFIG_LOGOS_DIR
)

BUILDING_DATA_PATH = str(CONFIG_BUILDING_DATA_PATH)
PORTFOLIO_DATA_PATH = str(CONFIG_PORTFOLIO_DATA_PATH)
BUILDINGS_TAB_DATA_PATH = str(CONFIG_BUILDINGS_TAB_DATA_PATH)
PORTFOLIO_ORGS_PATH = str(CONFIG_PORTFOLIO_ORGS_PATH)
IMAGES_DIR = str(CONFIG_IMAGES_DIR)
LOGOS_DIR = str(CONFIG_LOGOS_DIR)

# =============================================================================
# DATA LOADING FUNCTIONS
# =============================================================================

def load_building_data():
    """
    Load the main building dataset (26,648 buildings).
    DEPRECATED: Use load_portfolio_data() or load_buildings_tab_data() instead.

    Returns:
        pd.DataFrame with columns: building_id, address, city, state, vertical,
        building_type, square_footage, building_owner, property_manager,
        odcv_dollar_savings, fine_avoidance_yr1, total_annual_opex_avoidance,
        odcv_valuation_impact_usd, carbon_emissions_reduction_yr1, latitude,
        longitude, building_url, etc.
    """
    print("Loading building data...")

    df = pd.read_csv(BUILDING_DATA_PATH, encoding='utf-8')

    # Ensure critical columns exist and have proper types
    df['building_id'] = df['building_id'].astype(str)
    df['square_footage'] = pd.to_numeric(df['square_footage'], errors='coerce').fillna(0)
    df['odcv_dollar_savings'] = pd.to_numeric(df['odcv_dollar_savings'], errors='coerce').fillna(0)
    df['fine_avoidance_yr1'] = pd.to_numeric(df['fine_avoidance_yr1'], errors='coerce').fillna(0)
    df['total_annual_opex_avoidance'] = pd.to_numeric(df['total_annual_opex_avoidance'], errors='coerce').fillna(0)
    df['odcv_valuation_impact_usd'] = pd.to_numeric(df['odcv_valuation_impact_usd'], errors='coerce').fillna(0)
    df['carbon_emissions_reduction_yr1'] = pd.to_numeric(df['carbon_emissions_reduction_yr1'], errors='coerce').fillna(0)
    df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
    df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')

    # Clean string columns
    for col in ['building_owner', 'property_manager', 'address', 'city', 'state', 'vertical', 'building_type']:
        if col in df.columns:
            df[col] = df[col].fillna('').astype(str).str.strip()

    print(f"  Loaded {len(df):,} buildings")
    print(f"  Verticals: {df['vertical'].value_counts().to_dict()}")

    return df


def load_portfolio_data():
    """
    Load building data for the Portfolio tab from portfolio_data.csv.

    Returns:
        pd.DataFrame with building data for portfolio aggregation
    """
    print("Loading portfolio data...")

    df = pd.read_csv(PORTFOLIO_DATA_PATH, encoding='utf-8')

    # Ensure critical columns exist and have proper types
    df['building_id'] = df['building_id'].astype(str)
    df['square_footage'] = pd.to_numeric(df['square_footage'], errors='coerce').fillna(0)
    df['odcv_dollar_savings'] = pd.to_numeric(df['odcv_dollar_savings'], errors='coerce').fillna(0)
    df['fine_avoidance_yr1'] = pd.to_numeric(df['fine_avoidance_yr1'], errors='coerce').fillna(0)
    df['total_annual_opex_avoidance'] = pd.to_numeric(df['total_annual_opex_avoidance'], errors='coerce').fillna(0)
    df['odcv_valuation_impact_usd'] = pd.to_numeric(df['odcv_valuation_impact_usd'], errors='coerce').fillna(0)
    df['carbon_emissions_reduction_yr1'] = pd.to_numeric(df['carbon_emissions_reduction_yr1'], errors='coerce').fillna(0)
    df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
    df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')

    # Clean string columns
    for col in ['building_owner', 'property_manager', 'address', 'city', 'state', 'vertical', 'building_type']:
        if col in df.columns:
            df[col] = df[col].fillna('').astype(str).str.strip()

    print(f"  Loaded {len(df):,} portfolio buildings")
    print(f"  Verticals: {df['vertical'].value_counts().to_dict()}")

    return df


def load_buildings_tab_data():
    """
    Load building data for the Buildings tab from buildings_tab_data.csv.

    Returns:
        pd.DataFrame with building data for all-buildings display
    """
    print("Loading buildings tab data...")

    df = pd.read_csv(BUILDINGS_TAB_DATA_PATH, encoding='utf-8')

    # Ensure critical columns exist and have proper types
    df['building_id'] = df['building_id'].astype(str)
    df['square_footage'] = pd.to_numeric(df['square_footage'], errors='coerce').fillna(0)
    df['odcv_dollar_savings'] = pd.to_numeric(df['odcv_dollar_savings'], errors='coerce').fillna(0)
    df['fine_avoidance_yr1'] = pd.to_numeric(df['fine_avoidance_yr1'], errors='coerce').fillna(0)
    df['total_annual_opex_avoidance'] = pd.to_numeric(df['total_annual_opex_avoidance'], errors='coerce').fillna(0)
    df['odcv_valuation_impact_usd'] = pd.to_numeric(df['odcv_valuation_impact_usd'], errors='coerce').fillna(0)
    df['carbon_emissions_reduction_yr1'] = pd.to_numeric(df['carbon_emissions_reduction_yr1'], errors='coerce').fillna(0)
    df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
    df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')

    # Clean string columns
    for col in ['building_owner', 'property_manager', 'address', 'city', 'state', 'vertical', 'building_type']:
        if col in df.columns:
            df[col] = df[col].fillna('').astype(str).str.strip()

    print(f"  Loaded {len(df):,} buildings tab buildings")
    print(f"  Verticals: {df['vertical'].value_counts().to_dict()}")

    return df


def calculate_portfolio_orgs(buildings_df, min_rows=3):
    """
    Calculate portfolio organizations from building data.

    An org qualifies if it appears in 3+ separate ROWS (not 3 mentions).
    Multiple appearances in the same row count as 1 row.

    Args:
        buildings_df: DataFrame with building_owner, property_manager, tenant columns
        min_rows: Minimum rows to qualify as portfolio org (default 3)

    Returns:
        dict: {org_name: row_count}
    """
    print("Calculating portfolio organizations from building data...")

    org_rows = {}  # {org_name: set of row indices}

    for idx, row in buildings_df.iterrows():
        row_orgs = set()  # Collect unique orgs in this row

        for col in ['building_owner', 'property_manager', 'tenant', 'tenant_sub_org']:
            org = str(row.get(col, '')).strip()
            if org:
                row_orgs.add(org)

        # Add this row index to each org's set
        for org in row_orgs:
            if org not in org_rows:
                org_rows[org] = set()
            org_rows[org].add(idx)

    # Filter to orgs with min_rows+ rows
    portfolio_orgs = {
        org: len(rows)
        for org, rows in org_rows.items()
        if len(rows) >= min_rows
    }

    print(f"  Found {len(portfolio_orgs):,} portfolio organizations (appearing in {min_rows}+ rows)")
    return portfolio_orgs


def load_logo_mappings():
    """
    Load logo file and classification mappings from portfolio_organizations.csv.

    Returns:
        dict: {org_name: {'logo_file': str, 'classification': str}}
    """
    print("Loading logo mappings...")

    if not os.path.exists(PORTFOLIO_ORGS_PATH):
        print("  Warning: portfolio_organizations.csv not found")
        return {}

    df = pd.read_csv(PORTFOLIO_ORGS_PATH, encoding='utf-8')

    mappings = {}
    for _, row in df.iterrows():
        org_name = safe_str(row.get('organization', ''))
        if not org_name:
            continue
        logo_file = safe_str(row.get('logo_file', ''))
        classification = safe_str(row.get('classification', '')).lower()
        # Validate classification
        if classification not in ['owner', 'tenant', 'property manager', 'owner/occupier', 'owner/operator', 'tenant_sub_org']:
            classification = ''
        display_name = safe_str(row.get('display_name', '')) or org_name  # fallback to org_name
        aws_logo_url = safe_str(row.get('aws_logo_url', ''))

        # Parse search_aliases (pipe-separated)
        search_aliases_raw = safe_str(row.get('search_aliases', ''))
        search_aliases = [a.strip() for a in search_aliases_raw.split('|') if a.strip()]

        mappings[org_name] = {
            'logo_file': logo_file,
            'classification': classification,
            'display_name': display_name,
            'aws_logo_url': aws_logo_url,
            'search_aliases': search_aliases
        }

    print(f"  Loaded {len(mappings):,} org mappings (logos + classifications + aliases)")
    return mappings


def build_image_map(images_dir=IMAGES_DIR):
    """
    Build mapping from building_id to image filename.

    Image naming pattern: PREFIX_ID_source.ext
    Examples:
        - NYC_1005980058_AWS.jpg -> NYC_1005980058
        - ATL_8_streetview.jpg -> ATL_8
        - BOS_123_EnergyStar.jpg -> BOS_123

    Returns:
        dict: {building_id: image_filename}
    """
    print("Building image map...")

    image_map = {}

    if not os.path.exists(images_dir):
        print(f"  Warning: Images directory not found: {images_dir}")
        return image_map

    for filename in os.listdir(images_dir):
        if not filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
            continue

        # Pattern: PREFIX_ID_source.ext
        # Match city prefix (letters) + underscore + ID (alphanumeric) + underscore + rest
        match = re.match(r'^([A-Z]+_[A-Za-z0-9]+)_', filename)
        if match:
            building_id = match.group(1)
            # Only store first image found for each building (prefer alphabetically first)
            if building_id not in image_map:
                image_map[building_id] = filename

    print(f"  Mapped {len(image_map):,} building images")
    return image_map


def build_logo_map(logos_dir=LOGOS_DIR):
    """
    Build set of available logo files.

    Returns:
        set: {logo_filename, ...}
    """
    print("Building logo map...")

    logo_files = set()

    if not os.path.exists(logos_dir):
        print(f"  Warning: Logos directory not found: {logos_dir}")
        return logo_files

    for filename in os.listdir(logos_dir):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            logo_files.add(filename)

    print(f"  Found {len(logo_files):,} logo files")
    return logo_files


# =============================================================================
# PORTFOLIO AGGREGATION
# =============================================================================

def aggregate_portfolios(buildings_df, portfolio_orgs, logo_mappings, image_map):
    """
    Aggregate building data by portfolio organization.

    A building belongs to an organization's portfolio if:
    - building_owner matches org name, OR
    - property_manager matches org name, OR
    - tenant matches org name

    Args:
        buildings_df: DataFrame with building data
        portfolio_orgs: dict {org_name: row_count} from calculate_portfolio_orgs()
        logo_mappings: dict {org_name: logo_file} from load_logo_mappings()
        image_map: dict {building_id: image_file}

    Returns:
        list of dicts, sorted by total_opex_avoidance descending:
        [
            {
                'org_name': 'Marriott',
                'logo_file': 'Marriott.png',
                'building_count': 540,
                'total_sqft': 45000000,
                'total_utility_savings': 15000000,
                'total_fine_avoidance': 5000000,
                'total_opex_avoidance': 20000000,
                'total_valuation_impact': 100000000,  # Commercial only
                'total_carbon_reduction': 50000,
                'verticals': ['Commercial', 'Healthcare'],  # list of unique verticals
                'buildings': [  # list of building dicts
                    {
                        'building_id': 'NYC_123',
                        'address': '123 Main St',
                        'city': 'New York',
                        'state': 'NY',
                        'building_type': 'Office',
                        'vertical': 'Commercial',
                        'sqft': 500000,
                        'utility_savings': 100000,
                        'fine_avoidance': 25000,
                        'total_opex': 125000,
                        'valuation_impact': 1500000,
                        'carbon_reduction': 250,
                        'image_file': 'NYC_123_AWS.jpg',
                        'building_url': 'https://energystar.gov/...',
                        'latitude': 40.7128,
                        'longitude': -74.0060
                    },
                    ...
                ]
            },
            ...
        ]
    """
    print("Aggregating portfolios...")

    portfolios = {}

    # Build tenant_sub_org -> parent_tenant mapping from building data
    sub_org_to_parent = {}
    for _, row in buildings_df.iterrows():
        sub_org = safe_str(row.get('tenant_sub_org'))
        tenant = safe_str(row.get('tenant'))
        if sub_org and tenant:
            sub_org_to_parent[sub_org] = tenant

    # Create lookup for buildings by owner, manager, tenant, AND tenant_sub_org (per methodology)
    owner_buildings = defaultdict(list)
    manager_buildings = defaultdict(list)
    tenant_buildings = defaultdict(list)
    tenant_sub_org_buildings = defaultdict(list)

    for _, row in buildings_df.iterrows():
        building_data = {
            'building_id': safe_str(row['building_id']),
            'address': safe_str(row['address']),
            'city': safe_str(row.get('city')),
            'state': safe_str(row.get('state')),
            'building_type': normalize_building_type(safe_str(row.get('building_type'))),
            'radio_type': normalize_building_type(safe_str(row.get('radio_button_building_type'))),
            'vertical': safe_str(row.get('vertical')),
            'sqft': safe_float(row['square_footage']),
            'utility_savings': safe_float(row['odcv_dollar_savings']),
            'fine_avoidance': safe_float(row['fine_avoidance_yr1']),
            'total_opex': safe_float(row['total_annual_opex_avoidance']),
            'valuation_impact': safe_float(row['odcv_valuation_impact_usd']),
            'carbon_reduction': safe_float(row['carbon_emissions_reduction_yr1']),
            'total_building_cost_savings_pct': safe_float(row.get('total_building_cost_savings_pct', 0)),
            'image': image_map.get(row['building_id'], ''),
            'building_url': safe_str(row.get('building_url')),
            'latitude': safe_float(row['latitude'], None),
            'longitude': safe_float(row['longitude'], None),
            'property_name': safe_str(row.get('property_name')),
            'tenant': safe_str(row.get('tenant')),
            'tenant_sub_org': safe_str(row.get('tenant_sub_org')),
            'site_eui': safe_float(row.get('site_eui'), None),
            'eui_benchmark': safe_float(row.get('eui_benchmark'), None),
            'owner': safe_str(row.get('building_owner')),
            'manager': safe_str(row.get('property_manager'))
        }

        owner = safe_str(row.get('building_owner'))
        manager = safe_str(row.get('property_manager'))
        tenant = safe_str(row.get('tenant'))

        if owner:
            owner_buildings[owner].append(building_data)
        if manager:
            manager_buildings[manager].append(building_data)
        if tenant:
            tenant_buildings[tenant].append(building_data)
        tenant_sub_org = safe_str(row.get('tenant_sub_org'))
        if tenant_sub_org:
            tenant_sub_org_buildings[tenant_sub_org].append(building_data)

    # Process each portfolio organization (calculated dynamically from building data)
    for org_name, row_count in portfolio_orgs.items():
        # Collect buildings from owner, manager, AND tenant relationships (per methodology)
        org_buildings = {}  # Use dict to dedupe by building_id

        for bldg in owner_buildings.get(org_name, []):
            org_buildings[bldg['building_id']] = bldg

        for bldg in manager_buildings.get(org_name, []):
            org_buildings[bldg['building_id']] = bldg

        for bldg in tenant_buildings.get(org_name, []):
            org_buildings[bldg['building_id']] = bldg

        for bldg in tenant_sub_org_buildings.get(org_name, []):
            org_buildings[bldg['building_id']] = bldg

        if not org_buildings:
            continue

        buildings_list = list(org_buildings.values())

        # Calculate aggregates
        total_sqft = sum(b['sqft'] for b in buildings_list)
        total_utility_savings = sum(b['utility_savings'] for b in buildings_list)
        total_fine_avoidance = sum(b['fine_avoidance'] for b in buildings_list)
        total_opex_avoidance = sum(b['total_opex'] for b in buildings_list)

        # Valuation impact only for Commercial buildings
        commercial_buildings = [b for b in buildings_list if b['vertical'] == 'Commercial']
        total_valuation_impact = sum(b['valuation_impact'] for b in commercial_buildings)

        total_carbon_reduction = sum(b['carbon_reduction'] for b in buildings_list)

        # Get unique verticals
        verticals = sorted(list(set(b['vertical'] for b in buildings_list if b['vertical'])))

        # Get unique cities and building types for filtering
        cities = sorted(list(set(b['city'] for b in buildings_list if b.get('city'))))
        building_types = sorted(list(set(b['radio_type'] for b in buildings_list if b.get('radio_type'))))
        radio_types = sorted(list(set(b['radio_type'] for b in buildings_list if b.get('radio_type'))))

        # Get unique tenants, tenant sub-orgs, owners, and managers for search
        tenants = sorted(list(set(b['tenant'] for b in buildings_list if b.get('tenant'))))
        tenant_sub_orgs = sorted(list(set(b['tenant_sub_org'] for b in buildings_list if b.get('tenant_sub_org'))))
        owners = sorted(list(set(b['owner'] for b in buildings_list if b.get('owner'))))
        managers = sorted(list(set(b['manager'] for b in buildings_list if b.get('manager'))))

        # Calculate OpEx by vertical for sorting
        opex_by_vertical = {}
        for v in ['Commercial', 'Education', 'Healthcare']:
            v_buildings = [b for b in buildings_list if b['vertical'] == v]
            opex_by_vertical[v] = sum(b['total_opex'] for b in v_buildings)

        # Sort buildings by total_opex descending
        buildings_list.sort(key=lambda x: x['total_opex'], reverse=True)

        # Calculate median EUI for portfolio
        eui_values = [b['site_eui'] for b in buildings_list if b.get('site_eui')]
        median_eui = statistics.median(eui_values) if eui_values else None

        # Get median benchmark for portfolio rating
        benchmark_values = [b['eui_benchmark'] for b in buildings_list if b.get('eui_benchmark')]
        median_eui_benchmark = statistics.median(benchmark_values) if benchmark_values else None

        # Try exact match first, then try without acronym suffix like (MIT), (GSA), etc.
        org_info = logo_mappings.get(org_name, {})
        if not org_info:
            # Try stripping trailing acronym in parentheses
            stripped_name = re.sub(r'\s*\([A-Z]+\)\s*$', '', org_name)
            org_info = logo_mappings.get(stripped_name, {})
        # Get parent tenant info for tenant_sub_org portfolios
        classification = org_info.get('classification', '')
        parent_tenant = ''
        parent_logo_url = ''
        if classification == 'tenant_sub_org':
            parent_tenant = sub_org_to_parent.get(org_name, '')
            if parent_tenant:
                parent_info = logo_mappings.get(parent_tenant, {})
                parent_logo_url = parent_info.get('aws_logo_url', '')

        portfolios[org_name] = {
            'org_name': org_name,
            'display_name': org_info.get('display_name', org_name),
            'logo_file': org_info.get('logo_file', ''),
            'aws_logo_url': org_info.get('aws_logo_url', ''),
            'classification': classification,
            'search_aliases': org_info.get('search_aliases', []),
            'parent_tenant': parent_tenant,
            'parent_logo_url': parent_logo_url,
            'building_count': len(buildings_list),
            'total_sqft': total_sqft,
            'total_utility_savings': total_utility_savings,
            'total_fine_avoidance': total_fine_avoidance,
            'total_opex_avoidance': total_opex_avoidance,
            'total_valuation_impact': total_valuation_impact,
            'total_carbon_reduction': total_carbon_reduction,
            'median_eui': median_eui,
            'median_eui_benchmark': median_eui_benchmark,
            'verticals': verticals,
            'cities': cities,
            'building_types': building_types,
            'radio_types': radio_types,
            'tenants': tenants,
            'tenant_sub_orgs': tenant_sub_orgs,
            'owners': owners,
            'managers': managers,
            'opex_by_vertical': opex_by_vertical,
            'buildings': buildings_list
        }

    # Sort portfolios by total_opex_avoidance descending
    sorted_portfolios = sorted(
        portfolios.values(),
        key=lambda x: x['total_opex_avoidance'],
        reverse=True
    )

    print(f"  Aggregated {len(sorted_portfolios):,} portfolios")
    if sorted_portfolios:
        top5 = [p['org_name'] for p in sorted_portfolios[:5]]
        print(f"  Top 5 by OpEx: {top5}")

    return sorted_portfolios


# =============================================================================
# STATISTICS CALCULATION
# =============================================================================

def calculate_stats(buildings_df, portfolios):
    """
    Calculate overall statistics for header cards.

    Returns:
        dict with keys:
            - total_buildings
            - total_opex_avoidance
            - total_utility_savings
            - total_fine_avoidance
            - total_carbon_reduction
            - total_valuation_impact (Commercial only)
            - total_sqft
            - by_vertical: {vertical: {building_count, opex, carbon}}
    """
    print("Calculating statistics...")

    # BPS cities (Building Performance Standards)
    bps_cities = [
        'Boston', 'Cambridge', 'Denver', 'New York',
        'San Francisco', 'Seattle', 'St. Louis', 'Washington'
    ]

    # Get all unique building types
    all_building_types = sorted(buildings_df['radio_button_building_type'].dropna().unique().tolist())

    stats = {
        'total_buildings': len(buildings_df),
        'total_opex_avoidance': buildings_df['total_annual_opex_avoidance'].sum(),
        'total_utility_savings': buildings_df['odcv_dollar_savings'].sum(),
        'total_fine_avoidance': buildings_df['fine_avoidance_yr1'].sum(),
        'total_carbon_reduction': buildings_df['carbon_emissions_reduction_yr1'].sum(),
        'total_sqft': buildings_df['square_footage'].sum(),
        'by_vertical': {},
        'bps_cities': bps_cities,
        'all_building_types': all_building_types
    }

    # Commercial-only valuation impact
    commercial_df = buildings_df[buildings_df['vertical'] == 'Commercial']
    stats['total_valuation_impact'] = commercial_df['odcv_valuation_impact_usd'].sum()

    # Stats by vertical
    for vertical in ['Commercial', 'Education', 'Healthcare']:
        v_df = buildings_df[buildings_df['vertical'] == vertical]
        stats['by_vertical'][vertical] = {
            'building_count': len(v_df),
            'opex_avoidance': v_df['total_annual_opex_avoidance'].sum(),
            'utility_savings': v_df['odcv_dollar_savings'].sum(),
            'fine_avoidance': v_df['fine_avoidance_yr1'].sum(),
            'carbon_reduction': v_df['carbon_emissions_reduction_yr1'].sum(),
            'sqft': v_df['square_footage'].sum(),
            'valuation_impact': v_df['odcv_valuation_impact_usd'].sum() if vertical == 'Commercial' else 0
        }

    # Radio button building type counts
    radio_type_counts = buildings_df['radio_button_building_type'].value_counts().to_dict()
    stats['radio_type_counts'] = radio_type_counts

    # Building types by vertical - for dynamic left sidebar filtering
    # Only include types with at least 50 buildings in that vertical
    types_by_vertical = {}
    for vertical in ['Commercial', 'Education', 'Healthcare']:
        v_df = buildings_df[buildings_df['vertical'] == vertical]
        type_counts = v_df['radio_button_building_type'].value_counts()
        types = [t for t, c in type_counts.items() if c >= 50]
        types_by_vertical[vertical] = sorted(types)
    stats['types_by_vertical'] = types_by_vertical

    print(f"  Total buildings: {stats['total_buildings']:,}")
    print(f"  Total OpEx avoidance: ${stats['total_opex_avoidance']:,.0f}")
    print(f"  Total carbon reduction: {stats['total_carbon_reduction']:,.0f} tCO2e")

    return stats


# =============================================================================
# COORDINATE MAPPING
# =============================================================================

def build_coordinates_map(buildings_df):
    """
    Build mapping for map pins: building_id -> [lon, lat].
    Mapbox expects [longitude, latitude] format.

    Returns:
        dict: {building_id: [lon, lat]}
    """
    print("Building coordinates map...")

    coords = {}
    valid_count = 0

    for _, row in buildings_df.iterrows():
        lat = row['latitude']
        lon = row['longitude']

        if pd.notna(lat) and pd.notna(lon):
            coords[row['building_id']] = [float(lon), float(lat)]
            valid_count += 1

    print(f"  Coordinates for {valid_count:,} buildings")
    return coords


# =============================================================================
# ALL BUILDINGS LIST (for Building Search tab)
# =============================================================================

def prepare_all_buildings(buildings_df, image_map):
    """
    Prepare all buildings list for the Building Search tab.

    Returns:
        list of dicts with essential building info for search/display
    """
    print("Preparing all buildings list...")

    all_buildings = []

    for _, row in buildings_df.iterrows():
        bldg = {
            'id': safe_str(row['building_id']),
            'address': safe_str(row['address']),
            'city': safe_str(row.get('city')),
            'state': safe_str(row.get('state')),
            'type': normalize_building_type(safe_str(row.get('radio_button_building_type'))),
            'radio_type': normalize_building_type(safe_str(row.get('radio_button_building_type'))),
            'vertical': safe_str(row.get('vertical')),
            'sqft': safe_float(row['square_footage']),
            'utility_savings': safe_float(row['odcv_dollar_savings']),
            'fine_avoidance': safe_float(row['fine_avoidance_yr1']),
            'total_opex': safe_float(row['total_annual_opex_avoidance']),
            'valuation_impact': safe_float(row['odcv_valuation_impact_usd']),
            'carbon': safe_float(row['carbon_emissions_reduction_yr1']),
            'lat': safe_float(row['latitude'], None),
            'lon': safe_float(row['longitude'], None),
            'image': image_map.get(row['building_id'], ''),
            'url': safe_str(row.get('building_url')),
            'owner': safe_str(row.get('building_owner')),
            'manager': safe_str(row.get('property_manager')),
            'tenant': safe_str(row.get('tenant')),
            'sub_org': safe_str(row.get('tenant_sub_org')),
            'property_name': safe_str(row.get('property_name')),
            'site_eui': safe_float(row.get('site_eui', 0)),
            'year_built': safe_int(row.get('year_built', 0))
        }
        all_buildings.append(bldg)

    # Sort by total_opex descending
    all_buildings.sort(key=lambda x: x['total_opex'], reverse=True)

    print(f"  Prepared {len(all_buildings):,} buildings for search")
    return all_buildings


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def load_all_data():
    """
    Load and process all data for the Nationwide ODCV Prospector.

    Uses separate CSV files for Portfolio tab and Buildings tab:
    - portfolio_data.csv -> Portfolio tab (portfolios, portfolio stats)
    - buildings_tab_data.csv -> Buildings tab (all_buildings, coords_map, building stats)

    Returns:
        dict with keys:
            - portfolio_df: Raw pandas DataFrame for portfolio tab
            - buildings_tab_df: Raw pandas DataFrame for buildings tab
            - portfolios: List of portfolio dicts sorted by OpEx
            - all_buildings: List of all building dicts for search
            - stats: Overall statistics dict
            - image_map: {building_id: image_file}
            - logo_files: Set of available logo files
            - coords_map: {building_id: [lon, lat]}
    """
    print("=" * 60)
    print("Nationwide ODCV Prospector - Data Loading")
    print("=" * 60)

    # Load raw data - use portfolio_data.csv for everything
    portfolio_df = load_portfolio_data()        # For Portfolio tab
    buildings_tab_df = portfolio_df.copy()      # Use same data for Buildings tab
    image_map = build_image_map()
    logo_files = build_logo_map()

    # Calculate portfolio orgs from portfolio data (3+ rows rule)
    portfolio_orgs = calculate_portfolio_orgs(portfolio_df, min_rows=3)
    logo_mappings = load_logo_mappings()

    # Process portfolios from portfolio_df
    portfolios = aggregate_portfolios(portfolio_df, portfolio_orgs, logo_mappings, image_map)

    # Process buildings tab from buildings_tab_df
    all_buildings = prepare_all_buildings(buildings_tab_df, image_map)
    coords_map = build_coordinates_map(buildings_tab_df)

    # Calculate stats (using portfolio_df for consistency with portfolio data)
    stats = calculate_stats(portfolio_df, portfolios)

    # Image coverage stats
    buildings_with_images = sum(1 for b in all_buildings if b['image'])
    image_coverage = buildings_with_images / len(all_buildings) * 100 if all_buildings else 0
    print(f"\nImage coverage: {buildings_with_images:,} / {len(all_buildings):,} ({image_coverage:.1f}%)")

    print("\n" + "=" * 60)
    print("Data loading complete!")
    print("=" * 60)

    return {
        'portfolio_df': portfolio_df,
        'buildings_tab_df': buildings_tab_df,
        'portfolios': portfolios,
        'all_buildings': all_buildings,
        'stats': stats,
        'image_map': image_map,
        'logo_files': logo_files,
        'logo_mappings': logo_mappings,
        'coords_map': coords_map
    }


# =============================================================================
# INSTAGRAM-STYLE DATA EXPORT - Split into small on-demand files
# =============================================================================

def export_split_data(data, output_dir):
    """
    Export data as split JSON files for on-demand loading.

    Creates:
    - data/summary.json - Portfolio metadata only (no buildings), ~100KB
    - data/portfolios/portfolio_0.json, portfolio_1.json, etc. - One per portfolio
    - data/map_markers.json - Just coordinates for map pins

    This allows:
    - Initial page load: Only summary.json (~100KB vs 12MB)
    - Portfolio expand: Fetch that portfolio's JSON on demand
    - Map tab: Fetch map_markers.json only when user clicks map
    """
    import json
    import os

    portfolios = data['portfolios']
    all_buildings = data['all_buildings']

    # Create data directories
    data_dir = os.path.join(output_dir, 'data')
    portfolios_dir = os.path.join(data_dir, 'portfolios')
    os.makedirs(portfolios_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print("Exporting split data files (Instagram-style)")
    print(f"{'='*60}")

    # -------------------------------------------------------------------------
    # 1. SUMMARY.JSON - Portfolio metadata only (no building details)
    # -------------------------------------------------------------------------
    summary = []
    for idx, p in enumerate(portfolios):
        summary.append({
            'idx': idx,
            'org_name': p['org_name'],
            'logo_file': p['logo_file'],
            'aws_logo_url': p.get('aws_logo_url', ''),
            'classification': p.get('classification', ''),
            'building_count': p['building_count'],
            'total_sqft': p['total_sqft'],
            'total_utility_savings': p['total_utility_savings'],
            'total_fine_avoidance': p['total_fine_avoidance'],
            'total_opex_avoidance': p['total_opex_avoidance'],
            'total_valuation_impact': p['total_valuation_impact'],
            'total_carbon_reduction': p['total_carbon_reduction'],
            'median_eui': p.get('median_eui'),
            'median_eui_benchmark': p.get('median_eui_benchmark'),
            'verticals': p['verticals'],
            'opex_by_vertical': p['opex_by_vertical'],
            # Stats by building type for filtering
            'building_types': p.get('building_types', []),
            'radio_types': p.get('radio_types', [])
        })

    summary_path = os.path.join(data_dir, 'summary.json')
    with open(summary_path, 'w') as f:
        json.dump(summary, f)
    summary_size = os.path.getsize(summary_path) / 1024
    print(f"  summary.json: {summary_size:.1f} KB ({len(summary)} portfolios)")

    # -------------------------------------------------------------------------
    # 2. INDIVIDUAL PORTFOLIO JSON FILES - Buildings for each portfolio
    # -------------------------------------------------------------------------
    total_portfolio_size = 0
    for idx, p in enumerate(portfolios):
        # Minimal building data needed for display
        buildings = [{
            'id': b['building_id'],
            'address': b['address'],
            'city': b.get('city', ''),
            'state': b.get('state', ''),
            'type': b.get('radio_type', ''),
            'building_type': b.get('building_type', ''),
            'vertical': b['vertical'],
            'sqft': b['sqft'],
            'opex': b['total_opex'],
            'valuation': b['valuation_impact'],
            'carbon': b['carbon_reduction'],
            'eui': b.get('site_eui'),
            'image': b.get('image', ''),
            'lat': b.get('latitude'),
            'lon': b.get('longitude')
        } for b in p['buildings']]

        portfolio_path = os.path.join(portfolios_dir, f'portfolio_{idx}.json')
        with open(portfolio_path, 'w') as f:
            json.dump(buildings, f)
        file_size = os.path.getsize(portfolio_path)
        total_portfolio_size += file_size

    avg_size = total_portfolio_size / len(portfolios) / 1024
    print(f"  portfolios/: {len(portfolios)} files, avg {avg_size:.1f} KB each")
    print(f"              Total: {total_portfolio_size / 1024 / 1024:.1f} MB")

    # -------------------------------------------------------------------------
    # 3. MAP_MARKERS.JSON - Just coordinates for map (loaded on map tab click)
    # -------------------------------------------------------------------------
    markers = []
    for b in all_buildings:
        if b.get('lat') and b.get('lon'):
            markers.append({
                'id': b['id'],
                'lat': b['lat'],
                'lon': b['lon'],
                'type': b.get('radio_type') or b.get('type', ''),
                'vertical': b['vertical'],
                'opex': b['total_opex']
            })

    markers_path = os.path.join(data_dir, 'map_markers.json')
    with open(markers_path, 'w') as f:
        json.dump(markers, f)
    markers_size = os.path.getsize(markers_path) / 1024
    print(f"  map_markers.json: {markers_size:.1f} KB ({len(markers)} markers)")

    # -------------------------------------------------------------------------
    # 4. ALL_BUILDINGS.JSON - Full building data for export (loaded on demand)
    # -------------------------------------------------------------------------
    all_buildings_export = [{
        'id': b['id'],
        'address': b['address'],
        'city': b.get('city', ''),
        'state': b.get('state', ''),
        'type': b.get('radio_type') or b.get('type', ''),
        'radio_type': b.get('radio_type', ''),
        'vertical': b['vertical'],
        'sqft': b['sqft'],
        'owner': b.get('owner', ''),
        'utility_savings': b['utility_savings'],
        'fine_avoidance': b['fine_avoidance'],
        'total_opex': b['total_opex'],
        'valuation_impact': b['valuation_impact'],
        'carbon': b['carbon'],
        'site_eui': b.get('site_eui', 0),
        'year_built': b.get('year_built', 0),
        'lat': b.get('lat'),
        'lon': b.get('lon'),
        'image': b.get('image', ''),
        'url': b.get('url', '')
    } for b in all_buildings]

    all_path = os.path.join(data_dir, 'all_buildings.json')
    with open(all_path, 'w') as f:
        json.dump(all_buildings_export, f)
    all_size = os.path.getsize(all_path) / 1024 / 1024
    print(f"  all_buildings.json: {all_size:.1f} MB (for CSV export, loaded on demand)")

    print(f"\n  INITIAL PAGE LOAD: ~{summary_size:.0f} KB")
    print(f"  (Down from ~24 MB = 99.6% reduction!)")

    return {
        'summary_path': summary_path,
        'portfolios_dir': portfolios_dir,
        'markers_path': markers_path,
        'all_buildings_path': all_path
    }


# =============================================================================
# TEST
# =============================================================================

if __name__ == '__main__':
    data = load_all_data()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    stats = data['stats']
    print(f"\nTotal Buildings: {stats['total_buildings']:,}")
    print(f"Total OpEx Avoidance: ${stats['total_opex_avoidance']:,.0f}")
    print(f"Total Carbon Reduction: {stats['total_carbon_reduction']:,.0f} tCO2e")
    print(f"Total Valuation Impact (Commercial): ${stats['total_valuation_impact']:,.0f}")

    print("\nBy Vertical:")
    for v, v_stats in stats['by_vertical'].items():
        print(f"  {v}: {v_stats['building_count']:,} buildings, ${v_stats['opex_avoidance']:,.0f} OpEx")

    print(f"\nPortfolios: {len(data['portfolios'])}")
    if data['portfolios']:
        print("Top 10 Portfolios by OpEx:")
        for i, p in enumerate(data['portfolios'][:10], 1):
            print(f"  {i}. {p['org_name']}: {p['building_count']} bldgs, ${p['total_opex_avoidance']:,.0f}/yr")
