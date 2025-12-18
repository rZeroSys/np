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
    'new': "Projected energy after ODCV implementation.",
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
    return f"Actual metered consumption from the building's utility bills, as reported to {city} through mandatory {law} disclosure. This is real data, not an estimate. It is what the building actually used."

def get_new_column_tooltip(row):
    """NEW column tooltip - explains projection by building type.

    Structure: MEANING → METHOD → DATA USED → SOURCE → JUSTIFICATION
    """
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    city = safe_val(row, 'loc_city', '')

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        meaning = "What this represents: Projected energy consumption if ventilation matched actual occupancy instead of running at design capacity."
        method = "How it's calculated: We apply the ODCV savings percentage to the HVAC portion of current consumption. The reduction reflects not conditioning empty floors due to vacancy and not ventilating unused desks on occupied floors due to low utilization."
        data_used = "Data used: Current consumption from city benchmarking, HVAC percentage by fuel type, vacancy rate for this market, and actual office attendance patterns."
        source = f"Sources: Current consumption from {city} benchmarking disclosure. Vacancy from CBRE/Cushman & Wakefield using {city} market data. Utilization from Kastle Systems badge swipes. HVAC percentages from CBECS 2018."
        justification = "Why this is achievable: Office HVAC is centralized and can be modulated with occupancy sensors. When you reduce airflow, fan energy drops dramatically due to fan affinity laws. Cooling load drops too because you condition less air."

    elif bldg_type in ('K-12 School', 'Higher Ed'):
        meaning = "What this represents: Projected energy consumption if HVAC responded to the actual school calendar instead of running fixed schedules."
        method = "How it's calculated: We apply schedule-based savings to the HVAC portion of current consumption. The reduction reflects summers, weekends, afternoons after dismissal, and holiday breaks when buildings sit empty but systems often keep running."
        data_used = "Data used: Current consumption from city benchmarking, HVAC percentage by fuel type, and school calendar patterns showing actual days and hours of student presence."
        source = f"Sources: Current consumption from {city} benchmarking disclosure. Schedule data from NCES. HVAC percentages from CBECS 2018 for educational buildings."
        justification = "Why this is achievable: Schools have predictable, published calendars. ODCV replaces legacy timers with calendar-aware controls. The building can maintain deep setback when empty and recover before students arrive."

    elif bldg_type == 'Hotel':
        meaning = "What this represents: Projected energy consumption if room ventilation matched guest presence instead of conditioning every room around the clock."
        method = "How it's calculated: We apply room-level occupancy savings to the HVAC portion of current consumption. The reduction reflects unoccupied rooms plus hours when guests are out during the day. Note that hotel gas is split between HVAC, hot water, and kitchens—only the HVAC portion responds to occupancy."
        data_used = "Data used: Current consumption from city benchmarking, hotel-specific HVAC percentages (which account for hot water and kitchen loads), and room-night occupancy for this market."
        source = f"Sources: Current consumption from {city} benchmarking disclosure. Room occupancy from STR Global using {city} market data. HVAC percentages from CBECS 2018 hotel-specific data."
        justification = "Why this is achievable: Each guest room has its own HVAC unit. Room-level sensors or door/key card integration enables setback when unoccupied. Even sold rooms are only occupied about ten hours per day."

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital'):
        meaning = "What this represents: Projected energy consumption with occupancy-based ventilation in non-clinical areas only. Patient care spaces maintain required airflow regardless."
        method = "How it's calculated: We apply conservatively capped savings to the HVAC portion of current consumption, limiting to non-clinical zones only. Lobbies, offices, cafeterias, and conference rooms can use occupancy control. Patient care areas are excluded."
        data_used = "Data used: Current consumption from city benchmarking, healthcare-specific HVAC percentages, and square footage breakdown by clinical vs. non-clinical space."
        source = f"Sources: Current consumption from {city} benchmarking disclosure. Ventilation requirements from ASHRAE 170. HVAC percentages from CBECS 2018 for healthcare buildings."
        justification = "Why this is achievable: Hospitals are mostly non-clinical space. Those areas can use standard occupancy-based control while patient areas maintain required air changes. The projection is conservative because care requirements come first."

    elif bldg_type == 'Residential Care':
        meaning = "What this represents: Projected energy consumption with occupancy-based conditioning in common areas and non-resident spaces. Resident rooms maintain required ventilation."
        method = "How it's calculated: We apply conservatively capped savings limited to controllable zones (common areas, administrative spaces). Resident room ventilation is not reduced."
        data_used = "Data used: Current consumption from city benchmarking, senior housing HVAC percentages, and space breakdown by resident vs. common areas."
        source = f"Sources: Current consumption from {city} benchmarking disclosure. Occupancy from NIC MAP Vision using {city}-area market data. HVAC percentages from CBECS 2018."
        justification = "Why this is achievable: Common areas and administrative spaces can use occupancy-based control while resident rooms maintain required levels. The projection reflects only the controllable portion."

    elif bldg_type in ('Retail', 'Retail Store'):
        meaning = "What this represents: Projected energy consumption if ventilation matched actual foot traffic instead of running at peak capacity all day."
        method = "How it's calculated: We apply traffic-based savings to the HVAC portion of current consumption. The reduction reflects slow periods when stores have few customers but systems run full blast."
        data_used = "Data used: Current consumption from city benchmarking, retail-specific HVAC percentages, and foot traffic patterns by day and time."
        source = f"Sources: Current consumption from {city} benchmarking disclosure. Traffic patterns from retail studies. HVAC percentages from CBECS 2018 for retail buildings."
        justification = "Why this is achievable: Retail HVAC can modulate based on CO2 sensors as a proxy for occupancy. Stores are packed on weekends but nearly empty on weekday mornings. Matching ventilation to traffic captures the waste."

    elif bldg_type == 'Supermarket':
        meaning = "What this represents: Projected energy consumption if sales floor conditioning matched customer traffic. Refrigeration is unchanged because it runs continuously regardless of traffic."
        method = "How it's calculated: We apply traffic-based savings only to the HVAC portion—refrigeration is carved out. The reduction reflects slow traffic periods when HVAC can respond to fewer customers."
        data_used = "Data used: Current consumption from city benchmarking, HVAC vs. refrigeration breakdown, and customer traffic patterns."
        source = f"Sources: Current consumption from {city} benchmarking disclosure. HVAC/refrigeration breakdown from CBECS 2018. Traffic patterns from retail studies."
        justification = "Why this is achievable: Refrigeration must run continuously—that can't change. But sales floor HVAC can respond to traffic. We isolate the controllable portion and apply savings there."

    elif bldg_type == 'Wholesale Club':
        meaning = "What this represents: Projected energy consumption if conditioning matched member traffic patterns, which are concentrated on weekends."
        method = "How it's calculated: We apply traffic-based savings to the HVAC portion of current consumption. The reduction reflects slower weekday periods when HVAC can modulate down."
        data_used = "Data used: Current consumption from city benchmarking, big-box retail HVAC percentages, and member traffic patterns."
        source = f"Sources: Current consumption from {city} benchmarking disclosure. Traffic patterns from retail studies. HVAC percentages from CBECS 2018."
        justification = "Why this is achievable: Wholesale clubs have high ceilings and large HVAC loads. Traffic is predictable and concentrated on weekends. Matching ventilation to traffic during slower periods captures significant waste."

    elif bldg_type in ('Venue', 'Theater'):
        meaning = "What this represents: Projected energy consumption if conditioning matched actual event schedules instead of running continuously."
        method = "How it's calculated: We apply event-schedule-based savings to the HVAC portion of current consumption. The reduction reflects the gap between event hours and total operating hours."
        data_used = "Data used: Current consumption from city benchmarking, venue HVAC percentages, and event scheduling patterns."
        source = f"Sources: Current consumption from {city} benchmarking disclosure. HVAC percentages from CBECS 2018 for entertainment buildings."
        justification = "Why this is achievable: Venues sit empty most of the time. Event schedules are known in advance. Matching conditioning to actual events instead of running around the clock captures significant waste."

    elif bldg_type == 'Restaurant/Bar':
        meaning = "What this represents: Projected energy consumption if dining area HVAC matched meal-time patterns. Kitchen ventilation is unchanged because exhaust hoods cannot be demand-controlled."
        method = "How it's calculated: We apply savings only to dining area conditioning—kitchen exhaust and makeup air are excluded. Most restaurant gas goes to cooking, not space heating."
        data_used = "Data used: Current consumption from city benchmarking, restaurant-specific HVAC percentages (which are much lower than other building types), and meal-time traffic patterns."
        source = f"Sources: Current consumption from {city} benchmarking disclosure. CBECS 2018 shows only about 18% of restaurant gas goes to space heating—the rest is cooking."
        justification = "Why this is achievable: Kitchen exhaust must run continuously—that can't change. But dining area HVAC can respond to customer traffic. We apply savings only to the controllable portion."

    elif bldg_type in ('Library/Museum', 'Library', 'Museum'):
        meaning = "What this represents: Projected energy consumption if conditioning aligned with operating hours and visitor traffic patterns."
        method = "How it's calculated: We apply operating-hours-based savings to the HVAC portion of current consumption. The reduction reflects hours when closed but systems keep running, plus slower periods during open hours."
        data_used = "Data used: Current consumption from city benchmarking, public building HVAC percentages, and operating hour patterns."
        source = f"Sources: Current consumption from {city} benchmarking disclosure. HVAC percentages from CBECS 2018 for public buildings."
        justification = "Why this is achievable: Public buildings have clear open/closed hours. HVAC often runs beyond operating hours. Aligning conditioning with actual use captures that waste."

    elif bldg_type == 'Outpatient Clinic':
        meaning = "What this represents: Projected energy consumption if ventilation matched appointment schedules and clinic operating hours."
        method = "How it's calculated: We apply schedule-based savings to the HVAC portion of current consumption. Unlike hospitals, clinics don't have 24/7 care or the same strict ventilation codes."
        data_used = "Data used: Current consumption from city benchmarking, medical office HVAC percentages, and appointment scheduling patterns."
        source = f"Sources: Current consumption from {city} benchmarking disclosure. Scheduling patterns from MGMA. HVAC percentages from CBECS 2018."
        justification = "Why this is achievable: Clinics operate on appointment schedules with clear business hours. Matching ventilation to the appointment schedule and reducing conditioning outside clinic hours captures real waste."

    else:
        meaning = "What this represents: Projected energy consumption if ventilation matched actual occupancy instead of running at design capacity around the clock."
        method = "How it's calculated: We apply an occupancy-based savings percentage to the HVAC portion of current consumption. The reduction reflects periods when spaces are empty but HVAC keeps running."
        data_used = "Data used: Current consumption from city benchmarking, HVAC percentages by fuel type, and occupancy patterns for this building type."
        source = f"Sources: Current consumption from {city} benchmarking disclosure. HVAC percentages from CBECS 2018."
        justification = "Why this is achievable: HVAC systems run at design capacity regardless of actual occupancy. Matching ventilation to when people are actually present captures the waste from conditioning empty spaces."

    return f"{meaning}\n\n{method}\n\n{data_used}\n\n{source}\n\n{justification}"

def get_change_column_tooltip(row):
    """CHANGE column tooltip - explains what the difference represents.

    Structure: MEANING → METHOD → DATA USED → SOURCE → JUSTIFICATION
    """
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')

    # MEANING is the same across types
    meaning = "What this represents: The difference between current and projected consumption—this is energy currently being wasted conditioning empty or underutilized spaces."

    # METHOD is the same across types
    method = "How it's calculated: Current consumption minus projected consumption. The reduction equals the HVAC portion of energy times the savings percentage for this building type."

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        data_used = "Data used: The current and projected values shown in this row, derived from this building's actual consumption, vacancy rate for this market, and office attendance patterns."
        justification = "What this means: HVAC running at full capacity for vacant floors, conference rooms with no meetings, and desks with no one sitting at them. This is the recoverable waste from conditioning spaces as if they were full when they're not."

    elif bldg_type in ('K-12 School', 'Higher Ed'):
        data_used = "Data used: The current and projected values shown in this row, derived from this building's actual consumption and school calendar patterns."
        justification = "What this means: HVAC running during summers, weekends, afternoons after dismissal, and holiday breaks when the building sits empty. This is the recoverable waste from running on fixed timers instead of responding to the academic calendar."

    elif bldg_type == 'Hotel':
        data_used = "Data used: The current and projected values shown in this row, derived from this building's actual consumption and room occupancy patterns for this market."
        justification = "What this means: Guest rooms being conditioned around the clock when guests are present only a fraction of that time. This includes both unsold rooms and rooms where the guest is out during the day."

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital', 'Residential Care'):
        data_used = "Data used: The current and projected values shown in this row, limited to non-clinical and common areas where occupancy-based control is safe."
        justification = "What this means: Non-clinical spaces (lobbies, offices, cafeterias) being conditioned at full capacity regardless of use. Patient care areas are excluded—this reflects only the controllable portion."

    elif bldg_type in ('Retail', 'Retail Store', 'Supermarket', 'Wholesale Club'):
        data_used = "Data used: The current and projected values shown in this row, derived from this building's actual consumption and customer traffic patterns."
        justification = "What this means: HVAC running at peak capacity during slow periods when the store has few customers. This is the waste from conditioning for the busiest hour all day long."

    elif bldg_type in ('Venue', 'Theater'):
        data_used = "Data used: The current and projected values shown in this row, derived from this building's actual consumption and event scheduling."
        justification = "What this means: Conditioning running around the clock for a venue designed for intermittent use. This is the waste from maintaining conditions during the many hours between events."

    elif bldg_type == 'Restaurant/Bar':
        data_used = "Data used: The current and projected values shown in this row, limited to dining area HVAC (kitchen exhaust is excluded)."
        justification = "What this means: Dining area conditioning running during dead hours between meals. Kitchen ventilation is unchanged—this reflects only the controllable portion."

    else:
        data_used = "Data used: The current and projected values shown in this row, derived from this building's actual consumption and occupancy patterns for this building type."
        justification = "What this means: HVAC running at design capacity regardless of actual occupancy. This is the recoverable waste from conditioning spaces when they're empty or underutilized."

    return f"{meaning}\n\n{method}\n\n{data_used}\n\n{justification}"

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
    """Dynamic ODCV opportunity explanation by building type.

    Structure: MEANING → METHOD → DATA USED → SOURCE → JUSTIFICATION
    """
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    city = safe_val(row, 'loc_city', '')

    # MEANING is similar across types but customized
    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        meaning = "What this represents: The percentage of HVAC energy that can be saved by matching ventilation to actual occupancy instead of running at design capacity."
        method = """How it's calculated: Savings % = Floor + (Opportunity × Automation × Range) × Modifiers.

Opportunity Score combines two waste streams: Vacancy + (1 − Vacancy) × (1 − Utilization). Example: 25% vacancy plus 75% leased at 55% utilization = 59% opportunity.

Automation Score averages year built (newer = better controls) and size (larger = more sophisticated BMS). A 2018 building over 250,000 sqft scores 1.0; a 1975 building under 50,000 sqft scores ~0.35.

Modifiers adjust for efficiency (already-efficient buildings have less waste to capture) and climate (colder climates have higher heating penalties per CFM reduced)."""
        data_used = f"Data used: Vacancy rate for {city} market, actual office attendance patterns for this region, building year built, building square footage, Energy Star score (or EUI if no score), and climate zone."
        source = f"Sources: Vacancy from CBRE and Cushman & Wakefield quarterly reports, using {city} market data—not national averages. Utilization from Kastle Systems badge swipe tracking—measured values from real buildings. Climate zones from ASHRAE. Efficiency from EPA Portfolio Manager."
        justification = "Why this works: Office HVAC is centralized—landlords cannot just shut off vacant floors due to fire codes and BMS limitations. Vacant space gets conditioned like occupied space. And the leased floors are not full either—hybrid work means many desks sit empty. Both waste streams are real and measurable."

    elif bldg_type == 'K-12 School':
        meaning = "What this represents: The percentage of HVAC energy that can be saved by aligning ventilation with the school calendar instead of running on fixed timers."
        method = """How it's calculated: Savings % = Floor + (Opportunity × Automation × Range) × Modifiers.

Opportunity Score for schools = 1 − Utilization. Schools don't have vacancy like offices—there's one tenant. But they have extreme schedule-driven emptiness: summers, weekends, afternoons after 3pm, holidays. Total empty time often exceeds 50% of the year.

Automation Score averages year built and size (same as offices).

Modifiers adjust for efficiency and climate."""
        data_used = "Data used: School calendar patterns showing actual days and hours of student presence, building year built, building square footage, efficiency rating, and climate zone."
        source = "Sources: Schedule data from NCES (National Center for Education Statistics). School calendars are public, predictable, and standardized across districts. Not estimated—these are actual operating schedules."
        justification = "Why this works: Schools are designed for full classrooms but sit empty over half the calendar year. HVAC often runs on fixed timers that ignore the calendar entirely. The gap between designed capacity and actual student presence is recoverable waste."

    elif bldg_type == 'Higher Ed':
        meaning = "What this represents: The percentage of HVAC energy that can be saved by matching ventilation to academic schedules and classroom utilization."
        method = "How it's calculated: We account for calendar gaps (summer, winter, spring breaks) plus daily variability—classrooms packed some hours and empty others. A lecture hall might be used three days a week and sit empty the rest."
        data_used = "Data used: Academic calendar patterns, classroom utilization rates, building year built, and building size."
        source = "Sources: Academic scheduling data from NCES. University schedules and classroom utilization are well documented through institutional reporting."
        justification = "Why this works: Universities have the same calendar gaps as K-12 plus even more daily variability. Academic schedules are predictable. Matching ventilation to actual class schedules captures significant waste."

    elif bldg_type == 'Hotel':
        meaning = "What this represents: The percentage of HVAC energy that can be saved by matching room conditioning to guest presence instead of running continuously."
        method = """How it's calculated: Savings % = Floor + (Opportunity × Automation × Range) × Modifiers.

Opportunity Score for hotels = 1 − Utilization. Two waste sources: unsold rooms (average US occupancy ~63%) plus rooms where guest is out during the day. Even sold rooms are only occupied ~10 hours/day. True utilization runs ~28%.

Automation Score averages year built and size. Many hotels already have room-level sensing (key cards, motion detectors).

Modifiers adjust for efficiency and climate."""
        data_used = f"Data used: Room-night occupancy for {city} market, typical guest-in-room hours, building year built, building square footage, efficiency rating, and climate zone."
        source = f"Sources: Room occupancy from STR Global, using {city} market data—not national averages. STR is the hotel industry's authoritative tracking source. This is the same data hotel operators use internally for revenue management."
        justification = "Why this works: Hotels condition every room around the clock, but even sold rooms are only occupied about ten hours per day. Room-level sensors enable setback when guests are out. The opportunity is well-documented through industry tracking."

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital'):
        meaning = "What this represents: The percentage of HVAC energy that can be saved in non-clinical areas while maintaining required airflow in patient care spaces."
        method = """How it's calculated: Savings % = Floor + (Opportunity × Automation × Range) × Modifiers.

Opportunity Score for hospitals = (1 − Utilization) × 0.3. We apply a 0.3 multiplier because patient care areas cannot reduce ventilation regardless of census. ASHRAE 170 mandates minimum air changes for infection control.

The savings range is capped lower than other building types. Only non-clinical zones (lobbies, offices, cafeterias, conference rooms) can use occupancy-based control."""
        data_used = "Data used: Hospital census patterns, square footage breakdown by clinical vs. non-clinical space, building year built, building square footage, and efficiency rating."
        source = "Sources: Occupancy patterns from AHA Hospital Statistics. Ventilation requirements from ASHRAE 170 standards for healthcare facilities. These are code requirements, not optional."
        justification = "Why this works: ASHRAE 170 mandates minimum air changes in patient areas—we don't touch those. But hospitals are mostly non-clinical space. Those areas can use standard occupancy-based control. The calculation is conservative because patient care comes first."

    elif bldg_type == 'Residential Care':
        meaning = "What this represents: The percentage of HVAC energy that can be saved in common areas and non-resident spaces while maintaining care standards."
        method = "How it's calculated: We apply savings only to controllable zones (common areas, administrative spaces) and cap conservatively. Resident room ventilation maintains required levels."
        data_used = "Data used: Facility occupancy rates, space breakdown by resident vs. common areas, building year built, and building size."
        source = f"Sources: Occupancy data from NIC MAP Vision, using {city}-area senior housing market data. Care requirements from facility licensing standards."
        justification = "Why this works: Residential care has ventilation requirements for resident rooms, but common areas and administrative spaces can use occupancy-based control. We limit savings to those zones for a conservative, defensible estimate."

    elif bldg_type in ('Retail', 'Retail Store'):
        meaning = "What this represents: The percentage of HVAC energy that can be saved by matching ventilation to actual foot traffic instead of running at peak capacity all day."
        method = "How it's calculated: We look at traffic patterns throughout operating hours. Retail doesn't have vacancy—it's owner-occupied. But traffic swings wildly between busy periods and slow hours."
        data_used = "Data used: Foot traffic patterns by day and time, building year built, and building size."
        source = "Sources: Traffic patterns from retail studies and sources like Placer.ai. Retail traffic is well-studied and predictable."
        justification = "Why this works: Stores are packed on weekends but nearly empty on weekday mornings. HVAC runs at the same capacity regardless. Matching ventilation to actual traffic captures the waste from over-conditioning during slow periods."

    elif bldg_type == 'Supermarket':
        meaning = "What this represents: The percentage of HVAC energy that can be saved by matching sales floor conditioning to customer traffic. Refrigeration is excluded because it runs continuously regardless of traffic."
        method = "How it's calculated: We isolate HVAC from refrigeration and apply occupancy-based savings only to the space conditioning portion. Refrigeration cannot respond to occupancy."
        data_used = "Data used: Customer traffic patterns, HVAC vs. refrigeration energy breakdown, building year built, and building size."
        source = "Sources: HVAC/refrigeration breakdown from CBECS 2018 for grocery buildings. Traffic patterns from retail studies."
        justification = "Why this works: Supermarkets have unique energy profiles. Refrigeration runs continuously—that can't change. But HVAC conditioning the sales floor can respond to traffic. We isolate the controllable portion."

    elif bldg_type == 'Wholesale Club':
        meaning = "What this represents: The percentage of HVAC energy that can be saved by matching conditioning to member traffic patterns, which are concentrated on weekends."
        method = "How it's calculated: We look at traffic patterns—wholesale clubs see heavy weekend traffic but are much quieter on weekdays. HVAC runs at peak capacity regardless."
        data_used = "Data used: Member traffic patterns by day and time, building year built, and building size."
        source = "Sources: Traffic patterns from retail studies. Wholesale club traffic is predictable and concentrated on weekends."
        justification = "Why this works: Wholesale clubs have high ceilings and large HVAC loads. Traffic is predictable and concentrated on weekends. Matching ventilation to traffic during slower periods captures significant waste."

    elif bldg_type in ('Venue', 'Theater'):
        meaning = "What this represents: The percentage of HVAC energy that can be saved by matching conditioning to actual event schedules instead of running continuously."
        method = "How it's calculated: We look at the gap between event hours and total hours. Venues are designed for intermittent peak use but often condition around the clock."
        data_used = "Data used: Event scheduling patterns, typical hours of operation vs. event hours, building year built, and building size."
        source = "Sources: Venue operating patterns. Event schedules are predictable and published."
        justification = "Why this works: Event venues sit empty most of the time. HVAC often maintains conditions around the clock for intermittent use. Matching conditioning to actual event schedules captures the waste from conditioning empty spaces."

    elif bldg_type == 'Restaurant/Bar':
        meaning = "What this represents: The percentage of dining area HVAC energy that can be saved. Kitchen ventilation is excluded because exhaust hoods cannot be demand-controlled."
        method = "How it's calculated: We apply savings only to dining area conditioning, not kitchen exhaust. CBECS data shows most restaurant gas goes to cooking, not space heating. Only the small HVAC portion is controllable."
        data_used = "Data used: Meal-time traffic patterns, HVAC vs. cooking energy breakdown, building year built, and building size."
        source = "Sources: Energy breakdown from CBECS 2018 showing only about 18% of restaurant gas goes to space heating—the rest is cooking."
        justification = "Why this works: Kitchen exhaust hoods require constant makeup air that must be heated—that can't be demand-controlled. Only dining area HVAC responds to occupancy. The calculation is conservative but accurate to what's actually controllable."

    elif bldg_type in ('Library/Museum', 'Library', 'Museum'):
        meaning = "What this represents: The percentage of HVAC energy that can be saved by aligning conditioning with operating hours and visitor traffic patterns."
        method = "How it's calculated: We look at operating hours plus traffic patterns when open. The opportunity comes from hours when closed but systems keep running, plus slower periods during open hours."
        data_used = "Data used: Operating hours, visitor traffic patterns, building year built, and building size."
        source = "Sources: Public building operating patterns. Hours are fixed and predictable."
        justification = "Why this works: Public buildings have clear open/closed hours and relatively steady traffic when open. HVAC often runs beyond operating hours. Aligning conditioning with actual use captures that waste."

    elif bldg_type == 'Outpatient Clinic':
        meaning = "What this represents: The percentage of HVAC energy that can be saved by matching ventilation to appointment schedules and clinic operating hours."
        method = "How it's calculated: We look at appointment scheduling patterns and clinic hours. Unlike hospitals, outpatient clinics don't have 24/7 care or the same strict ventilation codes."
        data_used = "Data used: Appointment scheduling patterns, clinic operating hours, building year built, and building size."
        source = "Sources: Scheduling patterns from MGMA medical office benchmarks. Clinic schedules are predictable."
        justification = "Why this works: Clinics operate on appointment schedules with clear business hours. Matching ventilation to the appointment schedule and reducing conditioning outside clinic hours captures real waste."

    else:
        meaning = "What this represents: The percentage of HVAC energy that can be saved by matching ventilation to actual occupancy patterns."
        method = "How it's calculated: We estimate opportunity based on how much of the time spaces sit empty while HVAC keeps running. The method varies by building type—multi-tenant buildings factor in vacancy, single-tenant buildings look at operating schedules."
        data_used = "Data used: Occupancy patterns appropriate for this building type, building year built, and building size."
        source = "Sources: Occupancy data from industry sources appropriate for this building type."
        justification = "Why this works: HVAC systems typically run at design capacity regardless of actual occupancy. Matching ventilation to when people are actually present captures the waste from conditioning empty spaces."

    return f"{meaning}\n\n{method}\n\n{data_used}\n\n{source}\n\n{justification}"


def get_property_value_tooltip(row):
    """Property value tooltip - explains method, data source, justification by building type.

    Structure: MEANING → METHOD → DATA USED → SOURCE → JUSTIFICATION
    """
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    city = safe_val(row, 'loc_city', '')

    # MEANING (same for all types)
    meaning = "What this represents: The increase in property value from reducing annual operating costs."

    # METHOD (same for all types)
    method = """How it's calculated: Valuation Impact = Total Annual OpEx Avoidance ÷ Cap Rate.

Total Annual OpEx Avoidance includes both utility savings and BPS fine avoidance (for buildings in cities with Building Performance Standards). Both are operating expenses that reduce when HVAC waste is eliminated.

The cap rate acts as a multiplier. A lower cap rate means investors pay more for each dollar of income, so the same dollar of savings creates a larger value increase. Cap rates vary by property type (hotels higher, grocery-anchored retail lower) and market (gateway cities lower, secondary markets higher)."""

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        data_used = "Data used: This building's projected utility savings and fine avoidance (if in a BPS city), plus the cap rate for office properties in this market."
        source = f"Sources: Cap rate from CBRE's quarterly Cap Rate Survey, using {city} market data. Savings calculated from this building's actual energy consumption reported through city benchmarking disclosure."
        justification = "Why this works: Every dollar of reduced operating expense flows directly to Net Operating Income. Office landlords capture utility savings directly. Lower expenses mean higher income, which investors capitalize into higher property value."

    elif bldg_type == 'Hotel':
        data_used = "Data used: This hotel's projected utility savings (accounting for the split between HVAC, hot water, and kitchen gas use), plus the cap rate for hotels."
        source = f"Sources: Cap rate from CBRE's quarterly Cap Rate Survey, using {city}-area hotel market data. Savings calculated from actual energy consumption, with HVAC portion isolated using CBECS hotel-specific breakdowns."
        justification = "Why this works: Hotels trade at higher cap rates than offices, so the value multiplier per dollar saved is lower. But hotel operating costs are a larger share of revenue, making efficiency gains proportionally more impactful on absolute value."

    elif bldg_type in ('K-12 School', 'Higher Ed'):
        data_used = "Data used: This building's projected utility savings from aligning HVAC with the academic calendar, plus the cap rate for educational properties."
        source = "Sources: Cap rate from CBRE's quarterly Cap Rate Survey for institutional properties. Savings calculated from actual energy consumption and NCES schedule data."
        justification = "Why this works: Educational buildings are income-producing assets (tuition, state funding per pupil). Lower operating costs free budget for educational priorities. The same income capitalization logic applies even for non-profit operators."

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital'):
        data_used = "Data used: This hospital's projected utility savings from non-clinical areas only (lobbies, offices, cafeterias), plus healthcare facility cap rates."
        source = "Sources: Cap rate from CBRE's quarterly Cap Rate Survey for healthcare properties. Savings are conservatively capped because clinical areas cannot reduce ventilation under ASHRAE 170."
        justification = "Why this works: Healthcare facilities are valued like other commercial properties. Operating cost reductions flow to NOI. We apply savings only to non-clinical spaces, so the improvement is conservative but defensible."

    elif bldg_type == 'Residential Care':
        data_used = "Data used: This facility's projected utility savings from common areas and non-patient spaces, plus senior housing cap rates."
        source = f"Sources: Cap rate from CBRE's quarterly Cap Rate Survey, using {city}-area senior housing data. Occupancy patterns from NIC MAP Vision. Savings conservatively applied only to controllable zones."
        justification = "Why this works: Senior housing is valued on NOI like other commercial properties. Care requirements limit where savings can be captured, but common areas and administrative spaces offer real opportunity."

    elif bldg_type in ('Retail', 'Retail Store'):
        data_used = "Data used: This store's projected utility savings from traffic-based ventilation control, plus retail property cap rates."
        source = f"Sources: Cap rate from CBRE's quarterly Cap Rate Survey for {city}-area retail. Savings calculated from actual energy consumption and traffic pattern data."
        justification = "Why this works: Retail properties are income-producing assets. Net lease structures may affect whether landlord or tenant captures savings, but the property value impact is real regardless of who pays the utility bills."

    elif bldg_type == 'Supermarket':
        data_used = "Data used: This supermarket's projected HVAC savings (refrigeration excluded), plus grocery-anchored retail cap rates."
        source = f"Sources: Cap rate from CBRE's quarterly Cap Rate Survey for {city}-area grocery-anchored retail. Refrigeration is carved out because it cannot respond to occupancy."
        justification = "Why this works: Supermarkets have unique energy profiles. Refrigeration runs continuously regardless of traffic. But HVAC for the sales floor can respond to occupancy. We isolate the controllable portion."

    elif bldg_type == 'Wholesale Club':
        data_used = "Data used: This building's projected HVAC savings from matching conditioning to member traffic patterns, plus big-box retail cap rates."
        source = f"Sources: Cap rate from CBRE's quarterly Cap Rate Survey for {city}-area big-box retail. Traffic patterns from retail studies."
        justification = "Why this works: Wholesale clubs have high ceilings and large HVAC loads. Traffic is predictable and concentrated on weekends. Matching ventilation to traffic yields significant savings that flow to property value."

    elif bldg_type == 'Restaurant/Bar':
        data_used = "Data used: This restaurant's projected HVAC savings (kitchen exhaust excluded), plus restaurant property cap rates."
        source = "Sources: Cap rate from CBRE's quarterly Cap Rate Survey for restaurant properties. CBECS data shows only about 18% of restaurant gas goes to space heating—the rest is cooking."
        justification = "Why this works: Restaurant HVAC savings are limited because kitchen exhaust hoods require constant makeup air. We apply savings only to the small controllable portion. The calculation is conservative but accurate."

    elif bldg_type in ('Venue', 'Theater'):
        data_used = "Data used: This venue's projected savings from event-schedule-based conditioning, plus entertainment venue cap rates."
        source = "Sources: Cap rate from CBRE's quarterly Cap Rate Survey for entertainment/special purpose properties. Savings reflect the gap between event hours and total operating hours."
        justification = "Why this works: Venues are designed for intermittent peak use but often condition continuously. Matching HVAC to event schedules captures significant waste. The value impact flows through NOI like any commercial property."

    elif bldg_type in ('Library/Museum', 'Library', 'Museum'):
        data_used = "Data used: This building's projected savings from operating-hours-based conditioning, plus institutional property cap rates."
        source = "Sources: Cap rate from CBRE's quarterly Cap Rate Survey for institutional/special purpose properties. Operating hours are fixed and predictable."
        justification = "Why this works: Public buildings have clear open/closed hours. HVAC often runs beyond operating hours. Aligning conditioning with actual use reduces waste that flows to operating budgets and property value."

    elif bldg_type == 'Outpatient Clinic':
        data_used = "Data used: This clinic's projected savings from appointment-schedule-based conditioning, plus medical office cap rates."
        source = f"Sources: Cap rate from CBRE's quarterly Cap Rate Survey, using {city} medical office market data. Scheduling patterns from MGMA medical office benchmarks."
        justification = "Why this works: Outpatient clinics operate on appointment schedules with clear business hours, unlike hospitals with 24/7 care. This makes them more like offices for HVAC purposes—predictable schedules yield predictable savings."

    else:
        data_used = "Data used: This building's projected utility savings plus the appropriate cap rate for this property type."
        source = f"Sources: Cap rate from CBRE's quarterly Cap Rate Survey, using market data appropriate for {city} and this building type."
        justification = "Why this works: Every dollar of reduced operating expense flows directly to Net Operating Income. Investors value properties as a multiple of NOI. Lower expenses mean higher income, which capitalizes into higher property value."

    return f"{meaning}\n\n{method}\n\n{data_used}\n\n{source}\n\n{justification}"

def get_energy_star_tooltip(row):
    """Energy Star tooltip - explains method, data source, justification by building type.

    Structure: MEANING → METHOD → DATA USED → SOURCE → JUSTIFICATION
    """
    bldg_type = safe_val(row, 'bldg_type', '')
    city = safe_val(row, 'loc_city', '')

    # MEANING (same for all types)
    meaning = "What this represents: A percentile ranking of this building's energy efficiency compared to similar buildings nationwide. A score of 50 means average; 75 or above earns EPA certification."

    # METHOD (same for all types)
    method = "How it's calculated: EPA uses source energy (not site energy), normalized for weather, operating hours, and other factors. Buildings are compared only to peers of the same type and climate zone."

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        data_used = "Data used: This building's energy consumption from city benchmarking disclosure, compared to the national database of office buildings with similar characteristics."
        source = f"Sources: Current score from {city} benchmarking disclosure or estimated using EPA Portfolio Manager methodology. Peer comparison from EPA's CBECS-based regression models."
        justification = "Why this matters: Reducing HVAC waste improves efficiency relative to peers who are still conditioning empty space. Getting from below-average to certification territory can meaningfully affect tenant perception and lease negotiations."

    elif bldg_type == 'Hotel':
        data_used = "Data used: This hotel's energy consumption from city benchmarking disclosure, compared to the national database of hotels with similar characteristics."
        source = f"Sources: Current score from {city} benchmarking disclosure or estimated using EPA Portfolio Manager methodology. Hotels have their own peer group separate from offices."
        justification = "Why this matters: Hotels have their own Energy Star category with different benchmarks. Improving room-level efficiency moves you up in the hotel peer group. DC's BEPS uses Energy Star targets—hotels have a specific threshold different from offices."

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital'):
        data_used = "Data used: This hospital's energy consumption from city benchmarking disclosure, compared to the national database of hospitals with similar characteristics."
        source = f"Sources: Current score from {city} benchmarking disclosure or estimated using EPA Portfolio Manager methodology. Hospitals are scored only against other hospitals."
        justification = "Why this matters: Hospitals are scored against other hospitals, which all have high energy use due to ventilation requirements. Even modest improvements can move you up several percentiles since the peer group is tightly clustered around high consumption."

    elif bldg_type in ('K-12 School', 'Higher Ed'):
        data_used = "Data used: This school's energy consumption from city benchmarking disclosure, compared to the national database of educational buildings with similar characteristics."
        source = f"Sources: Current score from {city} benchmarking disclosure or estimated using EPA Portfolio Manager methodology. Educational buildings have their own peer group."
        justification = "Why this matters: Schools with better schedule-aligned HVAC rank higher than those running equipment continuously. Matching ventilation to the academic calendar improves efficiency relative to schools still running on legacy timers."

    elif bldg_type in ('Retail', 'Retail Store'):
        data_used = "Data used: This store's energy consumption from city benchmarking disclosure, compared to the national database of retail buildings with similar characteristics."
        source = f"Sources: Current score from {city} benchmarking disclosure or estimated using EPA Portfolio Manager methodology. Retail buildings have their own peer group."
        justification = "Why this matters: Retail buildings that match ventilation to traffic patterns will rank higher than stores conditioning at peak capacity all day. Efficiency improvements move you up relative to less optimized peers."

    elif bldg_type == 'Supermarket':
        data_used = "Data used: This supermarket's energy consumption from city benchmarking disclosure, compared to the national database of supermarkets with similar characteristics."
        source = f"Sources: Current score from {city} benchmarking disclosure or estimated using EPA Portfolio Manager methodology. Supermarkets have their own peer group that accounts for refrigeration loads."
        justification = "Why this matters: Supermarkets are compared only to other supermarkets, which all have high refrigeration loads. The score reflects efficiency in space conditioning and other controllable areas relative to grocery peers."

    elif bldg_type in ('Residential Care',):
        data_used = "Data used: This facility's energy consumption from city benchmarking disclosure, compared to the national database of senior care facilities with similar characteristics."
        source = f"Sources: Current score from {city} benchmarking disclosure or estimated using EPA Portfolio Manager methodology. Senior care facilities have their own peer group."
        justification = "Why this matters: Senior housing that reduces conditioning in common areas while maintaining care standards will rank higher than facilities running at full capacity regardless of occupancy."

    else:
        data_used = "Data used: This building's energy consumption from city benchmarking disclosure, compared to the national database of similar buildings."
        source = f"Sources: Current score from {city} benchmarking disclosure or estimated using EPA Portfolio Manager methodology."
        justification = "Why this matters: Less energy means better efficiency relative to peer buildings, which means a higher percentile ranking. The score reflects how this building compares to similar buildings nationwide."

    return f"{meaning}\n\n{method}\n\n{data_used}\n\n{source}\n\n{justification}"

def get_electricity_kwh_tooltip(row):
    """ROW tooltip for electricity consumption - explains the concept of electrical waste by building type.

    Structure: MEANING → METHOD → DATA USED → SOURCE → JUSTIFICATION
    """
    bldg_type = safe_val(row, 'bldg_type', '')
    city = safe_val(row, 'loc_city', '')

    # MEANING (same for all)
    meaning = "What this represents: The electricity consumption row shows current usage, projected usage after ODCV, and the reduction in kilowatt-hours per year."

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        method = "How electricity is used: Fans, chillers, and pumps run the HVAC system. Air handling units run at design capacity regardless of how many people are present. Chillers cool that air even when floors sit empty."
        data_used = "Data used: Actual electricity consumption from city benchmarking, HVAC percentage for electricity (which varies by building efficiency), vacancy rate for this market, and office attendance patterns."
        source = f"Sources: Consumption from {city} benchmarking disclosure. Vacancy from CBRE/Cushman & Wakefield using {city} market data. Utilization from Kastle Systems badge swipes. HVAC percentage from CBECS 2018."
        justification = "Why savings are possible: ODCV uses occupancy sensors to modulate fans. When you reduce airflow, fan energy drops dramatically due to fan affinity laws (cubic relationship). Cooling load drops too because you're conditioning less air."

    elif bldg_type in ('K-12 School', 'Higher Ed'):
        method = "How electricity is used: HVAC fans, cooling equipment, and pumps run on fixed schedules regardless of the academic calendar. Systems pull the same air whether students are present or not."
        data_used = "Data used: Actual electricity consumption from city benchmarking, educational building HVAC percentage, and school calendar patterns."
        source = f"Sources: Consumption from {city} benchmarking disclosure. Schedule data from NCES. HVAC percentage from CBECS 2018 for educational buildings."
        justification = "Why savings are possible: ODCV replaces legacy timer schedules with calendar-aware controls. The building can reduce conditioning during summers, weekends, afternoons after dismissal, and holidays—all times when students are absent but systems currently run."

    elif bldg_type == 'Hotel':
        method = "How electricity is used: Each guest room has its own HVAC unit running continuously. Common areas run 24/7. Waste comes from unsold rooms and rooms where guests are out during the day."
        data_used = "Data used: Actual electricity consumption from city benchmarking, hotel-specific HVAC percentage, and room-night occupancy for this market."
        source = f"Sources: Consumption from {city} benchmarking disclosure. Room occupancy from STR Global using {city} market data. HVAC percentage from CBECS 2018 hotel-specific data."
        justification = "Why savings are possible: Room-level sensors or key card integration allows setback when rooms are unoccupied. Even sold rooms are only occupied about ten hours per day—the rest is recoverable waste."

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital'):
        method = "How electricity is used: HVAC runs at high capacity for ventilation requirements. Patient areas must maintain minimum air changes under ASHRAE 170 regardless of occupancy."
        data_used = "Data used: Actual electricity consumption from city benchmarking, healthcare-specific HVAC percentage, and conservative savings ceiling limited to non-clinical areas."
        source = f"Sources: Consumption from {city} benchmarking disclosure. HVAC percentage from CBECS 2018 for healthcare. Ventilation requirements from ASHRAE 170."
        justification = "Why savings are limited: Patient care areas cannot reduce ventilation—infection control requirements come first. But hospitals are mostly non-clinical space: lobbies, cafeterias, offices, conference rooms. Those areas can use standard ODCV."

    elif bldg_type == 'Residential Care':
        method = "How electricity is used: HVAC runs for both resident rooms and common areas. Care requirements affect what can be controlled."
        data_used = "Data used: Actual electricity consumption from city benchmarking, senior housing HVAC percentage, and occupancy patterns limited to controllable zones."
        source = f"Sources: Consumption from {city} benchmarking disclosure. Occupancy from NIC MAP Vision using {city}-area market data. HVAC percentage from CBECS 2018."
        justification = "Why savings are possible: Common areas and administrative spaces can use occupancy-based control while resident rooms maintain required levels. We limit savings to controllable zones."

    elif bldg_type in ('Retail', 'Retail Store'):
        method = "How electricity is used: HVAC runs at full capacity from open to close regardless of foot traffic. Traffic swings wildly between busy periods and slow hours."
        data_used = "Data used: Actual electricity consumption from city benchmarking, retail HVAC percentage, and foot traffic patterns."
        source = f"Sources: Consumption from {city} benchmarking disclosure. Traffic patterns from retail studies. HVAC percentage from CBECS 2018 for retail."
        justification = "Why savings are possible: ODCV can modulate based on CO2 sensors as a proxy for occupancy. Stores are packed on weekends but nearly empty on weekday mornings. Matching ventilation to traffic captures the waste."

    elif bldg_type == 'Supermarket':
        method = "How electricity is used: Refrigeration runs continuously—that cannot change. But HVAC conditioning the sales floor can respond to traffic."
        data_used = "Data used: Actual electricity consumption from city benchmarking, HVAC vs. refrigeration breakdown, and customer traffic patterns."
        source = f"Sources: Consumption from {city} benchmarking disclosure. HVAC/refrigeration breakdown from CBECS 2018. Traffic patterns from retail studies."
        justification = "Why savings are limited: We isolate HVAC from refrigeration and apply savings only to the space conditioning portion. Refrigeration is a continuous load that cannot respond to occupancy."

    elif bldg_type in ('Venue', 'Theater'):
        method = "How electricity is used: HVAC often maintains conditions around the clock for venues designed for intermittent peak use. Most hours, the space sits empty."
        data_used = "Data used: Actual electricity consumption from city benchmarking, venue HVAC percentage, and event scheduling patterns."
        source = f"Sources: Consumption from {city} benchmarking disclosure. HVAC percentage from CBECS 2018 for entertainment buildings."
        justification = "Why savings are possible: ODCV matches conditioning to actual event schedules. The gap between event hours and total operating hours is where the waste occurs."

    elif bldg_type == 'Restaurant/Bar':
        method = "How electricity is used: Kitchen exhaust fans run continuously during cooking hours—that cannot change. Only dining area HVAC can respond to occupancy."
        data_used = "Data used: Actual electricity consumption from city benchmarking, restaurant-specific HVAC percentage (which is lower than other types), and meal-time patterns."
        source = f"Sources: Consumption from {city} benchmarking disclosure. HVAC/cooking breakdown from CBECS 2018."
        justification = "Why savings are limited: Kitchen exhaust requires constant makeup air. Only the dining area HVAC portion is controllable. We apply savings only to that portion."

    else:
        method = "How electricity is used: Fans, chillers, and pumps run the HVAC system at design capacity regardless of actual occupancy."
        data_used = "Data used: Actual electricity consumption from city benchmarking and HVAC percentage by building type."
        source = f"Sources: Consumption from {city} benchmarking disclosure. HVAC percentage from CBECS 2018."
        justification = "Why savings are possible: ODCV detects when spaces are empty and reduces airflow. You only condition air for people who are actually there."

    return f"{meaning}\n\n{method}\n\n{data_used}\n\n{source}\n\n{justification}"

def get_natural_gas_tooltip(row):
    """ROW tooltip for natural gas consumption - explains the concept of gas heating waste by building type.

    Structure: MEANING → METHOD → DATA USED → SOURCE → JUSTIFICATION
    """
    bldg_type = safe_val(row, 'bldg_type', '')
    city = safe_val(row, 'loc_city', '')

    # MEANING (same for all)
    meaning = "What this represents: The natural gas consumption row shows current usage, projected usage after ODCV, and the reduction in therms per year."

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        method = "How gas is used: Gas heats the building, including all the fresh outdoor air that ventilation pulls in. In winter, every cubic foot of cold outside air must be heated before delivery to occupied spaces."
        data_used = "Data used: Actual gas consumption from city benchmarking, HVAC percentage for gas (CBECS shows nearly 88% of office gas goes to space heating), vacancy rate for this market, and office attendance patterns."
        source = f"Sources: Consumption from {city} benchmarking disclosure. Vacancy from CBRE/Cushman & Wakefield using {city} market data. Utilization from Kastle Systems. HVAC percentage from CBECS 2018."
        justification = "Why savings are possible: When you reduce ventilation to empty spaces, you heat less air. The reduction comes from not heating air for vacant floors and underutilized occupied floors."

    elif bldg_type in ('K-12 School', 'Higher Ed'):
        method = "How gas is used: Gas heats the building. Boilers often run through winter break, spring break, and sometimes maintain temperatures all summer. Schools routinely heat empty buildings."
        data_used = "Data used: Actual gas consumption from city benchmarking, educational building HVAC percentage (CBECS shows about 80% of school gas goes to HVAC), and school calendar patterns."
        source = f"Sources: Consumption from {city} benchmarking disclosure. Schedule data from NCES. HVAC percentage from CBECS 2018 for educational buildings."
        justification = "Why savings are possible: ODCV allows deep setback when the calendar shows empty days, then recovery before students arrive. Aligning heating with actual school schedules captures significant waste."

    elif bldg_type == 'Hotel':
        method = "How gas is used: Hotels split gas three ways—space heating gets about 20%, domestic hot water for guests gets about 42%, and cooking gets about 33%. Hot water and kitchen demand do not change with room occupancy because guests still shower and restaurants still cook."
        data_used = "Data used: Actual gas consumption from city benchmarking, hotel-specific gas breakdown (only the 20% heating portion responds to occupancy), and room-night occupancy for this market."
        source = f"Sources: Consumption from {city} benchmarking disclosure. Room occupancy from STR Global using {city} market data. Gas breakdown from CBECS 2018 hotel-specific data."
        justification = "Why savings are limited: Only the space heating portion responds to occupancy—hot water and cooking cannot be reduced. We are explicit about this split because overstating hotel gas savings would be misleading."

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital'):
        method = "How gas is used: Gas heats the building, but patient areas must maintain temperature regardless of census. ASHRAE 170 requirements mandate this."
        data_used = "Data used: Actual gas consumption from city benchmarking, healthcare-specific HVAC percentage, and conservative savings limited to non-clinical zones."
        source = f"Sources: Consumption from {city} benchmarking disclosure. HVAC percentage from CBECS 2018 for healthcare. Temperature requirements from ASHRAE 170."
        justification = "Why savings are limited: Healthcare requirements come first. We limit savings to non-clinical zones only—lobbies, offices, cafeterias, conference rooms—where occupancy-based control is safe."

    elif bldg_type == 'Residential Care':
        method = "How gas is used: Gas heats the building, including resident rooms and common areas. Care requirements affect what can be controlled."
        data_used = "Data used: Actual gas consumption from city benchmarking, senior housing HVAC percentage, and occupancy patterns limited to controllable zones."
        source = f"Sources: Consumption from {city} benchmarking disclosure. Occupancy from NIC MAP Vision using {city}-area market data. HVAC percentage from CBECS 2018."
        justification = "Why savings are possible: Common areas and administrative spaces can use occupancy-based control while resident rooms maintain required levels."

    elif bldg_type == 'Restaurant/Bar':
        method = "How gas is used: Restaurants use gas primarily for cooking. CBECS shows only about 18% goes to space heating while 72% goes to cooking. Kitchen exhaust hoods require constant makeup air that must be heated."
        data_used = "Data used: Actual gas consumption from city benchmarking, restaurant-specific gas breakdown (cooking vs. HVAC), and meal-time patterns."
        source = f"Sources: Consumption from {city} benchmarking disclosure. Gas breakdown from CBECS 2018 showing restaurant-specific end uses."
        justification = "Why savings are limited: ODCV savings are limited to the small HVAC portion because most gas use is cooking, not conditioning. Kitchen makeup air cannot be demand-controlled."

    elif bldg_type in ('Retail', 'Retail Store'):
        method = "How gas is used: Gas heats the sales floor. CBECS shows about 78% of retail gas goes to HVAC."
        data_used = "Data used: Actual gas consumption from city benchmarking, retail HVAC percentage, and foot traffic patterns."
        source = f"Sources: Consumption from {city} benchmarking disclosure. Traffic patterns from retail studies. HVAC percentage from CBECS 2018 for retail."
        justification = "Why savings are possible: The reduction reflects not heating at full capacity during slow traffic periods. Traffic patterns are predictable—weekday mornings are much slower than weekends."

    elif bldg_type == 'Supermarket':
        method = "How gas is used: Gas heats the building and makeup air for refrigeration exhaust. Refrigeration creates baseline heating demand that cannot be avoided."
        data_used = "Data used: Actual gas consumption from city benchmarking, HVAC vs. refrigeration breakdown, and customer traffic patterns."
        source = f"Sources: Consumption from {city} benchmarking disclosure. HVAC/refrigeration breakdown from CBECS 2018."
        justification = "Why savings are limited: The reduction reflects slower traffic periods, but refrigeration exhaust requires constant makeup air regardless of customer count."

    else:
        method = "How gas is used: Gas heats the building and the outdoor air that ventilation brings in. Every cubic foot of cold outside air must be heated in winter."
        data_used = "Data used: Actual gas consumption from city benchmarking and HVAC percentage for this building type."
        source = f"Sources: Consumption from {city} benchmarking disclosure. HVAC percentage from CBECS 2018."
        justification = "Why savings are possible: When you reduce ventilation to empty spaces, you heat less air. The reduction reflects not heating air for people who are not there."

    return f"{meaning}\n\n{method}\n\n{data_used}\n\n{source}\n\n{justification}"

def get_fuel_oil_tooltip(row):
    """ROW tooltip for fuel oil consumption - explains method, data source, justification.

    Structure: MEANING → METHOD → DATA USED → SOURCE → JUSTIFICATION
    """
    bldg_type = safe_val(row, 'bldg_type', '')
    city = safe_val(row, 'loc_city', '')

    # MEANING (same for all)
    meaning = "What this represents: The fuel oil consumption row shows current usage, projected usage after ODCV, and the reduction in gallons per year."

    # METHOD (same for all)
    method = "How fuel oil is used: Fuel oil heats the building, typically in older buildings or areas without natural gas service. Nearly all fuel oil goes to space heating."

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        data_used = "Data used: Actual fuel oil consumption from city benchmarking, HVAC percentage (nearly 100% for fuel oil), vacancy rate for this market, and office attendance patterns."
        source = f"Sources: Consumption from {city} benchmarking disclosure. Vacancy from CBRE using {city} market data. Utilization from Kastle badge swipes. HVAC percentage from CBECS 2018."
        justification = "Why this matters: The reduction comes from not heating air for empty floors. Fuel oil produces more carbon per unit of heat than natural gas, so reducing it has outsized emissions impact for BPS compliance."

    elif bldg_type in ('K-12 School', 'Higher Ed'):
        data_used = "Data used: Actual fuel oil consumption from city benchmarking, educational building HVAC percentage, and school calendar patterns."
        source = f"Sources: Consumption from {city} benchmarking disclosure. Schedule data from NCES. HVAC percentage from CBECS 2018."
        justification = "Why savings are possible: Schools with oil heat often run boilers year-round at some level. The reduction comes from aligning heating with the school calendar—summers, weekends, afternoons, and holidays when buildings sit empty."

    else:
        data_used = "Data used: Actual fuel oil consumption from city benchmarking and HVAC percentage (nearly 100% for fuel oil since it's used almost exclusively for heating)."
        source = f"Sources: Consumption from {city} benchmarking disclosure. HVAC percentage from CBECS 2018."
        justification = "Why this matters: The reduction reflects not heating air for empty spaces. Fuel oil produces more carbon per unit of heat than natural gas, so reducing it has outsized emissions impact."

    return f"{meaning}\n\n{method}\n\n{data_used}\n\n{source}\n\n{justification}"

def get_district_steam_tooltip(row):
    """ROW tooltip for district steam consumption - explains method, data source, justification.

    Structure: MEANING → METHOD → DATA USED → SOURCE → JUSTIFICATION
    """
    city = safe_val(row, 'loc_city', '')
    bldg_type = safe_val(row, 'bldg_type', '')

    # MEANING (same for all)
    meaning = "What this represents: The district steam consumption row shows current usage, projected usage after ODCV, and the reduction in MMBtu per year."

    if 'New York' in city or city == 'NYC':
        method = "How steam is used: Con Edison operates one of the world's largest district steam systems, piping steam directly to Manhattan buildings for heating. Steam replaces on-site boilers—the building receives heat without burning fuel locally."

        if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
            data_used = "Data used: Actual steam consumption from NYC LL84 benchmarking (this is real utility data from Con Edison, not an estimate), HVAC percentage for steam (nearly all goes to space heating), vacancy rate for NYC, and office attendance patterns."
            source = "Sources: Consumption from NYC LL84 benchmarking disclosure. Vacancy from CBRE using NYC market data. Utilization from Kastle Systems badge swipes. HVAC percentage from CBECS 2018. Steam emission factors from NYC Local Law 97."
            justification = "Why this matters: The reduction comes from not heating air for empty floors. For LL97 compliance, steam has its own emission factor set by NYC—different from electricity and gas. Reducing steam consumption directly reduces carbon penalties."
        else:
            data_used = "Data used: Actual steam consumption from NYC LL84 benchmarking (real Con Edison utility data), HVAC percentage for steam, and occupancy patterns for this building type."
            source = "Sources: Consumption from NYC LL84 benchmarking disclosure. HVAC percentage from CBECS 2018. Steam emission factors from NYC Local Law 97."
            justification = "Why this matters: The reduction comes from cutting ventilation heating to unoccupied spaces. For LL97 compliance, steam has its own emission factor. Reducing consumption directly reduces carbon penalties."

    else:
        method = "How steam is used: District steam from a central plant heats this building. Steam replaces on-site boilers—the building receives heat without burning fuel locally."
        data_used = "Data used: Actual steam consumption from city benchmarking disclosure and HVAC percentage for steam (nearly all goes to space heating)."
        source = f"Sources: Consumption from {city} benchmarking disclosure. HVAC percentage from CBECS 2018."
        justification = "Why savings are possible: The reduction comes from cutting ventilation heating to unoccupied spaces. Less air to heat means less steam required."

    return f"{meaning}\n\n{method}\n\n{data_used}\n\n{source}\n\n{justification}"

def get_site_eui_tooltip(row):
    """EUI tooltip - explains method, data source, justification by building type.

    Structure: MEANING → METHOD → DATA USED → SOURCE → JUSTIFICATION
    """
    city = safe_val(row, 'loc_city', '')
    bldg_type = safe_val(row, 'bldg_type', '')

    # MEANING (same for all types)
    meaning = "What this represents: Site Energy Use Intensity—total energy consumption normalized by building size, measured in kBtu per square foot per year."

    # METHOD (same for all types)
    method = "How it's calculated: Total site energy (electricity kWh × 3.412 + gas therms × 100 + steam MMBtu × 1000 + fuel oil gallons × 138.5) divided by gross floor area."

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        data_used = "Data used: This building's actual electricity, gas, steam, and fuel oil consumption from city benchmarking disclosure, plus building square footage."
        source = f"Sources: All energy data from {city} benchmarking disclosure—this is real metered consumption, not an estimate. Building area from the same disclosure."
        justification = "Why this matters: When you stop conditioning empty floors and underutilized workspaces, EUI drops. This metric matters for Energy Star certification, tenant perception, and BPS compliance where EUI-based targets apply (Denver, St. Louis)."

    elif bldg_type in ('K-12 School', 'Higher Ed'):
        data_used = "Data used: This school's actual electricity and gas consumption from city benchmarking disclosure, plus building square footage."
        source = f"Sources: All energy data from {city} benchmarking disclosure. Building area from the same disclosure."
        justification = "Why this matters: Schools often have high EUI despite limited operating hours because HVAC runs continuously on timers. Matching ventilation to actual school hours dramatically improves this efficiency metric."

    elif bldg_type == 'Hotel':
        data_used = "Data used: This hotel's actual electricity, gas, and any steam consumption from city benchmarking disclosure, plus building square footage."
        source = f"Sources: All energy data from {city} benchmarking disclosure. Building area from the same disclosure."
        justification = "Why this matters: Hotels have unusual EUI patterns—high base load from 24/7 common areas but variable load from guest rooms. Room-level occupancy control can significantly improve this efficiency metric."

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital'):
        data_used = "Data used: This hospital's actual electricity, gas, and any steam consumption from city benchmarking disclosure, plus building square footage."
        source = f"Sources: All energy data from {city} benchmarking disclosure. Building area from the same disclosure."
        justification = "Why this matters: Healthcare buildings have inherently high EUI due to ventilation requirements. Improvements come only from non-clinical areas. Do not compare hospital EUI to other building types—they have fundamentally different requirements."

    elif bldg_type == 'Supermarket':
        data_used = "Data used: This supermarket's actual electricity and gas consumption from city benchmarking disclosure, plus building square footage."
        source = f"Sources: All energy data from {city} benchmarking disclosure. Building area from the same disclosure."
        justification = "Why this matters: Supermarket EUI is high due to refrigeration. Improvements in space conditioning reduce EUI, but refrigeration creates a baseline that cannot be reduced through occupancy-based control. Compare only to other supermarkets."

    elif bldg_type == 'Restaurant/Bar':
        data_used = "Data used: This restaurant's actual electricity and gas consumption from city benchmarking disclosure, plus building square footage."
        source = f"Sources: All energy data from {city} benchmarking disclosure. Building area from the same disclosure."
        justification = "Why this matters: Restaurant EUI is high because most energy goes to cooking and kitchen exhaust. The controllable HVAC portion is small. Compare only to other restaurants—they have fundamentally different loads than offices."

    elif bldg_type in ('Retail', 'Retail Store', 'Wholesale Club'):
        data_used = "Data used: This store's actual electricity and gas consumption from city benchmarking disclosure, plus building square footage."
        source = f"Sources: All energy data from {city} benchmarking disclosure. Building area from the same disclosure."
        justification = "Why this matters: When you match conditioning to traffic instead of running at peak capacity all day, EUI drops. Lower EUI signals efficiency and can affect operating costs and property value."

    else:
        data_used = "Data used: This building's actual electricity, gas, and any steam or fuel oil consumption from city benchmarking disclosure, plus building square footage."
        source = f"Sources: All energy data from {city} benchmarking disclosure—this is real metered consumption, not an estimate."
        justification = "Why this matters: When you stop conditioning empty spaces, the building uses less energy per square foot. Lower EUI signals better efficiency to tenants, investors, and regulators."

    return f"{meaning}\n\n{method}\n\n{data_used}\n\n{source}\n\n{justification}"

def get_hvac_pct_tooltip(row):
    """HVAC percentage tooltip - explains method, data source, justification.

    Structure: MEANING → METHOD → DATA USED → SOURCE → JUSTIFICATION
    """
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')

    # MEANING (same for all)
    meaning = "What this represents: The percentage of this building's energy consumption that goes to heating, cooling, and ventilation—the portion that ODCV can reduce."

    if bldg_type == 'Hotel':
        method = "How it's determined: Hotels have a unique energy breakdown. Electricity mostly goes to HVAC (fans, chillers, room units). But gas splits three ways—only about 20% goes to space heating, while 42% goes to domestic hot water and 33% to cooking."
        data_used = "Data used: Building-type-specific HVAC percentages by fuel type, adjusted for this building's efficiency rating."
        source = "Sources: HVAC percentages from CBECS 2018 hotel-specific tables. Adjustments based on building age and Energy Star score."
        justification = "Why this matters: Only the HVAC portion responds to occupancy. Hot water and cooking demand don't change based on room occupancy—guests still shower and restaurants still cook. We are explicit about this split to avoid overstating savings."

    elif bldg_type == 'Restaurant/Bar':
        method = "How it's determined: Restaurants have a unique energy breakdown. Gas primarily goes to cooking—CBECS shows only about 18% goes to space heating while 72% goes to cooking. Kitchen exhaust requires constant makeup air."
        data_used = "Data used: Restaurant-specific HVAC percentages by fuel type."
        source = "Sources: HVAC percentages from CBECS 2018 restaurant-specific tables."
        justification = "Why this matters: Only the small HVAC portion is controllable. Kitchen exhaust and makeup air cannot be demand-controlled. We apply savings only to the dining area conditioning portion."

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital'):
        method = "How it's determined: Hospitals have high HVAC percentages due to ventilation requirements, but much of that cannot be reduced due to ASHRAE 170 infection control mandates."
        data_used = "Data used: Healthcare-specific HVAC percentages by fuel type."
        source = "Sources: HVAC percentages from CBECS 2018 healthcare tables. Ventilation requirements from ASHRAE 170."
        justification = "Why this matters: Patient care areas must maintain minimum air changes regardless of census. The HVAC percentage is high, but the controllable portion is limited to non-clinical spaces."

    elif bldg_type == 'Supermarket':
        method = "How it's determined: Supermarkets have significant electricity going to refrigeration, which is separate from HVAC. We isolate space conditioning from refrigeration loads."
        data_used = "Data used: Grocery-specific HVAC and refrigeration percentages by fuel type."
        source = "Sources: HVAC/refrigeration breakdown from CBECS 2018 grocery-specific tables."
        justification = "Why this matters: Refrigeration runs continuously regardless of customer traffic—that cannot change. We apply savings only to the space conditioning portion."

    elif bldg_type in ('K-12 School', 'Higher Ed'):
        method = "How it's determined: Educational buildings have high HVAC percentages—CBECS shows about 80% of school gas goes to HVAC because schools don't have the hot water and cooking loads of hotels."
        data_used = "Data used: Educational building HVAC percentages by fuel type."
        source = "Sources: HVAC percentages from CBECS 2018 educational building tables."
        justification = "Why this matters: The high HVAC percentage means most energy consumption is controllable through schedule-based optimization. Calendar alignment captures a large share of total building energy."

    elif bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        method = "How it's determined: Office buildings have high HVAC percentages—CBECS shows nearly 88% of office gas goes to space heating, and a large share of electricity goes to fans, chillers, and pumps."
        data_used = "Data used: Office building HVAC percentages by fuel type, adjusted for this building's efficiency rating."
        source = "Sources: HVAC percentages from CBECS 2018 office tables. Adjustments based on building age and Energy Star score."
        justification = "Why this matters: The high HVAC percentage means occupancy-based control affects a large share of total building energy. The rest goes to lighting, plug loads, and equipment unaffected by ventilation control."

    else:
        method = "How it's determined: The HVAC percentage varies by building type and fuel. It represents the share of energy going to heating, cooling, and ventilation versus lighting, plug loads, and other uses."
        data_used = "Data used: Building-type-specific HVAC percentages by fuel type."
        source = "Sources: HVAC percentages from CBECS 2018, adjusted for building type and efficiency."
        justification = "Why this matters: Only the HVAC portion responds to occupancy-based control. The rest goes to lighting, plug loads, and equipment that are not affected by ventilation changes."

    return f"{meaning}\n\n{method}\n\n{data_used}\n\n{source}\n\n{justification}"

def get_size_tooltip(row):
    """Size tooltip - explains method, data source, justification."""
    return "Square footage from city benchmarking disclosure filings. Size affects both the opportunity and system sophistication. Larger buildings have more zones to optimize. Bigger buildings typically have more advanced controls. Size also determines BPS applicability. Most laws only cover buildings above 20,000 to 50,000 sqft thresholds."

def get_year_built_tooltip(row):
    """Year built tooltip - explains method, data source, justification."""
    return "Building age indicates control system sophistication. Pre-1970 buildings typically have pneumatic controls that cannot easily implement occupancy-based adjustments. Buildings from the 1970s and 80s have early electronic controls with limited flexibility. The 1990s and 2000s saw digital controls become standard. Buildings from 2010 and later usually have modern BMS systems ready for smart ventilation control. Older buildings can still benefit but may need control upgrades first."

def get_utility_tooltip(row):
    """Utility tooltip - explains how we convert energy usage into energy costs.

    Structure: MEANING → METHOD → DATA USED → SOURCE → JUSTIFICATION
    """
    utility = safe_val(row, 'cost_utility_name', '')
    city = safe_val(row, 'loc_city', '')
    rate = safe_num(row, 'cost_elec_rate_kwh')

    meaning = "What this represents: How we convert this building's energy consumption into annual energy costs, using the actual utility rates for this specific ZIP code."

    method = """How electricity costs are calculated: Commercial electricity bills have two components.

Energy charges: Annual kWh × energy rate × 1.10 multiplier. The 1.10 accounts for distribution charges, transmission charges, taxes, and surcharges that appear on real utility bills beyond the base commodity rate.

Demand charges: Peak kW × demand rate × 12 months × 1.265 multiplier. Peak demand is estimated as annual kWh ÷ (8,760 hours × load factor). The 1.265 accounts for demand ratchet clauses (utilities bill minimum 60-80% of your annual peak), seasonal rate differentials (summer rates 20-40% higher), and power factor penalties.

How gas costs are calculated: Therms (kBtu ÷ 100) × rate × 1.10 multiplier.

How steam costs are calculated: Mlb (kBtu ÷ 909) × rate. No multiplier—steam rates are typically all-inclusive.

How fuel oil costs are calculated: MMBtu (kBtu ÷ 1000) × rate × 1.10 multiplier."""

    if utility:
        data_used = f"Data used: This building's metered consumption from city benchmarking. Electricity rate specific to this ZIP code from {utility} commercial tariff schedules. Gas rate specific to this ZIP code. Load factor assigned by building type (offices typically 0.40-0.50, hospitals 0.60-0.70, data centers 0.70-0.85)."
    else:
        data_used = "Data used: This building's metered consumption from city benchmarking. Electricity and gas rates specific to this ZIP code from local utility tariff schedules. Load factor assigned by building type."

    source = f"Sources: Energy consumption from {city} benchmarking disclosure. Electricity and gas rates from NREL Utility Rate Database, looked up by this building's ZIP code. We use ZIP-specific rates because electricity prices vary nearly 5x across the country ($0.11/kWh in cheap markets to $0.52/kWh in expensive ones) and gas varies 10x ($0.23 to $2.42/therm). Using national averages would badly misrepresent costs."

    justification = "Why this matters: A building in San Francisco pays completely different utility rates than one in Atlanta. We pull the actual rate for each ZIP code so the cost calculations reflect what this building actually pays—not a national average that could be off by 3-4x."

    return f"{meaning}\n\n{method}\n\n{data_used}\n\n{source}\n\n{justification}"

def get_total_ghg_tooltip(row):
    """Total GHG tooltip - explains method, data source, justification by grid type.

    Structure: MEANING → METHOD → DATA USED → SOURCE → JUSTIFICATION
    """
    city = safe_val(row, 'loc_city', '')
    bldg_type = safe_val(row, 'bldg_type', '')

    # MEANING (same for all)
    meaning = "What this represents: This building's total greenhouse gas emissions in metric tons of CO2 equivalent per year."

    # METHOD (same for all)
    method = "How it's calculated: Electricity consumption × grid emission factor + gas consumption × combustion factor + any steam or fuel oil × their respective factors."

    # Clean grid cities
    if city in ('Seattle', 'Portland', 'San Francisco', 'Los Angeles', 'San Diego'):
        data_used = "Data used: This building's actual electricity, gas, and any steam or fuel oil consumption from city benchmarking disclosure."
        source = f"Sources: Energy data from {city} benchmarking disclosure. Emission factors from EPA eGRID 2023 for this region's electric grid—not national averages. This region uses hydro and renewables, so electricity has low carbon intensity."
        justification = f"Regional context: Because {city}'s grid is relatively clean, most of this building's emissions come from burning natural gas for heating, not electricity. Cutting gas consumption has the biggest emissions impact in this region."

    # Dirty grid cities
    elif city in ('Chicago', 'St. Louis', 'Denver'):
        data_used = "Data used: This building's actual electricity, gas, and any steam or fuel oil consumption from city benchmarking disclosure."
        source = f"Sources: Energy data from {city} benchmarking disclosure. Emission factors from EPA eGRID 2023 for this region's electric grid. This region relies heavily on coal and natural gas generation."
        justification = f"Regional context: {city}'s grid has high carbon intensity—significantly higher than coastal cities. Every kWh saved here prevents more emissions than in cleaner-grid regions. Both electricity and gas reductions contribute meaningfully."

    # NYC with steam
    elif city in ('New York', 'NYC', 'Manhattan'):
        data_used = "Data used: This building's actual electricity, gas, and Con Edison steam consumption from city benchmarking disclosure."
        source = "Sources: Energy data from NYC LL84 benchmarking disclosure. Emission factors from NYC Local Law 97—these are the legally binding coefficients, including specific factors for Con Edison's district steam network."
        justification = "Regional context: NYC has its own emission factors set by law for LL97 compliance. The steam factor is specific to Con Edison's Manhattan district system. These are the exact factors the city uses to calculate BPS penalties."

    # Boston area
    elif city in ('Boston', 'Cambridge'):
        data_used = "Data used: This building's actual electricity, gas, and any steam consumption from city benchmarking disclosure."
        source = f"Sources: Energy data from {city} benchmarking disclosure. Emission factors from EPA eGRID 2023 for the New England grid region—cleaner than the national average due to nuclear and renewables."
        justification = "Regional context: The New England grid has moderate carbon intensity. Both electricity and gas reductions contribute to emissions reduction. For BPS compliance, these factors determine whether the building exceeds its carbon cap."

    else:
        data_used = "Data used: This building's actual electricity, gas, and any steam or fuel oil consumption from city benchmarking disclosure."
        source = f"Sources: Energy data from {city} benchmarking disclosure. Emission factors from EPA eGRID 2023 for this region's electric grid plus EIA standard combustion factors for gas."
        justification = "Regional context: Grid carbon intensity varies significantly by region. We use the specific factors for the electric grid serving this location—not national averages."

    return f"{meaning}\n\n{method}\n\n{data_used}\n\n{source}\n\n{justification}"

def get_carbon_reduction_tooltip(row):
    """Carbon reduction tooltip - explains method, data source, justification by grid type.

    Structure: MEANING → METHOD → DATA USED → SOURCE → JUSTIFICATION
    """
    city = safe_val(row, 'loc_city', '')
    bldg_type = safe_val(row, 'bldg_type', '')

    # MEANING (same for all)
    meaning = "What this represents: The reduction in greenhouse gas emissions from implementing ODCV, in metric tons of CO2 equivalent per year."

    # METHOD (same for all)
    method = "How it's calculated: Current emissions minus projected emissions. The reduction reflects energy savings by fuel type, each multiplied by its respective emission factor."

    # Clean grid cities
    if city in ('Seattle', 'Portland', 'San Francisco', 'Los Angeles', 'San Diego'):
        data_used = "Data used: This building's projected electricity and gas savings, each multiplied by the appropriate emission factor for this region."
        source = f"Sources: Emission factors from EPA eGRID 2023 specific to {city}'s electric grid—not national averages. This region has relatively clean electricity from hydro and renewables."
        justification = f"Regional context: Because {city}'s grid is clean, most emissions come from burning natural gas. Cutting gas consumption through reduced ventilation heating has the biggest emissions impact here. Electricity savings have smaller carbon impact in this region."

    # Dirty grid cities
    elif city in ('Chicago', 'St. Louis', 'Denver'):
        data_used = "Data used: This building's projected electricity and gas savings, each multiplied by the appropriate emission factor for this region."
        source = f"Sources: Emission factors from EPA eGRID 2023 specific to {city}'s electric grid. This region relies heavily on coal and natural gas generation, giving electricity high carbon intensity."
        justification = f"Regional context: {city}'s grid has high carbon intensity—much higher than the West Coast. Every kWh saved here prevents more emissions than in cleaner-grid cities. Both electricity and gas reductions have meaningful carbon impact."

    # NYC with steam
    elif city in ('New York', 'NYC', 'Manhattan'):
        data_used = "Data used: This building's projected electricity, gas, and steam savings, each multiplied by NYC's official LL97 emission factors."
        source = "Sources: Emission factors from NYC Local Law 97—these are the exact same factors the city uses to calculate BPS penalties. They include specific values for electricity, gas, and Con Edison steam."
        justification = "Regional context: The reduction uses the legally binding methodology, not our own assumptions. Steam from Con Edison's district system has its own emission factor. This is the carbon reduction NYC will recognize for LL97 compliance."

    # Boston area
    elif city in ('Boston', 'Cambridge'):
        data_used = "Data used: This building's projected electricity and gas savings, each multiplied by the appropriate emission factor for the New England grid."
        source = f"Sources: Emission factors from EPA eGRID 2023 for the New England grid region. This grid is cleaner than the national average due to nuclear and renewables."
        justification = "Regional context: Both electricity and gas reductions contribute to carbon reduction in this region. For BERDO/BEUDO compliance, this reduction determines whether the building meets its carbon cap."

    else:
        data_used = "Data used: This building's projected electricity and gas savings, each multiplied by the appropriate emission factor for this region."
        source = f"Sources: Emission factors from EPA eGRID 2023 for {city}'s regional electric grid. This is published data on actual power plant emissions in this area, not national averages."
        justification = "Regional context: The reduction reflects tons of CO2 avoided based on this building's specific fuel mix and local grid carbon intensity. Grid factors vary significantly by region."

    return f"{meaning}\n\n{method}\n\n{data_used}\n\n{source}\n\n{justification}"

def get_fine_avoidance_tooltip(row):
    """Fine avoidance tooltip - explains method, data source, justification by city/law.

    Structure: MEANING → METHOD → DATA USED → SOURCE → JUSTIFICATION
    """
    city = safe_val(row, 'loc_city', '')
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')

    # NYC Local Law 97
    if city in ('New York', 'NYC', 'Manhattan'):
        meaning = "What this represents: The Building Performance Standard penalty this building avoids by reducing carbon emissions below the legal cap."
        method = "How it's calculated: We calculate current emissions from metered energy, compare to the carbon cap for this building type, determine the penalty for excess tons, then calculate post-ODCV emissions and compare. The difference is avoided fines."
        data_used = "Data used: This building's electricity, gas, and steam consumption converted to carbon using NYC's official coefficients. The carbon cap is set by building type and applies per square foot."
        source = "Sources: Emission factors from NYC Department of Buildings Local Law 97 regulations—these are the legally binding coefficients for electricity, gas, and Con Edison steam, not our estimates. Penalty rates set by city law for the 2024-2029 compliance period."
        justification = "Why this works: LL97 is real law with real fines. The calculation uses the exact same methodology the city will use to assess penalties. Reducing energy reduces emissions reduces fines. The emission factors are NYC-specific—steam has its own coefficient for the Con Edison district system."

    # Boston BERDO
    elif city == 'Boston':
        meaning = "What this represents: The Building Performance Standard penalty this building avoids by reducing carbon emissions below the BERDO 2.0 cap."
        method = "How it's calculated: We calculate current emissions from metered energy using regional grid factors, compare to Boston's carbon cap for this building type, then calculate how ODCV reduction affects the penalty."
        data_used = "Data used: This building's electricity and gas consumption converted to carbon. The carbon cap is set by building type and compliance period."
        source = "Sources: Emission factors from EPA eGRID for the New England grid region—not national averages. Caps and penalty rates from Boston Environment Department BERDO 2.0 regulations."
        justification = "Why this works: BERDO 2.0 sets carbon caps that tighten over time. Buildings exceeding the cap pay per excess ton as an alternative compliance payment. The New England grid is cleaner than many regions, so Boston's electricity has lower carbon intensity than Midwest cities."

    # Cambridge BEUDO
    elif city == 'Cambridge':
        meaning = "What this represents: The penalty this building avoids by meeting Cambridge's building-specific emissions reduction requirement."
        method = "How it's calculated: Unlike fixed caps, BEUDO requires each building to cut emissions a percentage from its own baseline. We calculate this building's baseline emissions, apply the reduction target, and determine penalties for any shortfall after ODCV implementation."
        data_used = "Data used: This building's baseline energy consumption establishing its individual target, plus current consumption converted to carbon."
        source = "Sources: Emission factors from EPA eGRID for the New England grid region. Reduction targets and penalty rates from Cambridge BEUDO regulations."
        justification = "Why this works: BEUDO's building-specific approach means each property has its own reduction requirement based on where it started. This is fairer to already-efficient buildings but means every building has a compliance obligation. The target is this building's specific requirement, not a generic benchmark."

    # DC BEPS
    elif city in ('Washington', 'Washington DC', 'DC'):
        meaning = "What this represents: The penalty this building avoids by meeting DC's Energy Star score target."
        method = "How it's calculated: DC BEPS uses Energy Star score targets instead of carbon caps. We calculate how much ODCV improves this building's score based on EPA's methodology, then determine if it meets the threshold for this building type."
        if bldg_type == 'Hotel':
            data_used = "Data used: This hotel's current Energy Star score and projected improvement from reduced energy consumption. Hotels have a specific target different from offices."
        elif bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
            data_used = "Data used: This office building's current Energy Star score and projected improvement from reduced energy consumption. Offices have a specific target."
        else:
            data_used = "Data used: This building's current Energy Star score and projected improvement from reduced energy consumption. The target varies by building type."
        source = "Sources: Energy Star score targets from DC's Clean Energy DC Building Code—these are the actual thresholds by building type. Penalty rates from DC DOEE regulations."
        justification = "Why this works: DC chose Energy Star scores instead of carbon caps because they normalize for weather and building type. Meeting the score threshold means the building is performing at or above the target percentile for its peer group."

    # Seattle BEPS
    elif city == 'Seattle':
        meaning = "What this represents: The Building Performance Standard penalty this building avoids by reducing carbon intensity below Seattle's cap."
        method = "How it's calculated: We calculate current emissions using Seattle-specific grid factors, compare to the carbon intensity cap for this building type, then determine avoided penalties from ODCV-driven reduction."
        data_used = "Data used: This building's electricity and gas consumption converted to carbon using regional factors. Seattle's grid is 98% hydroelectric—one of the cleanest in the country."
        source = "Sources: Emission factors from EPA eGRID for the Northwest Power Pool region—these are much lower than national average for electricity because Seattle's grid is almost entirely hydro. Penalty rates from Seattle Office of Sustainability BEPS regulations."
        justification = "Why this works: Because Seattle's grid is so clean, the emissions math is different than NYC or Boston. Most of this building's carbon footprint comes from burning natural gas for heating, not electricity. Cutting gas consumption through reduced ventilation heating has the biggest emissions impact in this region."

    # Denver Energize Denver
    elif city == 'Denver':
        meaning = "What this represents: The penalty this building avoids by meeting Denver's EUI target for its building type."
        method = "How it's calculated: Energize Denver sets EUI (energy use intensity) targets by building type with a glide path to 2032 goals. We calculate current EUI from benchmarking data, compare to the interim target, and determine penalties for overages."
        data_used = "Data used: This building's actual Site EUI from benchmarking disclosure compared to the target for this building type and compliance period."
        source = "Sources: EUI targets and penalty rates from Denver's Office of Climate Action Energize Denver regulations. Targets are building-type-specific and tighten over time."
        justification = "Why this works: Denver chose EUI targets because they directly measure energy efficiency regardless of fuel mix. Meeting the target means the building uses energy at or below the threshold for its type. The glide path gives buildings time to improve but requires steady progress."

    # St. Louis BEPS
    elif city == 'St. Louis':
        meaning = "What this represents: The penalty this building avoids by meeting St. Louis's EUI target for its building type."
        method = "How it's calculated: St. Louis BEPS sets EUI targets roughly at the 35th percentile for local buildings of each type. We calculate whether this building's energy reduction brings it under the target."
        data_used = "Data used: This building's actual Site EUI from benchmarking disclosure compared to the local target for this building type."
        source = "Sources: EUI targets from St. Louis BEPS regulations based on local building stock. Penalty structure from city ordinance."
        justification = "Why this works: The 35th percentile target means buildings need to be better than roughly two-thirds of their local peers. This is achievable for most buildings with efficiency improvements but requires action from the worst performers."

    else:
        meaning = "What this represents: This building is not currently in a city with Building Performance Standard fines."
        method = "How it applies: No BPS law currently covers this building, so there are no fines to avoid."
        data_used = "Data used: We checked this building's city against the seven major BPS jurisdictions (NYC, Boston, Cambridge, DC, Seattle, Denver, St. Louis)."
        source = "Sources: Current BPS law coverage as of 2025. Many additional cities are considering or passing BPS laws."
        justification = "Why this matters: While no fines apply today, many cities are adopting these laws. Reducing energy consumption now builds a track record, demonstrates leadership, and avoids scrambling when regulations arrive in this market."

    return f"{meaning}\n\n{method}\n\n{data_used}\n\n{source}\n\n{justification}"


def get_utility_cost_savings_tooltip(row):
    """Utility cost savings tooltip - explains method, data source, justification by building type.

    Structure: MEANING → METHOD → DATA USED → SOURCE → JUSTIFICATION
    """
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    city = safe_val(row, 'loc_city', '')

    # MEANING (same for all types)
    meaning = "What this represents: Annual dollar savings from reducing HVAC energy waste by matching ventilation to actual occupancy."

    if bldg_type in ('Office', 'Medical Office', 'Mixed Use'):
        method = "How it's calculated: We isolate the HVAC portion of energy costs using CBECS building-type breakdowns, then apply the savings percentage based on this market's vacancy rate and utilization patterns."
        data_used = "Data used: This building's actual energy consumption from city benchmarking disclosure, utility rates for this ZIP code, HVAC percentage by fuel type, vacancy rate for this market, and office attendance patterns."
        source = f"Sources: Energy data from {city} benchmarking disclosure. Utility rates from NREL database. Vacancy data from CBRE and Cushman & Wakefield quarterly reports, using {city} market data. Utilization from Kastle Systems badge swipe tracking. HVAC percentages from CBECS 2018."
        justification = "Why this works: Office HVAC is centralized—landlords condition vacant floors and underutilized occupied floors the same as full ones. The vacancy and utilization data are measured, not assumed. This is what buildings like this one actually experience."

    elif bldg_type == 'K-12 School':
        method = "How it's calculated: We isolate the HVAC portion of energy costs, then apply the savings percentage based on how much of the year the building sits empty while systems run."
        data_used = "Data used: This school's actual energy consumption from city benchmarking disclosure, utility rates for this ZIP code, HVAC percentage by fuel type, and school calendar patterns."
        source = f"Sources: Energy data from {city} benchmarking disclosure. Utility rates from NREL database. Schedule data from NCES (National Center for Education Statistics). HVAC percentages from CBECS 2018 for educational buildings."
        justification = "Why this works: Schools don't have vacancy like offices—they have schedule-driven emptiness. Buildings sit empty summers, weekends, afternoons, and holidays, but HVAC often runs on legacy timers. The gap between designed capacity and actual student presence is the opportunity."

    elif bldg_type == 'Higher Ed':
        method = "How it's calculated: We isolate the HVAC portion of energy costs, then apply savings based on academic calendar gaps and daily classroom utilization patterns."
        data_used = "Data used: This building's actual energy consumption from city benchmarking disclosure, utility rates for this ZIP code, HVAC percentage by fuel type, and academic calendar patterns."
        source = f"Sources: Energy data from {city} benchmarking disclosure. Utility rates from NREL database. Academic scheduling data from NCES. HVAC percentages from CBECS 2018 for educational buildings."
        justification = "Why this works: Universities have calendar gaps like K-12 (summer, winter, spring breaks) plus daily variability. A lecture hall might be packed three days a week and empty the rest. Academic schedules are documented and predictable."

    elif bldg_type == 'Hotel':
        method = "How it's calculated: We isolate the HVAC portion of energy costs—accounting for the fact that most hotel gas goes to hot water and kitchens, not heating—then apply savings based on room occupancy and guest presence patterns."
        data_used = "Data used: This hotel's actual energy consumption from city benchmarking disclosure, utility rates for this ZIP code, hotel-specific HVAC percentage (which is lower than offices because gas serves hot water and kitchens), and room-night occupancy for this market."
        source = f"Sources: Energy data from {city} benchmarking disclosure. Utility rates from NREL database. Room occupancy from STR Global, using {city} market data. STR is the hotel industry's authoritative tracking source. HVAC percentages from CBECS 2018 hotel-specific data."
        justification = "Why this works: Each guest room has its own HVAC running continuously. Waste comes from unsold rooms plus rooms where the guest is out. Even when sold, a room is only occupied about ten hours per day. Room-level sensors enable setback during empty periods."

    elif bldg_type in ('Inpatient Hospital', 'Specialty Hospital'):
        method = "How it's calculated: We isolate the HVAC portion of energy costs, then apply a conservatively capped savings percentage that reflects opportunity only in non-clinical areas."
        data_used = "Data used: This hospital's actual energy consumption from city benchmarking disclosure, utility rates for this ZIP code, healthcare-specific HVAC percentages, and a conservative ceiling on savings."
        source = f"Sources: Energy data from {city} benchmarking disclosure. Utility rates from NREL database. HVAC percentages from CBECS 2018 for healthcare buildings. Occupancy patterns from AHA Hospital Statistics. Savings capped per ASHRAE 170 clinical ventilation requirements."
        justification = "Why this works: Patient care areas must maintain minimum air changes for infection control—we don't touch those. But hospitals are mostly non-clinical space: lobbies, offices, cafeterias, conference rooms. Those areas can use standard occupancy-based control. We apply savings only there."

    elif bldg_type == 'Residential Care':
        method = "How it's calculated: We isolate the HVAC portion of energy costs, then apply a conservatively capped savings percentage reflecting opportunity only in common areas and non-patient spaces."
        data_used = "Data used: This facility's actual energy consumption from city benchmarking disclosure, utility rates for this ZIP code, senior housing HVAC percentages, and occupancy patterns."
        source = f"Sources: Energy data from {city} benchmarking disclosure. Utility rates from NREL database. Occupancy data from NIC MAP Vision, using {city}-area senior housing market data. HVAC percentages from CBECS 2018."
        justification = "Why this works: Residential care has ventilation requirements for patient rooms, but common areas and administrative spaces can use occupancy-based control. We limit savings to those zones for a conservative, defensible estimate."

    elif bldg_type in ('Retail', 'Retail Store'):
        method = "How it's calculated: We isolate the HVAC portion of energy costs, then apply savings based on foot traffic patterns throughout operating hours."
        data_used = "Data used: This store's actual energy consumption from city benchmarking disclosure, utility rates for this ZIP code, retail-specific HVAC percentages, and traffic pattern data."
        source = f"Sources: Energy data from {city} benchmarking disclosure. Utility rates from NREL database. Traffic patterns from retail studies. HVAC percentages from CBECS 2018 for retail buildings."
        justification = "Why this works: Retail doesn't have vacancy—it's owner-occupied. But traffic swings wildly. Stores are packed on weekends but nearly empty on weekday mornings. HVAC runs at the same capacity regardless. Matching ventilation to actual traffic captures the waste."

    elif bldg_type == 'Supermarket':
        method = "How it's calculated: We isolate the HVAC portion of energy costs—excluding refrigeration, which runs continuously regardless of traffic—then apply savings based on customer traffic patterns."
        data_used = "Data used: This supermarket's actual energy consumption from city benchmarking disclosure, utility rates for this ZIP code, grocery-specific HVAC percentage (refrigeration carved out), and traffic patterns."
        source = f"Sources: Energy data from {city} benchmarking disclosure. Utility rates from NREL database. HVAC percentages from CBECS 2018, with refrigeration isolated from space conditioning."
        justification = "Why this works: Supermarkets have unique energy profiles. Refrigeration runs continuously—that can't change. But HVAC conditioning the sales floor can respond to traffic. We isolate the controllable portion and apply savings only there."

    elif bldg_type == 'Wholesale Club':
        method = "How it's calculated: We isolate the HVAC portion of energy costs, then apply savings based on member traffic patterns concentrated on weekends."
        data_used = "Data used: This building's actual energy consumption from city benchmarking disclosure, utility rates for this ZIP code, big-box retail HVAC percentages, and member traffic patterns."
        source = f"Sources: Energy data from {city} benchmarking disclosure. Utility rates from NREL database. Traffic patterns from retail studies. HVAC percentages from CBECS 2018."
        justification = "Why this works: Wholesale clubs have high ceilings and large HVAC loads. Member traffic is predictable and concentrated on weekends. Matching ventilation to traffic patterns during slower periods captures significant waste."

    elif bldg_type == 'Restaurant/Bar':
        method = "How it's calculated: We isolate the small HVAC portion of energy costs—kitchen gas and exhaust are excluded because they can't be demand-controlled—then apply savings based on meal-time patterns."
        data_used = "Data used: This restaurant's actual energy consumption from city benchmarking disclosure, utility rates for this ZIP code, and restaurant-specific HVAC percentage (which is much lower than other building types)."
        source = f"Sources: Energy data from {city} benchmarking disclosure. Utility rates from NREL database. CBECS 2018 shows only about 18% of restaurant gas goes to space heating—the rest is cooking."
        justification = "Why this works: Restaurant savings are limited because kitchen exhaust hoods require constant makeup air that must be heated. We apply savings only to the dining area HVAC portion. The calculation is conservative but accurate to what's actually controllable."

    elif bldg_type in ('Venue', 'Theater'):
        method = "How it's calculated: We isolate the HVAC portion of energy costs, then apply savings based on the gap between event hours and total operating hours."
        data_used = "Data used: This venue's actual energy consumption from city benchmarking disclosure, utility rates for this ZIP code, venue-specific HVAC percentages, and event scheduling patterns."
        source = f"Sources: Energy data from {city} benchmarking disclosure. Utility rates from NREL database. HVAC percentages from CBECS 2018 for entertainment buildings."
        justification = "Why this works: Event venues sit empty most of the time—they're designed for intermittent peak use. Yet HVAC often maintains conditions around the clock. Matching conditioning to actual event schedules captures significant waste."

    elif bldg_type in ('Library/Museum', 'Library', 'Museum'):
        method = "How it's calculated: We isolate the HVAC portion of energy costs, then apply savings based on operating hours and visitor traffic patterns."
        data_used = "Data used: This building's actual energy consumption from city benchmarking disclosure, utility rates for this ZIP code, public building HVAC percentages, and operating hour patterns."
        source = f"Sources: Energy data from {city} benchmarking disclosure. Utility rates from NREL database. HVAC percentages from CBECS 2018 for public buildings."
        justification = "Why this works: Public buildings have fixed operating hours and relatively steady traffic when open. The opportunity comes from hours when closed but systems keep running, plus slower periods during open hours."

    elif bldg_type == 'Outpatient Clinic':
        method = "How it's calculated: We isolate the HVAC portion of energy costs, then apply savings based on appointment schedules and clinic operating hours."
        data_used = "Data used: This clinic's actual energy consumption from city benchmarking disclosure, utility rates for this ZIP code, medical office HVAC percentages, and scheduling patterns."
        source = f"Sources: Energy data from {city} benchmarking disclosure. Utility rates from NREL database. Scheduling patterns from MGMA medical office benchmarks. HVAC percentages from CBECS 2018."
        justification = "Why this works: Outpatient clinics operate on appointment schedules with clear business hours. Unlike hospitals, they don't have 24/7 care or the same strict ventilation codes. Matching ventilation to the appointment schedule and reducing conditioning outside clinic hours captures real waste."

    else:
        method = "How it's calculated: We isolate the HVAC portion of energy costs using building-type-specific percentages, then apply a savings rate based on occupancy patterns for this building type."
        data_used = "Data used: This building's actual energy consumption from city benchmarking disclosure, utility rates for this ZIP code, and HVAC percentages by fuel type."
        source = f"Sources: Energy data from {city} benchmarking disclosure. Utility rates from NREL database. HVAC percentages from CBECS 2018."
        justification = "Why this works: The result reflects dollars currently spent conditioning spaces that sit empty or underutilized. The method is tailored to this building type's specific occupancy patterns."

    return f"{meaning}\n\n{method}\n\n{data_used}\n\n{source}\n\n{justification}"


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
            <a href="../methodology.html#energy" style="display:inline-flex;align-items:center;gap:4px;color:#6b7280;text-decoration:none;font-size:13px;font-weight:500;padding:4px 10px;background:#f3f4f6;border-radius:6px;transition:all 0.2s;" onmouseover="this.style.background='#e5e7eb';this.style.color='#374151'" onmouseout="this.style.background='#f3f4f6';this.style.color='#6b7280'">
                <span>Methodology</span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17l9.2-9.2M17 17V7H7"/></svg>
            </a>
        </h2>
        <table style="margin-bottom:0;">
            <tr>
                <th style="width:35%;"></th>
                <th style="width:22%;">Current{col_tooltip(current_tooltip)}</th>
                <th style="width:22%;">New{col_tooltip(new_tooltip)}</th>
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
            <a href="../methodology.html#opex" style="display:inline-flex;align-items:center;gap:4px;color:#6b7280;text-decoration:none;font-size:13px;font-weight:500;padding:4px 10px;background:#f3f4f6;border-radius:6px;transition:all 0.2s;" onmouseover="this.style.background='#e5e7eb';this.style.color='#374151'" onmouseout="this.style.background='#f3f4f6';this.style.color='#6b7280'">
                <span>Methodology</span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17l9.2-9.2M17 17V7H7"/></svg>
            </a>
        </h2>
        <table style="margin-bottom:0;">
            <tr>
                <th style="width:35%;"></th>
                <th style="width:22%;">Current</th>
                <th style="width:22%;">New</th>
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
