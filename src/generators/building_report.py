"""
Nationwide Building Report Generator
Simply displays the data we have, no bullshit explanations.
"""

import pandas as pd
import sys
import os
import subprocess
import math
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
    AWS_BASE_URL,
    PORTFOLIO_ORGS_PATH,
    NYC_BUILDING_SCRIPT as CONFIG_NYC_BUILDING_SCRIPT,
    NYC_10YR_SAVINGS_PATH,
    EUI_POST_ODCV_PATH,
    LEED_MATCHES_PATH
)

# NYC special buildings - use NYC building.py for these
NYC_BUILDING_SCRIPT = str(CONFIG_NYC_BUILDING_SCRIPT)
NYC_BBLS = set()
try:
    nyc_df = pd.read_csv(str(NYC_10YR_SAVINGS_PATH))
    NYC_BBLS = set(str(bbl) for bbl in nyc_df['bbl'].dropna())
    print(f"✓ Loaded {len(NYC_BBLS)} special NYC BBLs")
except Exception as e:
    print(f"Warning: Could not load NYC BBLs: {e}")

# Configuration - use centralized config
CSV_PATH = str(BUILDING_DATA_PATH)
OUTPUT_DIR = str(BUILDINGS_OUTPUT_DIR) + '/'
IMAGES_DIR = str(CONFIG_IMAGES_DIR)
AWS_BUCKET = AWS_BASE_URL

# Load organization display names and URLs mapping
ORG_DISPLAY_NAMES = {}
ORG_URLS = {}
try:
    orgs_df = pd.read_csv(str(PORTFOLIO_ORGS_PATH))
    for _, org_row in orgs_df.iterrows():
        org_name = org_row.get('organization', '')
        display_name = org_row.get('display_name', '')
        org_url = org_row.get('org_url', '')
        if org_name:
            org_key = str(org_name).strip().lower()
            if display_name and pd.notna(display_name) and str(display_name).strip():
                ORG_DISPLAY_NAMES[org_key] = str(display_name).strip()
            if org_url and pd.notna(org_url) and str(org_url).strip():
                ORG_URLS[org_key] = str(org_url).strip()
except Exception as e:
    print(f"Warning: Could not load organization data: {e}")

# Load post-ODCV EUI lookup
EUI_POST_ODCV = {}
try:
    eui_df = pd.read_csv(str(EUI_POST_ODCV_PATH))
    for _, eui_row in eui_df.iterrows():
        bid = eui_row.get('id_building', '')
        eui_val = eui_row.get('energy_site_eui_post_odcv')
        if bid and pd.notna(eui_val):
            EUI_POST_ODCV[bid] = float(eui_val)
except Exception as e:
    print(f"Warning: Could not load EUI post-ODCV data: {e}")

# Load LEED certification data
LEED_DATA = {}
try:
    leed_df = pd.read_csv(str(LEED_MATCHES_PATH))
    for _, leed_row in leed_df.iterrows():
        p_idx = leed_row.get('portfolio_idx')
        if pd.notna(p_idx):
            LEED_DATA[int(p_idx)] = {
                'level': leed_row.get('leed_certification_level'),
                'url': leed_row.get('leed_project_url'),
                'date': leed_row.get('leed_certification_date'),
                'rating_system': leed_row.get('leed_rating_system')
            }
    print(f"✓ Loaded {len(LEED_DATA)} LEED certifications")
except Exception as e:
    print(f"Warning: Could not load LEED data: {e}")

# Load utility logo mappings from CSV
UTILITY_LOGOS = {}
try:
    utility_logos_path = os.path.join(os.path.dirname(__file__), '../../data/source/utility_logos.csv')
    utility_df = pd.read_csv(utility_logos_path)
    for _, row in utility_df.iterrows():
        name = row.get('utility_name', '')
        logo_url = row.get('aws_logo_url', '')
        logo_file = row.get('logo_file', '')
        if name and (logo_url or logo_file):
            if logo_url and str(logo_url).lower() not in ['nan', '', 'none']:
                UTILITY_LOGOS[name] = logo_url
            elif logo_file and str(logo_file).lower() not in ['nan', '', 'none']:
                UTILITY_LOGOS[name] = f'https://nationwide-odcv-images.s3.us-east-2.amazonaws.com/logos/utilities/{logo_file}'
    print(f"✓ Loaded {len(UTILITY_LOGOS)} utility logo mappings")
except Exception as e:
    print(f"Warning: Could not load utility logos: {e}")

# Utility rate page URLs - click logo to view commercial rates
UTILITY_RATE_URLS = {
    'PG&E': 'https://www.pge.com/tariffs/en/rate-information/electric-rates.html',
    'Con Ed': 'https://www.coned.com/en/rates-tariffs/rates/electric-rates-schedule',
    'SoCal Edison': 'https://www.sce.com/regulatory/regulatory-information/tariff-books',
    'Pepco': 'https://www.pepco.com/MyAccount/MyBillUsage/Pages/CurrentElectric.aspx',
    'LADWP': 'https://www.ladwp.com/account/understanding-your-rates/commercial-electric-rates',
    'SDG&E': 'https://www.sdge.com/rates-and-regulations/current-and-effective-tariffs',
    'ComEd': 'https://www.comed.com/MyAccount/MyBillUsage/Pages/RatePamphlets.aspx',
    'Eversource': 'https://www.eversource.com/business/account-billing/manage-bill/about-your-bill/rates-tariffs/summary-of-electric-rates',
    'Xcel Energy': 'https://www.xcelenergy.com/company/rates_and_regulations/rates/rate_books',
    'City Light': 'https://www.seattle.gov/city-light/business-solutions/business-billing-and-account-information/business-rates',
    'PECO': 'https://www.puc.pa.gov/filing-resources/tariffs/electric-tariffs/',
    'Portland General': 'https://portlandgeneral.com/about/info/rates-and-regulatory/tariff',
    'SMUD': 'https://www.smud.org/Rate-Information/Business-rates',
    'Georgia Power': 'https://www.georgiapower.com/business/billing-and-rates/power-and-light-tariffs.html',
    'Evergy': 'https://www.evergy.com/manage-account/rate-information-link/how-rates-are-set/rate-overviews/detailed-tariffs',
    'PSE': 'https://www.pse.com/en/pages/rates/electric-tariffs-and-rules',
    'Ameren': 'https://www.ameren.com/bill/rates/business',
    'Duke Energy': 'https://www.duke-energy.com/home/billing/rates/index-of-rate-schedules?jur=FL01',
    'Glendale Water & Power': 'https://www.glendaleca.gov/government/departments/glendale-water-and-power/rates',
    'Pasadena Water & Power': 'https://pwp.cityofpasadena.net/rates-information/',
    'Burbank Water & Power': 'https://www.burbankwaterandpower.com/electric/rates-and-charges',
}

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
    'Berkeley': 'BESO',  # Berkeley Energy Saving Ordinance
    'default_ca': 'AB 802',
}

# Cities with Building Performance Standards (have fine avoidance)
BPS_CITIES = ['New York', 'Boston', 'Cambridge', 'Washington', 'Denver', 'Seattle', 'St. Louis']

# BPS law details for tooltips - explains fine avoidance calculation method
# Includes exemption info for dynamic tooltip generation
BPS_TOOLTIP_INFO = {
    'New York': {
        'law': 'NYC Local Law 97',
        'method': 'emission cap',
        'penalty': '$268/tCO2e over cap',
        'cap': '0.00758 tCO2e/sqft',
        'min_sqft': 25000,
        'source': 'NYC Dept of Buildings',
        'source_url': 'https://www.nyc.gov/site/buildings/codes/ll97-greenhouse-gas-emissions-reductions.page',
        'effective': '2024-2029 (stricter limits 2030+)',
        'note': 'Current cap applies through 2029. In 2030, caps tighten ~50% making compliance harder.',
        'exempt_types': ['K-12 School', 'Government'],
        'exempt_reason': 'have alternative compliance pathways under Article 321'
    },
    'Boston': {
        'law': 'BERDO 2.0',
        'method': 'emission cap',
        'penalty': '$234/tCO2e over cap',
        'cap': '0.0053 tCO2e/sqft',
        'min_sqft': 20000,
        'source': 'City of Boston',
        'source_url': 'https://www.boston.gov/departments/environment/berdo',
        'effective': '2025 (first compliance year)',
        'note': 'Emissions caps decrease every 5 years through 2050, requiring ongoing improvements.',
        'exempt_types': [],
        'exempt_reason': ''
    },
    'Cambridge': {
        'law': 'Cambridge BEUDO',
        'method': 'baseline reduction',
        'penalty': '$234/tCO2e over target',
        'cap': '20% below baseline',
        'min_sqft': 25000,
        'source': 'City of Cambridge',
        'source_url': 'https://www.cambridgema.gov/beudo',
        'effective': '2025 (first compliance period)',
        'note': 'Unlike Boston (fixed cap), Cambridge requires 20% reduction from each building\'s own baseline emissions. Multifamily only reports.',
        'exempt_types': ['Multifamily'],
        'exempt_reason': 'only report emissions (no reduction fines)'
    },
    'Washington': {
        'law': 'DC BEPS',
        'method': 'ENERGY STAR score',
        'penalty': '$10/sqft (prorated)',
        'cap': 'By type (ES targets)',
        'min_sqft': 50000,
        'source': 'DC DOEE',
        'source_url': 'https://doee.dc.gov/service/building-energy-performance-standards',
        'effective': '2026 (first compliance deadline)',
        'note': 'Uses ENERGY STAR targets by building type: Office=71, Hotel=54, Hospital=50, Multifamily=66. Fine prorated by gap from target.',
        'exempt_types': [],
        'exempt_reason': ''
    },
    'Denver': {
        'law': 'Energize Denver',
        'method': 'EUI glide path',
        'penalty': '$0.15/kBtu over target',
        'cap': 'By type (glide path to 2032)',
        'min_sqft': 25000,
        'source': 'City of Denver',
        'source_url': 'https://www.denvergov.org/Government/Agencies-Departments-Offices/Agencies-Departments-Offices-Directory/Climate-Action-Sustainability-and-Resiliency/Energize-Denver',
        'effective': '2029 (first fines, 2028 interim target)',
        'note': 'Penalty rate reduced 50% (April 2025). Timeline: 2028 interim → 2032 final. Linear glide path (9/13 progress by 2028).',
        'exempt_types': ['K-12 School'],
        'exempt_reason': 'have alternative compliance pathways'
    },
    'Seattle': {
        'law': 'Seattle BEPS',
        'method': 'emission cap',
        'penalty': '$10/sqft per 5yr cycle',
        'cap': '0.00081 tCO2e/sqft',
        'min_sqft': 20000,
        'source': 'City of Seattle',
        'source_url': 'https://www.seattle.gov/environment/climate-change/buildings-and-energy/building-performance-standards',
        'effective': '2027-2031 (first compliance cycle)',
        'note': 'Lower penalty rate but applies to entire building. Seattle\'s hydro grid (98% clean) makes this achievable.',
        'exempt_types': [],
        'exempt_reason': ''
    },
    'St. Louis': {
        'law': 'St. Louis BEPS',
        'method': 'EUI target',
        'penalty': '$500/day non-compliance',
        'cap': '71.7 kBtu/sqft EUI',
        'min_sqft': 50000,
        'source': 'City of St. Louis',
        'source_url': 'https://www.stlouis-mo.gov/government/departments/public-safety/building/',
        'effective': '2025 (reporting begins)',
        'note': 'Daily fines accumulate quickly—$182,500/year if non-compliant. Smaller cities often have aggressive enforcement.',
        'exempt_types': [],
        'exempt_reason': ''
    },
}

# Building type categorizations for ODCV savings calculation
# Building types where vacancy is used in the ODCV formula: V + (1-V)(1-U)
# Per ODCV_SAVINGS_METHODOLOGY_COMPLETE.md - these have centralized HVAC where vacant space still gets ventilated
USES_VACANCY_FORMULA = ['Office', 'Medical Office', 'Mixed Use']

SINGLE_TENANT_TYPES = [
    'K-12 School', 'Higher Ed', 'Retail',
    'Supermarket', 'Wholesale Club', 'Hotel',
    'Restaurant/Bar', 'Theater', 'Library/Museum', 'Venue',
    'Bank Branch', 'Vehicle Dealership', 'Courthouse', 'Outpatient Clinic',
    'Sports/Gaming Center'
]

CONSTRAINED_TYPES = [
    'Inpatient Hospital', 'Specialty Hospital', 'Residential Care',
    'Laboratory', 'Police Station', 'Fire Station'
]

#===============================================================================
# BUILDING TYPE INFO - For dynamic tooltips
#===============================================================================

BUILDING_TYPE_INFO = {
    'Office': {
        'category': 'Multi-Tenant',
        'floor': 0.20, 'ceiling': 0.40,
        'uses_vacancy': True,
        'formula': 'Vacancy + (1-Vacancy) × (1-Utilization)',
        'elec_hvac_typical': 0.60,
        'gas_hvac_typical': 0.875,
        'load_factor': 0.45,
        'demand_rate_typical': 35.0,
        'explanation': 'Centralized HVAC ventilates vacant floors at design capacity. Hybrid work (avg 52% utilization) + vacancy creates 50-60% opportunity in typical buildings.'
    },
    'Medical Office': {
        'category': 'Multi-Tenant',
        'floor': 0.20, 'ceiling': 0.40,
        'uses_vacancy': True,
        'formula': 'Vacancy + (1-Vacancy) × (1-Utilization)',
        'elec_hvac_typical': 0.60,
        'gas_hvac_typical': 0.848,
        'load_factor': 0.45,
        'demand_rate_typical': 35.0,
        'explanation': 'Like office buildings, medical offices have centralized systems that condition empty exam rooms and suites. ODCV adjusts ventilation to actual patient presence.'
    },
    'Mixed Use': {
        'category': 'Multi-Tenant',
        'floor': 0.18, 'ceiling': 0.38,
        'uses_vacancy': True,
        'formula': 'Vacancy + (1-Vacancy) × (1-Utilization)',
        'elec_hvac_typical': 0.55,
        'gas_hvac_typical': 0.80,
        'load_factor': 0.45,
        'demand_rate_typical': 35.0,
        'explanation': 'Combination of office, retail, residential uses. Savings vary by tenant mix but centralized systems still ventilate vacant spaces.'
    },
    'K-12 School': {
        'category': 'Single-Tenant',
        'floor': 0.20, 'ceiling': 0.45,
        'uses_vacancy': False,
        'formula': '1 - Utilization',
        'elec_hvac_typical': 0.55,
        'gas_hvac_typical': 0.796,
        'load_factor': 0.35,
        'demand_rate_typical': 8.0,
        'explanation': 'Schools empty after 3pm daily, all weekends, 10+ weeks summer. Total "empty" time exceeds 55% of year. Highest ceiling (45%) reflects extreme schedule-driven opportunity.'
    },
    'Higher Ed': {
        'category': 'Single-Tenant',
        'floor': 0.20, 'ceiling': 0.45,
        'uses_vacancy': False,
        'formula': '1 - Utilization',
        'elec_hvac_typical': 0.55,
        'gas_hvac_typical': 0.796,
        'load_factor': 0.35,
        'demand_rate_typical': 8.0,
        'explanation': 'Semester breaks (winter, spring, summer), variable class schedules, evening/weekend classes in some buildings. Similar to K-12 but more diverse usage patterns.'
    },
    'Hotel': {
        'category': 'Single-Tenant',
        'floor': 0.15, 'ceiling': 0.35,
        'uses_vacancy': False,
        'formula': '1 - Utilization',
        'elec_hvac_typical': 0.47,
        'gas_hvac_typical': 0.197,
        'load_factor': 0.55,
        'demand_rate_typical': 28.7,
        'explanation': 'Room-level variability: 60-80% occupancy typical, plus guests out during day. Note: Only 20% of gas goes to HVAC (rest is hot water 42%, cooking 33%).'
    },
    'Retail': {
        'category': 'Single-Tenant',
        'floor': 0.15, 'ceiling': 0.35,
        'uses_vacancy': False,
        'formula': '1 - Utilization',
        'elec_hvac_typical': 0.56,
        'gas_hvac_typical': 0.777,
        'load_factor': 0.40,
        'demand_rate_typical': 35.0,
        'explanation': 'Significant intra-day variability: opening/closing with staff only, mid-morning lulls, lunch/evening rushes. Opportunity comes from modulating to actual customer traffic.'
    },
    'Supermarket': {
        'category': 'Single-Tenant',
        'floor': 0.10, 'ceiling': 0.25,
        'uses_vacancy': False,
        'formula': '1 - Utilization',
        'elec_hvac_typical': 0.32,
        'gas_hvac_typical': 0.75,
        'load_factor': 0.65,
        'demand_rate_typical': 35.0,
        'explanation': 'Long hours (often 6am-midnight or 24/7) with steady traffic reduce empty-space opportunity.'
    },
    'Restaurant/Bar': {
        'category': 'Single-Tenant',
        'floor': 0.10, 'ceiling': 0.25,
        'uses_vacancy': False,
        'formula': '1 - Utilization',
        'elec_hvac_typical': 0.45,
        'gas_hvac_typical': 0.176,
        'load_factor': 0.45,
        'demand_rate_typical': 35.0,
        'explanation': 'Predictable meal-time peaks with low occupancy between lunch and dinner rushes.'
    },
    'Theater': {
        'category': 'Single-Tenant',
        'floor': 0.18, 'ceiling': 0.40,
        'uses_vacancy': False,
        'formula': '1 - Utilization',
        'elec_hvac_typical': 0.50,
        'gas_hvac_typical': 0.80,
        'load_factor': 0.35,
        'demand_rate_typical': 22.0,
        'explanation': 'Performance schedules create extreme variability—completely empty for hours then full capacity for shows. High opportunity during non-show periods.'
    },
    'Venue': {
        'category': 'Single-Tenant',
        'floor': 0.20, 'ceiling': 0.45,
        'uses_vacancy': False,
        'formula': '1 - Utilization',
        'elec_hvac_typical': 0.50,
        'gas_hvac_typical': 0.80,
        'load_factor': 0.35,
        'demand_rate_typical': 22.0,
        'explanation': 'Convention centers, banquet halls have most extreme occupancy variability—empty for days/weeks then full capacity for single events.'
    },
    'Library/Museum': {
        'category': 'Single-Tenant',
        'floor': 0.12, 'ceiling': 0.28,
        'uses_vacancy': False,
        'formula': '1 - Utilization',
        'elec_hvac_typical': 0.50,
        'gas_hvac_typical': 0.80,
        'load_factor': 0.35,
        'demand_rate_typical': 6.0,
        'explanation': 'Open ~50 hours/week with 30-40% visitor occupancy during those hours. Galleries sit mostly empty nights and weekends.'
    },
    'Wholesale Club': {
        'category': 'Single-Tenant',
        'floor': 0.10, 'ceiling': 0.25,
        'uses_vacancy': False,
        'formula': '1 - Utilization',
        'elec_hvac_typical': 0.35,
        'gas_hvac_typical': 0.75,
        'load_factor': 0.60,
        'demand_rate_typical': 35.0,
        'explanation': '30-40% of building is back-of-house warehouse with minimal staff. Sales floor sees weekend-heavy traffic patterns.'
    },
    'Outpatient Clinic': {
        'category': 'Single-Tenant',
        'floor': 0.15, 'ceiling': 0.32,
        'uses_vacancy': False,
        'formula': '1 - Utilization',
        'elec_hvac_typical': 0.54,
        'gas_hvac_typical': 0.60,
        'load_factor': 0.50,
        'demand_rate_typical': 22.0,
        'explanation': 'Appointment-driven: exam rooms occupied just 25-35% of operating hours, empty between patients.'
    },
    'Inpatient Hospital': {
        'category': 'Constrained',
        'floor': 0.05, 'ceiling': 0.15,
        'uses_vacancy': False,
        'formula': '(1 - Utilization) × 0.3',
        'elec_hvac_typical': 0.54,
        'gas_hvac_typical': 0.603,
        'load_factor': 0.65,
        'demand_rate_typical': 22.0,
        'explanation': '24/7 operation limits opportunity, but non-clinical areas (waiting rooms, admin, cafeteria) have variable occupancy.'
    },
    'Specialty Hospital': {
        'category': 'Constrained',
        'floor': 0.05, 'ceiling': 0.15,
        'uses_vacancy': False,
        'formula': '(1 - Utilization) × 0.3',
        'elec_hvac_typical': 0.54,
        'gas_hvac_typical': 0.603,
        'load_factor': 0.65,
        'demand_rate_typical': 22.0,
        'explanation': '24/7 operation limits opportunity, but admin areas and waiting rooms have variable occupancy.'
    },
    'Residential Care': {
        'category': 'Constrained',
        'floor': 0.05, 'ceiling': 0.15,
        'uses_vacancy': False,
        'formula': '(1 - Utilization) × 0.3',
        'elec_hvac_typical': 0.50,
        'gas_hvac_typical': 0.70,
        'load_factor': 0.65,
        'demand_rate_typical': 22.0,
        'explanation': 'Residents live there 24/7—unlike offices that empty at night. Common areas have some variability, but overall building load is relatively constant.'
    },
}

# Default building type info for unknown types
DEFAULT_BUILDING_INFO = {
    'category': 'Single-Tenant',
    'floor': 0.15, 'ceiling': 0.35,
    'uses_vacancy': False,
    'formula': '1 - Utilization',
    'elec_hvac_typical': 0.50,
    'gas_hvac_typical': 0.80,
    'load_factor': 0.45,
    'demand_rate_typical': 35.0,
    'explanation': 'Standard commercial building. Savings depend on operating hours and occupancy patterns.'
}

#===============================================================================
# BUILDING-TYPE SPECIFIC ENERGY NOTES (for dynamic tooltips)
#===============================================================================

BUILDING_TYPE_ENERGY_NOTES = {
    'Hotel': {
        'elec_note': "47% of electricity is HVAC - cooling and ventilation for guest rooms and common areas.",
        'gas_note': "Only 20% of gas goes to HVAC. 42% is domestic hot water, 33% is cooking/kitchens.",
        'load_factor_note': "Higher load factor (55%) due to 24/7 operation across guest rooms.",
    },
    'Restaurant/Bar': {
        'elec_note': "45% of electricity is HVAC. Kitchen exhaust fans are a significant electric load.",
        'gas_note': "Only 18% of gas is HVAC. Kitchen cooking consumes 72% of natural gas.",
        'load_factor_note': "Peak demand during meal rushes. Kitchen equipment draws constant power.",
    },
    'Supermarket': {
        'elec_note': "Only 32% of electricity is HVAC. ~40% is refrigeration for food cases and freezers.",
        'gas_note': "75% of gas used for HVAC - higher than average due to makeup air for exhaust.",
        'load_factor_note': "High load factor (65%) from continuous refrigeration systems running 24/7.",
    },
    'K-12 School': {
        'elec_note': "55% of electricity is HVAC. Large spaces, older systems, extreme seasonal variability.",
        'gas_note': "80% of gas is HVAC - mostly heating in cooler months. Minimal cooking/DHW.",
        'load_factor_note': "Lower load factor (35%) - empty nights, weekends, and 10+ weeks of summer vacation.",
    },
    'Higher Ed': {
        'elec_note': "55% of electricity is HVAC. Campus buildings have diverse usage patterns.",
        'gas_note': "80% of gas is HVAC. Research buildings may have higher due to fume hood makeup air.",
        'load_factor_note': "Variable load factor (35-45%) - semester breaks and summer significantly reduce load.",
    },
    'Office': {
        'elec_note': "60% of electricity is HVAC. Central systems condition entire floors even when partially occupied.",
        'gas_note': "87.5% of gas is HVAC - primarily heating. High percentage due to minimal cooking/DHW.",
        'load_factor_note': "Typical 45% load factor - peaks during 9-5 work hours, low overnight and weekends.",
    },
    'Medical Office': {
        'elec_note': "60% of electricity is HVAC. Similar to office but with additional ventilation requirements.",
        'gas_note': "85% of gas is HVAC. Medical sterilization and DHW use the remaining 15%.",
        'load_factor_note': "Moderate load factor (45%) - appointment-based occupancy with evening/weekend closures.",
    },
    'Retail': {
        'elec_note': "56% of electricity is HVAC. Open floor plans require high airflow for customer comfort.",
        'gas_note': "78% of gas is HVAC. Retail has minimal cooking or process loads.",
        'load_factor_note': "Moderate load factor (40%) - peaks during shopping hours, low overnight.",
    },
    'Inpatient Hospital': {
        'elec_note': "54% of electricity is HVAC. Strict ventilation codes (ASHRAE 170) require high air change rates.",
        'gas_note': "60% of gas is HVAC. Medical sterilization, DHW, and kitchen use remaining 40%.",
        'load_factor_note': "High load factor (65%) - 24/7 operation with critical care requirements.",
    },
}

# Default notes for building types not in the dictionary
DEFAULT_ENERGY_NOTES = {
    'elec_note': "Electricity HVAC shares from EIA CBECS 2018 survey, adjusted for building type and climate. (CBECS 2018)",
    'gas_note': "Natural gas HVAC shares from EIA CBECS 2018 survey, adjusted for building type and climate. (CBECS 2018)",
    'load_factor_note': "Load factor estimated from building type and operating patterns. (CBECS 2018)",
}

#===============================================================================
# BUILDING TYPE STORIES - For Energy section tooltips
# Each story explains WHY this building type has savings potential (or doesn't)
#===============================================================================

BUILDING_TYPE_STORIES = {
    'Office': "We calculate office savings using federal CBECS survey data for HVAC energy shares, city-specific vacancy rates from CBRE, and badge-swipe occupancy data from Kastle Systems. Hybrid work has dramatically reduced office attendance, while vacancy remains elevated in most markets. Buildings condition all spaces regardless of actual presence—ODCV captures the gap between design capacity and reality. (CBRE, Kastle Systems)",

    'Hotel': "We calculate hotel savings using STR room occupancy data combined with guest presence patterns—guests are typically out during daytime hours. Even booked rooms sit empty most of the day. Markets with higher occupancy show less savings potential than lower-occupancy markets. (STR)",

    'K-12 School': "We calculate school savings using NCES instructional day requirements and state calendar data. Schools are empty during summer break, weekends, holidays, and after dismissal. Year-round calendar schools have higher utilization than traditional calendar schools. Most school buildings sit empty the majority of annual hours. (NCES)",

    'Retail': "We calculate retail savings using traffic patterns—stores are built for peak capacity but see much lower average attendance. Mornings are slow, evenings busier, overnight closed. Urban locations with steadier foot traffic show less savings than suburban stores with sharper peaks and valleys. (CBECS 2018)",

    'Higher Ed': "We calculate university savings using NCES data and academic calendars. Only a portion of the year has classes in session, and during those weeks most classrooms sit empty between lectures. Entire buildings empty during breaks. (NCES)",

    'Residential Care': "We calculate residential care savings using NIC MAP Vision occupancy data. Unlike hotels where guests leave during the day, residents live on-site continuously. Savings are limited to common areas during overnight hours when residents are in their rooms. (NIC MAP Vision)",

    'Medical Office': "We calculate medical office savings using CBRE vacancy data and MGMA provider productivity benchmarks. Medical offices have low vacancy compared to regular offices, but exam rooms are occupied only during brief patient appointments. (CBRE, MGMA)",

    'Supermarket': "We calculate supermarket savings using traffic patterns. Supermarkets operate long hours with steady traffic, but still swing between evening peaks and quiet early mornings. (CBECS 2018)",

    'Specialty Hospital': "We calculate specialty hospital savings using AHA hospital data. Continuous operations limit savings in patient areas, but admin offices, waiting rooms, and cafeterias have variable occupancy—especially during off-hours. (AHA)",

    'Inpatient Hospital': "We calculate inpatient hospital savings using AHA data. Hospitals run continuously, but non-clinical areas have highly variable occupancy—waiting rooms, admin offices, and cafeterias empty at different times while patient areas stay occupied. (AHA)",

    'Mixed Use': "We calculate mixed-use savings using the same methodology as offices—CBRE vacancy data and Kastle badge-swipe utilization. Office floors follow hybrid work patterns while retail floors see variable traffic. Centralized HVAC conditions all spaces regardless of occupancy. (CBRE, Kastle Systems)",

    'Wholesale Club': "We calculate wholesale club savings by weighting the sales floor against large back-of-house warehouse areas with minimal staff. Sales floor traffic concentrates on weekends while warehouse areas see sparse occupancy. (CBECS 2018)",

    'Venue': "We calculate venue savings using event schedules. Arenas, convention centers, and concert halls host events sporadically but typically condition continuously. These massive spaces sit empty the vast majority of annual hours. (CBECS 2018)",

    'Theater': "We calculate theater savings using performance schedules. Shows run just a few hours at a time, a few days per week—but HVAC often conditions the space continuously. (CBECS 2018)",

    'Restaurant/Bar': "We calculate restaurant savings from dining areas—kitchens have exhaust requirements that can't be reduced. Dining rooms swing between busy meal rushes and empty periods between. (CBECS 2018)",

    'Library/Museum': "We calculate library and museum savings from visitor traffic patterns. Climate control runs continuously for collection preservation, but visitor presence varies widely. Galleries and reading rooms designed for crowds often see sparse attendance. (CBECS 2018)",

    'Outpatient Clinic': "We calculate clinic savings using MGMA provider productivity benchmarks. Exam rooms are occupied only during brief patient appointments, then sit empty until the next patient. (MGMA)",

}

# Default story for building types not in the dictionary
DEFAULT_BUILDING_STORY = "We calculate savings using federal CBECS survey data for HVAC energy shares, adjusted for this building's age, efficiency rating, and local climate. ODCV reduces ventilation when spaces are unoccupied—the savings depend on how much of the time this building sits empty or underutilized."

#===============================================================================
# UTILIZATION RANGES BY BUILDING TYPE (from methodology)
#===============================================================================

UTILIZATION_RANGES = {
    'Office': {'low': 55, 'high': 93, 'source': 'CBRE, Kastle Systems'},
    'Medical Office': {'low': 75, 'high': 75, 'source': 'CBRE Healthcare'},
    'K-12 School': {'low': 54, 'high': 85, 'source': 'NCES'},
    'Higher Ed': {'low': 66, 'high': 66, 'source': 'NCES'},
    'Hotel': {'low': 67, 'high': 73, 'source': 'STR/CoStar'},
    'Retail': {'low': 55, 'high': 65, 'source': 'CBECS 2018'},
    'Inpatient Hospital': {'low': 76, 'high': 78, 'source': 'AHA'},
    'Outpatient Clinic': {'low': 70, 'high': 70, 'source': 'MGMA'},
    'Library/Museum': {'low': 42, 'high': 55, 'source': 'CBECS 2018'},
    'Restaurant/Bar': {'low': 50, 'high': 60, 'source': 'CBECS 2018'},
}

#===============================================================================
# CITY ELECTRICITY EMISSION FACTORS (from methodology - EPA eGRID 2023)
#===============================================================================

CITY_EMISSION_FACTORS = {
    'Seattle': {
        'factor': 0.0000029,
        'relative': '32× cleaner than US average',
        'grid': '98% hydroelectric',
        'implication': 'gas reduction is more impactful for carbon savings'
    },
    'San Francisco': {
        'factor': 0.0000570,
        'relative': '1.6× cleaner than US average',
        'grid': 'California renewable mix',
        'implication': 'gas reduction often has more carbon impact than electricity'
    },
    'Los Angeles': {
        'factor': 0.0000570,
        'relative': '1.6× cleaner than US average',
        'grid': 'California renewable mix',
        'implication': 'gas reduction often has more carbon impact than electricity'
    },
    'Portland': {
        'factor': 0.0000595,
        'relative': '1.5× cleaner than US average',
        'grid': 'Pacific Northwest hydro mix',
        'implication': 'gas reduction has higher carbon impact'
    },
    'Boston': {
        'factor': 0.0000717,
        'relative': '1.3× cleaner than US average',
        'grid': 'New England natural gas',
        'implication': 'both electricity and gas reductions matter for carbon'
    },
    'Cambridge': {
        'factor': 0.0000717,
        'relative': '1.3× cleaner than US average',
        'grid': 'New England natural gas',
        'implication': 'both electricity and gas reductions matter for carbon'
    },
    'Washington': {
        'factor': 0.0000794,
        'relative': '1.2× cleaner than US average',
        'grid': 'PJM regional mix',
        'implication': 'both electricity and gas reductions matter'
    },
    'New York': {
        'factor': 0.0000847,
        'relative': '1.1× cleaner than US average',
        'grid': 'natural gas, nuclear, and renewables',
        'implication': 'ODCV reduces emissions from both electricity and gas'
    },
    'Atlanta': {
        'factor': 0.0000988,
        'relative': '1.1× dirtier than US average',
        'grid': 'Southern natural gas and coal mix',
        'implication': 'electricity reduction has moderate carbon impact'
    },
    'Denver': {
        'factor': 0.0001378,
        'relative': '1.5× dirtier than US average',
        'grid': 'Colorado coal transitioning to renewables',
        'implication': 'electricity reduction has significant carbon impact'
    },
    'Chicago': {
        'factor': 0.0001649,
        'relative': '1.8× dirtier than US average',
        'grid': 'Midwest coal-heavy grid',
        'implication': 'electricity reduction has major carbon impact'
    },
    'St. Louis': {
        'factor': 0.0001649,
        'relative': '1.8× dirtier than US average',
        'grid': 'Midwest coal-heavy grid',
        'implication': 'electricity reduction has major carbon impact'
    },
}

US_AVG_EMISSION_FACTOR = 0.0000922  # tCO2e/kBtu baseline

#===============================================================================
# AUTOMATION SCORE BY YEAR BUILT (from methodology)
#===============================================================================

def get_automation_score(year_built):
    """Return automation score (0-1) based on year built."""
    if year_built is None:
        return 0.50  # default
    if year_built < 1970:
        return 0.00  # pneumatic controls, constant volume
    elif year_built < 1990:
        return 0.25  # early electronic, limited DDC
    elif year_built < 2005:
        return 0.50  # DDC becoming standard, basic BMS
    elif year_built < 2015:
        return 0.75  # modern BMS, IP-based controls
    else:
        return 1.00  # smart building ready, integrated systems

def get_automation_description(year_built):
    """Return plain-language description of automation capability."""
    if year_built is None:
        return "moderate automation capability"
    if year_built < 1970:
        return "limited automation (pneumatic controls typical of pre-1970 buildings)"
    elif year_built < 1990:
        return "basic automation (early electronic controls)"
    elif year_built < 2005:
        return "moderate automation (basic building management systems)"
    elif year_built < 2015:
        return "good automation (modern BMS with IP-based controls)"
    else:
        return "excellent automation (smart building ready systems)"

#===============================================================================
# CAP RATE RANGES BY BUILDING TYPE (from methodology - CBRE)
#===============================================================================

CAP_RATE_RANGES = {
    'Office': {'low': 5.0, 'high': 10.2, 'multiplier_low': 10, 'multiplier_high': 20},
    'Hotel': {'low': 5.0, 'high': 9.5, 'multiplier_low': 11, 'multiplier_high': 20},
    'Retail': {'low': 5.0, 'high': 9.0, 'multiplier_low': 11, 'multiplier_high': 20},
    'Medical Office': {'low': 6.2, 'high': 8.5, 'multiplier_low': 12, 'multiplier_high': 16},
    'K-12 School': {'low': 7.0, 'high': 8.0, 'multiplier_low': 12, 'multiplier_high': 14},
    'Inpatient Hospital': {'low': 7.0, 'high': 8.0, 'multiplier_low': 12, 'multiplier_high': 14},
    'Higher Ed': {'low': 7.0, 'high': 8.0, 'multiplier_low': 12, 'multiplier_high': 14},
}

DEFAULT_CAP_RATE = {'low': 6.0, 'high': 9.0, 'multiplier_low': 11, 'multiplier_high': 17}

#===============================================================================
# ENERGY SECTION COLUMN TOOLTIPS
#===============================================================================

# Static fallback (dynamic functions below are preferred)
ENERGY_COLUMN_TOOLTIPS = {
    'current': "From city benchmarking disclosure. Actual metered energy.",
    'new': "Projected consumption if HVAC matched actual occupancy.",
    'change': "Annual energy reduction from ODCV.",
}

#===============================================================================
# DYNAMIC COLUMN TOOLTIP FUNCTIONS (for Energy section)
#===============================================================================

# NEW column: Methodology + data sources by building type
# Sources get auto-hyperlinked by inject_source_links()
NEW_COLUMN_SOURCES = {
    'Office': "HVAC reduced using CBECS 2018 fuel splits, CBRE vacancy rates, Kastle badge-swipe occupancy data.",
    'Medical Office': "HVAC reduced using CBECS 2018 fuel splits, CBRE vacancy data, MGMA exam room utilization benchmarks.",
    'Hotel': "HVAC reduced using CBECS 2018 fuel splits, STR room occupancy data, guest presence patterns.",
    'K-12 School': "HVAC reduced using CBECS 2018 fuel splits, NCES instructional day requirements, state calendar data.",
    'Higher Ed': "HVAC reduced using CBECS 2018 fuel splits, NCES data, semester and break schedules.",
    'Retail': "HVAC reduced using CBECS 2018 fuel splits, operating hours and traffic patterns.",
    'Supermarket': "HVAC reduced using CBECS 2018 fuel splits, operating hours and traffic patterns.",
    'Restaurant/Bar': "HVAC reduced using CBECS 2018 fuel splits, meal-time traffic patterns.",
    'Inpatient Hospital': "HVAC reduced using CBECS 2018 fuel splits, AHA bed occupancy data.",
    'Specialty Hospital': "HVAC reduced using CBECS 2018 fuel splits, AHA bed occupancy data.",
    'Residential Care': "HVAC reduced using CBECS 2018 fuel splits, NIC MAP Vision occupancy data.",
    'Mixed Use': "HVAC reduced using CBECS 2018 fuel splits, CBRE vacancy, Kastle occupancy for office portion.",
    'Venue': "HVAC reduced using event schedules, industry utilization data.",
    'Theater': "HVAC reduced using performance schedules, Broadway/regional theater utilization data.",
    'Library/Museum': "HVAC reduced using visitor traffic data, operating hours patterns.",
    'Outpatient Clinic': "HVAC reduced using CBECS 2018 fuel splits, MGMA provider productivity benchmarks.",
    'Wholesale Club': "HVAC reduced using member traffic data, sales floor vs back-of-house weighting.",
    'default': "HVAC reduced using CBECS 2018 fuel splits, building type utilization benchmarks.",
}

# CHANGE column: Human-readable insight (WHY savings exist) by building type
# Sources at end get auto-hyperlinked by inject_source_links()
CHANGE_COLUMN_INSIGHTS = {
    'Office': "Offices have massive ODCV opportunity. Hybrid work means most workers come in only part of the week, and many floors sit entirely vacant—but centralized HVAC conditions all spaces at design capacity regardless. (CBRE, Kastle Systems)",
    'Medical Office': "Medical offices have strong ODCV potential. Exam rooms are occupied only during brief patient appointments, then sit empty until the next visit. (CBRE, MGMA)",
    'Hotel': "Hotels have significant ODCV opportunity. Many rooms are unoccupied on any given night, and even booked rooms sit empty during daytime hours when guests are out. (STR)",
    'K-12 School': "Schools have the highest ODCV potential of any building type. Buildings are completely empty during summer break, weekends, holidays, and after dismissal each day. (NCES)",
    'Higher Ed': "Universities have extreme ODCV opportunity. Classrooms sit empty between lectures, and entire buildings empty during semester breaks. (NCES)",
    'Retail': "Retail has meaningful ODCV opportunity. Stores are designed for peak capacity but see much lower average traffic—slow mornings, busier afternoons, closed overnight. (CBECS 2018)",
    'Supermarket': "Supermarkets have limited but real ODCV opportunity. Traffic swings between busy evening periods and quiet early mornings. (CBECS 2018)",
    'Restaurant/Bar': "Restaurants have ODCV opportunity in dining areas. Tables swing between packed meal rushes and empty mid-afternoon lulls. (CBECS 2018)",
    'Inpatient Hospital': "Hospitals have constrained but real ODCV opportunity. Non-clinical areas—waiting rooms, admin offices, cafeterias—have variable occupancy while patient areas stay occupied. (AHA)",
    'Specialty Hospital': "Specialty hospitals have similar ODCV patterns to inpatient facilities. Support areas have variable occupancy during off-hours. (AHA)",
    'Residential Care': "Residential care has limited ODCV opportunity. Unlike hotels, residents live on-site continuously. Savings come from common areas during overnight hours. (NIC MAP Vision)",
    'Mixed Use': "Mixed-use buildings combine office and retail ODCV opportunities. Office floors follow hybrid work patterns while retail floors see variable traffic throughout the day. (CBRE, Kastle Systems)",
    'Venue': "Venues have massive ODCV opportunity. Arenas and convention centers host events sporadically but condition continuously—these huge spaces sit empty most of the year. (CBECS 2018)",
    'Theater': "Theaters have strong ODCV potential. Shows run just a few hours at a time, a few days per week—but HVAC often conditions the space continuously. (CBECS 2018)",
    'Library/Museum': "Libraries and museums have moderate ODCV opportunity. Climate control runs for collection preservation, but visitor traffic varies widely. (CBECS 2018)",
    'Outpatient Clinic': "Clinics have strong ODCV potential. Exam rooms are occupied only during brief appointments, then sit empty until the next patient. (MGMA)",
    'Wholesale Club': "Wholesale clubs have moderate ODCV opportunity. Large back-of-house warehouse areas have minimal staff, and sales floor traffic concentrates on weekends. (CBECS 2018)",
    'default': "Most buildings are ventilated at design capacity regardless of actual occupancy. ODCV adjusts airflow to match real presence, capturing the gap between design and reality. (CBECS 2018)",
}

def get_current_column_tooltip(row):
    """CURRENT column tooltip - explains data source."""
    city = safe_val(row, 'loc_city', '')
    law = CITY_DISCLOSURE_LAWS.get(city, 'benchmarking')
    return f"Actual metered consumption from utility bills, reported to {city} through {law} disclosure. Real data, not an estimate."

def get_new_column_tooltip(row):
    """NEW column tooltip - explains projection by building type."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    city = safe_val(row, 'loc_city', '')

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        return f"""Projected consumption if ventilation matched actual occupancy—accounting for vacant floors and low utilization on occupied floors.<br><br>
Uses {city} vacancy from CBRE/Cushman, attendance from Kastle badge swipes, and HVAC % from CBECS 2018."""

    elif bldg_type in ('K-12 School', 'Higher Ed'):
        return f"""Projected consumption if HVAC responded to school calendar—summers, weekends, afternoons, holidays—instead of fixed timers.<br><br>
Uses {city} benchmarking, schedule data from NCES, and HVAC % from CBECS 2018."""

    elif bldg_type == 'Hotel':
        return f"""Projected consumption if room conditioning matched when guests are actually present.<br><br>
Only HVAC responds to occupancy—hotel gas splits ~20% HVAC, ~42% hot water, ~33% kitchens. Uses {city} room occupancy from STR Global."""

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital'):
        return f"""What consumption would look like with occupancy-based ventilation in <b>non-clinical areas only</b>—lobbies, offices, cafeterias, conference rooms.<br><br>
Patient areas excluded per ASHRAE 170. Uses {city} benchmarking and HVAC % from CBECS 2018."""

    elif bldg_type == 'Residential Care':
        return f"""What consumption would look like with occupancy-based conditioning in common areas only. Resident rooms unchanged.<br><br>
Uses {city} benchmarking, occupancy from NIC MAP Vision, and HVAC % from CBECS 2018."""

    elif bldg_type in ('Retail', 'Retail Store'):
        return f"""Projected consumption if ventilation matched foot traffic instead of running at peak capacity all day.<br><br>
Uses {city} benchmarking and HVAC % from CBECS 2018."""

    elif bldg_type == 'Supermarket':
        return f"""Projected consumption if sales floor HVAC matched traffic. Refrigeration unchanged—it doesn't respond to occupancy.<br><br>
Uses {city} benchmarking and HVAC/refrigeration split from CBECS 2018."""

    elif bldg_type == 'Wholesale Club':
        return f"""Projected consumption if conditioning matched member traffic patterns.<br><br>
Uses {city} benchmarking and HVAC % from CBECS 2018."""

    elif bldg_type in ('Venue', 'Theater'):
        return f"""Projected consumption if conditioning matched event schedules instead of running 24/7.<br><br>
Uses {city} benchmarking and HVAC % from CBECS 2018."""

    elif bldg_type == 'Restaurant/Bar':
        return f"""Projected consumption if dining area HVAC matched meal-time patterns. Kitchen unchanged—it doesn't respond to traffic.<br><br>
Only ~18% of restaurant gas is space heating (rest is cooking). Uses {city} benchmarking."""

    elif bldg_type in ('Library/Museum', 'Library', 'Museum'):
        return f"""Projected consumption if conditioning aligned with operating hours and visitor traffic.<br><br>
Uses {city} benchmarking and HVAC % from CBECS 2018."""

    elif bldg_type == 'Outpatient Clinic':
        return f"""Projected consumption if ventilation matched appointment schedules and clinic hours.<br><br>
Uses {city} benchmarking, scheduling from MGMA, and HVAC % from CBECS 2018."""

    else:
        return f"""Projected consumption if ventilation matched actual occupancy.<br><br>
Uses {city} benchmarking and HVAC % from CBECS 2018."""

def get_change_column_tooltip(row):
    """CHANGE column tooltip - explains what the difference represents."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        return """Energy wasted conditioning empty/underutilized spaces: vacant floors, empty conference rooms, unoccupied desks. Building conditions as if full when it's not."""

    elif bldg_type in ('K-12 School', 'Higher Ed'):
        return """Energy wasted running HVAC during summers, weekends, afternoons after dismissal, holidays—fixed timers ignoring the calendar."""

    elif bldg_type == 'Hotel':
        return """Energy wasted conditioning rooms when guests aren't present. Includes unsold rooms plus hours when guests are out (even sold rooms are only occupied ~10 hrs/day)."""

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital', 'Residential Care'):
        return """Energy wasted in non-clinical spaces (lobbies, offices, cafeterias) running at full capacity regardless of use. Patient/resident areas excluded."""

    elif bldg_type in ('Retail', 'Retail Store', 'Supermarket', 'Wholesale Club'):
        return """Energy wasted running HVAC at peak capacity during slow periods. Building conditions for the busiest hour all day long."""

    elif bldg_type in ('Venue', 'Theater'):
        return """Energy wasted conditioning around the clock for an intermittent-use venue. Building maintains conditions during the many hours between events."""

    elif bldg_type == 'Restaurant/Bar':
        return """In restaurants, the kitchen exhaust runs at full speed all day, which means only the dining area can respond to occupancy. And since the kitchen is typically 30-40% of the floor space, savings potential is limited to the dining portion."""

    else:
        return """Energy wasted conditioning empty/underutilized spaces. HVAC runs at design capacity regardless of who's actually there."""

#===============================================================================
# TOOLTIP DEFINITIONS
#===============================================================================

# Static tooltips - only for items that truly don't vary
TOOLTIPS = {
    'owner': "Building ownership from public records and regulatory filings.",
    'utility_provider': "Electric utility serving this building's location. Rates from NREL utility rate database by ZIP code.",
}

# Source text to URL mapping for tooltip hyperlinks
# Order matters - longer/more specific patterns first to avoid partial matches
SOURCE_TEXT_TO_URL = [
    # EPA / EIA Sources
    ('EPA eGRID 2023', 'https://www.epa.gov/egrid'),
    ('EPA eGRID', 'https://www.epa.gov/egrid'),
    ('EIA CBECS 2018', 'https://www.eia.gov/consumption/commercial/'),
    ('CBECS 2018', 'https://www.eia.gov/consumption/commercial/'),
    ('CBECS', 'https://www.eia.gov/consumption/commercial/'),
    ('EIA standard', 'https://www.eia.gov/environment/emissions/co2_vol_mass.php'),

    # Real Estate / Occupancy Sources
    ('CBRE Cap Rate Survey Q4 2024', 'https://www.cbre.com/insights/reports/us-cap-rate-survey-h1-2025'),
    ('CBRE Q4 2024', 'https://www.cbre.com/insights/figures/q3-2025-us-office-figures'),
    ('CBRE/Cushman', 'https://www.cbre.com/insights/figures/q3-2025-us-office-figures'),
    ('CBRE', 'https://www.cbre.com/insights/figures/q3-2025-us-office-figures'),
    ('Cushman', 'https://www.cushmanwakefield.com/en/insights'),
    ('Kastle Systems', 'https://www.kastle.com/safety-wellness/getting-america-back-to-work/'),
    ('Kastle', 'https://www.kastle.com/safety-wellness/getting-america-back-to-work/'),

    # Industry-Specific Sources
    ('STR', 'https://www.hospitalitynet.org/news/4129415.html'),
    ('NCES', 'https://nces.ed.gov/'),
    ('AHA Hospital Statistics', 'https://www.aha.org/statistics/fast-facts-us-hospitals'),
    ('AHA', 'https://www.aha.org/statistics/fast-facts-us-hospitals'),
    ('MGMA', 'https://www.mgma.com/'),
    ('NIC MAP Vision', 'https://www.nic.org/blog/senior-housing-occupancy-continues-climbing-in-first-quarter-2025/'),
    ('IHRSA', 'https://www.ihrsa.org/'),
    ('ICSC', 'https://www.icsc.com/'),
    ('CoStar', 'https://www.costar.com/'),
    ('NADA', 'https://www.nada.org/'),
    ('NAEYC', 'https://www.naeyc.org/'),
    ('FDIC', 'https://www.fdic.gov/'),

    # ENERGY STAR / Portfolio Manager
    ('ENERGY STAR Portfolio Manager', 'https://portfoliomanager.energystar.gov/'),
    ('EPA Portfolio Manager', 'https://portfoliomanager.energystar.gov/'),
    ('Portfolio Manager', 'https://portfoliomanager.energystar.gov/'),
    ('ENERGY STAR', 'https://www.energystar.gov/'),

    # BPS Laws - NYC
    ('NYC Local Law 97', 'https://www.nyc.gov/site/buildings/codes/ll97-greenhouse-gas-emissions-reductions.page'),
    ('Local Law 97 of 2019', 'https://www.nyc.gov/site/buildings/codes/ll97-greenhouse-gas-emissions-reductions.page'),
    ('Local Law 97', 'https://www.nyc.gov/site/buildings/codes/ll97-greenhouse-gas-emissions-reductions.page'),
    ('LL97', 'https://www.nyc.gov/site/buildings/codes/ll97-greenhouse-gas-emissions-reductions.page'),
    ('LL84', 'https://www.nyc.gov/site/buildings/codes/ll84-benchmarking-law.page'),

    # BPS Laws - Boston
    ('BERDO 2.0', 'https://www.boston.gov/departments/environment/building-emissions-reduction-and-disclosure'),
    ('BERDO', 'https://www.boston.gov/departments/environment/building-emissions-reduction-and-disclosure'),

    # BPS Laws - Other Cities
    ('Cambridge BEUDO', 'https://www.cambridgema.gov/CDD/zoninganddevelopment/sustainabledevelopment/buildingenergydisclosureordinance'),
    ('BEUDO', 'https://www.cambridgema.gov/CDD/zoninganddevelopment/sustainabledevelopment/buildingenergydisclosureordinance'),
    ('DC BEPS', 'https://doee.dc.gov/service/building-energy-performance-standards-beps'),
    ('DC DOEE', 'https://doee.dc.gov/'),
    ('Energize Denver', 'https://www.denvergov.org/Government/Agencies-Departments-Offices/Agencies-Departments-Offices-Directory/Climate-Action-Sustainability-and-Resiliency/Cutting-Denvers-Carbon-Pollution/High-Performance-Buildings-and-Homes/Energize-Denver-Hub'),
    ('Seattle BEPS', 'https://www.seattle.gov/environment/climate-change/buildings-and-energy/building-performance-standards'),
    ('St. Louis BEPS', 'https://www.stlouis-mo.gov/government/departments/public-safety/building/'),
    ('California AB 802', 'https://www.energy.ca.gov/programs-and-topics/programs/building-energy-benchmarking-program'),
    ('AB 802', 'https://www.energy.ca.gov/programs-and-topics/programs/building-energy-benchmarking-program'),

    # ASHRAE Standards
    ('ASHRAE 170', 'https://www.ashrae.org/technical-resources/standards-and-guidelines'),
    ('ASHRAE', 'https://www.ashrae.org/'),

    # Other
    ('NREL utility rate database', 'https://openei.org/wiki/Utility_Rate_Database'),
    ('NREL', 'https://www.nrel.gov/'),
    ('Con Edison', 'https://www.coned.com/'),
]

def inject_source_links(text):
    """Replace source references with hyperlinks. Uses list to preserve order."""
    # Track which positions have been linked to avoid nested links
    linked_ranges = []

    for source_text, url in SOURCE_TEXT_TO_URL:
        start = text.find(source_text)
        if start == -1:
            continue

        # Check if this position overlaps with an already-linked range
        end = start + len(source_text)
        overlaps = False
        for linked_start, linked_end in linked_ranges:
            if start < linked_end and end > linked_start:
                overlaps = True
                break

        if overlaps:
            continue

        # Create the link
        link = f'<a href="{url}" target="_blank" rel="noopener">{source_text}</a>'
        text = text[:start] + link + text[end:]

        # Update linked ranges - the link is longer than the original text
        len_diff = len(link) - len(source_text)
        linked_ranges = [(s + len_diff if s > start else s, e + len_diff if e > start else e)
                        for s, e in linked_ranges]
        linked_ranges.append((start, start + len(link)))

    return text

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

def get_odcv_savings_tooltip(row):
    """Dynamic ODCV opportunity explanation by building type."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    city = safe_val(row, 'loc_city', '')

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        return f"""How much HVAC energy you could save by matching ventilation to actual occupancy.<br><br>
We combine vacancy (empty floors) with utilization (how full the occupied floors are). A building with 25% vacancy and 55% utilization on leased floors has about 59% opportunity. Newer and larger buildings score higher because they typically have better controls.<br><br>
<b>Data:</b> {city} vacancy from CBRE/Cushman, office attendance from Kastle badge swipes, plus year built, sqft, Energy Star score, and climate zone."""

    elif bldg_type == 'K-12 School':
        return f"""How much HVAC energy you could save by aligning ventilation with the school calendar.<br><br>
Schools are empty more than half the year—summers, weekends, afternoons, holidays—but HVAC often runs on fixed timers regardless. Calendars are predictable and public, so savings are straightforward to calculate.<br><br>
<b>Data:</b> Schedule patterns from NCES, year built, sqft, efficiency, climate."""

    elif bldg_type == 'Higher Ed':
        return f"""How much HVAC energy you could save by matching ventilation to academic schedules.<br><br>
Universities have the same calendar gaps as K-12 (summer, winter, spring breaks) plus daily variability—a lecture hall might be packed three days a week and empty the rest. Schedules are well-documented, making savings predictable.<br><br>
<b>Data:</b> Academic calendar and classroom utilization from NCES, year built, size."""

    elif bldg_type == 'Hotel':
        return f"""How much HVAC energy you could save by matching room conditioning to when guests are actually present.<br><br>
Two waste sources: unsold rooms (about 37% unoccupied on any given night) and sold rooms when guests are out. Even sold rooms are only occupied about 10 hours a day.<br><br>
<b>Data:</b> {city} room-night occupancy from STR Global, guest-in-room hours, year built, sqft."""

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital'):
        return f"""How much HVAC energy you could save in <b>non-clinical areas only</b>. Patient care areas maintain required airflow per ASHRAE 170—we don't touch those.<br><br>
Hospitals are mostly non-clinical space: lobbies, offices, cafeterias, conference rooms. Those areas can use standard occupancy control. We're conservative here because care comes first.<br><br>
<b>Data:</b> Census patterns, clinical vs non-clinical sqft breakdown from AHA Hospital Statistics, year built, efficiency."""

    elif bldg_type == 'Residential Care':
        return f"""How much HVAC energy you could save in common areas while keeping resident rooms unchanged.<br><br>
Resident rooms have specific ventilation requirements, but common areas and admin spaces can use standard occupancy control. We're conservative here—care standards come first.<br><br>
<b>Data:</b> Occupancy rates from NIC MAP Vision ({city} area), resident vs common area breakdown, year built, size."""

    elif bldg_type in ('Retail', 'Retail Store'):
        return f"""How much HVAC energy you could save by matching ventilation to foot traffic instead of running at peak capacity all day.<br><br>
Traffic swings wildly—packed on weekends, nearly empty on weekday mornings—but HVAC runs the same regardless. Retail traffic patterns are well-studied and predictable.<br><br>
<b>Data:</b> Traffic patterns by day/time from retail studies (Placer.ai, etc), year built, size."""

    elif bldg_type == 'Supermarket':
        return f"""How much sales floor HVAC energy you could save by matching conditioning to traffic. Refrigeration is excluded—it runs continuously regardless of traffic.<br><br>
We isolate space conditioning from refrigeration. The sales floor HVAC can respond to traffic patterns just like any retail store.<br><br>
<b>Data:</b> Traffic patterns, HVAC/refrigeration split from CBECS 2018, year built, size."""

    elif bldg_type == 'Wholesale Club':
        return f"""How much HVAC energy you could save by matching conditioning to member traffic.<br><br>
Wholesale clubs have predictable patterns—heavy on weekends, quiet on weekdays—but HVAC runs at peak regardless. High ceilings mean large HVAC loads, so matching to traffic captures significant waste.<br><br>
<b>Data:</b> Traffic by day/time from retail studies, year built, size."""

    elif bldg_type in ('Venue', 'Theater'):
        return f"""How much HVAC energy you could save by matching conditioning to event schedules instead of running 24/7.<br><br>
Venues sit empty most of the time but often condition around the clock. Event schedules are predictable and published.<br><br>
<b>Data:</b> Event scheduling, operating vs event hours, year built, size."""

    elif bldg_type == 'Restaurant/Bar':
        return f"""How much <b>dining area</b> HVAC energy you could save. Kitchen excluded—it doesn't vary with traffic.<br><br>
Only about 18% of restaurant gas goes to space heating (rest is cooking). Savings come from matching dining area ventilation to meal-time traffic.<br><br>
<b>Data:</b> Meal-time traffic patterns from CBECS 2018, year built, size."""

    elif bldg_type in ('Library/Museum', 'Library', 'Museum'):
        return f"""How much HVAC energy you could save by aligning conditioning with operating hours and visitor traffic.<br><br>
Clear open/closed hours, but HVAC often runs beyond them. Additional savings from slow periods when open.<br><br>
<b>Data:</b> Operating hours, visitor traffic patterns, year built, size."""

    elif bldg_type == 'Outpatient Clinic':
        return f"""How much HVAC energy you could save by matching ventilation to appointment schedules and clinic hours.<br><br>
Unlike hospitals, clinics have clear business hours and no 24/7 care requirements. Appointment schedules are predictable.<br><br>
<b>Data:</b> Appointment patterns from MGMA, clinic hours, year built, size."""

    else:
        return f"""How much HVAC energy you could save by matching ventilation to actual occupancy.<br><br>
For multi-tenant buildings we factor vacancy; for single-tenant we use operating schedules. Either way, HVAC typically runs at design capacity regardless of who's actually there.<br><br>
<b>Data:</b> Occupancy patterns for this building type, year built, size."""


def get_property_value_tooltip(row):
    """Property value tooltip - explains method, data source, justification by building type."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    city = safe_val(row, 'loc_city', '')

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        return f"""Commercial real estate is valued on income, so every dollar you save on operating costs increases the building's value by a multiple. We divide your annual savings by the cap rate for {city} offices (from CBRE's quarterly survey) to get the valuation impact. A 6% cap rate means $1 saved = ~$17 in property value."""

    elif bldg_type == 'Hotel':
        return f"""Hotels are valued on income just like offices, but with higher cap rates (meaning a lower multiplier per dollar saved). We only count HVAC savings here—hot water and kitchen energy don't respond to occupancy. Cap rates from CBRE's {city} hotel survey."""

    elif bldg_type in ('K-12 School', 'Higher Ed'):
        return f"""Schools and universities are funded institutions, but they still get valued based on operating costs. When you reduce energy bills, that money either goes back into the budget or increases the institution's financial position. We use institutional cap rates from CBRE to estimate the value impact."""

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital'):
        return f"""Hospitals are valued like commercial property—lower operating costs mean higher value. We only count savings from non-clinical areas (lobbies, offices, cafeterias) since patient areas have strict ventilation requirements. Cap rates from CBRE's healthcare survey."""

    elif bldg_type == 'Residential Care':
        return f"""Senior housing facilities are valued on their operating income, so reducing energy costs increases property value. We only count savings from common areas and admin spaces—resident rooms have to maintain certain conditions. Cap rates from CBRE's {city} senior housing data."""

    elif bldg_type in ('Retail', 'Retail Store'):
        return f"""Retail properties are valued on income. When you cut operating costs, that flows through to property value. Who captures the savings depends on the lease structure (net vs gross), but the value impact is real either way. Cap rates from CBRE's {city} retail survey."""

    elif bldg_type == 'Supermarket':
        return f"""Grocery stores are valued like other retail—lower costs mean higher value. We only count HVAC savings since refrigeration runs continuously no matter what. Cap rates from CBRE's grocery-anchored retail data for {city}."""

    elif bldg_type == 'Wholesale Club':
        return f"""Big-box retail is valued on operating income. These buildings have huge HVAC loads because of the high ceilings, so matching ventilation to traffic patterns (busy weekends, quiet weekdays) creates real savings that flow to property value. Cap rates from CBRE."""

    elif bldg_type == 'Restaurant/Bar':
        return f"""Restaurants are valued on income like other commercial property, but the savings opportunity is smaller because kitchen ventilation runs constantly. Only the dining area can respond to traffic, and that's typically a small portion of total energy use."""

    elif bldg_type in ('Venue', 'Theater'):
        return f"""Venues and theaters are often conditioned around the clock even though they're only used for events. Matching HVAC to the event schedule reduces costs, which increases property value. Cap rates from CBRE's entertainment/special purpose data."""

    elif bldg_type in ('Library/Museum', 'Library', 'Museum'):
        return f"""Public buildings like libraries and museums have clear operating hours, but HVAC often runs beyond them. Aligning conditioning to actual hours reduces costs. For public institutions, savings go back into the operating budget."""

    elif bldg_type == 'Outpatient Clinic':
        return f"""Medical offices work like regular offices—clear business hours, predictable schedules. Unlike hospitals, there's no 24/7 care requirement, so you can match ventilation to when people are actually there. Cap rates from CBRE's {city} medical office data."""

    else:
        return f"""Commercial property is valued on operating income. When you reduce energy costs, that savings gets multiplied into property value through the cap rate. We use CBRE's {city} cap rate data to estimate the impact."""

def get_energy_star_tooltip(row):
    """Energy Star tooltip - explains method, data source, justification by building type."""
    bldg_type = safe_val(row, 'bldg_type', '')
    city = safe_val(row, 'loc_city', '')

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        return f"""This is where your building ranks compared to similar offices nationwide—50 is average, 75+ qualifies for EPA certification. You're only compared to buildings of the same type in similar climates, so it's a fair comparison. When you reduce HVAC waste, your score improves relative to buildings still conditioning empty space."""

    elif bldg_type == 'Hotel':
        return f"""Hotels have their own Energy Star category, so you're compared to other hotels, not offices. A score of 50 is average, 75+ qualifies for certification. In DC, the building performance law uses Energy Star targets, so this score directly affects compliance."""

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital'):
        return f"""You're scored against other hospitals, which all have high energy use due to ventilation requirements. Since the peer group is tightly clustered, even modest efficiency improvements can move you up several percentiles. 50 is average, 75+ qualifies for certification."""

    elif bldg_type in ('K-12 School', 'Higher Ed'):
        return f"""You're compared to other schools, not commercial buildings. Schools that align their HVAC to the academic calendar score higher than those running on legacy timers all year. 50 is average among your peers, 75+ qualifies for EPA certification."""

    elif bldg_type in ('Retail', 'Retail Store'):
        return f"""You're compared to other retail buildings nationwide. Stores that match ventilation to traffic patterns score higher than those running at peak capacity all day. 50 is average, 75+ qualifies for EPA certification."""

    elif bldg_type == 'Supermarket':
        return f"""You're only compared to other supermarkets, which all have high energy use from refrigeration. Your score reflects how efficient you are in the controllable areas (HVAC, lighting) relative to other grocery stores. 50 is average, 75+ qualifies for certification."""

    elif bldg_type in ('Residential Care',):
        return f"""You're compared to other senior care facilities. Buildings that optimize common areas while maintaining care standards in resident rooms score higher than those running everything at full blast. 50 is average, 75+ qualifies for certification."""

    else:
        return f"""This ranks your building against similar buildings nationwide—50 is average, 75+ qualifies for EPA certification. EPA normalizes for weather, hours, and building type so comparisons are fair."""

def get_electricity_kwh_tooltip(row):
    """ROW tooltip for electricity consumption."""
    bldg_type = safe_val(row, 'bldg_type', '')
    city = safe_val(row, 'loc_city', '')

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        return f"""Most of an office building's electricity goes to HVAC—fans moving air, chillers cooling it, pumps circulating water. The system runs at design capacity even when floors are empty. When you reduce airflow to match actual occupancy, fan energy drops dramatically (cut airflow in half, fan energy drops by 75%). Data from {city} benchmarking plus CBRE vacancy and Kastle attendance data."""

    elif bldg_type in ('K-12 School', 'Higher Ed'):
        return f"""School HVAC typically runs on fixed schedules set years ago, regardless of the actual calendar. The fans and cooling run all summer, every weekend, every afternoon after dismissal. Aligning the schedule to when people are actually there saves significant electricity. Data from {city} benchmarking and NCES school schedules."""

    elif bldg_type == 'Hotel':
        return f"""Hotels condition every room around the clock, but about 37% of rooms are unsold on any given night, and even sold rooms are only occupied about 10 hours a day. That's a lot of electricity cooling empty rooms. Room sensors or key card systems can set back the HVAC when guests aren't there. Data from {city} benchmarking and STR Global occupancy."""

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital'):
        return f"""Hospitals use a lot of electricity for HVAC because patient areas have strict ventilation requirements. We can't touch those—but hospitals are mostly non-clinical space: lobbies, offices, cafeterias, conference rooms. Those areas can use normal occupancy-based control. Data from {city} benchmarking, savings limited to non-clinical areas per ASHRAE 170."""

    elif bldg_type == 'Residential Care':
        return f"""Senior care facilities have HVAC in both resident rooms and common areas. Resident rooms need to maintain certain conditions, but common areas and admin spaces can use standard occupancy control. Data from {city} benchmarking and NIC MAP Vision occupancy rates."""

    elif bldg_type in ('Retail', 'Retail Store'):
        return f"""Retail HVAC typically runs at full capacity from open to close, even though traffic swings wildly—packed on weekends, nearly empty on weekday mornings. Matching ventilation to actual traffic (using CO2 sensors as a proxy) saves significant electricity. Data from {city} benchmarking."""

    elif bldg_type == 'Supermarket':
        return f"""Supermarket electricity is split between refrigeration (which runs continuously no matter what) and sales floor HVAC (which can respond to traffic). We only count savings on the HVAC portion since refrigeration doesn't change with occupancy. Data from {city} benchmarking with HVAC/refrigeration split from CBECS."""

    elif bldg_type in ('Venue', 'Theater'):
        return f"""Venues often condition around the clock even though they're only used for events. That's a lot of electricity running fans and chillers for empty spaces. Matching HVAC to the actual event schedule saves significant electricity. Data from {city} benchmarking."""

    elif bldg_type == 'Restaurant/Bar':
        return f"""Restaurant electricity for HVAC is mostly in the dining area—kitchen ventilation runs constantly regardless of traffic. Savings come from matching dining area conditioning to meal-time patterns. Data from {city} benchmarking."""

    else:
        return f"""Most commercial buildings run HVAC at design capacity regardless of who's actually there. Matching ventilation to actual occupancy saves electricity by reducing fan and cooling loads. Data from {city} benchmarking."""

def get_natural_gas_tooltip(row):
    """ROW tooltip for natural gas consumption."""
    bldg_type = safe_val(row, 'bldg_type', '')
    city = safe_val(row, 'loc_city', '')

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        return f"""In offices, about 88% of gas goes to heating. Every cubic foot of outdoor air the ventilation system pulls in has to be heated in winter. When you're conditioning empty floors and half-empty occupied floors, that's a lot of gas heating air nobody needs. Data from {city} benchmarking, vacancy from CBRE, attendance from Kastle."""

    elif bldg_type in ('K-12 School', 'Higher Ed'):
        return f"""School boilers often run through winter break, spring break, even summer in some cases—heating empty buildings. About 80% of school gas goes to HVAC, so aligning the heating schedule to when students are actually there saves significant gas. Data from {city} benchmarking and NCES school schedules."""

    elif bldg_type == 'Hotel':
        return f"""Hotel gas splits three ways: about 20% to space heating, 42% to hot water, and 33% to kitchens. Only the space heating portion responds to room occupancy—you can't reduce hot water or cooking based on how many guests are in the building. So gas savings are limited to that 20%. Data from {city} benchmarking and STR Global occupancy."""

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital'):
        return f"""Hospital patient areas have to maintain temperature regardless of census—that's a code requirement (ASHRAE 170). But hospitals are mostly non-clinical space: lobbies, offices, cafeterias, conference rooms. Gas savings come from those areas only. Data from {city} benchmarking."""

    elif bldg_type == 'Residential Care':
        return f"""Senior care facilities heat both resident rooms and common areas. Resident rooms need to maintain certain temperatures, but common areas and admin spaces can reduce heating when unoccupied. Data from {city} benchmarking and NIC MAP Vision occupancy."""

    elif bldg_type == 'Restaurant/Bar':
        return f"""Only about 18% of restaurant gas goes to space heating—the rest is cooking. Kitchen gas usage doesn't change with traffic, so savings are limited to heating the dining area during slow periods. Data from {city} benchmarking."""

    elif bldg_type in ('Retail', 'Retail Store'):
        return f"""About 78% of retail gas goes to HVAC. The heating runs the same whether it's a packed Saturday or an empty Tuesday morning. Matching heating to actual traffic patterns saves gas. Data from {city} benchmarking."""

    elif bldg_type == 'Supermarket':
        return f"""Supermarket gas heating is separate from refrigeration. The refrigeration system runs continuously, but the sales floor heating can respond to traffic just like any retail store. Data from {city} benchmarking."""

    else:
        return f"""Gas mostly goes to heating the building and the outdoor air that ventilation pulls in. When you're heating air for empty spaces, that's wasted gas. Matching ventilation to occupancy reduces how much air needs heating. Data from {city} benchmarking."""

def get_fuel_oil_tooltip(row):
    """ROW tooltip for fuel oil consumption."""
    bldg_type = safe_val(row, 'bldg_type', '')
    city = safe_val(row, 'loc_city', '')

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        return f"""Some older buildings use fuel oil for heating instead of gas. Nearly 100% of fuel oil goes to space heating, so when you're heating empty floors, that's all waste. Fuel oil also produces more carbon per unit of heat than gas, so reducing it has an outsized impact on emissions and BPS compliance. Data from {city} benchmarking."""

    elif bldg_type in ('K-12 School', 'Higher Ed'):
        return f"""Schools with oil heat often run the boilers year-round, even through summer. Aligning heating to the school calendar—cutting back during summers, weekends, afternoons, holidays—saves significant fuel oil. Data from {city} benchmarking and NCES schedules."""

    else:
        return f"""Fuel oil goes almost entirely to heating. When you're heating empty spaces, that's wasted oil. Fuel oil also produces more carbon per unit of heat than natural gas, so reducing it has a bigger emissions impact. Data from {city} benchmarking."""

def get_district_steam_tooltip(row):
    """ROW tooltip for district steam consumption."""
    city = safe_val(row, 'loc_city', '')
    bldg_type = safe_val(row, 'bldg_type', '')

    if 'New York' in city or city == 'NYC':
        return f"""Con Edison pipes steam directly to Manhattan buildings—no on-site boilers needed. Steam goes almost entirely to heating, so when you're heating empty floors, that's wasted steam. Under Local Law 97, steam has its own emission factor, so reducing steam directly cuts your carbon penalties. Data from NYC LL84 benchmarking."""

    else:
        return f"""District steam from a central plant heats the building—no on-site boilers. Steam goes almost entirely to heating, so reducing ventilation to empty spaces means less steam needed. Data from {city} benchmarking."""

def get_site_eui_tooltip(row):
    """EUI tooltip - explains method, data source, justification by building type."""
    city = safe_val(row, 'loc_city', '')
    bldg_type = safe_val(row, 'bldg_type', '')

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        return f"""EUI (Energy Use Intensity) is your total energy consumption divided by square footage—it's how much energy your building uses per square foot per year. When you stop conditioning empty floors, your EUI drops. This affects your Energy Star score, tenant perception, and in cities like Denver and St. Louis, it's what determines BPS compliance. Data from {city} benchmarking."""

    elif bldg_type in ('K-12 School', 'Higher Ed'):
        return f"""EUI measures energy per square foot per year. Schools often have surprisingly high EUI despite being occupied limited hours, because the HVAC runs on fixed timers regardless of the calendar. Aligning to when students are actually there can dramatically improve this number. Data from {city} benchmarking."""

    elif bldg_type == 'Hotel':
        return f"""EUI measures energy per square foot per year. Hotels have an unusual pattern—common areas run 24/7 while room loads vary with occupancy. Room-level controls that respond to guest presence can improve this metric. Data from {city} benchmarking."""

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital'):
        return f"""EUI measures energy per square foot per year. Hospitals inherently have high EUI because of ventilation code requirements for patient areas. Improvements come from non-clinical areas only. Don't compare your hospital to office buildings—compare to other hospitals. Data from {city} benchmarking."""

    elif bldg_type == 'Supermarket':
        return f"""EUI measures energy per square foot per year. Supermarkets have high EUI because of refrigeration, which you can't reduce. HVAC savings help but compare yourself to other supermarkets, not other retail. Data from {city} benchmarking."""

    elif bldg_type == 'Restaurant/Bar':
        return f"""EUI measures energy per square foot per year. Restaurants have high EUI because of cooking and kitchen ventilation. The controllable HVAC portion is small, so compare yourself to other restaurants, not other building types. Data from {city} benchmarking."""

    elif bldg_type in ('Retail', 'Retail Store', 'Wholesale Club'):
        return f"""EUI measures energy per square foot per year. When you match HVAC to traffic instead of running at peak capacity all day, your EUI drops. Lower EUI signals efficiency to investors and regulators. Data from {city} benchmarking."""

    else:
        return f"""EUI (Energy Use Intensity) is your total energy divided by square footage—how much energy per square foot per year. When you stop conditioning empty spaces, your EUI drops. Lower EUI signals efficiency to tenants, investors, and regulators. Data from {city} benchmarking."""

def get_hvac_pct_tooltip(row):
    """HVAC percentage tooltip - explains method, data source, justification."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')

    if bldg_type == 'Hotel':
        return """In hotels, electricity mostly goes to HVAC, but gas splits differently: about 20% space heating, 42% hot water, 33% cooking. We only count the HVAC portion. From CBECS, which measured energy use in thousands of real hotels."""

    elif bldg_type == 'Restaurant/Bar':
        return """In restaurants, only about 18% of gas goes to space heating—the other 72% is cooking. We only count the dining area HVAC. From CBECS, which measured energy use in thousands of real restaurants."""

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital'):
        return """Hospitals use a lot of energy for ventilation, but patient areas have minimum air change requirements for infection control. We only count HVAC in non-clinical spaces. From CBECS."""

    elif bldg_type == 'Supermarket':
        return """A big chunk of supermarket electricity goes to refrigeration, which runs 24/7. We carve that out and only count the space conditioning. From CBECS."""

    elif bldg_type in ('K-12 School', 'Higher Ed'):
        return """About 80% of school gas goes to space heating (unlike hotels that use gas for hot water and cooking too). From CBECS, which measured energy use in thousands of real schools."""

    elif bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        return """About 88% of office gas goes to space heating. On the electric side, fans, chillers, and pumps are a big share. The rest is lighting and computers. From CBECS, which measured energy use in thousands of real office buildings."""

    else:
        return """The percentage going to HVAC vs other uses (lighting, equipment) varies by building type. From CBECS, which measured energy end-use breakdowns for each building type."""

def get_size_tooltip(row):
    """Size tooltip - explains method, data source, justification."""
    return """Square footage from city benchmarking disclosure.<br><br>
Larger buildings tend to have more sophisticated control systems, making occupancy-based ventilation easier to implement. They also have more zones to optimize—more opportunity. Most building performance laws kick in at 20,000-50,000+ square feet."""

def get_year_built_tooltip(row):
    """Year built tooltip - explains method, data source, justification."""
    return """Building age tells us about control system sophistication.<br><br>
Pre-1970 buildings usually have pneumatic controls—harder to make occupancy-based. 1970s-80s buildings have early electronic systems with limited flexibility. 1990s-2000s buildings typically have digital controls. 2010+ buildings usually have modern BMS systems that can handle smart ventilation easily. Older buildings can still benefit but might need control upgrades first."""

def get_utility_tooltip(row):
    """Utility tooltip - explains how we convert energy usage into energy costs."""
    utility = safe_val(row, 'cost_utility_name', '')
    city = safe_val(row, 'loc_city', '')

    utility_text = f"from {utility}" if utility else ""

    return f"""We convert consumption to annual costs using ZIP-specific rates from NREL's Utility Rate Database.<br><br>
For electricity, we multiply kWh by the rate, then add about 10% for distribution, taxes, and surcharges. Demand charges are based on peak kW times 12 months, with a 26% markup for ratchet clauses and seasonal variations. Gas and fuel oil get a 10% markup. Steam rates are all-inclusive.<br><br>
We use ZIP-specific rates because electricity prices vary 5x across the country ($0.11-$0.52/kWh) and gas varies 10x ($0.23-$2.42/therm). National averages would be off by 3-4x. Consumption data {utility_text} from {city} benchmarking."""

def get_total_ghg_tooltip(row):
    """Total GHG tooltip - explains method, data source, justification by grid type."""
    city = safe_val(row, 'loc_city', '')

    # Clean grid cities
    if city in ('Seattle', 'Portland', 'San Francisco', 'Los Angeles', 'San Diego'):
        return f"""Total greenhouse gas emissions in metric tons CO2e per year. We multiply electricity by the regional grid factor and gas by its combustion factor, using {city} benchmarking data.<br><br>
{city}'s grid is mostly hydro and renewables, so electricity is pretty clean here. Most of this building's emissions come from burning gas, not electricity. Cutting gas use has the biggest carbon impact in this region. Grid factors from EPA eGRID 2023."""

    # Dirty grid cities
    elif city in ('Chicago', 'St. Louis', 'Denver'):
        return f"""Total greenhouse gas emissions in metric tons CO2e per year. We multiply electricity by the regional grid factor and gas by its combustion factor, using {city} benchmarking data.<br><br>
{city}'s grid has more coal and gas generation, so electricity is carbon-intensive here. Every kWh saved prevents more emissions than in cleaner regions. Both electricity and gas reductions matter. Grid factors from EPA eGRID 2023."""

    # NYC with steam
    elif city in ('New York', 'NYC', 'Manhattan'):
        return f"""Total greenhouse gas emissions in metric tons CO2e per year. We multiply electricity by the grid factor, gas by its combustion factor, and Con Edison steam by its own factor, using NYC benchmarking data.<br><br>
NYC uses legally binding emission factors set by Local Law 97—these are the exact same coefficients the city uses to calculate compliance. Steam has its own coefficient for the district system. This is what your building's emissions look like to regulators."""

    # Boston area
    elif city in ('Boston', 'Cambridge'):
        return f"""Total greenhouse gas emissions in metric tons CO2e per year. We multiply electricity by the regional grid factor and gas by its combustion factor, using {city} benchmarking data.<br><br>
New England's grid is cleaner than the national average (nuclear and renewables), but both electricity and gas reductions contribute to lowering emissions. This number determines whether you meet the BPS carbon cap. Grid factors from EPA eGRID 2023."""

    else:
        return f"""Total greenhouse gas emissions in metric tons CO2e per year. We multiply electricity by the regional grid factor and gas by its combustion factor, using {city} benchmarking data.<br><br>
Grid carbon intensity varies a lot by region—we use specific factors for {city}'s location, not national averages. Grid factors from EPA eGRID 2023, combustion factors from EIA."""

def get_carbon_reduction_tooltip(row):
    """Carbon reduction tooltip - explains method, data source, justification by grid type."""
    city = safe_val(row, 'loc_city', '')

    # Clean grid cities
    if city in ('Seattle', 'Portland', 'San Francisco', 'Los Angeles', 'San Diego'):
        return f"""CO2 you'd avoid by reducing HVAC waste. {city}'s grid is mostly hydro/renewables, so most of your emissions come from burning gas, not electricity. Cutting gas has the biggest carbon impact here. Grid factors from EPA eGRID 2023."""

    # Dirty grid cities
    elif city in ('Chicago', 'St. Louis', 'Denver'):
        return f"""CO2 you'd avoid by reducing HVAC waste. {city}'s grid has more coal/gas generation, so electricity is carbon-heavy here. Every kWh saved prevents more emissions than in cleaner cities. Grid factors from EPA eGRID 2023."""

    # NYC with steam
    elif city in ('New York', 'NYC', 'Manhattan'):
        return """CO2 you'd avoid by reducing HVAC waste. Uses NYC's official LL97 emission factors—the same coefficients the city uses for compliance. This is the carbon reduction NYC will recognize."""

    # Boston area
    elif city in ('Boston', 'Cambridge'):
        return f"""CO2 you'd avoid by reducing HVAC waste. New England's grid is cleaner than average, but both electricity and gas reductions matter. This determines whether you meet the BPS carbon cap. Grid factors from EPA eGRID 2023."""

    else:
        return f"""CO2 you'd avoid by reducing HVAC waste. We use {city}'s regional grid intensity, not national averages—carbon per kWh varies a lot by region. Grid factors from EPA eGRID 2023."""

def get_fine_avoidance_tooltip(row):
    """Fine avoidance tooltip - explains method, data source, justification by city/law."""
    city = safe_val(row, 'loc_city', '')
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')

    # NYC Local Law 97
    if city in ('New York', 'NYC', 'Manhattan'):
        return """Fines you'd avoid by getting under Local Law 97's carbon cap. We use NYC's official emission factors—the same coefficients the city uses. Fines are per ton over the cap, and they add up fast."""

    # Boston BERDO
    elif city == 'Boston':
        return """Fines you'd avoid by getting under BERDO 2.0's carbon cap. Caps tighten over time, so buildings that are borderline now will be over the limit later. Fines are per ton over the cap."""

    # Cambridge BEUDO
    elif city == 'Cambridge':
        return """Fines you'd avoid by meeting Cambridge's reduction requirement. Unlike fixed caps, BEUDO requires a percentage reduction from your own baseline—so every building has an obligation based on where it started."""

    # DC BEPS
    elif city in ('Washington', 'Washington DC', 'DC'):
        return """Fines you'd avoid by meeting DC's Energy Star score target. DC uses score targets instead of carbon caps—you need to hit a certain percentile for your building type."""

    # Seattle BEPS
    elif city == 'Seattle':
        return """Fines you'd avoid by getting under Seattle's carbon intensity cap. Seattle's grid is 98% hydro, so most emissions come from gas, not electricity. Cutting gas has the biggest impact here."""

    # Denver Energize Denver
    elif city == 'Denver':
        return """Fines you'd avoid by meeting Denver's EUI target. Energize Denver sets targets that tighten over time through 2032—buildings need to show steady progress."""

    # St. Louis BEPS
    elif city == 'St. Louis':
        return """Fines you'd avoid by meeting St. Louis's EUI target. The target is set at roughly the 35th percentile—you need to be better than about 2/3 of similar local buildings."""

    else:
        return """This building isn't in a city with building performance standards yet, so there are no fines to avoid. BPS cities as of 2025: NYC, Boston, Cambridge, DC, Seattle, Denver, St. Louis."""


def get_utility_cost_savings_tooltip(row):
    """Utility cost savings tooltip - explains method, data source, justification by building type."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    city = safe_val(row, 'loc_city', '')

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        return f"""Annual savings from matching ventilation to actual occupancy. Centralized HVAC conditions vacant and underutilized floors the same as full ones—the savings come from stopping that. Vacancy from CBRE/Cushman, attendance from Kastle badge data, energy from {city} benchmarking, rates from NREL."""

    elif bldg_type == 'K-12 School':
        return f"""Annual savings from matching ventilation to schedules. Schools are empty summers, weekends, afternoons, holidays—but HVAC often runs on legacy timers. Calendar from NCES, energy from {city} benchmarking, rates from NREL."""

    elif bldg_type == 'Higher Ed':
        return f"""Annual savings from matching ventilation to schedules. Lecture halls packed 3 days, empty the rest. Big calendar gaps between semesters. Academic calendar from NCES, energy from {city} benchmarking, rates from NREL."""

    elif bldg_type == 'Hotel':
        return f"""Annual savings from matching ventilation to actual occupancy. Room HVAC runs 24/7 whether the room is sold or not—and even sold rooms are only occupied about 10 hours a day. Occupancy from STR Global, energy from {city} benchmarking, rates from NREL."""

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital'):
        return f"""Annual savings from occupancy control in non-clinical areas. Patient areas need minimum air changes for infection control, but hospitals are mostly lobbies, offices, and cafeterias—those can use occupancy control. Energy from {city} benchmarking, rates from NREL."""

    elif bldg_type == 'Residential Care':
        return f"""Annual savings from occupancy control in common areas. Resident rooms have ventilation requirements, but common areas and admin spaces can respond to occupancy. Occupancy from NIC MAP Vision, energy from {city} benchmarking, rates from NREL."""

    elif bldg_type in ('Retail', 'Retail Store'):
        return f"""Annual savings from matching ventilation to traffic. No vacancy—stores are owner-occupied—but traffic swings wildly: packed weekends, empty weekday mornings. HVAC runs the same regardless. Energy from {city} benchmarking, rates from NREL."""

    elif bldg_type == 'Supermarket':
        return f"""Annual savings from matching ventilation to traffic. Refrigeration runs 24/7 (can't change that), but the sales floor HVAC can respond to customer traffic. Energy from {city} benchmarking, rates from NREL."""

    elif bldg_type == 'Wholesale Club':
        return f"""Annual savings from matching ventilation to traffic. High ceilings mean large HVAC loads, and traffic is predictable—concentrated on weekends. Energy from {city} benchmarking, rates from NREL."""

    elif bldg_type == 'Restaurant/Bar':
        return f"""Annual savings from matching dining area ventilation to traffic. Only about 18% of restaurant gas goes to space heating—the rest is cooking, which doesn't change. Energy from {city} benchmarking, rates from NREL."""

    elif bldg_type in ('Venue', 'Theater'):
        return f"""Annual savings from matching ventilation to event schedules. Venues are designed for intermittent peak use, but HVAC often runs 24/7. Energy from {city} benchmarking, rates from NREL."""

    elif bldg_type in ('Library/Museum', 'Library', 'Museum'):
        return f"""Annual savings from matching ventilation to operating hours. Fixed hours, steady traffic when open—opportunity is when closed but systems still run, plus slow periods. Energy from {city} benchmarking, rates from NREL."""

    elif bldg_type == 'Outpatient Clinic':
        return f"""Annual savings from matching ventilation to appointments. Clear business hours, predictable schedules—unlike hospitals, no 24/7 care or strict ventilation codes. Energy from {city} benchmarking, rates from NREL."""

    else:
        return f"""Annual savings from matching ventilation to actual occupancy patterns. We take the HVAC portion of your energy costs and apply the savings % for this building type. Energy from {city} benchmarking, rates from NREL."""


# Map of dynamic tooltip keys to their generator functions
DYNAMIC_TOOLTIPS = {
    'bldg_type_opportunity': get_odcv_savings_tooltip,
    'utility_cost_savings': get_utility_cost_savings_tooltip,
    'property_value_increase': get_property_value_tooltip,
    'fine_avoidance': get_fine_avoidance_tooltip,
    'energy_star_score': get_energy_star_tooltip,
    'carbon_reduction': get_carbon_reduction_tooltip,
    'energy_elec_kwh': get_electricity_kwh_tooltip,
    'natural_gas': get_natural_gas_tooltip,
    'fuel_oil': get_fuel_oil_tooltip,
    'district_steam': get_district_steam_tooltip,
    'energy_site_eui': get_site_eui_tooltip,
    'pct_hvac_elec': get_hvac_pct_tooltip,
    'total_ghg': get_total_ghg_tooltip,
    'size': get_size_tooltip,
    'year_built': get_year_built_tooltip,
    'utility': get_utility_tooltip,
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

def get_org_url(org_name):
    """Get the website URL for an organization."""
    if not org_name or pd.isna(org_name):
        return None
    org_key = str(org_name).strip().lower()
    return ORG_URLS.get(org_key)

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
    """Format dollar amounts - guaranteed safe output"""
    if value is None:
        return "—"
    try:
        val = float(value)
        if math.isnan(val) or math.isinf(val):
            return "—"
        if val == 0:
            return "$0"
        # Handle negative values
        if val < 0:
            abs_val = abs(val)
            if abs_val >= 1e9:
                return f"-${abs_val/1e9:.2f}B"
            elif abs_val >= 1e6:
                return f"-${abs_val/1e6:.1f}M"
            elif abs_val >= 1e3:
                return f"-${abs_val/1e3:.0f}K"
            else:
                return f"-${abs_val:,.0f}"
        # Positive values
        if val >= 1e9:
            return f"${val/1e9:.2f}B"
        elif val >= 1e6:
            return f"${val/1e6:.1f}M"
        elif val >= 1e3:
            return f"${val/1e3:.0f}K"
        else:
            return f"${val:,.0f}"
    except (ValueError, TypeError):
        return "—"

def format_number(value, decimals=0):
    """Format numbers with commas - guaranteed safe output"""
    if value is None:
        return "—"
    try:
        num = float(value)
        if math.isnan(num) or math.isinf(num):
            return "—"
        if decimals > 0:
            return f"{num:,.{decimals}f}"
        return f"{int(num):,}"
    except (ValueError, TypeError):
        return "—"

def safe_percentage(numerator, denominator, default=0):
    """Calculate percentage safely - no division by zero, bounded output."""
    if numerator is None or denominator is None:
        return default
    try:
        num = float(numerator)
        denom = float(denominator)
        if denom == 0 or math.isnan(denom) or math.isinf(denom):
            return default
        pct = (num / denom) * 100
        # Clamp to reasonable bounds
        return max(0, min(pct, 999))
    except (ValueError, TypeError):
        return default

def clamp_energy_star(score):
    """Clamp Energy Star score to valid 0-100 range."""
    if score is None:
        return None
    try:
        s = float(score)
        if math.isnan(s) or math.isinf(s):
            return None
        return max(0, min(100, s))
    except (ValueError, TypeError):
        return None

def escape(text):
    """Escape HTML"""
    if pd.isna(text) or text == '':
        return ''
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

def is_valid_building(row):
    """Check if building data looks valid for report generation.
    Skips test/garbage data like numeric names or missing addresses.
    """
    # Get key fields
    name = safe_val(row, 'id_property_name') if hasattr(row, '__getitem__') else row.get('id_property_name', '')
    bldg_type = safe_val(row, 'bldg_type') if hasattr(row, '__getitem__') else row.get('bldg_type', '')
    address = safe_val(row, 'loc_address') if hasattr(row, '__getitem__') else row.get('loc_address', '')

    # Names/types shouldn't be pure numbers (indicates test data)
    for val in [name, bldg_type]:
        if val and str(val).strip():
            try:
                float(str(val).strip())
                return False  # Looks like test data
            except (ValueError, TypeError):
                pass  # Good - not a number

    # Must have a real address (at least 5 chars)
    if not address or len(str(address).strip()) < 5:
        return False

    # Address shouldn't be a pure number
    try:
        float(str(address).strip())
        return False  # Address looks like test data
    except (ValueError, TypeError):
        pass  # Good - not a number

    return True

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
    name = name.replace('-', '')      # Remove hyphens (Ritz-Carlton -> RitzCarlton)
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
    """Generate tooltip HTML span. If row is provided and key is dynamic, generates contextual tooltip.
    Wrapped in try/except for robustness - tooltips are optional enhancements.
    """
    try:
        # Check if this is a dynamic tooltip that needs row data
        if key in DYNAMIC_TOOLTIPS and row is not None:
            try:
                text = DYNAMIC_TOOLTIPS[key](row)
            except Exception:
                # Fallback to static tooltip if dynamic fails
                text = TOOLTIPS.get(key, '')
        else:
            text = TOOLTIPS.get(key, '')

        if not text:
            return ''

        # Inject hyperlinks into source references
        try:
            html_text = inject_source_links(text)
        except Exception:
            html_text = escape(text)  # Fallback to escaped plain text

        return f'<span class="info-tooltip" style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background: linear-gradient(135deg, #0066cc 0%, #004494 100%); color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i<span class="tooltip-content">{html_text}</span></span>'
    except Exception:
        return ''  # Fail silently - tooltips are optional enhancements

#===============================================================================
# HTML SECTIONS
#===============================================================================

def format_address(street, city, state, zip_code):
    """Format address with proper commas and no double spaces."""
    # Clean inputs
    street = str(street).strip() if street and str(street).lower() != 'nan' else ''
    city = str(city).strip() if city and str(city).lower() != 'nan' else ''
    state = str(state).strip() if state and str(state).lower() != 'nan' else ''
    zip_code = str(zip_code).strip() if zip_code and str(zip_code).lower() != 'nan' else ''

    # Check if city is already in street address
    if city and city in street:
        address = street
    else:
        # Build address with proper formatting
        parts = []
        if street:
            parts.append(street)
        if city and state:
            parts.append(f"{city}, {state}")
        elif city:
            parts.append(city)
        elif state:
            parts.append(state)
        if zip_code:
            if parts:
                parts[-1] = f"{parts[-1]} {zip_code}"
            else:
                parts.append(zip_code)
        address = ', '.join(parts) if len(parts) > 1 else (parts[0] if parts else 'Address not available')

    # Clean up any double spaces
    while '  ' in address:
        address = address.replace('  ', ' ')

    return address.strip()

def generate_hero(row):
    """Hero section - address with external link, centered with back button"""
    street = safe_val(row, 'loc_address', 'Address not available')
    city = safe_val(row, 'loc_city', '')
    state = safe_val(row, 'loc_state', '')
    zip_code = safe_val(row, 'loc_zip', '')

    # Use the robust address formatter
    address = format_address(street, city, state, zip_code)

    building_url = safe_val(row, 'id_source_url')
    has_url = building_url and str(building_url).lower() != 'nan'

    # Back button - big clickable area, uses JS to check 'from' param and return to correct tab
    back_btn = '''<a href="../index.html" onclick="event.preventDefault(); const from = new URLSearchParams(window.location.search).get('from'); window.location.href = '../index.html' + (from === 'cities' ? '#all-buildings' : '#portfolios');" style="position:absolute;left:10px;top:50%;transform:translateY(-50%);color:white;text-decoration:none;font-size:14px;font-weight:600;display:flex;align-items:center;gap:6px;padding:8px 14px;background:rgba(0,0,0,0.3);border-radius:6px;z-index:10;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
        Back
    </a>'''

    # Corporate Office badge for HQ buildings
    hq_org = safe_val(row, 'bldg_hq_org')
    hq_badge = f'<span class="hq-badge">{escape(str(hq_org))} HQ</span>' if hq_org and str(hq_org).lower() != 'nan' else ''

    html = f"""
    <div class="hero" style="position:relative;text-align:center;padding:20px 80px;">
        {back_btn}
        <h1 style="margin-bottom:0;">{escape(address)}{hq_badge}</h1>
    </div>
"""
    return html

def generate_building_info(row):
    """Property information table (merged from Building Info + Property Metrics)"""
    building_url = safe_val(row, 'id_source_url')
    has_url = building_url and str(building_url).lower() != 'nan'

    if has_url:
        more_info_link = f'''<a href="{escape(building_url)}" target="_blank" style="display:inline-flex;align-items:center;gap:4px;color:#6b7280;text-decoration:none;font-size:13px;font-weight:500;padding:4px 10px;background:#f3f4f6;border-radius:6px;transition:all 0.2s;" onmouseover="this.style.background='#e5e7eb';this.style.color='#374151'" onmouseout="this.style.background='#f3f4f6';this.style.color='#6b7280'">
                <span>More Info</span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17l9.2-9.2M17 17V7H7"/></svg>
            </a>'''
        html = f"""
    <div class="section">
        <h2 style="display:flex;align-items:center;gap:12px;">
            <span>Property</span>
            {more_info_link}
        </h2>
        <table>
"""
    else:
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
        html += f"<tr><td>Size{tooltip('size', row)}</td><td>{format_number(sqft)} sqft</td></tr>\n"

    # Type (with opportunity level tooltip explaining WHY this building type has savings potential)
    bldg_type = safe_val(row, 'bldg_type')
    if bldg_type and str(bldg_type).lower() != 'nan':
        html += f"<tr><td>Type{tooltip('bldg_type_opportunity', row)}</td><td>{escape(bldg_type)}</td></tr>\n"

    # Year Built - only show if it's a reasonable year (1800-2030)
    year = safe_num(row, 'bldg_year_built')
    if year and 1800 <= year <= 2030:
        html += f"<tr><td>Year Built{tooltip('year_built', row)}</td><td>{int(year)}</td></tr>\n"

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

    # Helper to build org - logo only with hover showing display name
    def build_org_with_logo(name):
        if not name:
            return ""
        logo = build_logo_img(name, 60)
        if logo:
            return f'<div style="">{logo}</div>'
        return f'{escape(get_org_display_name(name))}'

    # Helper for logo only (returns img tag, wrapped in link if org has website)
    # Falls back to org name text (hyperlinked if URL exists) when no logo or logo fails to load
    def build_logo_img(name, height=60):
        if not name:
            return ""
        display_name = get_org_display_name(name)
        logo_filename = get_logo_filename(name)
        org_url = get_org_url(name)
        if logo_filename:
            logo_url = f"{AWS_BUCKET}/logos/{logo_filename}.png"
            # onerror: hide wrapper, show fallback text (no hover since text is visible)
            fallback_text = f'<span style="display:none;">{escape(display_name)}</span>'
            if org_url:
                img_tag = f'<img src="{logo_url}" alt="{escape(display_name)}" style="height:{height}px;max-width:150px;object-fit:contain;" onerror="this.parentElement.className=\'\';this.parentElement.removeAttribute(\'data-org-name\');this.style.display=\'none\';this.nextElementSibling.style.display=\'inline\';">'
                return f'<a href="{escape(org_url)}" target="_blank" class="org-logo" data-org-name="{escape(display_name)}">{img_tag}{fallback_text}</a>'
            else:
                img_tag = f'<img src="{logo_url}" alt="{escape(display_name)}" style="height:{height}px;max-width:150px;object-fit:contain;" onerror="this.parentElement.className=\'\';this.parentElement.removeAttribute(\'data-org-name\');this.style.display=\'none\';this.nextElementSibling.style.display=\'inline\';">'
                return f'<span class="org-logo" data-org-name="{escape(display_name)}">{img_tag}{fallback_text}</span>'
        # No logo filename - just text (hyperlinked if URL exists), no hover
        if org_url:
            return f'<a href="{escape(org_url)}" target="_blank">{escape(display_name)}</a>'
        return f'{escape(display_name)}'

    # Build tenant with sub-org - logos centered, text fallback with hyperlinks
    def build_tenant_with_sub(tenant_name, sub_name):
        if not tenant_name:
            return ""

        if sub_name:
            sub_logo = build_logo_img(sub_name, 60)
            tenant_logo = build_logo_img(tenant_name, 60)
            # Both have content (logo or text fallback)
            if sub_logo and tenant_logo and sub_logo != tenant_logo:
                return f"<div style=''>{tenant_logo} &nbsp; {sub_logo}</div>"
            elif sub_logo:
                return f"<div style=''>{sub_logo}</div>"
            elif tenant_logo:
                return f"<div style=''>{tenant_logo}</div>"
            return ""
        else:
            # No sub-org
            tenant_logo = build_logo_img(tenant_name, 60)
            if tenant_logo:
                return f'<div style="">{tenant_logo}</div>'
            return ""

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

    # Utility Company (only show if not empty)
    utility = safe_val(row, 'cost_utility_name')
    if utility and str(utility).lower() not in ['nan', '', 'none']:
        utility_logo_url = UTILITY_LOGOS.get(utility, '')
        utility_rate_url = UTILITY_RATE_URLS.get(utility, '')
        if utility_logo_url:
            # Wrap logo in link to rate page if URL exists
            logo_html = f'<img src="{utility_logo_url}" alt="{escape(utility)}" style="height:40px;max-width:120px;object-fit:contain;vertical-align:middle;" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'inline\';">'
            fallback_html = f'<span style="display:none;">⚡ {escape(utility)}</span>'
            if utility_rate_url:
                logo_html = f'<a href="{utility_rate_url}" target="_blank" rel="noopener" title="View {escape(utility)} commercial rates" style="text-decoration:none;">{logo_html}</a>'
            html += f'<tr><td>Utility{tooltip("utility", row)}</td><td><span class="org-logo" data-org-name="{escape(utility)}">{logo_html}{fallback_html}</span></td></tr>\n'
        else:
            # No logo - show text, link if URL exists
            if utility_rate_url:
                html += f'<tr><td>Utility{tooltip("utility", row)}</td><td><a href="{utility_rate_url}" target="_blank" rel="noopener" title="View {escape(utility)} commercial rates">⚡ {escape(utility)}</a></td></tr>\n'
            else:
                html += f'<tr><td>Utility{tooltip("utility", row)}</td><td>⚡ {escape(utility)}</td></tr>\n'

    # LEED Certification (only show if certified, with logo) - lookup from leed_matches.csv
    row_idx = row.name if hasattr(row, 'name') else None
    leed_info = LEED_DATA.get(row_idx, {}) if row_idx is not None else {}
    leed_level = leed_info.get('level')

    if leed_level and str(leed_level).lower() not in ['nan', '', 'none']:
        # Map certification level to logo filename
        leed_logos = {
            'Platinum': 'leed_platinum.png',
            'Gold': 'leed_gold.png',
            'Silver': 'leed_silver.png',
            'Certified': 'leed_certified.png'
        }
        logo_file = leed_logos.get(leed_level, 'leed_certified.png')
        logo_url = f'https://nationwide-odcv-images.s3.us-east-2.amazonaws.com/logos/{logo_file}'
        leed_url = leed_info.get('url')

        if leed_url and str(leed_url).lower() not in ['nan', '', 'none']:
            html += f'<tr><td>LEED</td><td><a href="{escape(leed_url)}" target="_blank" class="org-logo" data-org-name="LEED {escape(leed_level)}"><img src="{logo_url}" alt="LEED {escape(leed_level)}" style="height:60px;max-width:220px;object-fit:contain;" onerror="this.parentElement.className=\'\';this.parentElement.removeAttribute(\'data-org-name\');this.style.display=\'none\';this.nextElementSibling.style.display=\'inline\';"><span style="display:none;color:#059669;font-weight:600;">{escape(leed_level)}</span></a></td></tr>\n'
        else:
            html += f'<tr><td>LEED</td><td><span class="org-logo" data-org-name="LEED {escape(leed_level)}"><img src="{logo_url}" alt="LEED {escape(leed_level)}" style="height:60px;max-width:220px;object-fit:contain;" onerror="this.parentElement.className=\'\';this.parentElement.removeAttribute(\'data-org-name\');this.style.display=\'none\';this.nextElementSibling.style.display=\'inline\';"><span style="display:none;color:#059669;font-weight:600;">{escape(leed_level)}</span></span></td></tr>\n'

    html += """
        </table>
    </div>
"""
    return html

def generate_energy_use(row):
    """Energy use table - HVAC % info now in fuel row tooltips"""
    html = f"""
    <div class="section">
        <h2>Energy Use</h2>
        <table>
            <tr>
                <th></th>
                <th>Annual Use</th>
                <th>Annual Cost</th>
            </tr>
"""

    # Electricity
    elec_kwh = safe_num(row, 'energy_elec_kwh')
    elec_cost = safe_num(row, 'cost_elec_total_annual')
    if elec_kwh or elec_cost:
        html += f"""
            <tr>
                <td>Electricity{tooltip('energy_elec_kwh', row)}</td>
                <td>{format_number(elec_kwh) + ' kWh' if elec_kwh else ''}</td>
                <td>{format_currency(elec_cost) if elec_cost else '$0'}</td>
            </tr>
"""

    # Natural Gas
    gas_use = safe_num(row, 'energy_gas_kbtu')
    gas_cost = safe_num(row, 'cost_gas_annual')
    fuel_use = safe_num(row, 'energy_fuel_oil_kbtu')
    fuel_cost = safe_num(row, 'cost_fuel_oil_annual')

    if gas_use and gas_use > 0:
        gas_therms = gas_use / 100  # kBtu to therms
        html += f"""
            <tr>
                <td>Natural Gas{tooltip('natural_gas', row)}</td>
                <td>{format_number(gas_therms)} therms</td>
                <td>{format_currency(gas_cost) if gas_cost else '$0'}</td>
            </tr>
"""

    # Fuel Oil
    if fuel_use and fuel_use > 0:
        fuel_gal = fuel_use / 138.5  # kBtu to gallons
        html += f"""
            <tr>
                <td>Fuel Oil{tooltip('fuel_oil', row)}</td>
                <td>{format_number(fuel_gal)} gallons</td>
                <td>{format_currency(fuel_cost) if fuel_cost else '$0'}</td>
            </tr>
"""

    # District Steam
    steam_use = safe_num(row, 'energy_steam_kbtu')
    steam_cost = safe_num(row, 'cost_steam_annual')
    if steam_use and steam_use > 0:
        steam_mlb = steam_use / 1194  # kBtu to Mlb
        html += f"""
            <tr>
                <td>District Steam{tooltip('district_steam', row)}</td>
                <td>{format_number(steam_mlb, 2)} Mlb</td>
                <td>{format_currency(steam_cost) if steam_cost else '$0'}</td>
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

def generate_hvac_breakdown(row):
    """HVAC energy breakdown"""
    html = f"""
    <div class="section">
        <h2>HVAC Breakdown</h2>
        <table>
            <tr>
                <th></th>
                <th>% HVAC{tooltip('pct_hvac_elec', row)}</th>
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
    """Energy section - shows Current vs New energy usage with Change column"""
    # Check if we have any energy data at all
    elec_kwh = safe_num(row, 'energy_elec_kwh')
    gas_use = safe_num(row, 'energy_gas_kbtu')
    steam_use = safe_num(row, 'energy_steam_kbtu')
    fuel_use = safe_num(row, 'energy_fuel_oil_kbtu')

    # Skip entire section if no energy data
    if not any([elec_kwh, gas_use, steam_use, fuel_use]):
        return ""

    # Get post-ODCV values
    elec_kwh_post = safe_num(row, 'energy_elec_kwh_post_odcv')
    gas_post = safe_num(row, 'energy_gas_kbtu_post_odcv')
    steam_post = safe_num(row, 'energy_steam_kbtu_post_odcv')
    fuel_post = safe_num(row, 'energy_fuel_oil_kbtu_post_odcv')

    # Get Site EUI data
    current_eui = safe_num(row, 'energy_site_eui')
    building_id = safe_val(row, 'id_building', '')
    new_eui = EUI_POST_ODCV.get(building_id)

    # Get dynamic column tooltips
    current_tooltip = get_current_column_tooltip(row)
    new_tooltip = get_new_column_tooltip(row)
    change_tooltip = get_change_column_tooltip(row)

    # Column header tooltip styling (same as row tooltips)
    def col_tooltip(text):
        html_text = inject_source_links(text)
        return f'<span class="info-tooltip" style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background: linear-gradient(135deg, #0066cc 0%, #004494 100%); color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i<span class="tooltip-content">{html_text}</span></span>'

    # Helper for change cell with absolute value + % in parens
    def change_cell(abs_val, pct, unit='', is_reduction=True):
        """Create styled change cell: absolute value with arrow, % in parens. Distinct colors for each tier."""
        if is_reduction:
            if pct >= 15: color = '#15803d'  # Dark green - great
            elif pct >= 8: color = '#0891b2'  # Teal/cyan - good
            else: color = '#3b82f6'  # Indigo - ok (still positive but modest)
            arrow = '↓'
        else:
            if pct >= 10: color = '#15803d'  # Dark green - great
            elif pct >= 5: color = '#0891b2'  # Teal/cyan - good
            else: color = '#3b82f6'  # Indigo - ok (still positive but modest)
            arrow = '↑'
        return f'<span style="color:{color};font-weight:700;">{arrow}{abs_val}{unit}</span> <span style="color:#64748b;font-size:0.9em;">({pct:.0f}%)</span>'

    row_num = 0
    def row_bg():
        nonlocal row_num
        row_num += 1
        return 'background:#f9fafb;' if row_num % 2 == 0 else ''

    html = f"""
    <div class="section">
        <h2 style="display:flex;align-items:center;gap:12px;">
            <span>Energy</span>
            <a href="../methodology.html#savings" target="_blank" style="display:inline-flex;align-items:center;gap:4px;color:#6b7280;text-decoration:none;font-size:13px;font-weight:500;padding:4px 10px;background:#f3f4f6;border-radius:6px;transition:all 0.2s;" onmouseover="this.style.background='#e5e7eb';this.style.color='#374151'" onmouseout="this.style.background='#f3f4f6';this.style.color='#6b7280'">
                <span>Methodology</span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17l9.2-9.2M17 17V7H7"/></svg>
            </a>
        </h2>
        <table style="margin-bottom:0;">
            <tr>
                <th style="width:35%;"></th>
                <th style="width:22%;">Current Usage{col_tooltip(current_tooltip)}</th>
                <th style="width:22%;">Usage w/ ODCV{col_tooltip(new_tooltip)}</th>
                <th style="width:21%;">Change{col_tooltip(change_tooltip)}</th>
            </tr>
"""

    # Electricity - only show if value will display as >= 1 kWh
    if elec_kwh and elec_kwh >= 0.5:
        current_val = elec_kwh
        new_val = elec_kwh_post
        current_str = f"{format_number(current_val)} kWh"
        new_str = f"{format_number(new_val)} kWh" if new_val and new_val >= 0.5 else "—"
        # Only show percentage if base value is meaningful
        if new_val and current_val >= 1:
            change = current_val - new_val
            pct = (change / current_val) * 100
            change_str = f'<td>{change_cell(format_number(change), pct, " kWh")}</td>'
        else:
            change_str = '<td>—</td>'
        html += f"""
            <tr style="{row_bg()}">
                <td><strong>Electricity</strong>{tooltip('energy_elec_kwh', row)}</td>
                <td>{current_str}</td>
                <td>{new_str}</td>
                {change_str}
            </tr>
"""

    # Natural Gas - only show if value will display as >= 1 therm
    if gas_use and gas_use > 0:
        gas_therms = gas_use / 100
        # Skip row if value rounds to 0 (avoids "0 therms (38%)" bug)
        if gas_therms >= 0.5:
            gas_therms_post = gas_post / 100 if gas_post else None
            current_str = f"{format_number(gas_therms)} therms"
            new_str = f"{format_number(gas_therms_post)} therms" if gas_therms_post and gas_therms_post >= 0.5 else "—"
            # Only show percentage if base value is meaningful
            if gas_therms_post and gas_therms >= 1:
                change = gas_therms - gas_therms_post
                pct = (change / gas_therms) * 100
                change_str = f'<td>{change_cell(format_number(change), pct, " therms")}</td>'
            else:
                change_str = '<td>—</td>'
            html += f"""
            <tr style="{row_bg()}">
                <td><strong>Natural Gas</strong>{tooltip('natural_gas', row)}</td>
                <td>{current_str}</td>
                <td>{new_str}</td>
                {change_str}
            </tr>
"""

    # Fuel Oil - only show if value will display as >= 1 gallon
    if fuel_use and fuel_use > 0:
        fuel_gal = fuel_use / 138.5
        # Skip row if value rounds to 0 (avoids "0 gallons (X%)" bug)
        if fuel_gal >= 0.5:
            fuel_gal_post = fuel_post / 138.5 if fuel_post else None
            current_str = f"{format_number(fuel_gal)} gallons"
            new_str = f"{format_number(fuel_gal_post)} gallons" if fuel_gal_post and fuel_gal_post >= 0.5 else "—"
            # Only show percentage if base value is meaningful
            if fuel_gal_post and fuel_gal >= 1:
                change = fuel_gal - fuel_gal_post
                pct = (change / fuel_gal) * 100
                change_str = f'<td>{change_cell(format_number(change), pct, " gal")}</td>'
            else:
                change_str = '<td>—</td>'
            html += f"""
            <tr style="{row_bg()}">
                <td><strong>Fuel Oil</strong>{tooltip('fuel_oil', row)}</td>
                <td>{current_str}</td>
                <td>{new_str}</td>
                {change_str}
            </tr>
"""

    # District Steam - only show if value will display as >= 0.01 Mlb
    if steam_use and steam_use > 0:
        steam_mlb = steam_use / 1194
        # Skip row if value rounds to 0.00 (avoids "0.00 Mlb (X%)" bug)
        if steam_mlb >= 0.005:
            steam_mlb_post = steam_post / 1194 if steam_post else None
            current_str = f"{format_number(steam_mlb, 2)} Mlb"
            new_str = f"{format_number(steam_mlb_post, 2)} Mlb" if steam_mlb_post and steam_mlb_post >= 0.005 else "—"
            # Only show percentage if base value is meaningful
            if steam_mlb_post and steam_mlb >= 0.01:
                change = steam_mlb - steam_mlb_post
                pct = (change / steam_mlb) * 100
                change_str = f'<td>{change_cell(format_number(change, 2), pct, " Mlb")}</td>'
            else:
                change_str = '<td>—</td>'
            html += f"""
            <tr style="{row_bg()}">
                <td><strong>District Steam</strong>{tooltip('district_steam', row)}</td>
                <td>{current_str}</td>
                <td>{new_str}</td>
                {change_str}
            </tr>
"""

    # Site EUI row
    if current_eui:
        current_str = f"{format_number(current_eui, 1)} kBtu/sqft"
        new_str = f"{format_number(new_eui, 1)} kBtu/sqft" if new_eui else "—"
        if new_eui:
            change = current_eui - new_eui
            pct = (change / current_eui) * 100
            change_str = f'<td>{change_cell(format_number(change, 1), pct, " kBtu/sqft")}</td>'
        else:
            change_str = '<td>—</td>'
        html += f"""
            <tr style="{row_bg()}">
                <td><strong>Site EUI</strong>{tooltip('energy_site_eui', row)}</td>
                <td>{current_str}</td>
                <td>{new_str}</td>
                {change_str}
            </tr>
"""

    html += """
        </table>
    </div>
"""
    return html

def generate_impact_section(row):
    """Impact section - shows Current vs New values with Change column"""
    # Get all the values we need
    elec_cost = safe_num(row, 'cost_elec_total_annual', 0)
    gas_cost = safe_num(row, 'cost_gas_annual', 0)
    steam_cost = safe_num(row, 'cost_steam_annual', 0)
    fuel_oil_cost = safe_num(row, 'cost_fuel_oil_annual', 0)
    total_energy_cost = elec_cost + gas_cost + steam_cost + fuel_oil_cost

    odcv_savings = safe_num(row, 'odcv_hvac_savings_annual_usd')
    val_impact = safe_num(row, 'val_odcv_impact_usd')
    carbon_current = safe_num(row, 'carbon_emissions_total_mt')
    carbon_post = safe_num(row, 'carbon_emissions_post_odcv_mt')

    # Skip if no savings data
    if not odcv_savings:
        return ""

    # Calculate new values
    new_utility_cost = total_energy_cost - odcv_savings if total_energy_cost else None

    # Helper for change cell with absolute value + % in parens
    def change_cell(abs_val, pct, unit='', is_reduction=True):
        """Create styled change cell: absolute value with arrow, % in parens. Distinct colors for each tier."""
        if is_reduction:
            if pct >= 15: color = '#15803d'  # Dark green - great
            elif pct >= 8: color = '#0891b2'  # Teal/cyan - good
            else: color = '#3b82f6'  # Indigo - ok (still positive but modest)
            arrow = '↓'
        else:
            if pct >= 10: color = '#15803d'  # Dark green - great
            elif pct >= 5: color = '#0891b2'  # Teal/cyan - good
            else: color = '#3b82f6'  # Indigo - ok (still positive but modest)
            arrow = '↑'
        return f'<span style="color:{color};font-weight:700;">{arrow}{abs_val}{unit}</span> <span style="color:#64748b;font-size:0.9em;">({pct:.0f}%)</span>'

    row_num = 0
    def row_bg():
        nonlocal row_num
        row_num += 1
        return 'background:#f9fafb;' if row_num % 2 == 0 else ''

    html = """
    <div class="section">
        <h2 style="display:flex;align-items:center;gap:12px;">
            <span>Impact</span>
            <a href="../methodology.html#benefits" target="_blank" style="display:inline-flex;align-items:center;gap:4px;color:#6b7280;text-decoration:none;font-size:13px;font-weight:500;padding:4px 10px;background:#f3f4f6;border-radius:6px;transition:all 0.2s;" onmouseover="this.style.background='#e5e7eb';this.style.color='#374151'" onmouseout="this.style.background='#f3f4f6';this.style.color='#6b7280'">
                <span>Methodology</span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17l9.2-9.2M17 17V7H7"/></svg>
            </a>
        </h2>
        <table style="margin-bottom:0;">
            <tr>
                <th style="width:35%;"></th>
                <th style="width:22%;">Current Usage</th>
                <th style="width:22%;">Usage w/ ODCV</th>
                <th style="width:21%;">Change</th>
            </tr>
"""

    # Utility Cost row
    if total_energy_cost and odcv_savings:
        pct = (odcv_savings / total_energy_cost) * 100
        html += f"""
            <tr style="{row_bg()}">
                <td><strong>Utility Cost</strong>{tooltip('utility_cost_savings', row)}</td>
                <td>{format_currency(total_energy_cost)}/yr</td>
                <td>{format_currency(new_utility_cost)}/yr</td>
                <td>{change_cell(format_currency(odcv_savings), pct, "/yr")}</td>
            </tr>
"""

    # Fine Avoidance row
    fine_baseline = safe_num(row, 'bps_fine_baseline_yr1_usd')
    fine_post_odcv = safe_num(row, 'bps_fine_post_odcv_yr1_usd')
    fine_avoided = safe_num(row, 'bps_fine_avoided_yr1_usd')

    if fine_avoided and fine_avoided > 0 and fine_baseline and fine_baseline > 0:
        pct = (fine_avoided / fine_baseline) * 100
        html += f"""
            <tr style="{row_bg()}">
                <td><strong>Fine Avoidance</strong>{tooltip('fine_avoidance', row)}</td>
                <td>{format_currency(fine_baseline)}/yr</td>
                <td>{format_currency(fine_post_odcv)}/yr</td>
                <td>{change_cell(format_currency(fine_avoided), pct, "/yr")}</td>
            </tr>
"""

    # Property Value row
    if val_impact and val_impact > 0:
        html += f"""
            <tr style="{row_bg()}">
                <td><strong>Property Value</strong>{tooltip('property_value_increase', row)}</td>
                <td>—</td>
                <td>—</td>
                <td><span style="color:#15803d;font-weight:700;">↑{format_currency(val_impact)}</span></td>
            </tr>
"""

    # Energy Star Score row with simple gauge showing green fill based on score
    current_es = clamp_energy_star(safe_num(row, 'energy_star_score'))
    post_es = clamp_energy_star(safe_num(row, 'energy_star_score_post_odcv'))
    if current_es and current_es > 0:
        # Color based on score
        def es_color(score):
            if score < 50: return '#b91c1c'  # Dark red
            elif score < 75: return '#a16207'  # Dark gold
            else: return '#15803d'  # Dark green

        # Simple gauge - gray background arc, colored fill based on score
        def mini_gauge(score):
            color = es_color(score)
            # Score determines how much of the arc is filled (0-100 maps to arc)
            # Full arc is 180 degrees, score% of that
            fill_pct = score / 100
            return f'''<div style="display:inline-flex;align-items:center;gap:8px;">
                <svg viewBox="0 0 100 55" style="width:60px;height:32px;filter:drop-shadow(0 1px 2px rgba(0,0,0,0.1));">
                    <!-- Gray background arc -->
                    <path d="M 10 50 A 40 40 0 0 1 90 50" fill="none" stroke="#e5e7eb" stroke-width="8" stroke-linecap="round"/>
                    <!-- Colored fill arc based on score -->
                    <path d="M 10 50 A 40 40 0 0 1 90 50" fill="none" stroke="{color}" stroke-width="8" stroke-linecap="round" stroke-dasharray="{fill_pct * 126} 126"/>
                </svg>
                <span style="font-weight:700;font-size:1.2em;color:{color};min-width:28px;">{int(score)}</span>
            </div>'''

        current_str = mini_gauge(current_es)
        new_str = mini_gauge(post_es) if post_es else '<span style="color:#999;">—</span>'

        # Check if ODCV crosses certification threshold
        crosses_threshold = current_es and post_es and current_es < 75 and post_es >= 75

        if crosses_threshold:
            # Special row for buildings where ODCV makes the certification difference
            change = int(post_es - current_es)
            cert_tooltip = '<span class="info-tooltip" style="display: inline-block; margin-left: 5px; width: 18px; height: 18px; background: linear-gradient(135deg, #0066cc 0%, #004494 100%); color: white; border-radius: 50%; text-align: center; line-height: 18px; font-size: 12px; cursor: help; position: relative; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">i<span class="tooltip-content">ENERGY STAR certification requires a score of 75+. This building scores below 75 today. ODCV makes the score cross the 75 eligibility threshold—qualifying for official EPA certification.</span></span>'
            html += f"""
            <tr style="{row_bg()}">
                <td><strong>ENERGY STAR</strong>{tooltip('energy_star_score', row)}<br><span style="color:#15803d;">ODCV makes building <a href="https://www.energystar.gov/buildings/building-recognition/building-certification" target="_blank" style="color:#0891b2;text-decoration:underline;">certification eligible</a>.{cert_tooltip}</span></td>
                <td>{current_str}</td>
                <td>{new_str}</td>
                <td><span style="color:#15803d;font-weight:700;">↑{change} pts</span></td>
            </tr>
"""
        else:
            # Normal row
            if post_es and post_es > current_es:
                change = int(post_es - current_es)
                pct = safe_percentage(change, current_es)
                color = '#15803d' if pct >= 10 else '#0891b2' if pct >= 5 else '#3b82f6'
                change_str = f'<td><span style="color:{color};font-weight:700;">↑{change} pts</span> <span style="color:#64748b;font-size:0.9em;">({pct:.0f}%)</span></td>'
            else:
                change_str = '<td>—</td>'
            html += f"""
            <tr style="{row_bg()}">
                <td><strong>ENERGY STAR</strong>{tooltip('energy_star_score', row)}</td>
                <td>{current_str}</td>
                <td>{new_str}</td>
                {change_str}
            </tr>
"""

    # Carbon Emissions row
    if carbon_current and carbon_current > 0 and carbon_post:
        carbon_reduction = carbon_current - carbon_post
        pct = safe_percentage(carbon_reduction, carbon_current)
        html += f"""
            <tr style="{row_bg()}">
                <td><strong>Carbon Emissions</strong>{tooltip('carbon_reduction', row)}</td>
                <td>{format_number(carbon_current, 1)} tCO2e/yr</td>
                <td>{format_number(carbon_post, 1)} tCO2e/yr</td>
                <td>{change_cell(format_number(carbon_reduction, 1), pct, " tCO2e")}</td>
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
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06);
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

        .hero .hq-badge {{
            display: inline-block;
            font-size: 11px;
            font-weight: 600;
            color: white;
            background: rgba(255, 255, 255, 0.25);
            padding: 4px 10px;
            border-radius: 4px;
            margin-left: 10px;
            vertical-align: middle;
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
            border-bottom: 2px solid;
            border-image: linear-gradient(to right, #0066cc 0%, #0066cc 60%, transparent 100%) 1;
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
            font-weight: 600;
        }}

        th:first-child {{
            border-radius: 6px 0 0 0;
        }}

        th:last-child {{
            border-radius: 0 6px 0 0;
        }}

        td {{
            padding: 12px;
            border-bottom: 1px solid #e5e7eb;
        }}

        tr:nth-child(even) td {{
            background: #f9fafb;
        }}

        tr:hover td {{
            background: #f3f4f6;
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
            width: 18px;
            height: 18px;
            background: linear-gradient(135deg, #0066cc 0%, #004494 100%);
            color: white;
            border-radius: 50%;
            text-align: center;
            line-height: 18px;
            font-size: 12px;
            cursor: help;
            position: relative;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }}

        .tooltip-content {{
            position: absolute;
            bottom: 125%;
            left: 50%;
            transform: translateX(-50%);
            background-color: #1e293b;
            color: #f1f5f9;
            padding: 16px 20px;
            border-radius: 10px;
            white-space: normal;
            width: 380px;
            max-width: 90vw;
            font-size: 13px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.7;
            letter-spacing: 0.01em;
            text-align: left;
            z-index: 2147483647;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.2s, visibility 0.2s;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
            pointer-events: auto;
        }}

        .info-tooltip:hover .tooltip-content {{
            opacity: 1;
            visibility: visible;
        }}

        .tooltip-content a {{
            color: #60a5fa;
            text-decoration: underline;
        }}

        .tooltip-content a:hover {{
            color: #93c5fd;
        }}

        /* Tooltip arrow */
        .tooltip-content::before {{
            content: "";
            position: absolute;
            bottom: -12px;
            left: 50%;
            transform: translateX(-50%);
            border: 6px solid transparent;
            border-top-color: #1e293b;
        }}

        /* Org Logo Tooltip - instant, visible */
        .org-logo {{
            position: relative;
            display: inline-block;
        }}

        .org-logo::after {{
            content: attr(data-org-name);
            position: absolute;
            bottom: 100%;
            left: 50%;
            transform: translateX(-50%);
            background-color: #1a1a1a;
            color: white;
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 14px;
            font-weight: 500;
            white-space: nowrap;
            z-index: 9999;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.1s, visibility 0.1s;
            pointer-events: none;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            margin-bottom: 6px;
        }}

        .org-logo:hover::after {{
            opacity: 1;
            visibility: visible;
        }}

        /* Mobile tooltip adjustments */
        @media (max-width: 768px) {{
            .tooltip-content {{
                width: 320px;
                font-size: 10px;
                left: auto;
                right: 0;
                transform: none;
            }}

            .tooltip-content::before {{
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

    # 3. Impact
    html += generate_impact_section(row)

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
        row.name = idx  # Preserve index for LEED lookup
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
    row.name = idx  # Preserve index for LEED lookup
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

    # Filter out garbage/test data
    valid_mask = df_clean.apply(is_valid_building, axis=1)
    invalid_count = (~valid_mask).sum()
    if invalid_count > 0:
        print(f"⚠ Skipping {invalid_count} buildings with invalid/test data")
    df_clean = df_clean[valid_mask]

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
