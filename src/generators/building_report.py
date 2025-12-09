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

# Static tooltips (don't vary by building type or city)
TOOLTIPS = {
    # Building Information
    'building_type': "Primary use classification (energy disclosure filing).",
    'year_built': "Construction year (energy disclosure filing).",
    'owner': "Building owner (30+ data sources).",
    'site_eui': "Energy Use Intensity: kBtu/sqft/year (energy disclosure). Lower = more efficient.",
    'vacancy_rate': "Unleased space % (CoStar).",
    'utilization_rate': "% of time occupied space is in use (Placer AI). 50% = half operating hours building is empty but ventilated.",

    # Energy Use
    'total_energy_cost': "Annual electricity + gas + steam. Usage from disclosure, rates from NREL by ZIP.",
    'electricity_cost': "Energy charges + demand charges. Rates from NREL by ZIP.",
    'district_steam': "Steam use in Mlb (energy disclosure). Common in dense urban areas.",
    'fuel_oil': "Fuel oil in gallons (energy disclosure).",

    # Electricity Details
    'total_annual_cost': "Energy charges + demand charges.",
    'energy_charges': "kWh × rate. Rate from NREL by ZIP.",
    'demand_charges': "Peak kW × demand rate × 12 months. Rate from NREL by ZIP.",
    'energy_rate': "$/kWh for this ZIP (NREL).",
    'demand_rate': "$/kW monthly demand charge for this ZIP (NREL).",
    'peak_demand': "Peak power draw (kW). Estimated: kWh ÷ (8760 × load factor). Utilities charge separately for peak infrastructure.",
    'load_factor': "How steady vs spiky power usage is. High (60%+) = steady. Low (30-40%) = peaky. By building type (NREL).",
    'utility_provider': "Electric utility serving building.",

    # HVAC Breakdown (from EIA CBECS 2018)
    'total_hvac_cost': "HVAC portion of energy bill (CBECS 2018). Adjusted for building type, climate, age, efficiency.",
    'pct_hvac_elec': "% electricity for HVAC (CBECS 2018). Adjusted for efficiency, age, energy intensity.",
    'pct_hvac_gas': "% gas for HVAC heating (CBECS 2018).",
    'pct_hvac_steam': "% steam for HVAC (CBECS 2018).",
    'hvac_disagg': "HVAC % estimated from EIA CBECS 2018 microdata. Adjusted for: building type, climate zone, year built (±4%), ENERGY STAR score (±5%), EUI vs peers (±6%). 15% minimum floor for ventilation/pumps/controls. Cap: ±12% total adjustment.",

    # ODCV Savings (from NATIONAL METHODS)
    'odcv_savings_pct': "HVAC savings from matching ventilation to occupancy. Based on ASHRAE 62.1 standards.",
    'annual_savings': "HVAC Cost × Savings %. Annual utility reduction from O-DCV.",
    'whole_building_savings': "Annual Utility Savings ÷ Total Energy Cost. Impact on entire bill, not just HVAC.",
    'property_value_increase': "Annual Utility Savings ÷ Cap Rate. Every $1 saved increases NOI → property value. Cap rate from caprateindex.com by type/market.",

    # Carbon Impact (from NATIONAL METHODS)
    'carbon_reduction': "MT CO2e reduced annually. HVAC reduction × emission factors (EPA eGRID by region).",
    'fine_avoidance': "Avoided BPS penalties. NYC LL97: $268/ton. Boston BERDO: $234/ton. DC BEPS: up to $10/sqft.",
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

def get_odcv_reduction_tooltip(row):
    """Dynamic tooltip for ODCV Reduction % based on building type."""
    building_type = safe_val(row, 'building_type', '')
    vacancy = safe_num(row, 'vacancy_rate')
    util = safe_num(row, 'utilization_rate')

    if building_type in USES_VACANCY_FORMULA:
        vacancy_str = f"{vacancy*100:.0f}% vacant (CoStar)" if vacancy else "vacancy (CoStar)"
        util_str = f"{util*100:.0f}% utilized (Placer AI)" if util else "utilization (Placer AI)"
        return (f"Factors: {vacancy_str}, {util_str}, automation capability. "
                "Vacant space gets full airflow. Leased but underutilized space ventilated for design occupancy.")

    elif building_type in CONSTRAINED_TYPES:
        util_str = f"{util*100:.0f}% utilized" if util else "utilization"
        return (f"Factors: {util_str} (Placer AI), automation—capped at 30% due to 24/7 airflow requirements (ASHRAE 170). "
                "Savings limited to non-critical areas.")

    else:  # Single-tenant or default
        util_str = f"{util*100:.0f}% utilized (Placer AI)" if util else "utilization (Placer AI)"
        return (f"Factors: {util_str}, automation capability. "
                "Empty hours still get full ventilation.")

def get_annual_savings_tooltip(row):
    """Dynamic tooltip for Annual Savings based on city's disclosure law."""
    law_name = get_law_name(row)
    return (f"Energy from {law_name} × HVAC % (CBECS 2018) × O-DCV savings % × rates (NREL by ZIP).")

def get_property_value_tooltip(row):
    """Dynamic tooltip for Property Value Increase based on BPS status."""
    city = safe_val(row, 'city', '')
    cap_rate = safe_num(row, 'cap_rate')
    cap_str = f"{cap_rate*100:.1f}% cap rate" if cap_rate else "cap rate"

    if city in BPS_CITIES:
        return (f"(Annual Utility Savings + Fine Avoidance) ÷ {cap_str} (caprateindex.com). "
                "Reduced OpEx → higher NOI → higher value.")
    else:
        return (f"Annual Utility Savings ÷ {cap_str} (caprateindex.com). "
                "Reduced OpEx → higher NOI → higher value.")

def get_size_tooltip(row):
    """Dynamic tooltip for building size based on city's disclosure law."""
    law_name = get_law_name(row)
    return f"Gross sqft ({law_name})."

def get_energy_star_tooltip(row):
    """Dynamic tooltip for Energy Star Score based on city's disclosure law."""
    law_name = get_law_name(row)
    return f"EPA rating 1-100 ({law_name}). Compares to similar buildings nationwide. Lower = more savings opportunity."

def get_electricity_kwh_tooltip(row):
    """Dynamic tooltip for electricity kWh based on city's disclosure law."""
    law_name = get_law_name(row)
    return f"Annual kWh ({law_name})."

def get_natural_gas_tooltip(row):
    """Dynamic tooltip for natural gas based on city's disclosure law."""
    law_name = get_law_name(row)
    return f"Annual therms ({law_name})."

def get_total_ghg_tooltip(row):
    """Dynamic tooltip for total GHG based on city."""
    city = safe_val(row, 'city', '')
    if city:
        return f"MT CO2e/year. Energy × {city} grid emission factors (EPA eGRID)."
    return "MT CO2e/year. Energy × local grid factors (EPA eGRID)."

def get_odcv_floor_ceiling_tooltip(row):
    """Dynamic tooltip showing floor/ceiling range for this building's type."""
    building_type = safe_val(row, 'building_type', '')

    # Building type to floor/ceiling mapping based on ODCV methodology
    RANGES = {
        # High opportunity (20%+ ceiling)
        'Office': (20, 40, "Hybrid work + clear occupied hours + VAV systems."),
        'Medical Office': (20, 40, "Similar to office with some area constraints."),
        'K-12 School': (20, 45, "Summers, after 3pm, weekends = 50%+ empty annually."),
        'Higher Ed': (20, 45, "Breaks, variable schedules, evening/weekend."),
        'Event Space': (20, 45, "Empty days/weeks, then full capacity."),

        # Medium opportunity (15-35%)
        'Retail Store': (15, 35, "Traffic varies opening to close."),
        'Hotel': (15, 35, "Room-by-room variability."),
        'Gym': (15, 35, "Peak 6-8am, 5-7pm; empty mid-day."),
        'Mixed Use': (18, 38, "Multi-tenant; varies by mix."),
        'Strip Mall': (15, 35, "Multi-tenant with variable traffic."),
        'Theater': (18, 40, "Performance schedule-dependent."),
        'Preschool/Daycare': (18, 38, "Seasonal and hourly variations."),
        'Arts & Culture': (15, 35, "Event/exhibition schedule-dependent."),

        # Lower opportunity (10-25%)
        'Supermarket/Grocery': (10, 25, "Long hours, steady traffic, refrigeration."),
        'Wholesale Club': (10, 25, "Long hours, steady traffic."),
        'Restaurant/Bar': (10, 25, "Kitchen ventilation runs constant."),
        'Library': (12, 28, "Fixed hours, steady occupancy."),
        'Bank Branch': (12, 28, "Fixed hours, steady traffic."),
        'Courthouse': (10, 25, "Fixed hours, steady occupancy."),
        'Enclosed Mall': (12, 30, "Multi-tenant, variable traffic."),
        'Vehicle Dealership': (15, 35, "Showroom vs service patterns differ."),
        'Public Service': (10, 25, "Fixed hours, steady occupancy."),
        'Outpatient Clinic': (15, 32, "Appointment-driven occupancy."),
        'Sports/Gaming Center': (18, 40, "Event schedule-dependent."),

        # Limited opportunity (5-15%)
        'Inpatient Hospital': (5, 15, "ASHRAE 170 infection control. Non-clinical areas only."),
        'Specialty Hospital': (5, 15, "Same as inpatient."),
        'Laboratory': (5, 15, "Fume hoods require constant exhaust."),
        'Police Station': (5, 15, "24/7 operation."),
        'Fire Station': (5, 15, "24/7 readiness."),
        'Residential Care Facility': (5, 15, "24/7 resident occupancy."),
        'Public Transit': (5, 15, "24/7 operation."),

        # Zero opportunity
        'Data Center': (0, 0, "Equipment cooling only. O-DCV N/A."),
    }

    if building_type in RANGES:
        floor, ceiling, explanation = RANGES[building_type]
        if ceiling == 0:
            return f"Range: N/A. {explanation}"
        return f"Range: {floor}%-{ceiling}%. {explanation}"

    return "Range varies by type, occupancy, automation."

def get_vacancy_rate_tooltip(row):
    """Dynamic tooltip for vacancy rate - only used in formula for certain building types."""
    building_type = safe_val(row, 'building_type', '')
    vacancy = safe_num(row, 'vacancy_rate')
    vacancy_str = f"{vacancy*100:.0f}%" if vacancy else "N/A"

    if building_type in USES_VACANCY_FORMULA:
        return (f"Unleased: {vacancy_str} (CoStar). Vacant space still gets full ventilation—pure waste O-DCV eliminates.")
    else:
        return f"Unleased: {vacancy_str} (CoStar). Not used in savings calc for single-tenant buildings."

def get_utilization_rate_tooltip(row):
    """Dynamic tooltip for utilization rate with actual values."""
    util = safe_num(row, 'utilization_rate')
    util_str = f"{util*100:.0f}%" if util else "N/A"
    empty_str = f"{(1-util)*100:.0f}%" if util else "N/A"

    return (f"Utilization: {util_str} (Placer AI). Building is empty {empty_str} of operating hours "
            "but still gets full ventilation.")

def get_load_factor_tooltip(row):
    """Dynamic tooltip for load factor with building-type context."""
    building_type = safe_val(row, 'building_type', '')
    load_factor = safe_num(row, 'load_factor_used')
    lf_str = f"{load_factor*100:.0f}%" if load_factor else ""

    base = f"Load factor{': ' + lf_str if lf_str else ''} (NREL by type). High (60%+) = steady. Low (30-40%) = peaky. "

    EXAMPLES = {
        'Data Center': "Data centers: 80%+ (24/7 equipment).",
        'K-12 School': "Schools: 30-40% (peaks school hours only).",
        'Higher Ed': "Universities: 35-45% (semester peaks).",
        'Office': "Offices: 45-55% (business hours).",
        'Hotel': "Hotels: 55-65% (steady occupancy).",
        'Retail Store': "Retail: 50-60% (business hours).",
        'Hospital': "Hospitals: 70%+ (24/7).",
        'Inpatient Hospital': "Hospitals: 70%+ (24/7).",
        'Restaurant/Bar': "Restaurants: 45-55% (meal peaks).",
        'Supermarket/Grocery': "Supermarkets: 60-70% (24/7 refrigeration).",
        'Wholesale Club': "Wholesale: 55-65% (refrigeration + hours).",
    }

    if building_type in EXAMPLES:
        return base + EXAMPLES[building_type]
    return base

# Map of dynamic tooltip keys to their generator functions
DYNAMIC_TOOLTIPS = {
    'odcv_reduction': get_odcv_reduction_tooltip,
    'odcv_savings_pct': get_odcv_reduction_tooltip,  # Same function, different key used in templates
    'odcv_floor_ceiling': get_odcv_floor_ceiling_tooltip,  # Building-type-specific ranges
    'vacancy_rate': get_vacancy_rate_tooltip,  # Building-type-specific vacancy explanation
    'utilization_rate': get_utilization_rate_tooltip,  # Shows actual utilization % and empty %
    'load_factor': get_load_factor_tooltip,  # Building-type-specific load factor examples
    'annual_savings': get_annual_savings_tooltip,
    'property_value_increase': get_property_value_tooltip,
    'size': get_size_tooltip,
    'energy_star_score': get_energy_star_tooltip,
    'electricity_kwh': get_electricity_kwh_tooltip,
    'natural_gas': get_natural_gas_tooltip,
    'total_ghg': get_total_ghg_tooltip,
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
    """Hero section with building basics - just address, sqft, type, year"""
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

    if has_building_url:
        html = f"""
    <div class="hero">
        <h1><a href="{escape(building_url)}" target="_blank" style="color: inherit; text-decoration: none;">{escape(title)} <span style="font-size: 0.5em; opacity: 0.7;">↗</span></a></h1>
"""
    else:
        html = f"""
    <div class="hero">
        <h1>{escape(title)}</h1>
"""
    # Only show address line if we have a property name (otherwise address is already the title)
    if has_property_name:
        html += f'        <div class="address">{escape(address)}</div>\n'

    html += '        <div class="building-info">\n'

    if sqft:
        html += f"{format_number(sqft)} sqft"
    if bldg_type:
        html += f" | {escape(bldg_type)}"
    if year:
        html += f" | Built {int(year)}"

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

    # Helper to build logo HTML
    def build_logo(name):
        if not name:
            return ""
        logo_filename = get_logo_filename(name)
        if logo_filename:
            logo_url = f"{AWS_BUCKET}/logos/{logo_filename}.png"
            return f' <img src="{logo_url}" style="height:30px;margin-left:10px;vertical-align:middle;" onerror="this.style.display=\'none\'">'
        return ""

    # Build tenant sub-org HTML with logo (if exists)
    tenant_sub_html = ""
    if tenant_sub:
        tenant_sub_html = f" ({escape(tenant_sub)}{build_logo(tenant_sub)})"

    # Determine matching pattern and render rows
    all_same = owner and entities_match(owner, pm) and entities_match(owner, tenant)
    owner_tenant = owner and tenant and entities_match(owner, tenant) and not all_same
    owner_pm = owner and pm and entities_match(owner, pm) and not all_same
    tenant_pm = tenant and pm and entities_match(tenant, pm) and not all_same

    if all_same:
        # All three are the same entity - show as "All Roles"
        html += f"<tr><td>All Roles{tooltip('owner')}</td><td>{escape(owner)}{build_logo(owner)}{tenant_sub_html}</td></tr>"
    elif owner_tenant and owner_pm:
        # Owner matches both tenant and PM - show as "All Roles"
        html += f"<tr><td>All Roles{tooltip('owner')}</td><td>{escape(tenant)}{build_logo(owner)}{tenant_sub_html}</td></tr>"
    elif owner_tenant:
        # Owner and Tenant match - owner/occupier
        html += f"<tr><td>Owner/Occupier{tooltip('owner')}</td><td>{escape(tenant)}{build_logo(owner)}{tenant_sub_html}</td></tr>"
        if pm:
            html += f"<tr><td>Property Manager</td><td>{escape(pm)}{build_logo(pm)}</td></tr>"
    elif owner_pm:
        # Owner and Property Manager match - owner/operator
        html += f"<tr><td>Owner/Operator{tooltip('owner')}</td><td>{escape(owner)}{build_logo(owner)}</td></tr>"
        if tenant:
            html += f"<tr><td>Tenant</td><td>{escape(tenant)}{build_logo(tenant)}{tenant_sub_html}</td></tr>"
    elif tenant_pm:
        # Tenant and Property Manager match
        if owner:
            html += f"<tr><td>Owner{tooltip('owner')}</td><td>{escape(owner)}{build_logo(owner)}</td></tr>"
        html += f"<tr><td>Tenant & Property Manager</td><td>{escape(tenant)}{build_logo(tenant)}{tenant_sub_html}</td></tr>"
    else:
        # All different - show separately
        if owner:
            html += f"<tr><td>Owner{tooltip('owner')}</td><td>{escape(owner)}{build_logo(owner)}</td></tr>"
        if pm:
            html += f"<tr><td>Property Manager</td><td>{escape(pm)}{build_logo(pm)}</td></tr>"
        if tenant:
            html += f"<tr><td>Tenant</td><td>{escape(tenant)}{build_logo(tenant)}{tenant_sub_html}</td></tr>"

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
                <th>Fuel Type</th>
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
                <th>Fuel Type</th>
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
                <th>Fuel Type</th>
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

    # Total HVAC cost (single line summary)
    total_hvac_cost = safe_num(row, 'total_hvac_energy_cost')
    ghg = safe_num(row, 'total_ghg_emissions_mt_co2e')

    # Add HVAC Cost row
    if total_hvac_cost:
        html += f"""
            <tr style="border-top: 2px solid #e0e0e0;">
                <td style="padding-top: 12px;"><strong>Total HVAC Cost</strong>{tooltip('total_hvac_cost')}</td>
                <td style="padding-top: 12px;" colspan="3"><strong>{format_currency(total_hvac_cost)}</strong></td>
            </tr>
"""

    # Add GHG Emissions row
    if ghg:
        html += f"""
            <tr>
                <td><strong>GHG Emissions</strong>{tooltip('total_ghg', row)}</td>
                <td colspan="3"><strong>{format_number(ghg, 1)} MT CO2e</strong></td>
            </tr>
"""

    html += """
        </table>
    </div>
"""
    return html

def generate_odcv_savings(row):
    """ODCV Savings section - shows calculation flow: Energy Cost → HVAC Cost → Savings % → Savings $ → Value"""
    # Get all the values we need
    elec_cost = safe_num(row, 'total_annual_electricity_cost', 0)
    gas_cost = safe_num(row, 'annual_gas_cost', 0)
    steam_cost = safe_num(row, 'annual_steam_cost', 0)
    fuel_oil_cost = safe_num(row, 'annual_fuel_oil_cost', 0)
    total_energy_cost = elec_cost + gas_cost + steam_cost + fuel_oil_cost

    total_hvac_cost = safe_num(row, 'total_hvac_energy_cost')
    odcv_pct = safe_num(row, 'odcv_savings_pct')
    odcv_savings = safe_num(row, 'odcv_dollar_savings')
    whole_bldg_pct = safe_num(row, 'total_building_cost_savings_pct')
    val_impact = safe_num(row, 'odcv_valuation_impact_usd')
    fine_avoid = safe_num(row, 'fine_avoidance_yr1')
    carbon_reduction = safe_num(row, 'carbon_emissions_reduction_yr1')

    # Skip if no savings data
    if not odcv_savings:
        return ""

    html = """
    <div class="section">
        <h2>ODCV Savings</h2>
        <table>
"""

    # 4. Annual Utility Bill Savings (the payoff) - BOLD this row
    if odcv_savings and odcv_savings > 0:
        html += f"<tr style=\"background: #f0f9ff;\"><td><strong>Annual Utility Savings{tooltip('annual_savings', row)}</strong></td><td><strong>{format_currency(odcv_savings)}</strong></td></tr>"

    # 5. Whole Building Savings %
    if whole_bldg_pct and whole_bldg_pct > 0:
        html += f"<tr><td>Whole Building Savings{tooltip('whole_building_savings')}</td><td>{whole_bldg_pct*100:.1f}%</td></tr>"

    # 6. Property Valuation Increase
    if val_impact and val_impact > 0:
        html += f"<tr><td>Property Value Increase{tooltip('property_value_increase', row)}</td><td>{format_currency(val_impact)}</td></tr>"

    # 7. Fine Avoidance (only if > 0 - BPS cities only)
    if fine_avoid and fine_avoid > 0:
        html += f"<tr><td>Fine Avoidance Year 1{tooltip('fine_avoidance')}</td><td>{format_currency(fine_avoid)}</td></tr>"

    # 8. Carbon Reduction
    if carbon_reduction and carbon_reduction > 0:
        html += f"<tr><td>Carbon Reduction Year 1{tooltip('carbon_reduction')}</td><td>{format_number(carbon_reduction, 1)} MT CO2e</td></tr>"

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

        /* Hero */
        .hero {{
            background: linear-gradient(135deg, #0066cc 0%, #0052a3 100%);
            color: white;
            padding: 20px 30px;
            border-radius: 8px;
            margin-bottom: 30px;
        }}

        .hero h1 {{
            font-size: 1.8em;
            margin-bottom: 5px;
        }}

        .hero .address {{
            font-size: 1em;
            opacity: 0.9;
            margin-bottom: 3px;
        }}

        .hero .building-info {{
            font-size: 0.9em;
            opacity: 0.8;
            margin-bottom: 15px;
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

    # Header navigation bar
    html += """
    <div style="padding: 15px 20px; display: flex; align-items: center;">
        <a href="../index.html" style="text-decoration: none; display: flex; align-items: center; gap: 8px; color: #0066cc; font-weight: 500;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
            Back to Nationwide Prospector
        </a>
    </div>
"""

    # Add sections
    html += generate_hero(row)

    # Add building image if exists
    image_url = get_building_image_url(building_id)
    if image_url:
        html += f"""
    <div class="section" style="margin: 0; padding: 0;">
        <img src="{image_url}" alt="Building {building_id}" style="width: 100%; max-height: 600px; object-fit: cover; border-radius: 8px;">
    </div>
"""

    # 1. Building & Property
    html += generate_building_info(row)

    # 2. Energy
    html += generate_energy_section(row)

    # 3. ODCV Savings
    html += generate_odcv_savings(row)

    # Close container
    html += """
    </div>
</body>
</html>
"""
    return html

def main():
    """Main execution"""
    print("=" * 70)
    print("Building Reports Generator - Nationwide Prospector")
    print("=" * 70)
    print()

    # Ensure output directory exists
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    print(f"✓ Output directory: {OUTPUT_DIR}\n")

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
    else:
        df_to_process = df_clean
        print(f"Generating reports for all {len(df_to_process)} buildings\n")

    # Generate reports
    print(f"{'Progress':<15} {'Building ID':<25} {'Status':<30}")
    print("-" * 70)

    start_time = time.time()
    generated = 0
    errors = 0

    for idx, row in df_to_process.iterrows():
        building_id = row.get('building_id', f'unknown_{idx}')
        # Sanitize building_id for filename (remove slashes and other problematic chars)
        safe_building_id = building_id.replace('/', '_').replace('\\', '_')
        try:
            # Generate HTML
            html = generate_html_report(row)

            # Write file
            output_path = os.path.join(OUTPUT_DIR, f"{safe_building_id}.html")
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html)

            generated += 1
            status = f"Generated ({generated}/{len(df_to_process)})"
            print(f"[{generated}/{len(df_to_process)}]".ljust(15) + f"{building_id:<25} {status:<30}")

        except Exception as e:
            errors += 1
            print(f"[{generated + errors}/{len(df_to_process)}]".ljust(15) + f"{building_id:<25} {'ERROR: ' + str(e):<30}")
            traceback.print_exc()

    # Summary
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    print()
    print("=" * 70)
    print("Generation Complete!")
    print("=" * 70)
    print(f"Total reports generated: {generated}")
    print(f"Errors encountered: {errors}")
    print(f"Time elapsed: {minutes}m {seconds}s")
    print(f"Output directory: {OUTPUT_DIR}")
    print("=" * 70)

if __name__ == '__main__':
    main()
