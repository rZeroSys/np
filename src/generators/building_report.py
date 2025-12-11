"""
Nationwide Building Report Generator
Simply displays the data we have, no bullshit explanations.
"""

import pandas as pd
import sys
import os
import traceback
import subprocess
from pathlib import Path
from datetime import datetime
import pytz
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import multiprocessing

# NYC special buildings - use NYC building.py for these
NYC_BUILDING_SCRIPT = "/Users/forrestmiller/Desktop/New/Scripts/building.py"
NYC_BBLS = set()
try:
    nyc_df = pd.read_csv("/Users/forrestmiller/Desktop/New/data/10_year_savings_by_building.csv")
    NYC_BBLS = set(str(bbl) for bbl in nyc_df['bbl'].dropna())
    print(f"✓ Loaded {len(NYC_BBLS)} special NYC BBLs")
except Exception as e:
    print(f"Warning: Could not load NYC BBLs: {e}")

# Import functions from modules
from src.data.loader import load_csv, extract_filename
from src.config import (
    BUILDING_DATA_PATH, BUILDINGS_OUTPUT_DIR,
    IMAGES_DIR as CONFIG_IMAGES_DIR,
    AWS_BASE_URL,
    PORTFOLIO_ORGS_PATH
)

# Configuration - use centralized config
CSV_PATH = str(BUILDING_DATA_PATH)
OUTPUT_DIR = str(BUILDINGS_OUTPUT_DIR) + '/'
IMAGES_DIR = str(CONFIG_IMAGES_DIR)
AWS_BUCKET = AWS_BASE_URL

# Load organization display names mapping
ORG_DISPLAY_NAMES = {}
try:
    orgs_df = pd.read_csv(str(PORTFOLIO_ORGS_PATH))
    for _, org_row in orgs_df.iterrows():
        org_name = org_row.get('organization', '')
        display_name = org_row.get('display_name', '')
        if org_name and display_name and pd.notna(display_name) and str(display_name).strip():
            ORG_DISPLAY_NAMES[str(org_name).strip().lower()] = str(display_name).strip()
except Exception as e:
    print(f"Warning: Could not load organization display names: {e}")

# Load post-ODCV EUI lookup
EUI_POST_ODCV = {}
try:
    eui_df = pd.read_csv('/Users/forrestmiller/Desktop/nationwide-prospector/data/source/eui_post_odcv.csv')
    for _, eui_row in eui_df.iterrows():
        bid = eui_row.get('id_building', '')
        eui_val = eui_row.get('energy_site_eui_post_odcv')
        if bid and pd.notna(eui_val):
            EUI_POST_ODCV[bid] = float(eui_val)
except Exception as e:
    print(f"Warning: Could not load EUI post-ODCV data: {e}")

#===============================================================================
# CITY & BUILDING TYPE CLASSIFICATIONS
#===============================================================================

# City to disclosure law name mapping
CITY_DISCLOSURE_LAWS = {
    'New York': 'LL84',
    'Boston': 'BERDO',
    'Washington': 'DC BEPS',
    'Cambridge': 'BEUDO',
    'Los Angeles': 'EBEWE',
    'Chicago': 'Chicago Benchmarking Ordinance',
    'Seattle': 'Seattle Benchmarking Ordinance',
    'San Francisco': 'SF Environment Code',
    'Denver': 'Energize Denver',
    'Philadelphia': 'Philadelphia Benchmarking',
    'Portland': 'Portland Energy Reporting',
    'Atlanta': 'Atlanta Commercial Buildings Energy Efficiency Ordinance',
    'Kansas City': 'KC Benchmarking',
    'Orlando': 'BEWES',
    'St. Louis': 'St. Louis BEPS',
    'Austin': 'Austin ECAD',
    'Minneapolis': 'Minneapolis Energy Disclosure',
    'Montgomery County': 'Montgomery County Benchmarking',
    'default_ca': 'AB 802',
}

# Cities with Building Performance Standards (have fine avoidance)
BPS_CITIES = ['New York', 'Boston', 'Cambridge', 'Washington', 'Denver', 'Seattle', 'St. Louis']

# Building type categorizations for ODCV savings calculation
# Building types where vacancy is used in the ODCV formula: V + (1-V)(1-U)
# Per ODCV_SAVINGS_METHODOLOGY_COMPLETE.md - these have centralized HVAC where vacant space still gets ventilated
USES_VACANCY_FORMULA = ['Office', 'Medical Office', 'Mixed Use', 'Strip Mall']

SINGLE_TENANT_TYPES = [
    'K-12 School', 'Higher Ed', 'Preschool/Daycare', 'Retail Store',
    'Supermarket/Grocery', 'Wholesale Club', 'Enclosed Mall', 'Hotel',
    'Restaurant/Bar', 'Gym', 'Event Space', 'Theater', 'Library/Museum',
    'Bank Branch', 'Vehicle Dealership', 'Courthouse', 'Outpatient Clinic',
    'Sports/Gaming Center'
]

CONSTRAINED_TYPES = [
    'Inpatient Hospital', 'Specialty Hospital', 'Residential Care Facility',
    'Laboratory', 'Police Station', 'Fire Station'
]

#===============================================================================
# TOOLTIP DEFINITIONS
#===============================================================================

# Static tooltips - ONLY tooltips that are actually used in the report
TOOLTIPS = {
    'owner': "Sources: ENERGY STAR Portfolio Manager, city benchmarking filings, CoStar, SEC 10-K, corporate websites.",
    'energy_site_eui': "Energy use per square foot. Office average: 70-90. Source: city benchmarking law.",
    'district_steam': "Piped steam from central plant. Source: city benchmarking.",
    'fuel_oil': "Heating oil. Source: city benchmarking.",
    'pct_hvac_elec': "Source: EIA CBECS 2018 survey of 6,436 buildings. Adjusted for building type, climate, age, efficiency.",
    'carbon_reduction': "Source: EPA eGRID grid emission factors.",
}

#===============================================================================
# CORE UTILITY FUNCTIONS (needed by dynamic tooltips)
#===============================================================================

def safe_val(row, column, default=''):
    """Extract value safely"""
    try:
        if column not in row.index:
            return default
        val = row[column]
        if pd.isna(val) or val == '':
            return default
        return val
    except:
        return default

#===============================================================================
# DYNAMIC TOOLTIP FUNCTIONS
#===============================================================================

def get_law_name(row):
    """Get the energy disclosure law name for this building's city."""
    city = safe_val(row, 'loc_city', '')
    state = safe_val(row, 'loc_state', '')

    # Check for exact city match
    if city in CITY_DISCLOSURE_LAWS:
        return CITY_DISCLOSURE_LAWS[city]

    # California default
    if state == 'CA':
        return CITY_DISCLOSURE_LAWS['default_ca']

    # Generic fallback
    return 'energy disclosure'

def get_annual_savings_tooltip(row):
    """Dynamic tooltip for Annual Savings based on city's disclosure law."""
    law_name = get_law_name(row)
    return f"HVAC savings × utility rates. Sources: {law_name}, NREL utility rates by ZIP."

def get_property_value_tooltip(row):
    """Dynamic tooltip for Property Value Increase."""
    cap_rate = safe_num(row, 'val_cap_rate_pct')
    if cap_rate:
        cap_pct = cap_rate * 100
        multiplier = int(100 / cap_pct)
        return f"Annual savings ÷ {cap_pct:.1f}% cap rate. $1 saved → ${multiplier} higher value. Cap rate source: caprateindex.com."
    return "Annual savings ÷ cap rate. Cap rate source: caprateindex.com."

def get_energy_star_tooltip(row):
    """Dynamic tooltip for Energy Star Score."""
    law_name = get_law_name(row)
    return f"1-100 percentile ranking vs peers. 50 = median, 75+ = ENERGY STAR certified. Current score from {law_name}. Post-ODCV estimated using EPA efficiency ratio methodology: new EUI reduces ratio, improving percentile rank via gamma distribution. See docs/methodology/ENERGY_STAR_ESTIMATE_METHODOLOGY.md"

def get_electricity_kwh_tooltip(row):
    """Dynamic tooltip for electricity."""
    law_name = get_law_name(row)
    return f"Source: {law_name}. Cost includes energy charges (per kWh) and demand charges (per peak kW). Rates from NREL."

def get_natural_gas_tooltip(row):
    """Dynamic tooltip for natural gas."""
    law_name = get_law_name(row)
    return f"Source: {law_name}. Rate from NREL."

# Map of dynamic tooltip keys to their generator functions
DYNAMIC_TOOLTIPS = {
    'annual_savings': get_annual_savings_tooltip,
    'property_value_increase': get_property_value_tooltip,
    'energy_star_score': get_energy_star_tooltip,
    'energy_elec_kwh': get_electricity_kwh_tooltip,
    'natural_gas': get_natural_gas_tooltip,
}

#===============================================================================
# UTILITY FUNCTIONS
#===============================================================================

def entities_match(a, b):
    """Check if two entity names match (case-insensitive, whitespace-normalized)"""
    if not a or not b:
        return False
    if pd.isna(a) or pd.isna(b):
        return False
    return str(a).strip().lower() == str(b).strip().lower()

def get_org_display_name(org_name):
    """Get the display name for an organization, falling back to original name."""
    if not org_name or pd.isna(org_name):
        return org_name
    org_key = str(org_name).strip().lower()
    return ORG_DISPLAY_NAMES.get(org_key, org_name)

def safe_num(row, column, default=None):
    """Extract number safely, return None if not available"""
    try:
        if column not in row.index:
            return default
        val = row[column]
        if pd.isna(val) or val == '':
            return default
        return float(val)
    except:
        return default

def format_currency(value):
    """Format dollar amounts"""
    if value is None or value == 0:
        return "$0"
    try:
        val = float(value)
        if val >= 1e9:
            return f"${val/1e9:.2f}B"
        elif val >= 1e6:
            return f"${val/1e6:.1f}M"
        elif val >= 1e3:
            return f"${val/1e3:.0f}K"
        else:
            return f"${val:,.0f}"
    except:
        return "$0"

def format_number(value, decimals=0):
    """Format numbers with commas"""
    if value is None:
        return ""
    try:
        if decimals > 0:
            return f"{float(value):,.{decimals}f}"
        return f"{int(float(value)):,}"
    except:
        return ""

def escape(text):
    """Escape HTML"""
    if pd.isna(text) or text == '':
        return ''
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

def get_building_image_url(building_id):
    """Get AWS S3 URL for building image if it exists"""
    import glob
    pattern = os.path.join(IMAGES_DIR, f"{building_id}_*.jpg")
    matches = glob.glob(pattern)
    if matches:
        # Get filename and construct AWS URL
        filename = os.path.basename(matches[0])
        return f"{AWS_BUCKET}/images/{filename}"
    return None

def get_logo_filename(name):
    """Convert name to logo filename format (same as homepage)"""
    if not name or pd.isna(name):
        return None
    # Remove ampersands with surrounding spaces, then handle other special chars
    name = name.replace(' & ', ' ')  # Remove ampersand with spaces
    name = name.replace('&', '')      # Remove any remaining ampersands
    name = name.replace('.', '_')     # Periods to underscores
    name = name.replace("'", '_')     # Apostrophes to underscores
    name = name.replace(' ', '_')     # Spaces to underscores
    name = name.replace('(', '')      # Remove opening parentheses
    name = name.replace(')', '')      # Remove closing parentheses
    name = name.replace('/', '_')     # Forward slashes to underscores
    # Clean up any double underscores created by the transformations
    while '__' in name:
        name = name.replace('__', '_')
    # Remove leading/trailing underscores
    name = name.strip('_')
    return name

def tooltip(key, row=None):
    """Generate tooltip HTML span. If row is provided and key is dynamic, generates contextual tooltip."""
    # Check if this is a dynamic tooltip that needs row data
    if key in DYNAMIC_TOOLTIPS and row is not None:
        text = DYNAMIC_TOOLTIPS[key](row)
    else:
        text = TOOLTIPS.get(key, '')

    if not text:
        return ''
    return f'<span class="info-tooltip" data-tooltip="{escape(text)}" style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #0066cc; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>'

#===============================================================================
# HTML SECTIONS
#===============================================================================

def generate_hero(row):
    """Hero section - address with external link, centered with back button"""
    street = safe_val(row, 'loc_address', 'Address not available')
    city = safe_val(row, 'loc_city', '')
    state = safe_val(row, 'loc_state', '')
    zip_code = safe_val(row, 'loc_zip', '')

    # Build full address - only append city/state/zip if not already in loc_address
    if city and city in street:
        # Address already contains city, use as-is
        address = street
    else:
        # Address is just street, append city/state/zip
        address_parts = [street]
        if city and state:
            address_parts.append(f"{city}, {state}")
        if zip_code:
            address_parts[-1] = address_parts[-1] + f" {zip_code}" if len(address_parts) > 1 else zip_code
        address = ', '.join(address_parts) if len(address_parts) > 1 else street

    building_url = safe_val(row, 'id_source_url')
    has_url = building_url and str(building_url).lower() != 'nan'

    # Back button - big clickable area, uses JS to check 'from' param and return to correct tab
    back_btn = '''<a href="../index.html" onclick="event.preventDefault(); const from = new URLSearchParams(window.location.search).get('from'); window.location.href = '../index.html' + (from === 'cities' ? '#all-buildings' : '#portfolios');" style="position:absolute;left:10px;top:10px;color:white;text-decoration:none;font-size:14px;font-weight:600;display:flex;align-items:center;gap:6px;padding:8px 14px;background:rgba(0,0,0,0.3);border-radius:6px;z-index:10;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
        Back
    </a>'''

    if has_url:
        html = f"""
    <div class="hero" style="position:relative;text-align:center;">
        {back_btn}
        <h1><a href="{escape(building_url)}" target="_blank" style="color: inherit; text-decoration: none;">{escape(address)} <span style="font-size: 0.6em; font-weight: bold; opacity: 1; background: rgba(255,255,255,0.25); padding: 2px 6px; border-radius: 4px; margin-left: 8px;">↗</span></a></h1>
    </div>
"""
    else:
        html = f"""
    <div class="hero" style="position:relative;text-align:center;">
        {back_btn}
        <h1>{escape(address)}</h1>
    </div>
"""
    return html

def generate_building_info(row):
    """Property information table (merged from Building Info + Property Metrics)"""
    html = """
    <div class="section">
        <h2>Property</h2>
        <table>
"""

    # Property Name (link is now in header)
    property_name = safe_val(row, 'id_property_name')
    has_property_name = property_name and str(property_name).lower() != 'nan'

    if has_property_name:
        html += f"<tr><td>Name</td><td>{escape(property_name)}</td></tr>\n"

    # Size
    sqft = safe_num(row, 'bldg_sqft')
    if sqft:
        html += f"<tr><td>Size</td><td>{format_number(sqft)} sqft</td></tr>\n"

    # Type
    bldg_type = safe_val(row, 'bldg_type')
    if bldg_type and str(bldg_type).lower() != 'nan':
        html += f"<tr><td>Type</td><td>{escape(bldg_type)}</td></tr>\n"

    # Year Built
    year = safe_num(row, 'bldg_year_built')
    if year:
        html += f"<tr><td>Year Built</td><td>{int(year)}</td></tr>\n"

    # Owner/Tenant/Property Manager - collapsed when matching
    owner = safe_val(row, 'org_owner')
    pm = safe_val(row, 'org_manager')
    tenant = safe_val(row, 'org_tenant')
    tenant_sub = safe_val(row, 'org_tenant_subunit')

    # Normalize: filter out invalid values
    owner = owner if owner and str(owner).lower() != 'nan' else None
    pm = pm if pm and str(pm).lower() != 'nan' else None
    tenant = tenant if tenant and str(tenant).lower() != 'nan' else None
    tenant_sub = tenant_sub if tenant_sub and str(tenant_sub).lower() != 'nan' else None

    # Helper to build org - logo and name on same row (uses display name)
    def build_org_with_logo(name):
        if not name:
            return ""
        display_name = get_org_display_name(name)
        logo_filename = get_logo_filename(name)  # Logo lookup uses original name
        if logo_filename:
            logo_url = f"{AWS_BUCKET}/logos/{logo_filename}.png"
            return f'{escape(display_name)} <img src="{logo_url}" style="height:25px;vertical-align:middle;margin-left:8px;" onerror="this.style.display=\'none\'">'
        return f'{escape(display_name)}'

    # Helper for logo only (returns just the img tag)
    def build_logo_img(name, height=30):
        if not name:
            return ""
        logo_filename = get_logo_filename(name)
        if logo_filename:
            logo_url = f"{AWS_BUCKET}/logos/{logo_filename}.png"
            return f'<img src="{logo_url}" style="height:{height}px;" onerror="this.style.display=\'none\'">'
        return ""

    # Build tenant with sub-org - logos only, centered
    def build_tenant_with_sub(tenant_name, sub_name):
        if not tenant_name:
            return ""
        tenant_display = get_org_display_name(tenant_name)

        if sub_name:
            sub_logo = build_logo_img(sub_name, 30)
            tenant_logo = build_logo_img(tenant_name, 30)
            # Logos centered using margin:auto on block element
            if sub_logo and tenant_logo and sub_logo != tenant_logo:
                return f"<div style=''>{tenant_logo} &nbsp; {sub_logo}</div>"
            elif sub_logo:
                return f"<div style=''>{sub_logo}</div>"
            elif tenant_logo:
                return f"<div style=''>{tenant_logo}</div>"
            # Fallback to text if no logos
            return f'{escape(tenant_display)} ({escape(get_org_display_name(sub_name))})'
        else:
            # No sub-org, show tenant name with logo inline
            tenant_logo = build_logo_img(tenant_name, 25)
            if tenant_logo:
                return f'{escape(tenant_display)} {tenant_logo}'
            return f'{escape(tenant_display)}'

    tenant_sub_html = ""  # No longer used separately

    # Determine matching pattern and render rows
    all_same = owner and entities_match(owner, pm) and entities_match(owner, tenant)
    owner_tenant = owner and tenant and entities_match(owner, tenant) and not all_same
    owner_pm = owner and pm and entities_match(owner, pm) and not all_same
    tenant_pm = tenant and pm and entities_match(tenant, pm) and not all_same

    # No special td style - centering handled in content
    td_center = ""

    if all_same:
        # All three are the same entity - show as "All Roles"
        html += f"<tr><td>All Roles{tooltip('owner')}</td><td{td_center}>{build_tenant_with_sub(owner, tenant_sub)}</td></tr>"
    elif owner_tenant and owner_pm:
        # Owner matches both tenant and PM - show as "All Roles"
        html += f"<tr><td>All Roles{tooltip('owner')}</td><td{td_center}>{build_tenant_with_sub(tenant, tenant_sub)}</td></tr>"
    elif owner_tenant:
        # Owner and Tenant match - owner/occupier
        html += f"<tr><td>Owner/Occupier{tooltip('owner')}</td><td{td_center}>{build_tenant_with_sub(tenant, tenant_sub)}</td></tr>"
        if pm:
            html += f"<tr><td>Manager</td><td>{build_org_with_logo(pm)}</td></tr>"
    elif owner_pm:
        # Owner and Property Manager match - owner/operator
        html += f"<tr><td>Owner/Operator{tooltip('owner')}</td><td>{build_org_with_logo(owner)}</td></tr>"
        if tenant:
            html += f"<tr><td>Tenant</td><td{td_center}>{build_tenant_with_sub(tenant, tenant_sub)}</td></tr>"
    elif tenant_pm:
        # Tenant and Property Manager match
        if owner:
            html += f"<tr><td>Owner{tooltip('owner')}</td><td>{build_org_with_logo(owner)}</td></tr>"
        html += f"<tr><td>Tenant & Manager</td><td{td_center}>{build_tenant_with_sub(tenant, tenant_sub)}</td></tr>"
    else:
        # All different - show separately
        if owner:
            html += f"<tr><td>Owner{tooltip('owner')}</td><td>{build_org_with_logo(owner)}</td></tr>"
        if pm:
            html += f"<tr><td>Manager</td><td>{build_org_with_logo(pm)}</td></tr>"
        if tenant:
            html += f"<tr><td>Tenant</td><td{td_center}>{build_tenant_with_sub(tenant, tenant_sub)}</td></tr>"

    # Vacancy/Utilization rates are shown in the ODCV Savings % tooltip dynamically
    # Energy Star Score moved to Savings section

    html += """
        </table>
    </div>
"""
    return html

def generate_energy_use(row):
    """Energy use table with HVAC % inline"""
    # Get HVAC percentages
    pct_elec_hvac = safe_num(row, 'hvac_pct_elec')
    pct_gas_hvac = safe_num(row, 'hvac_pct_gas')
    pct_steam_hvac = safe_num(row, 'hvac_pct_steam')
    pct_fuel_hvac = safe_num(row, 'hvac_pct_fuel_oil')

    html = f"""
    <div class="section">
        <h2>Energy Use</h2>
        <table>
            <tr>
                <th></th>
                <th>Annual Use</th>
                <th>Annual Cost</th>
                <th>HVAC %{tooltip('pct_hvac_elec')}</th>
            </tr>
"""

    # Electricity
    elec_kwh = safe_num(row, 'energy_elec_kwh')
    elec_cost = safe_num(row, 'cost_elec_total_annual')
    if elec_kwh or elec_cost:
        hvac_pct_str = f"{pct_elec_hvac*100:.0f}%" if pct_elec_hvac else "—"
        html += f"""
            <tr>
                <td>Electricity{tooltip('energy_elec_kwh', row)}</td>
                <td>{format_number(elec_kwh) + ' kWh' if elec_kwh else ''}</td>
                <td>{format_currency(elec_cost) if elec_cost else '$0'}</td>
                <td>{hvac_pct_str}</td>
            </tr>
"""

    # Natural Gas
    gas_use = safe_num(row, 'energy_gas_kbtu')
    gas_cost = safe_num(row, 'cost_gas_annual')
    fuel_use = safe_num(row, 'energy_fuel_oil_kbtu')
    fuel_cost = safe_num(row, 'cost_fuel_oil_annual')

    if gas_use and gas_use > 0:
        gas_therms = gas_use / 100  # kBtu to therms
        hvac_pct_str = f"{pct_gas_hvac*100:.0f}%" if pct_gas_hvac else "—"
        html += f"""
            <tr>
                <td>Natural Gas{tooltip('natural_gas', row)}</td>
                <td>{format_number(gas_therms)} therms</td>
                <td>{format_currency(gas_cost) if gas_cost else '$0'}</td>
                <td>{hvac_pct_str}</td>
            </tr>
"""

    # Fuel Oil
    if fuel_use and fuel_use > 0:
        fuel_gal = fuel_use / 138.5  # kBtu to gallons
        hvac_pct_str = f"{pct_fuel_hvac*100:.0f}%" if pct_fuel_hvac else "—"
        html += f"""
            <tr>
                <td>Fuel Oil{tooltip('fuel_oil')}</td>
                <td>{format_number(fuel_gal)} gallons</td>
                <td>{format_currency(fuel_cost) if fuel_cost else '$0'}</td>
                <td>{hvac_pct_str}</td>
            </tr>
"""

    # District Steam
    steam_use = safe_num(row, 'energy_steam_kbtu')
    steam_cost = safe_num(row, 'cost_steam_annual')
    if steam_use and steam_use > 0:
        steam_mlb = steam_use / 1194  # kBtu to Mlb
        hvac_pct_str = f"{pct_steam_hvac*100:.0f}%" if pct_steam_hvac else "—"
        html += f"""
            <tr>
                <td>District Steam{tooltip('district_steam')}</td>
                <td>{format_number(steam_mlb, 2)} Mlb</td>
                <td>{format_currency(steam_cost) if steam_cost else '$0'}</td>
                <td>{hvac_pct_str}</td>
            </tr>
"""

    html += """
        </table>
"""

    # GHG Emissions
    ghg = safe_num(row, 'carbon_emissions_total_mt')
    if ghg:
        html += f"""
        <p style="margin-top: 15px;"><strong>Total GHG Emissions{tooltip('total_ghg', row)}:</strong> {format_number(ghg, 1)} tCO2e/yr</p>
"""

    html += """
    </div>
"""
    return html

def generate_electricity_details(row):
    """Electricity cost breakdown"""
    html = """
    <div class="section">
        <h2>Electricity Details</h2>
        <table>
"""

    # Total cost
    total_cost = safe_num(row, 'cost_elec_total_annual')
    if total_cost:
        html += f"<tr><td>Total Annual Cost{tooltip('total_annual_cost')}</td><td>{format_currency(total_cost)}</td></tr>"

    # Energy charges
    energy_cost = safe_num(row, 'cost_elec_energy_annual')
    if energy_cost:
        html += f"<tr><td>Energy Charges{tooltip('energy_charges')}</td><td>{format_currency(energy_cost)}</td></tr>"

    # Demand charges
    demand_cost = safe_num(row, 'cost_elec_demand_annual')
    if demand_cost:
        html += f"<tr><td>Demand Charges{tooltip('demand_charges')}</td><td>{format_currency(demand_cost)}</td></tr>"

    # Energy rate
    energy_rate = safe_num(row, 'cost_elec_rate_kwh')
    if energy_rate:
        html += f"<tr><td>Energy Rate{tooltip('energy_rate')}</td><td>${energy_rate:.4f}/kWh</td></tr>"

    # Demand rate
    demand_rate = safe_num(row, 'cost_elec_rate_demand_kw')
    if demand_rate:
        html += f"<tr><td>Demand Rate{tooltip('demand_rate')}</td><td>${demand_rate:.2f}/kW</td></tr>"

    # Peak demand
    peak_kw = safe_num(row, 'cost_elec_peak_kw')
    if peak_kw:
        html += f"<tr><td>Peak Demand{tooltip('peak_demand')}</td><td>{format_number(peak_kw)} kW</td></tr>"

    # Load factor
    load_factor = safe_num(row, 'cost_elec_load_factor')
    if load_factor:
        html += f"<tr><td>Load Factor{tooltip('load_factor', row)}</td><td>{load_factor*100:.1f}%</td></tr>"

    # Utility
    utility = safe_val(row, 'cost_utility_name')
    if utility:
        html += f"<tr><td>Utility Provider{tooltip('utility_provider')}</td><td>{escape(utility)}</td></tr>"

    html += """
        </table>
    </div>
"""
    return html

def generate_hvac_breakdown(row):
    """HVAC energy breakdown"""
    html = f"""
    <div class="section">
        <h2>HVAC Breakdown</h2>
        <table>
            <tr>
                <th></th>
                <th>% HVAC{tooltip('pct_hvac_elec')}</th>
                <th>HVAC Cost</th>
            </tr>
"""

    # Electricity HVAC
    pct_elec_hvac = safe_num(row, 'hvac_pct_elec')
    elec_cost = safe_num(row, 'cost_elec_total_annual', 0)
    if pct_elec_hvac:
        hvac_elec_cost = elec_cost * pct_elec_hvac if elec_cost else 0
        html += f"""
            <tr>
                <td>Electricity</td>
                <td>{pct_elec_hvac*100:.1f}%</td>
                <td>{format_currency(hvac_elec_cost)}</td>
            </tr>
"""

    # Gas HVAC
    pct_gas_hvac = safe_num(row, 'hvac_pct_gas')
    gas_cost = safe_num(row, 'cost_gas_annual', 0)
    if pct_gas_hvac and gas_cost:
        hvac_gas_cost = gas_cost * pct_gas_hvac
        html += f"""
            <tr>
                <td>Natural Gas</td>
                <td>{pct_gas_hvac*100:.1f}%</td>
                <td>{format_currency(hvac_gas_cost)}</td>
            </tr>
"""

    # Steam HVAC
    pct_steam_hvac = safe_num(row, 'hvac_pct_steam')
    steam_cost = safe_num(row, 'cost_steam_annual', 0)
    if pct_steam_hvac and steam_cost:
        hvac_steam_cost = steam_cost * pct_steam_hvac
        html += f"""
            <tr>
                <td>District Steam</td>
                <td>{pct_steam_hvac*100:.1f}%</td>
                <td>{format_currency(hvac_steam_cost)}</td>
            </tr>
"""

    # Fuel Oil HVAC
    pct_fuel_hvac = safe_num(row, 'hvac_pct_fuel_oil')
    fuel_cost = safe_num(row, 'cost_fuel_oil_annual', 0)
    if pct_fuel_hvac and fuel_cost:
        hvac_fuel_cost = fuel_cost * pct_fuel_hvac
        html += f"""
            <tr>
                <td>Fuel Oil</td>
                <td>{pct_fuel_hvac*100:.1f}%</td>
                <td>{format_currency(hvac_fuel_cost)}</td>
            </tr>
"""

    html += """
        </table>
"""

    # Total HVAC cost
    total_hvac_cost = safe_num(row, 'hvac_cost_total_annual')
    if total_hvac_cost:
        html += f"""
        <p style="margin-top: 15px;"><strong>Total HVAC Cost:</strong> {format_currency(total_hvac_cost)}</p>
"""

    # HVAC Chart
    if pct_elec_hvac:
        html += f"""
        <div class="chart-container">
            <canvas id="hvacChart"></canvas>
        </div>
        <script>
        new Chart(document.getElementById('hvacChart'), {{
            type: 'bar',
            data: {{
                labels: ['Electricity HVAC %'],
                datasets: [{{
                    label: 'HVAC',
                    data: [{pct_elec_hvac*100:.1f}],
                    backgroundColor: '#0066cc'
                }}, {{
                    label: 'Non-HVAC',
                    data: [{(1-pct_elec_hvac)*100:.1f}],
                    backgroundColor: '#94a3b8'
                }}]
            }},
            options: {{
                indexAxis: 'y',
                scales: {{
                    x: {{
                        stacked: true,
                        max: 100,
                        ticks: {{
                            callback: function(value) {{ return value + '%'; }}
                        }}
                    }},
                    y: {{ stacked: true }}
                }},
                responsive: true,
                plugins: {{
                    legend: {{ position: 'bottom' }}
                }}
            }}
        }});
        </script>
"""

    html += """
    </div>
"""
    return html

def generate_energy_section(row):
    """Unified Energy section - Energy Use with HVAC % inline"""
    # Check if we have any energy data at all
    elec_kwh = safe_num(row, 'energy_elec_kwh')
    elec_cost = safe_num(row, 'cost_elec_total_annual')
    gas_use = safe_num(row, 'energy_gas_kbtu')
    steam_use = safe_num(row, 'energy_steam_kbtu')
    fuel_use = safe_num(row, 'energy_fuel_oil_kbtu')

    # Skip entire section if no energy data
    if not any([elec_kwh, elec_cost, gas_use, steam_use, fuel_use]):
        return ""

    # Get HVAC percentages
    pct_elec_hvac = safe_num(row, 'hvac_pct_elec')
    pct_gas_hvac = safe_num(row, 'hvac_pct_gas')
    pct_steam_hvac = safe_num(row, 'hvac_pct_steam')
    pct_fuel_hvac = safe_num(row, 'hvac_pct_fuel_oil')
    gas_cost = safe_num(row, 'cost_gas_annual')
    steam_cost = safe_num(row, 'cost_steam_annual')
    fuel_cost = safe_num(row, 'cost_fuel_oil_annual')

    html = f"""
    <div class="section">
        <h2>Energy</h2>
        <table>
            <tr>
                <th></th>
                <th>Annual Use</th>
                <th>Annual Cost</th>
                <th>HVAC %{tooltip('pct_hvac_elec')}</th>
            </tr>
"""

    # Electricity
    if elec_kwh or elec_cost:
        hvac_str = f"{pct_elec_hvac*100:.0f}%" if pct_elec_hvac else "—"
        html += f"""
            <tr>
                <td>Electricity{tooltip('energy_elec_kwh', row)}</td>
                <td>{format_number(elec_kwh) + ' kWh' if elec_kwh else ''}</td>
                <td>{format_currency(elec_cost) if elec_cost else ''}</td>
                <td>{hvac_str}</td>
            </tr>
"""

    # Natural Gas
    if gas_use and gas_use > 0:
        gas_therms = gas_use / 100
        hvac_str = f"{pct_gas_hvac*100:.0f}%" if pct_gas_hvac else "—"
        html += f"""
            <tr>
                <td>Natural Gas{tooltip('natural_gas', row)}</td>
                <td>{format_number(gas_therms)} therms</td>
                <td>{format_currency(gas_cost) if gas_cost else ''}</td>
                <td>{hvac_str}</td>
            </tr>
"""

    # Fuel Oil
    if fuel_use and fuel_use > 0:
        fuel_gal = fuel_use / 138.5
        hvac_str = f"{pct_fuel_hvac*100:.0f}%" if pct_fuel_hvac else "—"
        html += f"""
            <tr>
                <td>Fuel Oil{tooltip('fuel_oil')}</td>
                <td>{format_number(fuel_gal)} gallons</td>
                <td>{format_currency(fuel_cost) if fuel_cost else ''}</td>
                <td>{hvac_str}</td>
            </tr>
"""

    # District Steam
    if steam_use and steam_use > 0:
        steam_mlb = steam_use / 1194
        hvac_str = f"{pct_steam_hvac*100:.0f}%" if pct_steam_hvac else "—"
        html += f"""
            <tr>
                <td>District Steam{tooltip('district_steam')}</td>
                <td>{format_number(steam_mlb, 2)} Mlb</td>
                <td>{format_currency(steam_cost) if steam_cost else ''}</td>
                <td>{hvac_str}</td>
            </tr>
"""

    html += """
        </table>
    </div>
"""
    return html

def generate_savings_section(row):
    """Savings section - shows Current vs New values with Change column"""
    # Get all the values we need
    elec_cost = safe_num(row, 'cost_elec_total_annual', 0)
    gas_cost = safe_num(row, 'cost_gas_annual', 0)
    steam_cost = safe_num(row, 'cost_steam_annual', 0)
    fuel_oil_cost = safe_num(row, 'cost_fuel_oil_annual', 0)
    total_energy_cost = elec_cost + gas_cost + steam_cost + fuel_oil_cost

    odcv_savings = safe_num(row, 'odcv_hvac_savings_annual_usd')
    val_impact = safe_num(row, 'val_odcv_impact_usd')
    carbon_current = safe_num(row, 'carbon_emissions_total_mt')
    carbon_reduction = safe_num(row, 'odcv_carbon_reduction_yr1_mt')

    # Skip if no savings data
    if not odcv_savings:
        return ""

    # Calculate new values
    new_utility_cost = total_energy_cost - odcv_savings if total_energy_cost else None
    new_carbon = carbon_current - carbon_reduction if carbon_current and carbon_reduction else None

    # For property value, we don't have current value, so just show the increase
    # We'll show N/A for current/new and just the change

    html = """
    <div class="section">
        <h2>Savings</h2>
        <table>
            <tr>
                <th></th>
                <th>Current</th>
                <th>New</th>
                <th>Change</th>
            </tr>
"""

    # Utility Cost row
    if total_energy_cost and odcv_savings:
        html += f"""
            <tr>
                <td>Utility Cost{tooltip('annual_savings', row)}</td>
                <td>{format_currency(total_energy_cost)}/yr</td>
                <td>{format_currency(new_utility_cost)}/yr</td>
                <td style="color: #16a34a; font-weight: 600;">-{format_currency(odcv_savings)}/yr</td>
            </tr>
"""

    # Site EUI row
    current_eui = safe_num(row, 'energy_site_eui')
    building_id = safe_val(row, 'id_building', '')
    new_eui = EUI_POST_ODCV.get(building_id)
    if current_eui and new_eui:
        eui_reduction = current_eui - new_eui
        html += f"""
            <tr>
                <td>Site EUI{tooltip('energy_site_eui')}</td>
                <td>{format_number(current_eui, 1)} kBtu/sqft</td>
                <td>{format_number(new_eui, 1)} kBtu/sqft</td>
                <td style="color: #16a34a; font-weight: 600;">-{format_number(eui_reduction, 1)} kBtu/sqft</td>
            </tr>
"""

    # Carbon Emissions row
    if carbon_current and carbon_reduction:
        html += f"""
            <tr>
                <td>Carbon Emissions{tooltip('carbon_reduction')}</td>
                <td>{format_number(carbon_current, 1)} tCO2e/yr</td>
                <td>{format_number(new_carbon, 1)} tCO2e/yr</td>
                <td style="color: #16a34a; font-weight: 600;">-{format_number(carbon_reduction, 1)} tCO2e/yr</td>
            </tr>
"""

    # Property Value row - only show impact, not current/new values
    if val_impact and val_impact > 0:
        html += f"""
            <tr>
                <td>Property Value{tooltip('property_value_increase', row)}</td>
                <td>—</td>
                <td>—</td>
                <td style="color: #16a34a; font-weight: 600;">+{format_currency(val_impact)}</td>
            </tr>
"""

    # Energy Star Score row
    current_es = safe_num(row, 'energy_star_score')
    post_es = safe_num(row, 'energy_star_score_post_odcv')
    if current_es:
        current_es_str = f"{int(current_es)}"
        post_es_str = f"{int(post_es)}" if post_es else '—'
        if post_es and post_es > current_es:
            change = int(post_es - current_es)
            change_str = f'<td style="color: #16a34a; font-weight: 600;">+{change}</td>'
        else:
            change_str = '<td>—</td>'
        html += f"""
            <tr>
                <td>Energy Star Score{tooltip('energy_star_score', row)}</td>
                <td>{current_es_str}</td>
                <td>{post_es_str}</td>
                {change_str}
            </tr>
"""

    html += """
        </table>
    </div>
"""
    return html

#===============================================================================
# MAIN REPORT GENERATOR
#===============================================================================

def generate_html_report(row):
    """Generate complete HTML report"""
    building_id = safe_val(row, 'id_building', 'UNKNOWN')
    timestamp = datetime.now(pytz.timezone('US/Eastern')).strftime('%Y-%m-%d %H:%M:%S %Z')

    html = f"""<!DOCTYPE html>
<!-- Generated: {timestamp} -->
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Building Report - {building_id}</title>
    <link rel="icon" type="image/png" href="https://rzero.com/wp-content/themes/rzero/build/images/favicons/favicon.png">

    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.js"></script>

    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #1a202c;
            background: #f9fafb;
            padding: 20px;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}

        /* Page Header */
        .page-header {{
            background: url('https://rzero.com/wp-content/uploads/2025/02/bg-cta-bottom.jpg') center/cover;
            padding: 15px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 70px;
            position: relative;
        }}

        .page-header .back-link {{
            position: absolute;
            left: 15px;
            top: 50%;
            transform: translateY(-50%);
            color: rgba(255, 255, 255, 0.7);
            text-decoration: none;
            font-size: 11px;
            display: flex;
            align-items: center;
            gap: 4px;
        }}

        .page-header .back-link:hover {{
            color: white;
        }}

        .page-header .header-branding {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 4px;
        }}

        .page-header .header-title {{
            color: white;
            font-size: 11px;
            font-weight: 500;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            opacity: 0.9;
        }}

        .page-header .header-branding a {{
            display: block;
        }}

        /* Hero */
        .hero {{
            background: url('https://rzero.com/wp-content/uploads/2025/02/bg-cta-bottom.jpg') center/cover;
            color: white;
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}

        .hero h1 {{
            font-size: 1.3em;
            margin-bottom: 3px;
        }}

        .hero .address {{
            font-size: 0.9em;
            opacity: 0.9;
            margin-bottom: 2px;
        }}

        .hero .building-info {{
            font-size: 0.95em;
            opacity: 0.9;
            margin-bottom: 0;
            letter-spacing: 0.3px;
        }}

        .hero .opportunity {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }}

        .hero .metric {{
            background: rgba(255,255,255,0.1);
            padding: 10px;
            border-radius: 6px;
        }}

        .hero .metric-label {{
            font-size: 0.85em;
            opacity: 0.9;
        }}

        .hero .metric-value {{
            font-size: 1.5em;
            font-weight: 700;
        }}

        /* Sections */
        .section {{
            margin: 40px 0;
        }}

        h2 {{
            font-size: 1.8em;
            color: #1a202c;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #0066cc;
        }}

        /* Tables */
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}

        th {{
            background: #0066cc;
            color: white;
            padding: 12px;
            text-align: left;
        }}

        td {{
            padding: 12px;
            border-bottom: 1px solid #e5e7eb;
        }}

        tr:hover {{
            background: #f9fafb;
        }}

        /* Chart */
        .chart-container {{
            margin: 30px 0;
            padding: 20px;
            background: #f9fafb;
            border-radius: 6px;
        }}

        canvas {{
            max-height: 300px;
        }}

        /* Mobile */
        @media (max-width: 768px) {{
            .container {{
                padding: 20px;
            }}
            .hero h1 {{
                font-size: 1.8em;
            }}
            .hero .opportunity {{
                grid-template-columns: 1fr;
            }}
        }}

        /* Print */
        @media print {{
            body {{
                background: white;
                padding: 0;
            }}
            .container {{
                box-shadow: none;
            }}
        }}

        /* Tooltip Styles */
        .info-tooltip {{
            display: inline-block;
            margin-left: 5px;
            width: 16px;
            height: 16px;
            background-color: #0066cc;
            color: white;
            border-radius: 50%;
            text-align: center;
            line-height: 16px;
            font-size: 12px;
            cursor: help;
            position: relative;
        }}

        .info-tooltip::after {{
            content: attr(data-tooltip);
            position: absolute;
            bottom: 125%;
            left: 50%;
            transform: translateX(-50%);
            background-color: #333;
            color: white;
            padding: 8px 12px;
            border-radius: 6px;
            white-space: normal;
            width: 500px;
            max-width: 90vw;
            font-size: 13px;
            line-height: 1.4;
            text-align: left;
            z-index: 2147483647;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.3s, visibility 0.3s;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            pointer-events: none;
        }}

        .info-tooltip:hover::after {{
            opacity: 1;
            visibility: visible;
        }}

        .info-tooltip::before {{
            content: "";
            position: absolute;
            bottom: 115%;
            left: 50%;
            transform: translateX(-50%);
            border: 6px solid transparent;
            border-top-color: #333;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.3s, visibility 0.3s;
        }}

        .info-tooltip:hover::before {{
            opacity: 1;
            visibility: visible;
        }}

        /* Mobile tooltip adjustments */
        @media (max-width: 768px) {{
            .info-tooltip::after {{
                width: 280px;
                font-size: 12px;
                left: auto;
                right: 0;
                transform: none;
            }}

            .info-tooltip::before {{
                left: auto;
                right: 10px;
                transform: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
"""

    # Add sections
    html += generate_hero(row)

    # Add building image if exists - size adapts to resolution via onload
    image_url = get_building_image_url(building_id)
    if image_url:
        html += f"""
    <div class="section" style="margin: 0; padding: 0;">
        <img src="{image_url}" alt="Building {building_id}" id="building-image" style="width: 100%; max-height: 400px; object-fit: cover; border-radius: 8px;" onload="
            var img = this;
            var ratio = img.naturalWidth / img.naturalHeight;
            if (ratio > 2) {{ img.style.maxHeight = '300px'; }}
            else if (ratio > 1.5) {{ img.style.maxHeight = '400px'; }}
            else if (ratio < 0.8) {{ img.style.maxHeight = '500px'; img.style.objectFit = 'contain'; }}
            else {{ img.style.maxHeight = '450px'; }}
        ">
    </div>
"""

    # 1. Building & Property
    html += generate_building_info(row)

    # 2. Energy
    html += generate_energy_section(row)

    # 3. Savings
    html += generate_savings_section(row)

    # Close container
    html += """
    </div>
</body>
</html>
"""
    return html

def generate_batch_reports(args):
    """Generate a batch of building reports - worker function for parallel processing"""
    rows_batch, output_dir = args
    results = []

    for row_dict, idx in rows_batch:
        row = pd.Series(row_dict)
        building_id = row.get('id_building', f'unknown_{idx}')
        safe_building_id = building_id.replace('/', '_').replace('\\', '_')

        try:
            html = generate_html_report(row)
            output_path = f"{output_dir}{safe_building_id}.html"
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html)
            results.append((building_id, True, None))
        except Exception as e:
            results.append((building_id, False, str(e)))

    return results


def generate_single_report(args):
    """Generate a single building report - worker function for parallel processing"""
    row_dict, idx, output_dir = args

    # Convert dict back to pandas Series for compatibility
    row = pd.Series(row_dict)
    building_id = row.get('id_building', f'unknown_{idx}')
    safe_building_id = building_id.replace('/', '_').replace('\\', '_')

    try:
        html = generate_html_report(row)
        output_path = os.path.join(output_dir, f"{safe_building_id}.html")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        return (building_id, True, None)
    except Exception as e:
        return (building_id, False, str(e))


def run_nyc_batch_live(bbls, output_dir):
    """Run NYC buildings with LIVE streaming output"""
    if not bbls:
        return 0, 0

    batch_file = '/tmp/nyc_batch_all.txt'
    with open(batch_file, 'w') as f:
        f.write('\n'.join(bbls))

    success_count = 0
    error_count = 0

    try:
        # Use Popen for live streaming output
        process = subprocess.Popen(
            ['python3', '-u', NYC_BUILDING_SCRIPT, '--batch-file', batch_file, output_dir],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1  # Line buffered
        )

        # Stream output in real-time
        for line in iter(process.stdout.readline, ''):
            line = line.rstrip()
            if line:
                print(f"  [NYC] {line}", flush=True)
                # Count building completions (✓ N/M NYC_BBL pattern)
                if '✓' in line and 'NYC_' in line:
                    success_count += 1
                elif '❌' in line or 'Error' in line:
                    error_count += 1

        process.wait()
        return success_count, error_count

    except Exception as e:
        print(f"  [NYC] Error: {e}")
        return success_count, len(bbls) - success_count


def generate_nyc_special_reports(nyc_building_ids, output_dir):
    """Generate NYC reports with LIVE streaming output"""
    if not nyc_building_ids:
        return 0, 0

    print(f"\n{'='*70}")
    print(f"NYC BUILDINGS - LIVE PROGRESS")
    print(f"{'='*70}")

    start_time = time.time()
    bbls = [bid.replace('NYC_', '') for bid in nyc_building_ids]
    print(f"Processing {len(bbls)} NYC buildings...\n")

    # Single batch with live streaming - no chunking overhead
    generated, errors = run_nyc_batch_live(bbls, output_dir)

    elapsed = time.time() - start_time
    rate = generated / elapsed if elapsed > 0 else 0
    print(f"\n✓ NYC: {generated} ok, {errors} err in {elapsed:.0f}s ({rate:.1f}/sec)\n")
    return generated, errors


def main():
    """Main execution with parallel processing - OPTIMIZED FOR SPEED"""
    print("=" * 70)
    print("Building Reports Generator - Nationwide Prospector (TURBO)")
    print("=" * 70)
    print()

    # Ensure output directory exists
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    output_dir = OUTPUT_DIR if OUTPUT_DIR.endswith('/') else OUTPUT_DIR + '/'
    print(f"✓ Output directory: {output_dir}\n")

    # Load data
    print("Loading data...")
    df = load_csv(CSV_PATH)
    print(f"✓ Loaded {len(df)} buildings from CSV")

    # Remove buildings without coordinates
    df_clean = df.dropna(subset=['loc_lat', 'loc_lon'])
    removed = len(df) - len(df_clean)
    if removed > 0:
        print(f"⚠ Removed {removed} buildings without coordinates")

    # Check for specific building ID in command line args
    if len(sys.argv) > 1:
        building_id = sys.argv[1]
        df_to_process = df_clean[df_clean['id_building'] == building_id]
        if len(df_to_process) == 0:
            print(f"\n✗ Building ID '{building_id}' not found in dataset")
            sys.exit(1)

        # Check if it's a NYC special building
        if building_id.startswith('NYC_'):
            bbl = building_id.replace('NYC_', '')
            if bbl in NYC_BBLS:
                print(f"Generating NYC special report for: {building_id}\n")
                nyc_gen, nyc_err = generate_nyc_special_reports([building_id], output_dir)
                if nyc_gen > 0:
                    print(f"✓ Generated NYC special report for {building_id}")
                else:
                    print(f"✗ Error generating NYC special report for {building_id}")
                return

        print(f"Generating report for single building: {building_id}\n")
        for idx, row in df_to_process.iterrows():
            result = generate_single_report((row.to_dict(), idx, output_dir))
            if result[1]:
                print(f"✓ Generated report for {result[0]}")
            else:
                print(f"✗ Error for {result[0]}: {result[2]}")
        return

    df_to_process = df_clean
    total = len(df_to_process)
    print(f"Total buildings to process: {total}\n")

    # Separate NYC special buildings from the rest
    def is_nyc_special(building_id):
        if not building_id.startswith('NYC_'):
            return False
        bbl = building_id.replace('NYC_', '')
        return bbl in NYC_BBLS

    nyc_special_ids = [row['id_building'] for _, row in df_to_process.iterrows()
                       if is_nyc_special(row['id_building'])]
    df_regular = df_to_process[~df_to_process['id_building'].apply(is_nyc_special)]

    print(f"  - {len(nyc_special_ids)} NYC special buildings (using NYC building.py)")
    print(f"  - {len(df_regular)} regular buildings (using generic template)\n")

    # MAX SPEED MODE
    num_workers = multiprocessing.cpu_count() * 2
    batch_size = 100  # Larger batches = less overhead

    print(f"🚀 TURBO MODE: NYC batch + {num_workers} regular workers\n")

    start_time = time.time()

    # NYC batch (single call, CSVs load once)
    nyc_generated, nyc_errors = generate_nyc_special_reports(nyc_special_ids, output_dir)

    # Regular reports in parallel
    print(f"\n{'='*70}")
    print(f"REGULAR BUILDINGS - {len(df_regular)} total")
    print(f"{'='*70}\n")

    # Smaller batches = more frequent updates
    batch_size = 25
    all_rows = [(row.to_dict(), idx) for idx, row in df_regular.iterrows()]
    batches = []
    for i in range(0, len(all_rows), batch_size):
        batch = all_rows[i:i + batch_size]
        batches.append((batch, output_dir))

    generated = 0
    errors = 0
    regular_start = time.time()

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(generate_batch_reports, batch) for batch in batches]

        for future in as_completed(futures):
            batch_results = future.result()

            for building_id, success, error in batch_results:
                if success:
                    generated += 1
                    # Show progress every building
                    elapsed = time.time() - regular_start
                    rate = generated / elapsed if elapsed > 0 else 0
                    remaining = (len(df_regular) - generated) / rate if rate > 0 else 0
                    print(f"  ✓ {generated}/{len(df_regular)} | {rate:.0f}/sec | {remaining:.0f}s left | {building_id}", flush=True)
                else:
                    errors += 1
                    print(f"  ✗ {building_id}: {error}", flush=True)

    # Summary
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    rate = (generated + nyc_generated) / elapsed if elapsed > 0 else 0

    total_generated = generated + nyc_generated
    total_errors = errors + nyc_errors

    print()
    print("=" * 70)
    print("Generation Complete!")
    print("=" * 70)
    print(f"NYC special reports: {nyc_generated}")
    print(f"Regular reports: {generated}")
    print(f"Total reports generated: {total_generated}")
    print(f"Total errors: {total_errors}")
    print(f"Time elapsed: {minutes}m {seconds}s")
    print(f"Rate: {rate:.1f} reports/second (regular only)")
    print(f"Output directory: {output_dir}")
    print("=" * 70)

if __name__ == '__main__':
    main()
