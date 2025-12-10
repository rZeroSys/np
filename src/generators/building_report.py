"""
Nationwide Building Report Generator
Simply displays the data we have, no bullshit explanations.
"""

import pandas as pd
import sys
import os
import traceback
from pathlib import Path
from datetime import datetime
import pytz
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

# Import functions from modules
from src.data.loader import load_csv, extract_filename
from src.config import (
    BUILDING_DATA_PATH, BUILDINGS_OUTPUT_DIR,
    IMAGES_DIR as CONFIG_IMAGES_DIR,
    AWS_BASE_URL
)

# Configuration - use centralized config
CSV_PATH = str(BUILDING_DATA_PATH)
OUTPUT_DIR = str(BUILDINGS_OUTPUT_DIR) + '/'
IMAGES_DIR = str(CONFIG_IMAGES_DIR)
AWS_BUCKET = AWS_BASE_URL

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
    'site_eui': "Energy use per square foot. Office average: 70-90. Source: city benchmarking law.",
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
    city = safe_val(row, 'city', '')
    state = safe_val(row, 'state', '')

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
    cap_rate = safe_num(row, 'cap_rate')
    if cap_rate:
        cap_pct = cap_rate * 100
        multiplier = int(100 / cap_pct)
        return f"Annual savings ÷ {cap_pct:.1f}% cap rate. $1 saved → ${multiplier} higher value. Cap rate source: caprateindex.com."
    return "Annual savings ÷ cap rate. Cap rate source: caprateindex.com."

def get_energy_star_tooltip(row):
    """Dynamic tooltip for Energy Star Score."""
    law_name = get_law_name(row)
    return f"1-100. 50 = median building. Source: {law_name}."

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
    'electricity_kwh': get_electricity_kwh_tooltip,
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
    """Hero section with building basics - back button on left, centered content"""
    # Property name should be H1 if it exists
    property_name = safe_val(row, 'property_name')

    address = safe_val(row, 'address', 'Address not available')

    # Title priority: property_name, then address
    has_property_name = property_name and str(property_name).lower() != 'nan'
    title = property_name if has_property_name else address
    sqft = safe_num(row, 'square_footage')
    bldg_type = safe_val(row, 'building_type', 'Unknown')
    year = safe_num(row, 'year_built')

    # Building URL for linking title
    building_url = safe_val(row, 'building_url')
    has_building_url = building_url and str(building_url).lower() != 'nan'

    # Back button - big clickable area
    back_btn = '''<a href="../index.html" style="position:absolute;left:10px;top:10px;color:white;text-decoration:none;font-size:14px;font-weight:600;display:flex;align-items:center;gap:6px;padding:8px 14px;background:rgba(0,0,0,0.3);border-radius:6px;z-index:10;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
        Back
    </a>'''

    if has_building_url:
        html = f"""
    <div class="hero" style="position:relative;text-align:center;">
        {back_btn}
        <h1><a href="{escape(building_url)}" target="_blank" style="color: inherit; text-decoration: none;">{escape(title)} <span style="font-size: 0.5em; opacity: 0.7;">↗</span></a></h1>
"""
    else:
        html = f"""
    <div class="hero" style="position:relative;text-align:center;">
        {back_btn}
        <h1>{escape(title)}</h1>
"""
    # Only show address line if we have a property name (otherwise address is already the title)
    if has_property_name:
        html += f'        <div class="address">{escape(address)}</div>\n'

    html += '        <div class="building-info" style="justify-content:center;">\n'

    if sqft:
        html += f"<span>{format_number(sqft)} sqft</span>"
    if bldg_type:
        html += f"<span style='margin: 0 15px;'>•</span><span>{escape(bldg_type)}</span>"
    if year:
        html += f"<span style='margin: 0 15px;'>•</span><span>Built {int(year)}</span>"

    html += """
        </div>
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

    # Property Name - only show if hero used address as title (i.e., no property name was available)
    # If property_name exists, it's already the H1 in hero - don't repeat
    property_name = safe_val(row, 'property_name')
    has_property_name = property_name and str(property_name).lower() != 'nan'
    # Skip - property name is already shown as H1 in hero section

    # Note: Size, Type, Year Built already shown in hero - not repeated here

    # Owner/Tenant/Property Manager - collapsed when matching
    owner = safe_val(row, 'building_owner')
    pm = safe_val(row, 'property_manager')
    tenant = safe_val(row, 'tenant')
    tenant_sub = safe_val(row, 'tenant_sub_org')

    # Normalize: filter out invalid values
    owner = owner if owner and str(owner).lower() != 'nan' else None
    pm = pm if pm and str(pm).lower() != 'nan' else None
    tenant = tenant if tenant and str(tenant).lower() != 'nan' else None
    tenant_sub = tenant_sub if tenant_sub and str(tenant_sub).lower() != 'nan' else None

    # Helper to build org - logo and name on same row
    def build_org_with_logo(name):
        if not name:
            return ""
        logo_filename = get_logo_filename(name)
        if logo_filename:
            logo_url = f"{AWS_BUCKET}/logos/{logo_filename}.png"
            return f'{escape(name)} <img src="{logo_url}" style="height:25px;vertical-align:middle;margin-left:8px;" onerror="this.style.display=\'none\'">'
        return f'{escape(name)}'

    # Helper for logo only (used in combined rows)
    def build_logo(name):
        if not name:
            return ""
        logo_filename = get_logo_filename(name)
        if logo_filename:
            logo_url = f"{AWS_BUCKET}/logos/{logo_filename}.png"
            return f'<div style="text-align:center;margin-top:5px;"><img src="{logo_url}" style="height:30px;" onerror="this.parentElement.style.display=\'none\'"></div>'
        return ""

    # Build tenant sub-org HTML with logo (if exists)
    tenant_sub_html = ""
    if tenant_sub:
        tenant_sub_html = f"<div style='font-size:0.85em;color:#666;margin-top:3px;'>({escape(tenant_sub)})</div>{build_logo(tenant_sub)}"

    # Determine matching pattern and render rows
    all_same = owner and entities_match(owner, pm) and entities_match(owner, tenant)
    owner_tenant = owner and tenant and entities_match(owner, tenant) and not all_same
    owner_pm = owner and pm and entities_match(owner, pm) and not all_same
    tenant_pm = tenant and pm and entities_match(tenant, pm) and not all_same

    if all_same:
        # All three are the same entity - show as "All Roles"
        html += f"<tr><td>All Roles{tooltip('owner')}</td><td>{build_org_with_logo(owner)}{tenant_sub_html}</td></tr>"
    elif owner_tenant and owner_pm:
        # Owner matches both tenant and PM - show as "All Roles"
        html += f"<tr><td>All Roles{tooltip('owner')}</td><td>{build_org_with_logo(tenant)}{tenant_sub_html}</td></tr>"
    elif owner_tenant:
        # Owner and Tenant match - owner/occupier
        html += f"<tr><td>Owner/Occupier{tooltip('owner')}</td><td>{build_org_with_logo(tenant)}{tenant_sub_html}</td></tr>"
        if pm:
            html += f"<tr><td>Manager</td><td>{build_org_with_logo(pm)}</td></tr>"
    elif owner_pm:
        # Owner and Property Manager match - owner/operator
        html += f"<tr><td>Owner/Operator{tooltip('owner')}</td><td>{build_org_with_logo(owner)}</td></tr>"
        if tenant:
            html += f"<tr><td>Tenant</td><td>{build_org_with_logo(tenant)}{tenant_sub_html}</td></tr>"
    elif tenant_pm:
        # Tenant and Property Manager match
        if owner:
            html += f"<tr><td>Owner{tooltip('owner')}</td><td>{build_org_with_logo(owner)}</td></tr>"
        html += f"<tr><td>Tenant & Manager</td><td>{build_org_with_logo(tenant)}{tenant_sub_html}</td></tr>"
    else:
        # All different - show separately
        if owner:
            html += f"<tr><td>Owner{tooltip('owner')}</td><td>{build_org_with_logo(owner)}</td></tr>"
        if pm:
            html += f"<tr><td>Manager</td><td>{build_org_with_logo(pm)}</td></tr>"
        if tenant:
            html += f"<tr><td>Tenant</td><td>{build_org_with_logo(tenant)}{tenant_sub_html}</td></tr>"

    # Site EUI
    eui = safe_num(row, 'site_eui')
    if eui:
        html += f"<tr><td>Site EUI{tooltip('site_eui')}</td><td>{format_number(eui, 1)} kBtu/sqft</td></tr>"

    # Energy Star Score
    es_score = safe_num(row, 'energy_star_score')
    if es_score:
        html += f"<tr><td>Energy Star Score{tooltip('energy_star_score', row)}</td><td>{format_number(es_score)}</td></tr>"

    # Vacancy/Utilization rates are shown in the ODCV Savings % tooltip dynamically

    html += """
        </table>
    </div>
"""
    return html

def generate_energy_use(row):
    """Energy use table with HVAC % inline"""
    # Get HVAC percentages
    pct_elec_hvac = safe_num(row, 'pct_elec_hvac')
    pct_gas_hvac = safe_num(row, 'pct_gas_hvac')
    pct_steam_hvac = safe_num(row, 'pct_steam_hvac')
    pct_fuel_hvac = safe_num(row, 'pct_fuel_oil_hvac')

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
    elec_kwh = safe_num(row, 'electricity_kwh')
    elec_cost = safe_num(row, 'total_annual_electricity_cost')
    if elec_kwh or elec_cost:
        hvac_pct_str = f"{pct_elec_hvac*100:.0f}%" if pct_elec_hvac else "—"
        html += f"""
            <tr>
                <td>Electricity{tooltip('electricity_kwh', row)}</td>
                <td>{format_number(elec_kwh) + ' kWh' if elec_kwh else ''}</td>
                <td>{format_currency(elec_cost) if elec_cost else '$0'}</td>
                <td>{hvac_pct_str}</td>
            </tr>
"""

    # Natural Gas (and Fuel Oil if building has both)
    gas_use = safe_num(row, 'natural_gas_use_kbtu')
    gas_cost = safe_num(row, 'annual_gas_cost')
    gas_rate = safe_num(row, 'gas_rate_per_therm')
    fuel_use = safe_num(row, 'fuel_oil_use_kbtu')
    fuel_cost = safe_num(row, 'annual_fuel_oil_cost')

    if gas_use and gas_use > 0:
        gas_therms = gas_use / 100  # kBtu to therms

        # If building has BOTH gas and fuel oil, merge them
        if fuel_use and fuel_use > 0:
            fuel_therms = fuel_use / 100  # Convert fuel oil kBtu to therms
            total_therms = gas_therms + fuel_therms
            total_cost = (gas_cost or 0) + (fuel_cost or 0)
            use_str = f"{format_number(total_therms)} therms"
            hvac_pct_str = f"{pct_gas_hvac*100:.0f}%" if pct_gas_hvac else "—"
            html += f"""
            <tr>
                <td>Natural Gas & Fuel Oil{tooltip('natural_gas', row)}</td>
                <td>{use_str}</td>
                <td>{format_currency(total_cost) if total_cost else '$0'}</td>
                <td>{hvac_pct_str}</td>
            </tr>
"""
        else:
            # Gas only
            use_str = f"{format_number(gas_therms)} therms"
            hvac_pct_str = f"{pct_gas_hvac*100:.0f}%" if pct_gas_hvac else "—"
            html += f"""
            <tr>
                <td>Natural Gas{tooltip('natural_gas', row)}</td>
                <td>{use_str}</td>
                <td>{format_currency(gas_cost) if gas_cost else '$0'}</td>
                <td>{hvac_pct_str}</td>
            </tr>
"""

    # District Steam
    steam_use = safe_num(row, 'district_steam_use_kbtu')
    steam_cost = safe_num(row, 'annual_steam_cost')
    steam_rate = safe_num(row, 'steam_rate_per_mlb')
    if steam_use and steam_use > 0:
        steam_mlb = steam_use / 1194  # kBtu to Mlb
        use_str = f"{format_number(steam_mlb, 2)} Mlb"
        hvac_pct_str = f"{pct_steam_hvac*100:.0f}%" if pct_steam_hvac else "—"
        html += f"""
            <tr>
                <td>District Steam{tooltip('district_steam')}</td>
                <td>{use_str}</td>
                <td>{format_currency(steam_cost) if steam_cost else '$0'}</td>
                <td>{hvac_pct_str}</td>
            </tr>
"""

    # Fuel Oil - only show if NO natural gas (fuel oil only buildings)
    if fuel_use and fuel_use > 0 and (not gas_use or gas_use <= 0):
        fuel_gal = fuel_use / 138.5  # kBtu to gallons
        use_str = f"{format_number(fuel_gal)} gallons"
        hvac_pct_str = f"{pct_fuel_hvac*100:.0f}%" if pct_fuel_hvac else "—"
        html += f"""
            <tr>
                <td>Fuel Oil{tooltip('fuel_oil')}</td>
                <td>{use_str}</td>
                <td>{format_currency(fuel_cost) if fuel_cost else '$0'}</td>
                <td>{hvac_pct_str}</td>
            </tr>
"""

    html += """
        </table>
"""

    # GHG Emissions
    ghg = safe_num(row, 'total_ghg_emissions_mt_co2e')
    if ghg:
        html += f"""
        <p style="margin-top: 15px;"><strong>Total GHG Emissions{tooltip('total_ghg', row)}:</strong> {format_number(ghg, 1)} MT CO2e</p>
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
    total_cost = safe_num(row, 'total_annual_electricity_cost')
    if total_cost:
        html += f"<tr><td>Total Annual Cost{tooltip('total_annual_cost')}</td><td>{format_currency(total_cost)}</td></tr>"

    # Energy charges
    energy_cost = safe_num(row, 'annual_energy_cost')
    if energy_cost:
        html += f"<tr><td>Energy Charges{tooltip('energy_charges')}</td><td>{format_currency(energy_cost)}</td></tr>"

    # Demand charges
    demand_cost = safe_num(row, 'annual_demand_cost')
    if demand_cost:
        html += f"<tr><td>Demand Charges{tooltip('demand_charges')}</td><td>{format_currency(demand_cost)}</td></tr>"

    # Energy rate
    energy_rate = safe_num(row, 'energy_rate_per_kwh')
    if energy_rate:
        html += f"<tr><td>Energy Rate{tooltip('energy_rate')}</td><td>${energy_rate:.4f}/kWh</td></tr>"

    # Demand rate
    demand_rate = safe_num(row, 'demand_rate_per_kw')
    if demand_rate:
        html += f"<tr><td>Demand Rate{tooltip('demand_rate')}</td><td>${demand_rate:.2f}/kW</td></tr>"

    # Peak demand
    peak_kw = safe_num(row, 'estimated_peak_kw')
    if peak_kw:
        html += f"<tr><td>Peak Demand{tooltip('peak_demand')}</td><td>{format_number(peak_kw)} kW</td></tr>"

    # Load factor
    load_factor = safe_num(row, 'load_factor_used')
    if load_factor:
        html += f"<tr><td>Load Factor{tooltip('load_factor', row)}</td><td>{load_factor*100:.1f}%</td></tr>"

    # Utility
    utility = safe_val(row, 'utility_name_used')
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
    pct_elec_hvac = safe_num(row, 'pct_elec_hvac')
    elec_cost = safe_num(row, 'total_annual_electricity_cost', 0)
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
    pct_gas_hvac = safe_num(row, 'pct_gas_hvac')
    gas_cost = safe_num(row, 'annual_gas_cost', 0)
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
    pct_steam_hvac = safe_num(row, 'pct_steam_hvac')
    steam_cost = safe_num(row, 'annual_steam_cost', 0)
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
    pct_fuel_hvac = safe_num(row, 'pct_fuel_oil_hvac')
    fuel_cost = safe_num(row, 'annual_fuel_oil_cost', 0)
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
    total_hvac_cost = safe_num(row, 'total_hvac_energy_cost')
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
    elec_kwh = safe_num(row, 'electricity_kwh')
    elec_cost = safe_num(row, 'total_annual_electricity_cost')
    gas_use = safe_num(row, 'natural_gas_use_kbtu')
    steam_use = safe_num(row, 'district_steam_use_kbtu')
    fuel_use = safe_num(row, 'fuel_oil_use_kbtu')

    # Skip entire section if no energy data
    if not any([elec_kwh, elec_cost, gas_use, steam_use, fuel_use]):
        return ""

    # Get HVAC percentages
    pct_elec_hvac = safe_num(row, 'pct_elec_hvac')
    pct_gas_hvac = safe_num(row, 'pct_gas_hvac')
    pct_steam_hvac = safe_num(row, 'pct_steam_hvac')
    pct_fuel_hvac = safe_num(row, 'pct_fuel_oil_hvac')
    gas_cost = safe_num(row, 'annual_gas_cost')
    steam_cost = safe_num(row, 'annual_steam_cost')
    fuel_cost = safe_num(row, 'annual_fuel_oil_cost')

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
                <td>Electricity{tooltip('electricity_kwh', row)}</td>
                <td>{format_number(elec_kwh) + ' kWh' if elec_kwh else ''}</td>
                <td>{format_currency(elec_cost) if elec_cost else ''}</td>
                <td>{hvac_str}</td>
            </tr>
"""

    # Natural Gas (and Fuel Oil if building has both)
    if gas_use and gas_use > 0:
        gas_therms = gas_use / 100
        hvac_str = f"{pct_gas_hvac*100:.0f}%" if pct_gas_hvac else "—"

        # If building has BOTH gas and fuel oil, merge them
        if fuel_use and fuel_use > 0:
            fuel_therms = fuel_use / 100  # Convert fuel oil kBtu to therms
            total_therms = gas_therms + fuel_therms
            total_cost = (gas_cost or 0) + (fuel_cost or 0)
            html += f"""
            <tr>
                <td>Natural Gas & Fuel Oil{tooltip('natural_gas', row)}</td>
                <td>{format_number(total_therms)} therms</td>
                <td>{format_currency(total_cost) if total_cost else ''}</td>
                <td>{hvac_str}</td>
            </tr>
"""
        else:
            # Gas only
            html += f"""
            <tr>
                <td>Natural Gas{tooltip('natural_gas', row)}</td>
                <td>{format_number(gas_therms)} therms</td>
                <td>{format_currency(gas_cost) if gas_cost else ''}</td>
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

    # Fuel Oil - only show if NO natural gas (fuel oil only buildings)
    if fuel_use and fuel_use > 0 and (not gas_use or gas_use <= 0):
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

    html += """
        </table>
    </div>
"""
    return html

def generate_savings_section(row):
    """Savings section - shows Current vs New values with Change column"""
    # Get all the values we need
    elec_cost = safe_num(row, 'total_annual_electricity_cost', 0)
    gas_cost = safe_num(row, 'annual_gas_cost', 0)
    steam_cost = safe_num(row, 'annual_steam_cost', 0)
    fuel_oil_cost = safe_num(row, 'annual_fuel_oil_cost', 0)
    total_energy_cost = elec_cost + gas_cost + steam_cost + fuel_oil_cost

    odcv_savings = safe_num(row, 'odcv_dollar_savings')
    val_impact = safe_num(row, 'odcv_valuation_impact_usd')
    carbon_current = safe_num(row, 'total_ghg_emissions_mt_co2e')
    carbon_reduction = safe_num(row, 'carbon_emissions_reduction_yr1')

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
                <td>{format_currency(total_energy_cost)}</td>
                <td>{format_currency(new_utility_cost)}</td>
                <td style="color: #16a34a; font-weight: 600;">-{format_currency(odcv_savings)}</td>
            </tr>
"""

    # Carbon Emissions row
    if carbon_current and carbon_reduction:
        html += f"""
            <tr>
                <td>Carbon Emissions{tooltip('carbon_reduction')}</td>
                <td>{format_number(carbon_current, 1)} MT</td>
                <td>{format_number(new_carbon, 1)} MT</td>
                <td style="color: #16a34a; font-weight: 600;">-{format_number(carbon_reduction, 1)} MT</td>
            </tr>
"""

    # Property Value row - use existing valuation data from CSV
    current_val = safe_num(row, 'current_valuation_usd')
    post_val = safe_num(row, 'post_odcv_valuation_usd')

    if val_impact and val_impact > 0:
        current_str = format_currency(current_val) if current_val else '—'
        new_str = format_currency(post_val) if post_val else '—'
        html += f"""
            <tr>
                <td>Property Value{tooltip('property_value_increase', row)}</td>
                <td>{current_str}</td>
                <td>{new_str}</td>
                <td style="color: #16a34a; font-weight: 600;">+{format_currency(val_impact)}</td>
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
    building_id = safe_val(row, 'building_id', 'UNKNOWN')
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
        building_id = row.get('building_id', f'unknown_{idx}')
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
    building_id = row.get('building_id', f'unknown_{idx}')
    safe_building_id = building_id.replace('/', '_').replace('\\', '_')

    try:
        html = generate_html_report(row)
        output_path = os.path.join(output_dir, f"{safe_building_id}.html")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        return (building_id, True, None)
    except Exception as e:
        return (building_id, False, str(e))


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
    df_clean = df.dropna(subset=['latitude', 'longitude'])
    removed = len(df) - len(df_clean)
    if removed > 0:
        print(f"⚠ Removed {removed} buildings without coordinates")

    # Check for specific building ID in command line args
    if len(sys.argv) > 1:
        building_id = sys.argv[1]
        df_to_process = df_clean[df_clean['building_id'] == building_id]
        if len(df_to_process) == 0:
            print(f"\n✗ Building ID '{building_id}' not found in dataset")
            sys.exit(1)
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
    print(f"Generating reports for all {total} buildings\n")

    # Use 2x CPU count for I/O bound work (file writing)
    num_workers = multiprocessing.cpu_count() * 2
    # Batch size: process multiple buildings per task to reduce IPC overhead
    batch_size = 50
    print(f"🚀 Using {num_workers} parallel workers, batch size {batch_size}\n")

    # Convert to list of (dict, idx) tuples
    all_rows = [(row.to_dict(), idx) for idx, row in df_to_process.iterrows()]

    # Split into batches
    batches = []
    for i in range(0, len(all_rows), batch_size):
        batch = all_rows[i:i + batch_size]
        batches.append((batch, output_dir))

    print(f"Split into {len(batches)} batches\n")

    start_time = time.time()
    generated = 0
    errors = 0

    # Process batches in parallel
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(generate_batch_reports, batch) for batch in batches]

        batches_done = 0
        for future in as_completed(futures):
            batch_results = future.result()
            batches_done += 1

            for building_id, success, error in batch_results:
                if success:
                    generated += 1
                else:
                    errors += 1
                    print(f"✗ Error for {building_id}: {error}")

            # Progress update every 10 batches (500 buildings)
            if batches_done % 10 == 0:
                elapsed = time.time() - start_time
                rate = (generated + errors) / elapsed
                remaining = (total - generated - errors) / rate if rate > 0 else 0
                print(f"  Progress: {generated + errors}/{total} ({generated} ok, {errors} errors) "
                      f"- {rate:.1f} reports/sec - ~{remaining:.0f}s remaining")

    # Summary
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    rate = generated / elapsed if elapsed > 0 else 0

    print()
    print("=" * 70)
    print("Generation Complete!")
    print("=" * 70)
    print(f"Total reports generated: {generated}")
    print(f"Errors encountered: {errors}")
    print(f"Time elapsed: {minutes}m {seconds}s")
    print(f"Rate: {rate:.1f} reports/second")
    print(f"Output directory: {output_dir}")
    print("=" * 70)

if __name__ == '__main__':
    main()
