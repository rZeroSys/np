"""
Nationwide Building Report Generator
Simply displays the data we have, no bullshit explanations.
"""

import pandas as pd
import sys
import os
import traceback
import subprocess
import math
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
    eui_df = pd.read_csv('/Users/forrestmiller/Desktop/nationwide-prospector/data/source/eui_post_odcv.csv')
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
    leed_df = pd.read_csv('/Users/forrestmiller/Desktop/nationwide-prospector/data/source/leed_matches.csv')
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
    'Laboratory': {
        'category': 'Constrained',
        'floor': 0.05, 'ceiling': 0.15,
        'uses_vacancy': False,
        'formula': '(1 - Utilization) × 0.3',
        'elec_hvac_typical': 0.50,
        'gas_hvac_typical': 0.825,
        'load_factor': 0.50,
        'demand_rate_typical': 35.0,
        'explanation': 'Labs have limited opportunity due to 24/7 research schedules and specialized equipment.'
    },
    'Data Center': {
        'category': 'N/A',
        'floor': 0.0, 'ceiling': 0.0,
        'uses_vacancy': False,
        'formula': '0 (Not applicable)',
        'elec_hvac_typical': 0.42,
        'gas_hvac_typical': 0.0,
        'load_factor': 0.80,
        'demand_rate_typical': 35.0,
        'explanation': 'Cooling is for equipment heat removal, not people. A data center at 3am with one technician has identical cooling load to 3pm—occupancy is irrelevant.'
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
    'Data Center': {
        'elec_note': "42% of electricity is cooling. No occupancy-driven savings - cooling is for equipment heat.",
        'gas_note': "No natural gas usage for HVAC - cooling is 100% electric.",
        'load_factor_note': "Highest load factor (80%) - servers run 24/7 at near-constant load.",
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
    'Laboratory': {
        'elec_note': "50% of electricity is HVAC. Fume hoods require constant exhaust with makeup air.",
        'gas_note': "82% of gas is HVAC. Lab fume hood makeup air increases heating load significantly.",
        'load_factor_note': "Moderate load factor (50%) - equipment runs 24/7 but some labs have off-hours.",
    },
}

# Default notes for building types not in the dictionary
DEFAULT_ENERGY_NOTES = {
    'elec_note': "Based on EIA CBECS 2018 survey of 6,436 buildings, adjusted for building type and climate.",
    'gas_note': "Based on EIA CBECS 2018 survey of 6,436 buildings, adjusted for building type and climate.",
    'load_factor_note': "Load factor estimated from building type and operating patterns.",
}

#===============================================================================
# BUILDING TYPE STORIES - For Energy section tooltips
# Each story explains WHY this building type has savings potential (or doesn't)
#===============================================================================

BUILDING_TYPE_STORIES = {
    'Office': "We calculate savings using federal CBECS survey data for how much energy goes to HVAC, city-specific office vacancy rates from CBRE, and real occupancy data from Kastle Systems badge swipes. Buildings in cities with lower office attendance (San Francisco at 38%) show higher savings potential than cities with stronger return-to-office (New York at 55%). Adjusted for building age and current efficiency.",

    'Hotel': "Room occupancy (STR data: NYC 87%, national 63%) times guest presence (~45% of the day—the rest they're out at meetings, sightseeing, dining) gives true utilization. A 63%-occupied hotel runs just 28% actual utilization—meaning 72% of ventilation conditions empty rooms. High-occupancy markets like NYC show less savings potential than lower-occupancy markets like Denver or Atlanta.",

    'K-12 School': "Schools operate roughly 180 days per year, 7 hours per day—just 22-28% of annual hours depending on state. We calculate utilization using NCES instructional day requirements and state-level data on year-round school adoption. California schools (more year-round programs) run 28% utilization; Minnesota schools (traditional calendar, harsh winters) run 21%. Buildings empty 72-80% of the time.",

    'Retail': "Stores are built for peak crowds but average 35-45% capacity: slow mornings at 15-20%, lunch and evening rushes at 60-80%, overnight at zero. Urban locations with steadier foot traffic (NYC ~45%) show less savings than suburban stores with sharper peaks and valleys (~35%). The opportunity is in not ventilating for a full store during slow periods.",

    'Higher Ed': "Universities have extreme schedule-driven vacancy: only ~32 weeks in session per year, and during those weeks classrooms average just 35% utilization—most rooms sit empty between classes. Total building utilization runs 24-30% depending on academic calendar. Buildings empty 70-76% of the time.",

    'Residential Care': "Unlike hotels or offices, residents live on-site 24/7—sleeping, eating, spending most hours in the building. We use NIC MAP Vision Q4 2024 occupancy data: Boston 91%, Denver 86%, Atlanta 84%. With residents present ~95% of the time, there's far less empty space to recover compared to offices or schools that clear out nights and weekends.",

    'Medical Office': "Medical offices have just 9.5% vacancy (vs 20%+ for regular offices), but exam rooms are only occupied 25-35% of operating hours—patients are there for 15-30 minute appointments, then the room sits empty until the next one. (CBRE 2024-2025, MGMA)",

    'Supermarket': "Supermarkets operate long hours with steady traffic—but still swing between peaks and lulls. Peak hours (5-7pm) hit 80-100% capacity, off-peak (early morning, late night) drops to 15-30%. Weighted average: 45-55% of design.",

    'Specialty Hospital': "Specialty hospitals run 24/7 with 65-80% bed occupancy (AHA data). Limited opportunity in patient areas, but admin offices, waiting rooms, and cafeterias have variable occupancy—especially off-hours.",

    'Inpatient Hospital': "Hospitals run 24/7, but non-clinical areas have variable occupancy: waiting rooms empty overnight, exam rooms idle between appointments, admin offices with business-hours staff, cafeterias with meal-time peaks. Patient areas are limited opportunity, but support spaces offer savings.",

    'Mixed Use': "Mixed-use buildings—typically office towers with ground-floor retail—run centralized HVAC that ventilates vacant floors at near-design rates. We use the same sources as offices: city vacancy from CBRE (14-30% by market) and Kastle badge-swipe utilization (36-52%). Opportunity comes from both vacant space and leased space with low actual attendance.",

    'Wholesale Club': "Wholesale clubs have 30-40% of the building in back-of-house stock and warehouse space with almost nobody in it—just occasional forklift operators restocking shelves. We weight the sales floor (60% of building at ~48% customer traffic) against these giant empty stock areas (40% at ~10% occupancy), giving 30-38% true building-wide utilization.",

    'Venue': "Arenas, concert halls, and convention centers are empty 80%+ of the time—a typical arena hosts 60-80 events per year, totaling just 300-400 hours of actual use out of 8,760 hours annually. An NBA arena with 41 home games plus 30-40 concerts runs ~550 hours of HVAC-on time. That's 6-7% of the year. True utilization runs 15-22%.",

    'Theater': "Theaters sit empty most of the time—Broadway runs 8 shows per week × 3 hours = just 24 hours of performances out of 168 weekly hours. Adding pre-show HVAC warmup and tech rehearsals brings total conditioned time to ~35 hours per week—21% of the time. During shows, occupancy averages 70-80%. True utilization: 14-22%.",

    'Restaurant/Bar': "Dining areas (~60% of building) follow meal patterns: packed during lunch (50-70% capacity) and dinner (60-90%), nearly empty between. Weighted utilization runs 35-45%.",

    'Library/Museum': "Open ~50 hours/week with 30-40% visitor occupancy during those hours. Galleries and reading rooms designed for crowds see true utilization of just 10-15%.",

    'Outpatient Clinic': "Providers see 20-25 patients per day across 6-8 exam rooms—each room is occupied just 25-35% of operating hours. Between appointments, rooms sit empty. Weighted building utilization runs 42-48%.",

    'Data Center': "Data centers have zero ODCV savings. Cooling is driven by server heat loads, not people—a data center with 2 people or 20 requires the same cooling. No opportunity to reduce based on human presence.",

    'Bank Branch': "Bank branches operate limited hours—typically 9am-5pm weekdays, Saturday mornings—totaling just 45-50 hours per week (27-30% of time). During those hours, modern branches see minimal foot traffic as banking shifts online: 20-40 customers per day in spaces designed for queues of 30-50. Teller areas get full conditioning regardless of traffic.",

    'Vehicle Dealership': "Dealerships present a split opportunity: showrooms (30-40% of building) follow retail traffic with variable customer presence, while service bays (40-50%) have controlled utilization from scheduled appointments. Showroom traffic averages 35-45% of design, peaking on Saturdays. Service bays run 60-70% utilization during business hours. Showrooms with high ceilings and large glass have significant conditioning load for 40% average occupancy.",

}

# Default story for building types not in the dictionary
DEFAULT_BUILDING_STORY = "We calculate savings using federal CBECS survey data for HVAC energy shares, adjusted for this building's age, efficiency rating, and local climate. ODCV reduces ventilation when spaces are unoccupied—the savings depend on how much of the time this building sits empty or underutilized."

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
    'Data Center': "No ODCV reduction. Cooling is for equipment heat, not people.",
    'Venue': "HVAC reduced using event schedules, industry utilization data.",
    'Theater': "HVAC reduced using performance schedules, Broadway/regional theater utilization data.",
    'Library/Museum': "HVAC reduced using visitor traffic data, operating hours patterns.",
    'Outpatient Clinic': "HVAC reduced using CBECS 2018 fuel splits, MGMA provider productivity benchmarks.",
    'Bank Branch': "HVAC reduced using FDIC transaction trends, branch traffic patterns.",
    'Wholesale Club': "HVAC reduced using member traffic data, sales floor vs back-of-house weighting.",
    'Vehicle Dealership': "HVAC reduced using NADA traffic data, showroom vs service bay weighting.",
    'Laboratory': "HVAC reduced using CBECS 2018 fuel splits, research schedule patterns.",
    'Courthouse': "HVAC reduced using court administration docket data, public area patterns.",
    'default': "HVAC reduced using CBECS 2018 fuel splits, building type utilization benchmarks.",
}

# CHANGE column: Human-readable insight (WHY savings exist) by building type
# Sources at end get auto-hyperlinked by inject_source_links()
CHANGE_COLUMN_INSIGHTS = {
    'Office': "Most office space sits empty due to hybrid work and vacancies. Workers come in 2-3 days/week, and many floors have no tenants at all—but HVAC runs full blast regardless. (CBECS 2018, CBRE, Kastle)",
    'Medical Office': "Exam rooms are occupied just 25-35% of operating hours—patients are there for 15-30 minute appointments, then the room sits empty until the next one. (CBECS 2018, CBRE, MGMA)",
    'Hotel': "Most hotel rooms sit empty—national average is just 63% occupied. Even booked rooms are empty most of the day while guests are out at meetings, sightseeing, or meals. HVAC conditions empty rooms around the clock. (CBECS 2018, STR)",
    'K-12 School': "Schools are empty most of the year—summers off, weekends, holidays, and after 3pm daily. Buildings ventilate for students who aren't there 70-80% of the time. (CBECS 2018, NCES)",
    'Higher Ed': "Classrooms sit empty most of the year—semester breaks, weekends, summers, and between classes. Even when school's in session, most rooms are unused. (CBECS 2018, NCES)",
    'Retail': "Stores are built to handle Black Friday crowds, but most of the day they're nearly empty—slow mornings, quiet afternoons, closed overnight. HVAC runs as if the store were packed. (CBECS 2018)",
    'Supermarket': "Supermarkets run long hours with steadier traffic than most retail, but still swing between busy evenings and empty early mornings. (CBECS 2018)",
    'Restaurant/Bar': "Dining rooms are packed at meal times but empty the rest of the day—lunch rush, dinner rush, then dead time between and overnight. (CBECS 2018)",
    'Inpatient Hospital': "Hospitals run 24/7, but admin offices, waiting rooms, and cafeterias empty at night while patient areas stay occupied. (CBECS 2018, AHA)",
    'Specialty Hospital': "Specialty hospitals run 24/7, but non-clinical spaces like admin and waiting rooms empty during off-hours. (CBECS 2018, AHA)",
    'Residential Care': "Unlike hotels, residents live here 24/7—they don't leave for work or sightseeing. With people present ~95% of the time, there's less empty space to save on. (CBECS 2018, NIC MAP Vision)",
    'Mixed Use': "The office floors follow hybrid work patterns—workers come in 2-3 days/week, and vacant floors have no tenants at all. Ground-floor retail adds its own traffic variability. (CBECS 2018, CBRE, Kastle)",
    'Venue': "Arenas and convention centers sit empty 80%+ of the year. A typical arena hosts 60-80 events totaling just 300-400 hours—out of 8,760 hours annually. (CBECS 2018)",
    'Theater': "Theaters run just 8 shows per week, about 3 hours each—that's 21% of weekly hours at best. The rest of the time, seats sit empty. (CBECS 2018)",
    'Library/Museum': "Open ~50 hours/week, but visitors only occupy galleries 10-15% of the time. Reading rooms and exhibit halls designed for crowds often sit mostly empty. (CBECS 2018)",
    'Outpatient Clinic': "Patients occupy exam rooms for 15-30 minute appointments, then rooms sit empty until the next patient. Rooms designed for constant use are idle most of the day. (CBECS 2018, MGMA)",
    'Wholesale Club': "30-40% of the building is back-of-house warehouse with minimal staff. The sales floor is only busy on weekends. (CBECS 2018)",
    'default': "Most buildings are empty more often than people realize. HVAC runs at design capacity regardless of actual occupancy. (CBECS 2018)",
}

def get_current_column_tooltip(row):
    """CURRENT column tooltip - explains data source by city."""
    city = safe_val(row, 'loc_city', '')
    state = safe_val(row, 'loc_state', '')

    if city in CITY_DISCLOSURE_LAWS:
        law = CITY_DISCLOSURE_LAWS[city]
        return f"Based on regional disclosure laws, from {law} benchmarking disclosure. Actual metered energy reported by the building."
    elif state == 'CA':
        return "Based on regional disclosure laws, from California AB 802 disclosure. Actual metered energy reported by the building."
    else:
        return "From public energy benchmarking data. Actual metered energy."

def get_new_column_tooltip(row):
    """NEW column tooltip - explains methodology + data sources by building type."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    base_text = NEW_COLUMN_SOURCES.get(bldg_type, NEW_COLUMN_SOURCES['default'])
    return f"Based on building type: {base_text}"

def get_change_column_tooltip(row):
    """CHANGE column tooltip - the WHY punchline by building type."""
    # Delegate to get_odcv_savings_tooltip which has detailed building-type explanations
    return get_odcv_savings_tooltip(row)

#===============================================================================
# TOOLTIP DEFINITIONS
#===============================================================================

# Static tooltips - only for items that truly don't vary
TOOLTIPS = {
    'owner': "Building ownership from public records and regulatory filings.",
    'utility_provider': "Electric utility serving this building's location. Rates from NREL utility rate database by ZIP code.",
}

def get_energy_rate_tooltip(row):
    """Dynamic tooltip explaining energy rate concept - for ODCV provider audience."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    return f"Based on regional utility rates, base electricity rate before demand charges. Multiplier applied for taxes, distribution, and transmission fees not in the commodity rate. (NREL utility rate database)"

def get_demand_rate_tooltip(row):
    """Dynamic tooltip explaining demand rate concept - for ODCV provider audience."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    return f"Based on regional utility rates, utilities charge for peak power draw each month, not just consumption. Includes adjustments for demand ratchet clauses and seasonal rate premiums. (NREL utility rate database)"

def get_peak_demand_tooltip(row):
    """Dynamic tooltip explaining peak demand concept - for ODCV provider audience."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    context = {
        'Office': "offices peak mid-afternoon when HVAC, lighting, and equipment all run together.",
        'K-12 School': "schools peak when HVAC ramps up before students arrive and during hot afternoons.",
        'Hotel': "hotels peak in early evening when guests return and restaurant/laundry run simultaneously.",
        'Retail': "retail peaks during store hours when lighting, HVAC, and point-of-sale all operate.",
        'Inpatient Hospital': "hospitals have relatively flat demand since they run around the clock.",
        'Data Center': "data centers have very flat demand—servers run constantly.",
    }
    type_context = context.get(bldg_type, "peak typically occurs when HVAC, lighting, and equipment all run at once.")
    return f"Highest instantaneous power draw. Based on building type, {type_context} Calculated from annual usage and load factor."

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

def get_automation_score(year_built, sqft):
    """Calculate automation score from year built and sqft."""
    # Year score
    if not year_built or year_built < 1970:
        year_score = 0.0
    elif year_built < 1990:
        year_score = 0.25
    elif year_built < 2005:
        year_score = 0.50
    elif year_built < 2015:
        year_score = 0.75
    else:
        year_score = 1.0

    # Size score
    if not sqft or sqft < 50000:
        size_score = 0.25
    elif sqft < 100000:
        size_score = 0.50
    elif sqft < 250000:
        size_score = 0.75
    else:
        size_score = 1.0

    return (year_score + size_score) / 2.0

def get_efficiency_modifier(energy_star, eui, benchmark):
    """Calculate efficiency modifier from Energy Star or EUI ratio."""
    if energy_star:
        if energy_star >= 90:
            return 0.85, "very efficient"
        elif energy_star >= 75:
            return 0.95, "efficient"
        elif energy_star >= 50:
            return 1.00, "average"
        elif energy_star >= 25:
            return 1.05, "below avg"
        else:
            return 1.10, "inefficient"
    elif eui and benchmark and benchmark > 0:
        ratio = eui / benchmark
        if ratio > 1.5:
            return 1.10, "high EUI"
        elif ratio > 1.2:
            return 1.05, "above avg EUI"
        elif ratio > 0.85:
            return 1.00, "avg EUI"
        elif ratio > 0.70:
            return 0.95, "below avg EUI"
        else:
            return 0.90, "low EUI"
    return 1.00, "default"

def get_climate_modifier(climate_zone):
    """Get climate modifier from zone."""
    zone = str(climate_zone).lower() if climate_zone else ''
    if 'cold' in zone or 'very cold' in zone:
        return 1.10, "Cold"
    elif 'mixed' in zone:
        return 1.05, "Mixed"
    elif 'hot' in zone or 'warm' in zone:
        return 0.95, "Hot"
    return 1.00, "Moderate"

def get_odcv_savings_tooltip(row):
    """Dynamic ODCV opportunity explanation by building type.

    Explains WHY this building type has its specific ODCV savings potential.
    Uses hybrid style: real-world patterns + key data points + source citations.
    """
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')

    # Building-type specific explanations - hybrid style with data + sources
    tooltips = {
        # HIGH OPPORTUNITY (30%+ savings)
        'Office': "Post-COVID reality: Kastle Systems shows 50% average badge-ins nationally. Add 15-25% vacancy rates (SF: 34%, NYC: 15%) and you get massive over-ventilation. A building designed for 1,000 people often has 300-400 present. (CBECS 2018, CBRE, Kastle Systems)",

        'Medical Office': "Exam rooms sit empty between patients—each 15-30 minute appointment means the room is unoccupied 50-70% of operating hours. MGMA benchmarks show providers see 20-25 patients/day across 6-8 exam rooms. Add nights/weekends = closed. (CBECS 2018, MGMA)",

        'K-12 School': "Schools are empty 3+ months/year (summer, holidays, weekends) but HVAC often runs year-round. During school days, classrooms average 65-75% occupancy with significant empty periods between classes. Gyms, auditoriums, and cafeterias sit empty most of the day. (CBECS 2018, NCES)",

        'Higher Ed': "Universities have dramatic occupancy swings: summer break (12+ weeks), winter break, spring break, plus evenings and weekends. Lecture halls designed for 300 students often have 50. Research buildings run 24/7 HVAC for 9-5 occupancy. (CBECS 2018, NCES)",

        'Venue': "Arenas, concert halls, and convention centers are empty 80%+ of the time. A typical arena hosts 60-80 events/year—that's only 300-400 hours of actual use out of 8,760 hours/year. Yet HVAC conditions these massive spaces continuously. (CBECS 2018)",

        'Theater': "Broadway runs 8 shows/week x 3 hours = 24 hours of performances out of 168 hours/week. Even adding rehearsals and pre-show HVAC, theaters operate at 15-20% utilization. Movie theaters fare slightly better but still average 30% seat occupancy. (CBECS 2018)",

        'Inpatient Hospital': "Hospitals run 24/7, but non-clinical areas have variable occupancy: waiting rooms (30% occupied), exam rooms (35%), admin offices (40%), cafeterias (35%)—yet all receive the same aggressive ventilation as patient rooms. (CBECS 2018, AHA, ASHRAE 170)",

        'Mixed Use': "Office floors follow Kastle data (45-55% occupancy), retail floors follow traffic patterns (40-50%). Multi-tenant means vacancy challenges similar to office. Central HVAC controlled by landlord = same over-ventilation problem. (CBECS 2018, CBRE)",

        # MODERATE OPPORTUNITY (22-29%)
        'Specialty Hospital': "Rehab facilities, psychiatric hospitals, and specialty care have similar patterns to inpatient hospitals. Large waiting areas, admin offices, and therapy rooms are over-ventilated. True utilization 55-60%. (CBECS 2018, AHA)",

        'Hotel': "Average US hotel occupancy: 63%. But rooms are only occupied ~10 hours/day (evening to morning). Meeting rooms: booked 40% of time. Lobbies: 30% capacity average. HVAC runs 24/7 in all spaces regardless of occupancy. (CBECS 2018, STR)",

        'Outpatient Clinic': "Same pattern as medical office—exam rooms ventilated at medical-grade rates but patients only present for brief appointments. Operating hours: 8am-5pm weekdays. Effective utilization across exam rooms, waiting areas, and admin: 42-48%. (CBECS 2018, MGMA)",

        'Retail': "Foot traffic varies dramatically: weekday mornings see 15-25% of design capacity, weekend afternoons hit 60-80%. Stores condition for peak traffic 100% of operating hours. Back rooms and stockrooms (20-30% of space) see minimal occupancy. (CBECS 2018)",

        'Library': "HVAC runs 24/7 for collection preservation (temperature/humidity control), but visitors are sparse. Open ~50 hours/week with 30-40% average occupancy during those hours. True utilization: 12-15%. (CBECS 2018)",

        'Museum': "HVAC runs 24/7 for collection preservation (temperature/humidity control), but visitors are sparse. Open ~50 hours/week with 30-40% average occupancy during those hours. True utilization: 12-15%. (CBECS 2018)",

        'Library/Museum': "HVAC runs 24/7 for collection preservation (temperature/humidity control), but visitors are sparse. Open ~50 hours/week with 30-40% average occupancy during those hours. True utilization: 12-15%. (CBECS 2018)",

        # LIMITED OPPORTUNITY (20-22%)
        'Wholesale Club': "30-40% of the building is back-of-house warehouse with only forklift drivers present. Sales floor averages 48% traffic, stock areas 10%. Shorter hours than grocery (10am-8:30pm) and weekend-heavy traffic. (CBECS 2018)",

        'Restaurant/Bar': "Kitchen exhaust hoods must run at full blast during all cooking—not demand-controllable. ODCV opportunity exists only in dining areas (~60% of space). Dining follows meal patterns: packed at lunch/dinner, empty between. (CBECS 2018)",

        'Supermarket': "Longer hours (6am-midnight) than most retail, but still variable traffic. Open 126 hrs/week, but mornings and late nights see 20-30% of design. Food safety requirements limit how much ventilation can be reduced. (CBECS 2018)",

        'Residential Care': "Unlike hotels where guests leave during the day, residents actually live here 24/7. Savings limited to common areas during overnight hours—dining rooms, activity areas, lobbies when unoccupied. (CBECS 2018, NIC MAP Vision)",

        # VERY LIMITED OPPORTUNITY (5-15%)
        'Laboratory': "Labs have limited opportunity due to fume hoods requiring constant exhaust and specialized equipment. Negative pressure requirements override occupancy-based control. (CBECS 2018, ASHRAE)",

        'Police Station': "24/7 staffing requirement. Holding areas have specific ventilation requirements under detention standards. Savings limited to administrative and training spaces during off-hours. (CBECS 2018)",

        'Fire Station': "24/7 staffing requirement. Living quarters, apparatus bays, and ready rooms must maintain comfortable conditions for crews who may be called out at any moment. Response capability must remain immediate. (CBECS 2018, NFPA)",

        'Public Transit': "Station utilization follows commute patterns: packed 7-9am and 5-7pm, sparse overnight. But underground stations have specific ventilation requirements for tunnel air quality and emergency smoke evacuation. (CBECS 2018, NFPA 130)",

        'Courthouse': "Security requirements and unpredictable docket schedules limit flexibility. Courtrooms may sit empty between cases but require rapid climate recovery when sessions begin. (CBECS 2018)",

        'Bank Branch': "Limited hours—typically 9am-5pm weekdays, Saturday mornings (27-30% of time). During those hours, modern branches see minimal foot traffic: 20-40 customers/day in spaces designed for queues of 30-50. (CBECS 2018, FDIC)",

        'Public Service': "DMVs, permit centers operate standard business hours with variable public traffic. Waiting areas designed for 100 people often have 20-40 present except during peak periods. (CBECS 2018, GSA)",

        # OTHER TYPES
        'Arts & Culture': "Galleries require 24/7 climate control for artwork but see visitors only during limited hours. Performance spaces follow theater patterns with sparse scheduling. 15-25% visitor utilization. (CBECS 2018)",

        'Sports/Gaming Center': "Bowling alleys, ice rinks, arcades run 12-16 hours daily but average 35-45% utilization. Weekend afternoons hit 70-90% capacity; Tuesday mornings run 10-20%. Ice rinks need continuous cooling regardless of skaters. (CBECS 2018)",

        'Vehicle Dealership': "Showrooms (30-40% of building) follow retail traffic with variable customer presence. Service bays (40-50%) have controlled utilization from scheduled appointments. Showroom traffic averages 35-45% of design. (CBECS 2018, NADA)",

        # ZERO OPPORTUNITY
        'Data Center': "Data centers have zero ODCV savings potential. Cooling requirements are driven entirely by server heat loads, not human occupancy. A data center with 2 people or 20 people requires the same precise temperature and humidity control. (CBECS 2018)",
    }

    # Return building-type specific tooltip, or fallback for unknown types
    return tooltips.get(bldg_type, "Most buildings are ventilated at design capacity regardless of actual occupancy. Adjusting airflow to match real occupancy reduces waste during low-traffic periods. (CBECS 2018)")


def get_property_value_tooltip(row):
    """Dynamic property value tooltip - conceptual explanation only."""
    bldg_type = safe_val(row, 'bldg_type', '')
    city = safe_val(row, 'loc_city', '')
    fine_avoided = safe_num(row, 'bps_fine_avoided_yr1_usd', 0) or 0

    story = f"Commercial property values are based on Net Operating Income divided by capitalization rate—the standard income capitalization method used throughout real estate. "
    story += "Lower operating costs (like HVAC savings) flow directly to NOI, multiplying their impact on asset value. "
    if fine_avoided > 0:
        story += "Avoided BPS fines also reduce expenses, increasing NOI further. "
    story += f"Based on building type, cap rates for {bldg_type.lower()}s from CBRE Cap Rate Survey Q4 2024."
    return story

def get_energy_star_tooltip(row):
    """Dynamic methodology explanation for Energy Star score - for ODCV provider audience."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    return (f"Based on building type, ENERGY STAR® ranks this {bldg_type.lower()} against similar buildings nationwide using source energy (not site energy), "
            "normalized for weather and operating hours. Score of 75+ qualifies for EPA certification. "
            "Post-ODCV scores estimated by modeling how HVAC savings reduce source energy use. (EPA Portfolio Manager)")

def get_energy_star_threshold_upgrade(current, post):
    """Return upgrade message if post-ODCV score crosses certification threshold."""
    if current is None or post is None:
        return None
    # Certification threshold (75)
    if current < 75 and post >= 75:
        return ('<span style="display:inline-flex;align-items:center;gap:6px;background:#f0fdf4;'
                'border:1px solid #86efac;border-radius:4px;padding:4px 8px;margin-top:6px;font-size:0.8em;">'
                '<img src="../assets/images/energy_star_certified_building.png" alt="ENERGY STAR" '
                'style="width:32px;height:auto;">'
                '<span style="color:#15803d;">ODCV would make the difference between ENERGY STAR eligibility and ineligibility. '
                '<a href="https://www.energystar.gov/buildings/building-recognition/building-certification" '
                'target="_blank" style="color:#0891b2;">Learn more</a></span>'
                '</span>')
    # Median threshold (50)
    if current < 50 and post >= 50:
        return ('<div style="background:#f0f9ff;border:1px solid #0891b2;border-radius:6px;'
                'padding:8px 12px;margin-top:8px;font-size:0.85em;">'
                '<strong style="color:#0891b2;">↑ Above National Median</strong><br>'
                '<span style="color:#374151;font-size:0.9em;">Your building would outperform the typical building in its class.</span></div>')
    return None

def get_electricity_kwh_tooltip(row):
    """ROW tooltip - static per building type, with data year."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    data_year = safe_val(row, 'data_year', '')
    year_suffix = f" ({int(float(data_year))} data)" if data_year else ""
    tooltips = {
        'Data Center': "data centers use ~42% of electricity for cooling—but it removes server heat, not affected by occupancy. The rest powers IT equipment.",
        'Supermarket': "supermarkets use ~35% of electricity for HVAC. Refrigeration takes 40-50%, with lighting and equipment making up the rest.",
        'Inpatient Hospital': "hospitals use ~40-45% of electricity for HVAC. Medical imaging, life support, and 24/7 critical systems take the rest.",
        'Specialty Hospital': "specialty hospitals use ~40-45% of electricity for HVAC. Medical equipment and critical systems take the rest.",
        'Hotel': "hotels use ~45-50% of electricity for HVAC. Lighting, elevators, laundry, and kitchen equipment take the rest.",
        'Restaurant/Bar': "restaurants use ~30-35% of electricity for HVAC. Kitchen equipment, refrigeration, and lighting take the bulk.",
        'K-12 School': "schools use ~45-50% of electricity for HVAC. Lighting, computers, and cafeteria equipment take the rest.",
        'Higher Ed': "universities use ~45-50% of electricity for HVAC. Labs, computers, and lighting take the rest.",
        'Office': "offices use ~40-50% of electricity for HVAC. Lighting and plug loads (computers, equipment) take the rest.",
        'Medical Office': "medical offices use ~45-50% of electricity for HVAC. Medical equipment and lighting take the rest.",
        'Retail': "retail stores use ~40-45% of electricity for HVAC. Lighting is a major load, especially in display-heavy stores.",
    }
    base_text = tooltips.get(bldg_type, "commercial buildings typically use 40-50% of electricity for HVAC. Lighting and equipment take the rest.")
    return f"Based on building type, {base_text}" + year_suffix

def get_natural_gas_tooltip(row):
    """ROW tooltip - static per building type, with data year."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    data_year = safe_val(row, 'data_year', '')
    year_suffix = f" ({int(float(data_year))} data)" if data_year else ""
    tooltips = {
        'Hotel': "only ~20% of hotel gas goes to HVAC. The rest (~40% hot water, ~33% kitchen cooking) can't be reduced by occupancy controls.",
        'Restaurant/Bar': "just ~18% of restaurant gas is HVAC. The bulk (~72%) fires cooking equipment—that can't change with occupancy.",
        'Inpatient Hospital': "hospitals use ~60% of gas for HVAC. The rest goes to sterilization, hot water, and cafeteria.",
        'Specialty Hospital': "specialty hospitals use ~60% of gas for HVAC. The rest goes to sterilization and hot water.",
        'K-12 School': "schools use ~80% of gas for heating. The rest is cafeteria cooking and hot water.",
        'Higher Ed': "universities use ~80% of gas for heating. Labs, cafeterias, and hot water take the rest.",
        'Supermarket': "supermarkets use ~65-75% of gas for HVAC. Bakery ovens and deli equipment take the rest.",
        'Office': "offices use ~85-90% of gas for heating. Hot water takes the small remainder.",
        'Medical Office': "medical offices use ~85% of gas for heating. Hot water and sterilization take the rest.",
        'Retail': "retail stores use ~75-80% of gas for heating. Hot water takes the rest.",
        'Data Center': "data centers use almost no gas for HVAC—cooling is electric. Any gas goes to backup generators or office areas.",
    }
    base_text = tooltips.get(bldg_type, "commercial buildings typically use 75-85% of gas for heating. Hot water and process loads take the rest.")
    return f"Based on building type, {base_text}" + year_suffix

def get_fuel_oil_tooltip(row):
    """ROW tooltip - static per building type, with data year."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    data_year = safe_val(row, 'data_year', '')
    year_suffix = f" ({int(float(data_year))} data)" if data_year else ""
    tooltips = {
        'Inpatient Hospital': "hospitals use ~50-60% of fuel oil for HVAC. The rest runs backup generators and sterilization equipment.",
        'Specialty Hospital': "specialty hospitals use ~50-60% of fuel oil for HVAC. Backup generators and sterilization take the rest.",
        'Hotel': "hotels use ~70-80% of fuel oil for HVAC. The rest heats hot water.",
        'Laboratory': "labs use only ~12% of fuel oil for HVAC. Most powers backup generators and specialized equipment.",
        'Mixed Use': "mixed-use buildings use ~10-15% of fuel oil for HVAC. Much goes to backup power.",
        'Residential Care': "care facilities use ~40-50% of fuel oil for HVAC. Hot water for residents takes the rest.",
        'Retail': "retail stores use ~95%+ of fuel oil for heating—it's almost pure HVAC fuel.",
    }
    base_text = tooltips.get(bldg_type, "fuel oil is primarily a heating fuel—typically 80-95% goes to HVAC in commercial buildings.")
    return f"Based on building type, {base_text}" + year_suffix

def get_district_steam_tooltip(row):
    """ROW tooltip - static per building type, with data year."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    city = safe_val(row, 'loc_city', '')
    data_year = safe_val(row, 'data_year', '')
    year_suffix = f" ({int(float(data_year))} data)" if data_year else ""
    tooltips = {
        'Inpatient Hospital': "hospitals use ~85-90% of district steam for HVAC. Some runs sterilization equipment.",
        'Specialty Hospital': "specialty hospitals use ~85-90% of district steam for HVAC. Sterilization takes the rest.",
    }
    # NYC gets special mention of Con Edison
    if 'New York' in city or city == 'NYC':
        base = tooltips.get(bldg_type, "district steam is ~95%+ HVAC—piped from Con Edison's central plants. It's a heating-only fuel.")
        if bldg_type not in tooltips:
            return f"Based on building type and regional utility, {base}" + year_suffix
        return f"Based on building type and regional utility, {tooltips[bldg_type]} Piped from Con Edison." + year_suffix
    base_text = tooltips.get(bldg_type, "district steam is ~95%+ HVAC—a heating-only fuel from central plants.")
    return f"Based on building type, {base_text}" + year_suffix

def get_site_eui_tooltip(row):
    """EUI tooltip - explains what EUI is and provides benchmark context."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    data_year = safe_val(row, 'data_year', '')
    year_suffix = f" ({int(float(data_year))} data)" if data_year else ""

    # Building type median EUIs from CBECS 2018
    benchmarks = {
        'Office': 70, 'Medical Office': 85, 'Hotel': 95, 'K-12 School': 55,
        'Higher Ed': 90, 'Retail': 50, 'Restaurant/Bar': 250,
        'Supermarket': 180, 'Inpatient Hospital': 200, 'Specialty Hospital': 180,
        'Data Center': 800, 'Warehouse': 25, 'Residential Care': 100,
        'Mixed Use': 75, 'default': 70
    }
    type_benchmark = benchmarks.get(bldg_type, benchmarks['default'])

    return f"Energy Use Intensity measures total annual energy per square foot. Formula: EUI = Annual Energy (kBtu) ÷ Building Area (sq ft). Lower values mean better efficiency. Based on building type, {bldg_type.lower()} median: ~{type_benchmark} kBtu/sq ft/year.{year_suffix}"

def get_hvac_pct_tooltip(row):
    """Brief tooltip for HVAC percentage."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    return f"Based on building type, % of energy used by HVAC for {bldg_type.lower()}s. Adjusted for age, efficiency, and climate. (EIA CBECS 2018)"

def get_load_factor_tooltip(row):
    """Load factor tooltip - conceptual explanation with building-type context."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')

    # Building type context (conceptual)
    context = {
        'Data Center': "data centers have very high load factors—servers run around the clock at steady power.",
        'Inpatient Hospital': "hospitals have high load factors due to 24/7 operations.",
        'Specialty Hospital': "hospitals have high load factors due to 24/7 operations.",
        'Supermarket': "grocery stores have high load factors—refrigeration runs constantly.",
        'Office': "offices have lower load factors—busy during business hours, quiet nights and weekends.",
        'K-12 School': "schools have low load factors—empty summers, evenings, and weekends.",
        'Higher Ed': "universities have moderate load factors—semester schedules with breaks.",
        'Hotel': "hotels have moderate load factors—variable occupancy patterns.",
    }
    type_context = context.get(bldg_type, "load factor depends on how consistently the building operates.")

    return f"Load factor measures how evenly electricity is used (average load ÷ peak load). Higher values mean steadier usage, lower values mean sharp peaks. Based on building type, {type_context} Used to estimate peak demand for utility billing. (CBECS 2018)"

def get_total_ghg_tooltip(row):
    """Dynamic tooltip explaining total GHG emissions - city-specific grid context."""
    city = safe_val(row, 'loc_city', '')

    # City-specific grid context (conceptual, no numbers)
    grid_context = {
        'Seattle': "Seattle's grid is almost entirely hydroelectric, so electricity here has very low carbon intensity.",
        'New York': "NYC's grid uses a mix of natural gas, nuclear, and renewables.",
        'Chicago': "The Midwest grid relies heavily on coal, so electricity here has higher carbon intensity.",
        'Denver': "Colorado's grid is transitioning from coal but still has significant fossil fuel generation.",
        'Boston': "New England's grid is primarily natural gas with growing renewables.",
        'Los Angeles': "California's grid has significant solar and natural gas.",
        'San Francisco': "California's grid has significant solar and natural gas.",
    }

    city_note = grid_context.get(city, "")

    base = "Total emissions from all fuel types: electricity (varies by regional grid), natural gas (standard combustion), plus any steam or fuel oil. "
    if city_note:
        base += f"Based on regional grid mix, {city_note.lower()} "
    base += "(EPA eGRID 2023)"

    return base

def get_carbon_reduction_tooltip(row):
    """Dynamic carbon reduction tooltip with city-specific grid context."""
    city = safe_val(row, 'loc_city', '')

    # City-specific grid context (conceptual, no numbers)
    grid_context = {
        'Seattle': "Seattle's nearly all-hydro grid means most building emissions come from gas, not electricity.",
        'New York': "NYC's mixed grid means both electricity and gas contribute significantly to emissions.",
        'Chicago': "The coal-heavy Midwest grid means electricity reduction has a big emissions impact here.",
        'Denver': "Colorado's transitioning grid still has significant coal, making electricity cuts impactful.",
        'Boston': "New England's gas-heavy grid means both electricity and gas contribute to emissions.",
        'Los Angeles': "California's cleaner grid means gas is often the bigger emissions driver.",
        'San Francisco': "California's cleaner grid means gas is often the bigger emissions driver.",
    }

    city_note = grid_context.get(city, "")
    base = "Based on regional grid mix, carbon per kWh varies dramatically. "
    if city_note:
        base += city_note + " "
    base += "(EPA eGRID 2023)"

    return base

def get_fine_avoidance_tooltip(row):
    """Brief tooltip for BPS fine avoidance."""
    city = safe_val(row, 'loc_city', '')
    bldg_type = safe_val(row, 'bldg_type', '')
    bldg_vertical = safe_val(row, 'bldg_vertical', '')
    sqft = safe_num(row, 'bldg_sqft', 0) or 0
    fine_avoided = safe_num(row, 'bps_fine_avoided_yr1_usd', 0) or 0
    carbon = safe_num(row, 'carbon_emissions_total_mt', 0) or 0
    eui = safe_num(row, 'energy_site_eui', 0) or 0
    es_score = safe_num(row, 'energy_star_score', 0) or 0

    bps_info = BPS_TOOLTIP_INFO.get(city)

    if not bps_info:
        return "No Building Performance Standard law in this city yet."

    law = bps_info['law']
    min_sqft = bps_info.get('min_sqft', 0)

    exempt_types = bps_info.get('exempt_types', [])
    if bldg_type in exempt_types or bldg_vertical in exempt_types:
        return f"Based on local regulations, {law} provides {bldg_type.lower()}s alternative compliance pathways."

    if sqft > 0 and sqft < min_sqft:
        return f"Based on local regulations, {law} covers larger buildings—this one is below the size threshold."

    if city == 'New York':
        return "Based on local regulations: NYC Local Law 97 sets annual carbon emission limits. Buildings exceeding the cap pay fines per metric ton over the limit. ODCV reduces emissions by cutting HVAC energy waste. (NYC Local Law 97)"
    elif city == 'Boston':
        return "Based on local regulations: Boston's BERDO 2.0 sets emissions limits with per-ton penalties for excess emissions. ODCV reduces emissions by cutting the electricity and gas that generate them. (BERDO 2.0)"
    elif city == 'Cambridge':
        return "Based on local regulations: Cambridge BEUDO sets emissions limits with per-ton penalties for excess emissions. ODCV reduces emissions proportionally to energy savings. (Cambridge BEUDO)"
    elif city == 'Washington':
        return "Based on local regulations: DC BEPS requires buildings to meet an ENERGY STAR score threshold. Buildings below face fines based on how far below target they score. ODCV improves scores by reducing energy use. (DC BEPS)"
    elif city == 'Denver':
        return "Based on local regulations: Energize Denver fines buildings based on how far they exceed their EUI target. ODCV directly lowers EUI by reducing HVAC energy waste. (Energize Denver)"
    elif city == 'Seattle':
        return "Based on local regulations: Seattle BEPS sets emissions intensity targets with penalties for non-compliance. Seattle's nearly all-hydro grid means most building emissions come from gas—making HVAC gas reduction especially impactful. (Seattle Clean Buildings Act)"
    elif city == 'St. Louis':
        return "Based on local regulations: St. Louis BEPS sets EUI targets with daily fines for non-compliance. ODCV directly lowers EUI by reducing HVAC energy waste. (St. Louis BEPS)"

    return f"Based on local regulations, currently compliant with {law}."


def get_utility_cost_savings_tooltip(row):
    """Dynamic tooltip for utility cost savings - building-type HVAC context."""
    city = safe_val(row, 'loc_city', '')
    state = safe_val(row, 'loc_state', '')
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')

    # City-specific disclosure law
    if city in CITY_DISCLOSURE_LAWS:
        law_name = CITY_DISCLOSURE_LAWS[city]
        source = f"{law_name} disclosure"
    elif state == 'CA':
        source = "California AB 802 disclosure"
    else:
        source = "public energy benchmarking data"

    # Building-type HVAC context (conceptual)
    hvac_context = {
        'Office': "offices use a large share of electricity and most gas for HVAC.",
        'Hotel': "hotels use less gas for HVAC than you'd expect—hot water and kitchens take a large share.",
        'Restaurant/Bar': "restaurants use most gas for cooking, not HVAC.",
        'K-12 School': "schools use most gas for heating and a large share of electricity for cooling.",
        'Hospital': "hospitals have high ventilation requirements but also significant non-HVAC loads.",
        'Inpatient Hospital': "hospitals have high ventilation requirements but also significant non-HVAC loads.",
        'Retail': "retail uses a significant share of electricity for HVAC, with lighting as another major load.",
        'Data Center': "data centers use almost no HVAC for occupancy—cooling is for equipment heat removal.",
    }
    type_note = hvac_context.get(bldg_type, "HVAC is a significant portion of energy use for this building type.")

    return f"Annual savings from conditioning less empty space. Based on regional disclosure laws, energy data from {source}. Based on building type, {type_note} (CBECS 2018)"


# Map of dynamic tooltip keys to their generator functions
DYNAMIC_TOOLTIPS = {
    # Building Type Opportunity (Property section)
    'bldg_type_opportunity': get_odcv_savings_tooltip,
    # Impact Section
    'utility_cost_savings': get_utility_cost_savings_tooltip,
    'property_value_increase': get_property_value_tooltip,
    'fine_avoidance': get_fine_avoidance_tooltip,
    'energy_star_score': get_energy_star_tooltip,
    'carbon_reduction': get_carbon_reduction_tooltip,
    # Energy Table - ENERGY SAVINGS ONLY (no $ talk)
    'energy_elec_kwh': get_electricity_kwh_tooltip,
    'natural_gas': get_natural_gas_tooltip,
    'fuel_oil': get_fuel_oil_tooltip,
    'district_steam': get_district_steam_tooltip,
    'energy_site_eui': get_site_eui_tooltip,
    'pct_hvac_elec': get_hvac_pct_tooltip,
    # Electricity Details - now dynamic
    'energy_rate': get_energy_rate_tooltip,
    'demand_rate': get_demand_rate_tooltip,
    'peak_demand': get_peak_demand_tooltip,
    'load_factor': get_load_factor_tooltip,
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
        html += f"<tr><td>Size</td><td>{format_number(sqft)} sqft</td></tr>\n"

    # Type (with opportunity level tooltip explaining WHY this building type has savings potential)
    bldg_type = safe_val(row, 'bldg_type')
    if bldg_type and str(bldg_type).lower() != 'nan':
        html += f"<tr><td>Type{tooltip('bldg_type_opportunity', row)}</td><td>{escape(bldg_type)}</td></tr>\n"

    # Year Built - only show if it's a reasonable year (1800-2030)
    year = safe_num(row, 'bldg_year_built')
    if year and 1800 <= year <= 2030:
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
        if utility_logo_url:
            html += f'<tr><td>Utility</td><td><span class="org-logo" data-org-name="{escape(utility)}"><img src="{utility_logo_url}" alt="{escape(utility)}" style="height:24px;max-width:80px;object-fit:contain;vertical-align:middle;" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'inline\';"><span style="display:none;">⚡ {escape(utility)}</span></span></td></tr>\n'
        else:
            html += f"<tr><td>Utility</td><td>⚡ {escape(utility)}</td></tr>\n"

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
        html += f"<tr><td>Total Annual Cost</td><td>{format_currency(total_cost)}</td></tr>"

    # Energy charges
    energy_cost = safe_num(row, 'cost_elec_energy_annual')
    if energy_cost:
        html += f"<tr><td>Energy Charges</td><td>{format_currency(energy_cost)}</td></tr>"

    # Demand charges
    demand_cost = safe_num(row, 'cost_elec_demand_annual')
    if demand_cost:
        html += f"<tr><td>Demand Charges</td><td>{format_currency(demand_cost)}</td></tr>"

    # Energy rate
    energy_rate = safe_num(row, 'cost_elec_rate_kwh')
    if energy_rate:
        html += f"<tr><td>Energy Rate{tooltip('energy_rate', row)}</td><td>${energy_rate:.4f}/kWh</td></tr>"

    # Demand rate
    demand_rate = safe_num(row, 'cost_elec_rate_demand_kw')
    if demand_rate:
        html += f"<tr><td>Demand Rate{tooltip('demand_rate', row)}</td><td>${demand_rate:.2f}/kW</td></tr>"

    # Peak demand
    peak_kw = safe_num(row, 'cost_elec_peak_kw')
    if peak_kw:
        html += f"<tr><td>Peak Demand{tooltip('peak_demand', row)}</td><td>{format_number(peak_kw)} kW</td></tr>"

    # Load factor
    load_factor = safe_num(row, 'cost_elec_load_factor')
    if load_factor:
        html += f"<tr><td>Load Factor{tooltip('load_factor', row)}</td><td>{load_factor*100:.1f}%</td></tr>"

    # Utility
    utility = safe_val(row, 'cost_utility_name')
    if utility:
        utility_logo_url = UTILITY_LOGOS.get(utility, '')
        if utility_logo_url:
            html += f'<tr><td>Utility Provider{tooltip("utility_provider")}</td><td><span class="org-logo" data-org-name="{escape(utility)}"><img src="{utility_logo_url}" alt="{escape(utility)}" style="height:24px;max-width:80px;object-fit:contain;vertical-align:middle;" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'inline\';"><span style="display:none;">⚡ {escape(utility)}</span></span></td></tr>'
        else:
            html += f"<tr><td>Utility Provider{tooltip('utility_provider')}</td><td>⚡ {escape(utility)}</td></tr>"

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
