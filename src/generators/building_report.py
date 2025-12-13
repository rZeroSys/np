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
        'source_url': 'https://www.nyc.gov/site/sustainablebuildings/ll97/local-law-97.page',
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
        'method': 'emission cap',
        'penalty': '$234/tCO2e over cap',
        'cap': '0.0053 tCO2e/sqft',
        'min_sqft': 25000,
        'source': 'City of Cambridge',
        'source_url': 'https://www.cambridgema.gov/CDD/zoninganddevelopment/sustainablebldgs/beudo',
        'effective': '2025 (aligned with Boston BERDO)',
        'note': 'Uses same penalty structure as Boston. Caps tighten through 2050.',
        'exempt_types': [],
        'exempt_reason': ''
    },
    'Washington': {
        'law': 'DC BEPS',
        'method': 'Energy Star score',
        'penalty': '$10/sqft (prorated)',
        'cap': 'ENERGY STAR 71 target',
        'min_sqft': 50000,
        'source': 'DC DOEE',
        'source_url': 'https://doee.dc.gov/service/building-energy-performance-standards',
        'effective': '2026 (first compliance deadline)',
        'note': 'Unlike emission-based laws, DC uses Energy Star scores. Buildings scoring below 71 pay prorated fines.',
        'exempt_types': [],
        'exempt_reason': ''
    },
    'Denver': {
        'law': 'Energize Denver',
        'method': 'EUI target',
        'penalty': '$0.30/kBtu over target',
        'cap': '48.3 kBtu/sqft EUI',
        'min_sqft': 25000,
        'source': 'City of Denver',
        'source_url': 'https://www.denvergov.org/Government/Agencies-Departments-Offices/Agencies-Departments-Offices-Directory/Climate-Action-Sustainability-Resiliency/Energize-Denver',
        'effective': '2024-2027 (current compliance period)',
        'note': 'Penalties scale with how far over target. A building 10 kBtu over pays ~$3/sqft annually.',
        'exempt_types': ['K-12 School', 'Government'],
        'exempt_reason': 'have different compliance pathways'
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
        'source_url': 'https://www.stlouis-mo.gov/government/departments/mayor/initiatives/sustainability/building-energy-performance-standard.cfm',
        'effective': '2025 (reporting begins)',
        'note': 'Daily fines accumulate quickly—$182,500/year if non-compliant. Smaller cities often have aggressive enforcement.',
        'exempt_types': [],
        'exempt_reason': ''
    },
}

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
    'Strip Mall': {
        'category': 'Multi-Tenant',
        'floor': 0.15, 'ceiling': 0.35,
        'uses_vacancy': True,
        'formula': 'Vacancy + (1-Vacancy) × (1-Utilization)',
        'elec_hvac_typical': 0.56,
        'gas_hvac_typical': 0.777,
        'load_factor': 0.40,
        'demand_rate_typical': 35.0,
        'explanation': 'Individual tenant spaces may have separate systems, but common areas and some shared HVAC still create vacancy-driven opportunity.'
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
    'Retail Store': {
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
    'Supermarket/Grocery': {
        'category': 'Single-Tenant',
        'floor': 0.10, 'ceiling': 0.25,
        'uses_vacancy': False,
        'formula': '1 - Utilization',
        'elec_hvac_typical': 0.32,
        'gas_hvac_typical': 0.75,
        'load_factor': 0.65,
        'demand_rate_typical': 35.0,
        'explanation': 'Long hours (often 6am-midnight or 24/7) with steady traffic reduce empty-space opportunity. Note: ~40% of electricity is refrigeration, not HVAC.'
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
        'explanation': 'Predictable meal-time peaks, but kitchen runs at constant ventilation regardless of dining room occupancy. Note: Only 18% of gas is HVAC (72% is cooking).'
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
        'explanation': 'Fixed operating hours with relatively steady occupancy during open hours. Collection preservation may require stable conditions. Savings primarily from nights/weekends.'
    },
    'Gym': {
        'category': 'Single-Tenant',
        'floor': 0.15, 'ceiling': 0.35,
        'uses_vacancy': False,
        'formula': '1 - Utilization',
        'elec_hvac_typical': 0.55,
        'gas_hvac_typical': 0.80,
        'load_factor': 0.45,
        'demand_rate_typical': 35.0,
        'explanation': 'Extreme peak/off-peak patterns: 6-8am packed, 10am-4pm empty, 5-7pm packed again, 8pm-5am empty. Ventilating at peak capacity during dead hours is pure waste.'
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
        'explanation': 'Similar to supermarkets—high ceilings, refrigeration load, steady traffic. Lower HVAC % due to large refrigerated sections.'
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
        'explanation': 'Appointment-driven occupancy with clear operating hours. Less stringent than inpatient hospitals—no 24/7 operation or strict infection control in most areas.'
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
        'explanation': 'ASHRAE 170 mandates 15-25 air changes/hour in ORs regardless of occupancy. 24/7 operation, infection control requirements. Only ~30% of theoretical savings achievable in non-clinical areas.'
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
        'explanation': 'Similar constraints to inpatient hospitals. Procedure-specific ventilation requirements, 24/7 operation in most cases.'
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
    'Residential Care Facility': {
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
        'explanation': 'Fume hoods require constant exhaust (and makeup air). Many labs maintain negative pressure. Chemical/biological safety requirements override occupancy sensing.'
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
    'Supermarket/Grocery': {
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
    'Retail Store': {
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
    'Residential Care Facility': {
        'elec_note': "50% of electricity is HVAC. Comfort requirements for elderly residents.",
        'gas_note': "70% of gas is HVAC. DHW for bathing and kitchen use the remaining 30%.",
        'load_factor_note': "High load factor (65%) - residents live there 24/7, unlike offices that empty at night.",
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
    'Office': "We calculate savings using federal CBECS survey data for how much energy goes to HVAC, city-specific office vacancy rates from CBRE and Cushman & Wakefield, and real occupancy data from Kastle Systems badge swipes. Buildings in cities with lower office attendance (San Francisco at 38%) show higher savings potential than cities with stronger return-to-office (New York at 55%). Adjusted for building age and current efficiency.",

    'Hotel': "Room occupancy (STR data: NYC 87%, national 63%) times guest presence (~45% of the day—the rest they're out at meetings, sightseeing, dining) gives true utilization. A 63%-occupied hotel runs just 28% actual utilization—meaning 72% of ventilation conditions empty rooms. High-occupancy markets like NYC show less savings potential than lower-occupancy markets like Denver or Atlanta.",

    'K-12 School': "Schools operate roughly 180 days per year, 7 hours per day—just 22-28% of annual hours depending on state. We calculate utilization using NCES instructional day requirements and state-level data on year-round school adoption. California schools (more year-round programs) run 28% utilization; Minnesota schools (traditional calendar, harsh winters) run 21%. Buildings empty 72-80% of the time.",

    'Retail Store': "Stores are built for peak crowds but average 35-45% capacity: slow mornings at 15-20%, lunch and evening rushes at 60-80%, overnight at zero. Urban locations with steadier foot traffic (NYC ~45%) show less savings than suburban stores with sharper peaks and valleys (~35%). The opportunity is in not ventilating for a full store during slow periods.",

    'Higher Ed': "Universities have extreme schedule-driven vacancy: only ~32 weeks in session per year, and during those weeks classrooms average just 35% utilization—most rooms sit empty between classes. Total building utilization runs 24-30% depending on academic calendar. Buildings empty 70-76% of the time.",

    'Residential Care': "Unlike hotels or offices, residents live on-site 24/7—sleeping, eating, spending most hours in the building. We use NIC MAP Vision Q4 2024 occupancy data: Boston 91%, Denver 86%, Atlanta 84%. With residents present ~95% of the time, there's far less empty space to recover compared to offices or schools that clear out nights and weekends.",

    'Medical Office': "Medical offices get 2-3x the airflow of regular offices under ASHRAE 62.1 healthcare standards—even waiting rooms receive medical-grade ventilation. We use CBRE 2024-2025 data showing 9.5% vacancy (versus 20%+ for regular offices) and MGMA benchmarks showing 70% exam room utilization during business hours. The opportunity: exam rooms sit empty between appointments while still receiving full infection-control airflow.",

    'Supermarket/Grocery': "Supermarkets operate long hours with steady traffic—but still swing between peaks and lulls. We use Placer.ai foot traffic data: peak hours (5-7pm) hit 80-100% capacity, off-peak (early morning, late night) drops to 15-30%. Weighted average: 45-55% of design. Refrigeration cases also benefit—lower ventilation means reduced humidity loads.",

    'Specialty Hospital': "Specialty hospitals—psychiatric, rehab, children's, cancer centers—are limited-opportunity: they run 24/7 with patients who stay continuously. We use AHA bed occupancy data showing 65-80% depending on specialty and market. ASHRAE 170 mandates 15-25 air changes per hour in critical areas regardless of census—those rates can't drop. Savings come mainly from admin areas and waiting rooms during off-hours.",

    'Inpatient Hospital': "Hospitals are a limited-opportunity building type due to 24/7 operation and infection control requirements. Significant savings come from non-clinical areas over-ventilated at medical-grade rates around the clock: waiting rooms empty overnight, exam rooms only periodically occupied, admin offices with business-hours staff, cafeterias with variable traffic. ASHRAE 170 mandates minimum rates in critical areas, but waiting rooms, admin, and lobbies offer real opportunity.",

    'Mixed Use': "Mixed-use buildings—typically office towers with ground-floor retail—run centralized HVAC that ventilates vacant floors at near-design rates. We use the same sources as offices: city vacancy from CBRE and Cushman & Wakefield (14-30% by market) and Kastle badge-swipe utilization (36-52%). Opportunity comes from both vacant space and leased space with low actual attendance.",

    'Wholesale Club': "Wholesale clubs have 30-40% of the building in back-of-house stock and warehouse space with almost nobody in it—just occasional forklift operators restocking shelves. We weight the sales floor (60% of building at ~48% customer traffic) against these giant empty stock areas (40% at ~10% occupancy), giving 30-38% true building-wide utilization.",

    'Venue': "Arenas, concert halls, and convention centers are empty 80%+ of the time—a typical arena hosts 60-80 events per year, totaling just 300-400 hours of actual use out of 8,760 hours annually. An NBA arena with 41 home games plus 30-40 concerts runs ~550 hours of HVAC-on time. That's 6-7% of the year. True utilization runs 15-22%.",

    'Theater': "Theaters sit empty most of the time—Broadway runs 8 shows per week × 3 hours = just 24 hours of performances out of 168 weekly hours. Adding pre-show HVAC warmup and tech rehearsals brings total conditioned time to ~35 hours per week—21% of the time. During shows, occupancy averages 70-80%. True utilization: 14-22%.",

    'Restaurant/Bar': "Restaurants present a split opportunity: kitchen exhaust hoods must run at full blast during cooking hours—that's not demand-controllable. The opportunity exists in dining areas (~60% of the building), which follow meal patterns: packed during lunch and dinner, nearly empty between. We weight kitchen (limited ODCV) against dining (variable occupancy) for building-wide savings.",

    'Library/Museum': "Libraries and museums run HVAC 24/7 for collection preservation—temperature at 68-72°F and humidity at 45-55% RH to protect books, art, and artifacts—but visitors are sparse. Typical: 50 hours per week open to public, with 30-40% average occupancy during those hours. True visitor-driven utilization: 10-15%. The opportunity: conditioning galleries at preservation levels around the clock while visitors occupy them just 10-15% of the time.",

    'Outpatient Clinic': "Outpatient clinics follow medical office patterns—exam rooms ventilated at medical-grade rates but patients only present for 15-30 minute appointments. Between patients, rooms sit empty but fully ventilated. Providers see 20-25 patients per day across 6-8 exam rooms, meaning each room is occupied just 25-35% of operating hours. Weighted building utilization runs 42-48%.",

    'Enclosed Mall': "Enclosed malls face both vacancy and traffic challenges—inline store vacancy runs 15-30% as anchor stores close. We use ICSC and Placer.ai data: weekday morning traffic runs 10-20% of design, weekend afternoons hit 60-80%. Common areas get fully conditioned regardless of whether 100 or 1,000 shoppers are present. Weighted utilization runs 35-45%.",

    'Data Center': "Data centers have zero ODCV savings potential. Cooling requirements are driven entirely by server heat loads, not human occupancy. A data center with 2 people or 20 people requires the same precise temperature and humidity control. Ventilation rates are set by IT equipment density—ASHRAE recommends 64-80°F inlet temperatures regardless of occupancy. No opportunity to reduce conditioning based on human presence.",

    'Strip Mall': "Strip malls combine vacancy challenges (individual tenant spaces go empty during turnover) with retail traffic patterns. Vacancy runs 8-15% depending on market. Individual stores follow retail traffic patterns—busy evenings and weekends, slow weekday mornings. Tenant spaces typically served by individual rooftop units, making demand-based ventilation straightforward.",

    'Preschool/Daycare': "Daycares operate more hours than K-12 schools (typically 6:30am-6:30pm for working parents) but still close nights and weekends. Operating hours: ~60 per week versus 168 total = 36% of time open. During operating hours, rooms designed for 20 children often have 12-15 present (rolling drop-offs/pickups). Effective utilization: 25-32%.",

    'Bank Branch': "Bank branches operate limited hours—typically 9am-5pm weekdays, Saturday mornings—totaling just 45-50 hours per week (27-30% of time). During those hours, modern branches see minimal foot traffic as banking shifts online: 20-40 customers per day in spaces designed for queues of 30-50. Teller areas get full conditioning regardless of traffic.",

    'Vehicle Dealership': "Dealerships present a split opportunity: showrooms (30-40% of building) follow retail traffic with variable customer presence, while service bays (40-50%) have controlled utilization from scheduled appointments. Showroom traffic averages 35-45% of design, peaking on Saturdays. Service bays run 60-70% utilization during business hours. Showrooms with high ceilings and large glass have significant conditioning load for 40% average occupancy.",

    'Gym': "Gyms have extreme peak-valley patterns: packed at 6-8am and 5-8pm (60-80% equipment in use), nearly empty midday and late night (10-20%). Facilities average 35-45% utilization across operating hours. 24-hour gyms run even lower—overnight hours see single-digit utilization. High ventilation required during peaks (exercising people produce 5-10x the CO2), but that same rate conditions empty cardio floors at 2am.",

    'Event Space': "Event spaces—banquet halls, conference centers, wedding venues—are designed for peak events that occur infrequently. A typical venue hosts 2-4 events per week, each lasting 4-8 hours. Between events, spaces sit empty but require some conditioning. 20 hours of events per week + 10 hours setup = 30 hours conditioned out of 168 (18%). Weighted utilization runs 15-22%.",
}

# Default story for building types not in the dictionary
DEFAULT_BUILDING_STORY = "We calculate savings using federal CBECS survey data for HVAC energy shares, adjusted for this building's age, efficiency rating, and local climate. ODCV reduces ventilation when spaces are unoccupied—the savings depend on how much of the time this building sits empty or underutilized."

#===============================================================================
# ENERGY SECTION COLUMN TOOLTIPS
#===============================================================================

# Static fallback (dynamic functions below are preferred)
ENERGY_COLUMN_TOOLTIPS = {
    'current': "From city benchmarking disclosure or ENERGY STAR Portfolio Manager.",
    'new': "Projected energy after ODCV implementation.",
    'change': "Annual energy reduction from ODCV.",
}

#===============================================================================
# DYNAMIC COLUMN TOOLTIP FUNCTIONS (for Energy section)
#===============================================================================

# NEW column: Methodology + data sources by building type
NEW_COLUMN_SOURCES = {
    'Office': "HVAC reduced using <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a> fuel splits, <a href='https://www.cbre.com/insights' target='_blank'>CBRE</a>/Cushman vacancy rates, <a href='https://www.kastle.com/safety-wellness/getting-america-back-to-work/' target='_blank'>Kastle</a> badge-swipe occupancy data.",
    'Medical Office': "HVAC reduced using <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a> fuel splits, <a href='https://www.cbre.com/insights' target='_blank'>CBRE</a> vacancy data, <a href='https://www.mgma.com/' target='_blank'>MGMA</a> exam room utilization benchmarks.",
    'Hotel': "HVAC reduced using <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a> fuel splits, <a href='https://str.com/' target='_blank'>STR</a> room occupancy data, guest presence patterns.",
    'K-12 School': "HVAC reduced using <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a> fuel splits, <a href='https://nces.ed.gov/' target='_blank'>NCES</a> instructional day requirements, state calendar data.",
    'Higher Ed': "HVAC reduced using <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a> fuel splits, <a href='https://nces.ed.gov/' target='_blank'>NCES</a> data, semester and break schedules.",
    'Retail Store': "HVAC reduced using <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a> fuel splits, <a href='https://www.placer.ai/' target='_blank'>Placer.ai</a> foot traffic data.",
    'Supermarket/Grocery': "HVAC reduced using <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a> fuel splits, <a href='https://www.placer.ai/' target='_blank'>Placer.ai</a> traffic patterns.",
    'Restaurant/Bar': "HVAC reduced using <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a> fuel splits. Kitchen exhaust excluded—only dining area HVAC.",
    'Inpatient Hospital': "HVAC reduced using <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a> fuel splits, <a href='https://www.aha.org/' target='_blank'>AHA</a> bed occupancy data. <a href='https://www.ashrae.org/' target='_blank'>ASHRAE 170</a> limits applied.",
    'Specialty Hospital': "HVAC reduced using <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a> fuel splits, <a href='https://www.aha.org/' target='_blank'>AHA</a> bed occupancy data. <a href='https://www.ashrae.org/' target='_blank'>ASHRAE 170</a> limits applied.",
    'Residential Care': "HVAC reduced using <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a> fuel splits, <a href='https://www.nic.org/' target='_blank'>NIC MAP Vision</a> occupancy data.",
    'Residential Care Facility': "HVAC reduced using <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a> fuel splits, <a href='https://www.nic.org/' target='_blank'>NIC MAP Vision</a> occupancy data.",
    'Mixed Use': "HVAC reduced using <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a> fuel splits, <a href='https://www.cbre.com/insights' target='_blank'>CBRE</a> vacancy, <a href='https://www.kastle.com/safety-wellness/getting-america-back-to-work/' target='_blank'>Kastle</a> occupancy for office portion.",
    'Data Center': "No ODCV reduction. Cooling is for equipment heat, not people.",
    'Venue': "HVAC reduced using event schedules, industry utilization data.",
    'Theater': "HVAC reduced using performance schedules, Broadway/regional theater utilization data.",
    'Gym': "HVAC reduced using <a href='https://www.ihrsa.org/' target='_blank'>IHRSA</a> traffic patterns, peak/off-peak utilization data.",
    'Library/Museum': "HVAC reduced using visitor traffic data, collection preservation requirements.",
    'Outpatient Clinic': "HVAC reduced using <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a> fuel splits, <a href='https://www.mgma.com/' target='_blank'>MGMA</a> provider productivity benchmarks.",
    'Bank Branch': "HVAC reduced using <a href='https://www.fdic.gov/' target='_blank'>FDIC</a> transaction trends, branch traffic patterns.",
    'Enclosed Mall': "HVAC reduced using <a href='https://www.icsc.com/' target='_blank'>ICSC</a> and <a href='https://www.placer.ai/' target='_blank'>Placer.ai</a> traffic data, inline vacancy rates.",
    'Strip Mall': "HVAC reduced using <a href='https://www.cbre.com/insights' target='_blank'>CBRE</a>/CoStar vacancy, retail traffic patterns.",
    'Wholesale Club': "HVAC reduced using member traffic data, sales floor vs back-of-house weighting.",
    'Vehicle Dealership': "HVAC reduced using <a href='https://www.nada.org/' target='_blank'>NADA</a> traffic data, showroom vs service bay weighting.",
    'Event Space': "HVAC reduced using event booking schedules, setup/teardown patterns.",
    'Preschool/Daycare': "HVAC reduced using state licensing data, <a href='https://www.naeyc.org/' target='_blank'>NAEYC</a> capacity standards.",
    'Laboratory': "HVAC reduced using <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a> fuel splits. Fume hood makeup air limits ODCV opportunity.",
    'Courthouse': "HVAC reduced using court administration docket data, public area patterns.",
    'default': "HVAC reduced using <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a> fuel splits, building type utilization benchmarks.",
}

# CHANGE column: Human-readable insight (WHY savings exist) by building type
# Sources at end get auto-hyperlinked by inject_source_links()
CHANGE_COLUMN_INSIGHTS = {
    'Office': "Most office space sits empty due to hybrid work and vacancies. Workers come in 2-3 days/week, and many floors have no tenants at all—but HVAC runs full blast regardless. (CBECS 2018, CBRE, Kastle)",
    'Medical Office': "Exam rooms get 2-3x the airflow of regular offices for infection control, but patients are only there for 15-30 minute appointments. Between patients, rooms sit empty but fully ventilated. (CBECS 2018, CBRE, MGMA)",
    'Hotel': "Most hotel rooms sit empty—national average is just 63% occupied. Even booked rooms are empty most of the day while guests are out at meetings, sightseeing, or meals. HVAC conditions empty rooms around the clock. (CBECS 2018, STR)",
    'K-12 School': "Schools are empty most of the year—summers off, weekends, holidays, and after 3pm daily. Buildings ventilate for students who aren't there 70-80% of the time. (CBECS 2018, NCES)",
    'Higher Ed': "Classrooms sit empty most of the year—semester breaks, weekends, summers, and between classes. Even when school's in session, most rooms are unused. (CBECS 2018, NCES)",
    'Retail Store': "Stores are built to handle Black Friday crowds, but most of the day they're nearly empty—slow mornings, quiet afternoons, closed overnight. HVAC runs as if the store were packed. (CBECS 2018, Placer.ai)",
    'Supermarket/Grocery': "Supermarkets run long hours with steadier traffic than most retail, but still swing between busy evenings and empty early mornings. Refrigeration also benefits from lower humidity when fewer people are inside. (CBECS 2018, Placer.ai)",
    'Restaurant/Bar': "Kitchen exhaust fans run non-stop while cooking—that can't change. Savings come from the dining room, which is packed at meal times but empty the rest of the day. (CBECS 2018)",
    'Inpatient Hospital': "Hospitals have limited savings—infection control codes require high airflow in patient areas 24/7. Savings come from admin offices, waiting rooms, and cafeterias that empty at night. (CBECS 2018, AHA, ASHRAE 170)",
    'Specialty Hospital': "Specialty hospitals have limited savings—infection control codes require high airflow in clinical areas around the clock. Savings come from non-clinical spaces during off-hours. (CBECS 2018, AHA, ASHRAE 170)",
    'Residential Care': "Unlike hotels, residents live here 24/7—they don't leave for work or sightseeing. With people present ~95% of the time, there's less empty space to save on. (CBECS 2018, NIC MAP Vision)",
    'Residential Care Facility': "Unlike hotels, residents live here 24/7—they don't leave for work or sightseeing. With people present ~95% of the time, there's less empty space to save on. (CBECS 2018, NIC MAP Vision)",
    'Mixed Use': "The office floors follow hybrid work patterns—workers come in 2-3 days/week, and vacant floors have no tenants at all. Ground-floor retail adds its own traffic variability. (CBECS 2018, CBRE, Kastle)",
    'Data Center': "No savings possible. Cooling removes heat from servers, not people—whether 2 or 20 technicians are present, the cooling load is identical. (CBECS 2018)",
    'Venue': "Arenas and convention centers sit empty 80%+ of the year. A typical arena hosts 60-80 events totaling just 300-400 hours—out of 8,760 hours annually. HVAC conditions empty seats most of the time. (CBECS 2018)",
    'Theater': "Theaters run just 8 shows per week, about 3 hours each—that's 21% of weekly hours at best. The rest of the time, HVAC conditions empty seats for audiences that aren't there. (CBECS 2018)",
    'Gym': "Gyms are packed at 6-8am and 5-8pm, but nearly empty in between. Yet HVAC runs at peak capacity even at 2am when nobody's on the cardio machines. (CBECS 2018, IHRSA)",
    'Library/Museum': "HVAC runs 24/7 to protect books and artwork from humidity, but visitors only occupy the space 10-15% of the time. Climate control never stops; people come and go. (CBECS 2018)",
    'Outpatient Clinic': "Exam rooms are ventilated at medical-grade rates for infection control, but patients only occupy them for 15-30 minute appointments. Between patients, rooms sit empty but fully ventilated. (CBECS 2018, MGMA)",
    'Bank Branch': "Banks are open just 45-50 hours/week, with 20-40 customers per day in spaces designed for lines of 50. Digital banking means fewer visitors, but HVAC runs for a full lobby. (CBECS 2018, FDIC)",
    'Enclosed Mall': "Malls face both vacancy (anchor stores closing) and traffic swings—quiet weekday mornings, busy weekend afternoons. Common areas get fully conditioned whether 100 or 1,000 shoppers are present. (CBECS 2018, ICSC, Placer.ai)",
    'Strip Mall': "Strip malls have tenant turnover (spaces sit empty between leases) plus normal retail traffic swings. Individual rooftop units make it easy to condition only occupied spaces. (CBECS 2018, CBRE, CoStar)",
    'Wholesale Club': "30-40% of the building is back-of-house warehouse with almost nobody in it—just occasional forklift operators restocking shelves. The sales floor itself is only busy on weekends. (CBECS 2018)",
    'Vehicle Dealership': "Showrooms have high ceilings and huge windows conditioning space that averages 40% customer occupancy. Service bays are busier during business hours but close evenings and weekends. (CBECS 2018, NADA)",
    'Event Space': "Banquet halls and conference centers host 2-4 events per week, sitting empty the rest of the time. HVAC conditions empty ballrooms waiting for the next wedding or conference. (CBECS 2018)",
    'Preschool/Daycare': "Daycares run about 60 hours/week for working parents, but rooms designed for 20 kids often have 12-15 present due to rolling drop-offs and pickups. Closed nights and weekends. (CBECS 2018, NAEYC)",
    'Laboratory': "Labs have limited savings—fume hoods require constant exhaust for safety, and the makeup air that replaces it must be conditioned regardless of occupancy. (CBECS 2018)",
    'Courthouse': "Courtrooms sit empty between cases but must recover quickly when sessions begin. Savings come mainly from public waiting areas and admin offices during off-hours. (CBECS 2018)",
    'default': "HVAC conditions space based on design capacity, not actual occupancy. Most buildings are empty more often than people realize. (CBECS 2018)",
}

def get_current_column_tooltip(row):
    """CURRENT column tooltip - explains data source by city."""
    city = safe_val(row, 'loc_city', '')
    state = safe_val(row, 'loc_state', '')

    if city in CITY_DISCLOSURE_LAWS:
        law = CITY_DISCLOSURE_LAWS[city]
        return f"From {law} benchmarking disclosure. Actual metered energy reported by the building."
    elif state == 'CA':
        return "From California AB 802 disclosure. Actual metered energy reported by the building."
    else:
        return "From ENERGY STAR Portfolio Manager or city benchmarking. Actual metered energy."

def get_new_column_tooltip(row):
    """NEW column tooltip - explains methodology + data sources by building type."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    return NEW_COLUMN_SOURCES.get(bldg_type, NEW_COLUMN_SOURCES['default'])

def get_change_column_tooltip(row):
    """CHANGE column tooltip - the WHY punchline by building type."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    return CHANGE_COLUMN_INSIGHTS.get(bldg_type, CHANGE_COLUMN_INSIGHTS['default'])

#===============================================================================
# TOOLTIP DEFINITIONS
#===============================================================================

# Static tooltips - for items that don't need building-specific data
# NOTE: fuel_oil, district_steam, pct_hvac_elec are now DYNAMIC (see DYNAMIC_TOOLTIPS)
TOOLTIPS = {
    'owner': "Building ownership from public records and regulatory filings.",
    # 'energy_site_eui' is now a DYNAMIC tooltip - see get_site_eui_tooltip()
    'carbon_reduction': "Less energy used means less carbon emitted. Emissions calculated from your actual electricity, gas, and steam use—converted using EPA's regional grid emission factors.",
    # Electricity Details section (static explanations)
    'energy_rate': "Cost per kWh of electricity. Varies by utility and rate class. Source: NREL utility rate database.",
    'demand_rate': "Cost per kW of peak demand per month. Utilities charge this to cover infrastructure costs for peak capacity.",
    'peak_demand': "Estimated maximum power draw (kW) at any point. Calculated from annual kWh using load factor.",
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
    ('STR', 'https://str.com/'),
    ('NCES', 'https://nces.ed.gov/'),
    ('AHA Hospital Statistics', 'https://www.aha.org/statistics-trends-reports'),
    ('AHA', 'https://www.aha.org/statistics-trends-reports'),
    ('Placer.ai', 'https://www.placer.ai/'),
    ('MGMA', 'https://www.mgma.com/'),
    ('NIC MAP Vision', 'https://www.nic.org/nic-map-vision/'),
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
    ('NYC Local Law 97', 'https://www.nyc.gov/site/buildings/property-or-business-owner/ll97.page'),
    ('Local Law 97 of 2019', 'https://www.nyc.gov/assets/buildings/local_laws/ll97of2019.pdf'),
    ('Local Law 97', 'https://www.nyc.gov/site/buildings/property-or-business-owner/ll97.page'),
    ('LL97', 'https://www.nyc.gov/site/buildings/property-or-business-owner/ll97.page'),
    ('LL84', 'https://www.nyc.gov/site/buildings/property-or-business-owner/energy-and-water-benchmarking-ll84.page'),

    # BPS Laws - Boston
    ('BERDO 2.0', 'https://www.boston.gov/departments/environment/building-emissions-reduction-and-disclosure'),
    ('BERDO', 'https://www.boston.gov/departments/environment/building-emissions-reduction-and-disclosure'),

    # BPS Laws - Other Cities
    ('Cambridge BEUDO', 'https://www.cambridgema.gov/CDD/zoninganddevelopment/sustainabilityandresilienceprograms/beudo'),
    ('BEUDO', 'https://www.cambridgema.gov/CDD/zoninganddevelopment/sustainabilityandresilienceprograms/beudo'),
    ('DC BEPS', 'https://doee.dc.gov/service/building-energy-performance-standards-beps'),
    ('DC DOEE', 'https://doee.dc.gov/'),
    ('Energize Denver', 'https://www.denvergov.org/Government/Agencies-Departments-Offices/Climate-Action-Sustainability-Resiliency/Energize-Denver'),
    ('Seattle BEPS', 'https://www.seattle.gov/environment/climate-change/buildings-and-energy/building-performance-standards'),
    ('St. Louis BEPS', 'https://www.stlouis-mo.gov/government/departments/public-safety/building/building-performance/'),
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
    """
    Chad-readable ODCV savings explanation.
    Dynamic by building type - explains WHY this building has its specific %.
    Short enough to read aloud, technical enough to sound legit.
    """
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    type_info = BUILDING_TYPE_INFO.get(bldg_type, DEFAULT_BUILDING_INFO)

    odcv_pct = safe_num(row, 'odcv_hvac_savings_pct', 0) or 0
    vacancy = safe_num(row, 'occ_vacancy_rate', 0) or 0
    utilization = safe_num(row, 'occ_utilization_rate', 0) or 0

    floor_pct = type_info.get('floor', 0.15) * 100
    ceiling_pct = type_info.get('ceiling', 0.35) * 100
    uses_vacancy = type_info.get('uses_vacancy', False)
    category = type_info.get('category', 'Single-Tenant')

    # Data Center - special case, no savings
    if bldg_type == 'Data Center':
        return "Data centers: no occupancy-driven savings.\nCooling removes heat from servers, not people.\nA data center at 3am with one tech has the\nsame cooling load as 3pm - occupancy doesn't\nmatter here."

    lines = []

    # Building-type specific explanation
    if bldg_type == 'Office' or bldg_type == 'Medical Office':
        src = " (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>, <a href='https://www.cbre.com/insights' target='_blank'>CBRE</a>, <a href='https://www.kastle.com/safety-wellness/getting-america-back-to-work/' target='_blank'>Kastle</a>)"
        return f"Offices save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC. Office buildings face a double problem: vacant floors with no tenant, plus leased floors where hybrid work means most desks sit empty on any given day. Fire codes and BMS defaults keep ventilation running at full capacity in both—conditioning space for people who aren't there. This building: {odcv_pct*100:.0f}% savings.{src}"

    elif bldg_type == 'K-12 School':
        src = " (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>, <a href='https://nces.ed.gov/' target='_blank'>NCES</a>)"
        return f"Schools save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC—often the highest of any building type. Schools operate roughly 180 days per year for about 7 hours each day. Add summer break, weekends, and holidays, and the building sits empty over half the year—yet HVAC often keeps running at full capacity for maintenance setpoints. This building: {odcv_pct*100:.0f}% savings.{src}"

    elif bldg_type == 'Higher Ed':
        src = " (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>, <a href='https://nces.ed.gov/' target='_blank'>NCES</a>)"
        return f"Universities save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC. Campus buildings have dramatic swings: lecture halls designed for 300 often have 50, classrooms sit empty between periods, and entire buildings clear out for semester breaks and summers. Yet HVAC keeps running at design capacity regardless. This building: {odcv_pct*100:.0f}% savings.{src}"

    elif bldg_type == 'Hotel':
        src = " (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>, <a href='https://str.com/' target='_blank'>STR</a>)"
        return f"Hotels save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC. Most rooms sit empty on any given night, and even checked-in guests spend much of their day out—at meetings, sightseeing, or dining. That means ventilation is conditioning empty rooms most of the time. Also, most hotel gas goes to hot water and kitchens, not HVAC. This building: {odcv_pct*100:.0f}% savings.{src}"

    elif bldg_type == 'Retail Store':
        src = " (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>, <a href='https://www.placer.ai/' target='_blank'>Placer.ai</a>)"
        return f"Retail saves {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC. Customer traffic varies wildly throughout the day—staff-only during opening and closing, quiet mid-mornings, then lunch and evening rushes. ODCV modulates airflow to match actual foot traffic instead of running at peak capacity all day. This building: {odcv_pct*100:.0f}% savings.{src}"

    elif bldg_type == 'Restaurant/Bar':
        src = " (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"
        return f"Restaurants save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC. Dining rooms have predictable meal-time peaks with quiet periods between, but kitchen exhaust runs constantly regardless. Most restaurant gas goes to cooking, not HVAC—so the opportunity is in the dining area ventilation. This building: {odcv_pct*100:.0f}% savings.{src}"

    elif bldg_type == 'Supermarket/Grocery':
        src = " (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>, <a href='https://www.placer.ai/' target='_blank'>Placer.ai</a>)"
        return f"Supermarkets save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC. Long hours and steady customer traffic limit the empty-space opportunity compared to other building types. Also, a large share of grocery store electricity goes to refrigeration, not HVAC—so the savings focus on the sales floor ventilation. This building: {odcv_pct*100:.0f}% savings.{src}"

    elif bldg_type in ['Inpatient Hospital', 'Specialty Hospital']:
        src = " (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>, <a href='https://www.aha.org/' target='_blank'>AHA</a>, <a href='https://www.ashrae.org/' target='_blank'>ASHRAE 170</a>)"
        return f"Hospitals are constrained to {floor_pct:.0f}-{ceiling_pct:.0f}% savings. ASHRAE 170 mandates high air changes in clinical areas for infection control—those rates can't be reduced regardless of occupancy. But hospitals have large non-clinical areas over-ventilated at medical-grade rates around the clock: waiting rooms empty overnight, exam rooms idle between appointments, admin offices with business-hours-only staff. That's where the opportunity lives. This building: {odcv_pct*100:.0f}% savings.{src}"

    elif bldg_type in ['Residential Care', 'Residential Care Facility']:
        src = " (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>, <a href='https://www.nic.org/' target='_blank'>NIC MAP Vision</a>)"
        return f"Residential care facilities save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC. Unlike offices that empty at night, residents live here around the clock—so the empty-space opportunity is limited. Savings come from common areas like dining rooms and activity spaces where occupancy varies throughout the day. This building: {odcv_pct*100:.0f}% savings.{src}"

    elif bldg_type == 'Laboratory':
        src = " (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"
        return f"Labs are constrained to {floor_pct:.0f}-{ceiling_pct:.0f}% savings. Fume hoods require constant exhaust, and many labs maintain negative pressure for safety. These requirements limit how much ventilation can be reduced based on occupancy—safety overrides energy savings. This building: {odcv_pct*100:.0f}% savings.{src}"

    elif bldg_type in ['Theater', 'Venue']:
        src = " (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"
        return f"Venues save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC. Arenas and theaters are empty most of the time—a typical venue hosts maybe 60-80 events per year, leaving the space unused thousands of hours annually. Yet HVAC often runs at or near capacity for maintenance, pre-event conditioning, and building preservation. The opportunity is massive during all that non-event time. This building: {odcv_pct*100:.0f}% savings.{src}"

    elif bldg_type == 'Gym':
        lines.append(f"Gyms save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC.")
        lines.append("Extreme peak/off-peak: 6-8am packed,")
        lines.append("10am-4pm empty, 5-7pm packed again.")
        lines.append("Dead hours at full ventilation = waste.")
        lines.append("")
        lines.append(f"This building: {odcv_pct*100:.0f}% savings")
        return '\n'.join(lines)

    elif bldg_type == 'Mixed Use':
        src = " (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>, <a href='https://www.cbre.com/insights' target='_blank'>CBRE</a>)"
        return f"Mixed-use buildings save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC. These properties—typically office towers with ground-floor retail—run centralized HVAC controlled by the landlord. Vacant floors still get ventilated, and the office floors face the same hybrid-work utilization gap as pure office buildings. The retail and residential portions have their own occupancy patterns layered on top. This building: {odcv_pct*100:.0f}% savings.{src}"

    elif bldg_type == 'Wholesale Club':
        return "Wholesale clubs have large back-of-house warehouse areas with minimal staff—most of the building has very low occupancy compared to the sales floor. (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"

    elif bldg_type in ['Library', 'Museum', 'Library/Museum']:
        return "Libraries and museums have limited public hours with variable visitor traffic. Reading rooms and exhibit halls designed for crowds often have sparse attendance. (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"

    elif bldg_type == 'Outpatient Clinic':
        return "Outpatient clinics have exam rooms that sit empty between appointments. Patients occupy them briefly, then they're vacant until the next visit. (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"

    elif bldg_type == 'Enclosed Mall':
        return "Enclosed malls have high vacancy from anchor store closures. Common areas stay empty on weekday mornings while packed on weekend afternoons. (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"

    elif bldg_type == 'Strip Mall':
        return "Strip malls have tenant turnover leaving spaces vacant. Occupied stores see busy evenings and weekends but slow weekday mornings. (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"

    elif bldg_type in ['Preschool/Daycare', 'Preschool', 'Daycare']:
        return "Daycares have limited hours with rolling drop-off and pickup. Rooms designed for full enrollment rarely have all children present at once. (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"

    elif bldg_type == 'Bank Branch':
        return "Bank branches have limited hours as banking shifts digital. Spaces designed for queues see minimal foot traffic. (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"

    elif bldg_type == 'Vehicle Dealership':
        return "Dealerships have showrooms with variable customer traffic and service bays that only fill during scheduled appointments. (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"

    elif bldg_type == 'Courthouse':
        return "Courthouses have limited savings opportunity—courtrooms sit empty between cases but unpredictable docket schedules make occupancy hard to predict. (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"

    elif bldg_type == 'Public Service':
        return "Public service buildings have variable traffic during business hours. Waiting areas designed for peak crowds often have a fraction of that present. (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"

    elif bldg_type == 'Event Space':
        return "Event spaces sit empty most of the week—bookings are periodic. Between events, rooms designed for hundreds have zero occupancy. (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"

    elif bldg_type in ['Arts & Culture', 'Arts and Culture']:
        return "Arts and cultural venues have periodic performances—auditoriums and rehearsal spaces sit empty between scheduled shows. (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"

    elif bldg_type in ['Sports/Gaming Center', 'Sports Center', 'Gaming Center']:
        return "Sports and gaming centers have sharp traffic peaks—weekend afternoons packed, weekday mornings nearly empty. (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"

    elif bldg_type == 'Public Transit':
        return "Transit stations have limited savings opportunity—rush hour packed, overnight nearly empty, but 24/7 operations limit flexibility. (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"

    elif bldg_type == 'Police Station':
        return "Police stations have limited savings opportunity—24/7 staffing means occupancy never drops to zero across operational areas. (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"

    elif bldg_type == 'Fire Station':
        return "Fire stations have limited savings opportunity—crews are always present and response-ready, so occupancy never drops. (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"

    else:
        # Generic fallback
        src = " (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"
        return f"{bldg_type}s save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC. Most buildings are ventilated at design capacity regardless of how many people are actually inside. ODCV adjusts airflow to match real occupancy, reducing waste during low-traffic periods. This building: {odcv_pct*100:.0f}% savings.{src}"


def get_annual_savings_tooltip(row):
    """Alias for backward compatibility - redirects to new function."""
    return get_odcv_savings_tooltip(row)

def get_property_value_tooltip(row):
    """SALESPERSON TALKING POINTS - data sources for property value calculation."""
    bldg_type = safe_val(row, 'bldg_type', '')
    city = safe_val(row, 'loc_city', '')
    cap_rate_decimal = safe_num(row, 'val_cap_rate_pct', 0.07) or 0.07
    cap_rate_pct = cap_rate_decimal * 100
    multiplier = 1 / cap_rate_decimal if cap_rate_decimal > 0 else 14
    fine_avoided = safe_num(row, 'bps_fine_avoided_yr1_usd', 0) or 0

    # Salesperson talking points about valuation methodology and data sources
    story = f"Cap rate from CBRE Cap Rate Survey Q4 2024—{cap_rate_pct:.1f}% for {bldg_type}s in {city}. "
    story += f"Market-specific and building-type specific, not a national guess. "
    story += f"Income capitalization: every dollar of savings adds {multiplier:.0f}x to asset value (NOI ÷ cap rate). "
    if fine_avoided > 0:
        story += "Avoided BPS fines count the same way—they reduce operating expenses, which increases NOI. "
    story += "Ask the prospect: 'What cap rate did you underwrite?' If different, we adjust the model."
    return story

def get_energy_star_tooltip(row):
    """Brief methodology explanation for Energy Star score."""
    return ("ENERGY STAR® scores rank your building against similar buildings nationwide. "
            "A score of 75+ means you outperform 75% of peers and can apply for EPA certification. "
            "We estimate post-ODCV scores by modeling how HVAC savings reduce your energy use.")

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
    """ROW tooltip - static per building type, no dynamic values. (CBECS 2018)"""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    tooltips = {
        'Data Center': "Data centers use ~42% of electricity for cooling—but it removes server heat, not affected by occupancy. The rest powers IT equipment. (CBECS 2018)",
        'Supermarket/Grocery': "Supermarkets use ~35% of electricity for HVAC. Refrigeration takes 40-50%, with lighting and equipment making up the rest. (CBECS 2018)",
        'Inpatient Hospital': "Hospitals use ~40-45% of electricity for HVAC. Medical imaging, life support, and 24/7 critical systems take the rest. (CBECS 2018)",
        'Specialty Hospital': "Specialty hospitals use ~40-45% of electricity for HVAC. Medical equipment and critical systems take the rest. (CBECS 2018)",
        'Hotel': "Hotels use ~45-50% of electricity for HVAC. Lighting, elevators, laundry, and kitchen equipment take the rest. (CBECS 2018)",
        'Restaurant/Bar': "Restaurants use ~30-35% of electricity for HVAC. Kitchen equipment, refrigeration, and lighting take the bulk. (CBECS 2018)",
        'K-12 School': "Schools use ~45-50% of electricity for HVAC. Lighting, computers, and cafeteria equipment take the rest. (CBECS 2018)",
        'Higher Ed': "Universities use ~45-50% of electricity for HVAC. Labs, computers, and lighting take the rest. (CBECS 2018)",
        'Office': "Offices use ~40-50% of electricity for HVAC. Lighting and plug loads (computers, equipment) take the rest. (CBECS 2018)",
        'Medical Office': "Medical offices use ~45-50% of electricity for HVAC. Medical equipment and lighting take the rest. (CBECS 2018)",
        'Retail Store': "Retail stores use ~40-45% of electricity for HVAC. Lighting is a major load, especially in display-heavy stores. (CBECS 2018)",
    }
    return tooltips.get(bldg_type, "Commercial buildings typically use 40-50% of electricity for HVAC. Lighting and equipment take the rest. (CBECS 2018)")

def get_natural_gas_tooltip(row):
    """ROW tooltip - static per building type, no dynamic values. (CBECS 2018)"""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    tooltips = {
        'Hotel': "Only ~20% of hotel gas goes to HVAC. The rest (~40% hot water, ~33% kitchen cooking) can't be reduced by occupancy controls. (CBECS 2018)",
        'Restaurant/Bar': "Just ~18% of restaurant gas is HVAC. The bulk (~72%) fires cooking equipment—that can't change with occupancy. (CBECS 2018)",
        'Inpatient Hospital': "Hospitals use ~60% of gas for HVAC. The rest goes to sterilization, hot water, and cafeteria. (CBECS 2018)",
        'Specialty Hospital': "Specialty hospitals use ~60% of gas for HVAC. The rest goes to sterilization and hot water. (CBECS 2018)",
        'K-12 School': "Schools use ~80% of gas for heating. The rest is cafeteria cooking and hot water. (CBECS 2018)",
        'Higher Ed': "Universities use ~80% of gas for heating. Labs, cafeterias, and hot water take the rest. (CBECS 2018)",
        'Supermarket/Grocery': "Supermarkets use ~65-75% of gas for HVAC. Bakery ovens and deli equipment take the rest. (CBECS 2018)",
        'Office': "Offices use ~85-90% of gas for heating. Hot water takes the small remainder. (CBECS 2018)",
        'Medical Office': "Medical offices use ~85% of gas for heating. Hot water and sterilization take the rest. (CBECS 2018)",
        'Retail Store': "Retail stores use ~75-80% of gas for heating. Hot water takes the rest. (CBECS 2018)",
        'Data Center': "Data centers use almost no gas for HVAC—cooling is electric. Any gas goes to backup generators or office areas. (CBECS 2018)",
    }
    return tooltips.get(bldg_type, "Commercial buildings typically use 75-85% of gas for heating. Hot water and process loads take the rest. (CBECS 2018)")

def get_fuel_oil_tooltip(row):
    """ROW tooltip - static per building type, no dynamic values. (CBECS 2018)"""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    tooltips = {
        'Inpatient Hospital': "Hospitals use ~50-60% of fuel oil for HVAC. The rest runs backup generators and sterilization equipment. (CBECS 2018)",
        'Specialty Hospital': "Specialty hospitals use ~50-60% of fuel oil for HVAC. Backup generators and sterilization take the rest. (CBECS 2018)",
        'Hotel': "Hotels use ~70-80% of fuel oil for HVAC. The rest heats hot water. (CBECS 2018)",
        'Laboratory': "Labs use only ~12% of fuel oil for HVAC. Most powers backup generators and specialized equipment. (CBECS 2018)",
        'Mixed Use': "Mixed-use buildings use ~10-15% of fuel oil for HVAC. Much goes to backup power. (CBECS 2018)",
        'Residential Care': "Care facilities use ~40-50% of fuel oil for HVAC. Hot water for residents takes the rest. (CBECS 2018)",
        'Retail Store': "Retail stores use ~95%+ of fuel oil for heating—it's almost pure HVAC fuel. (CBECS 2018)",
    }
    return tooltips.get(bldg_type, "Fuel oil is primarily a heating fuel—typically 80-95% goes to HVAC in commercial buildings. (CBECS 2018)")

def get_district_steam_tooltip(row):
    """ROW tooltip - static per building type, no dynamic values. (CBECS 2018)"""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    city = safe_val(row, 'loc_city', '')
    tooltips = {
        'Inpatient Hospital': "Hospitals use ~85-90% of district steam for HVAC. Some runs sterilization equipment. (CBECS 2018)",
        'Specialty Hospital': "Specialty hospitals use ~85-90% of district steam for HVAC. Sterilization takes the rest. (CBECS 2018)",
    }
    # NYC gets special mention of Con Edison
    if 'New York' in city or city == 'NYC':
        base = tooltips.get(bldg_type, "District steam is ~95%+ HVAC—piped from Con Edison's central plants. It's a heating-only fuel. (CBECS 2018)")
        if bldg_type not in tooltips:
            return base
        return tooltips[bldg_type].replace("(CBECS 2018)", "Piped from Con Edison. (CBECS 2018)")
    return tooltips.get(bldg_type, "District steam is ~95%+ HVAC—a heating-only fuel from central plants. (CBECS 2018)")

def get_site_eui_tooltip(row):
    """EUI tooltip - explains what EUI is and provides benchmark context."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    src = " (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"

    # Building type median EUIs from CBECS 2018
    benchmarks = {
        'Office': 70, 'Medical Office': 85, 'Hotel': 95, 'K-12 School': 55,
        'Higher Ed': 90, 'Retail Store': 50, 'Restaurant/Bar': 250,
        'Supermarket/Grocery': 180, 'Inpatient Hospital': 200, 'Specialty Hospital': 180,
        'Data Center': 800, 'Warehouse': 25, 'Residential Care': 100,
        'Residential Care Facility': 100, 'Mixed Use': 75, 'default': 70
    }
    type_benchmark = benchmarks.get(bldg_type, benchmarks['default'])

    return f"Energy Use Intensity measures total annual energy per square foot. Formula: EUI = Annual Energy (kBtu) ÷ Building Area (sq ft). Lower values mean better efficiency. {bldg_type} median: ~{type_benchmark} kBtu/sq ft/year.{src}"

def get_hvac_pct_tooltip(row):
    """Brief tooltip for HVAC percentage."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    return f"% of energy used by HVAC for {bldg_type}s. Adjusted for age, efficiency, and climate. (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>EIA CBECS 2018</a>)"

def get_load_factor_tooltip(row):
    """Load factor tooltip - concise explanation with building-specific context."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    load_factor = safe_num(row, 'cost_elec_load_factor', 0) or 0
    type_info = BUILDING_TYPE_INFO.get(bldg_type, DEFAULT_BUILDING_INFO)
    typical_lf = type_info.get('load_factor', 0.45) * 100
    src = " (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>)"

    # Building type context
    context = {
        'Data Center': "constant 24/7 server loads",
        'Inpatient Hospital': "24/7 medical operations",
        'Specialty Hospital': "24/7 medical operations",
        'Supermarket/Grocery': "long hours, refrigeration loads",
        'Office': "9-5 peaks, nights and weekends low",
        'K-12 School': "empty summers and evenings",
        'Higher Ed': "semester schedules, breaks empty",
        'Hotel': "guest patterns, variable occupancy",
        'default': "operating schedule patterns"
    }
    type_context = context.get(bldg_type, context['default'])

    return f"Load factor measures how consistently a building uses electricity (average load ÷ peak load). Higher values mean steadier usage. This building: {load_factor*100:.0f}% ({bldg_type}s typically {typical_lf:.0f}% due to {type_context}). Used to estimate peak demand for utility billing.{src}"

def get_total_ghg_tooltip(row):
    """Dynamic tooltip explaining total GHG emissions calculation."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    city = safe_val(row, 'loc_city', '')

    # Get values
    ghg = safe_num(row, 'carbon_emissions_total_mt', 0) or 0
    elec_kwh = safe_num(row, 'energy_elec_kwh', 0) or 0
    gas_kbtu = safe_num(row, 'energy_gas_kbtu', 0) or 0

    lines = []
    lines.append("HOW GHG EMISSIONS ARE CALCULATED")
    lines.append("=" * 33)

    lines.append("")
    lines.append("FORMULA:")
    lines.append("  (Elec kWh × grid factor) +")
    lines.append("  (Gas kBtu × gas factor) +")
    lines.append("  (Steam/Oil × their factors)")

    lines.append("")
    lines.append("EMISSION FACTORS BY REGION:")
    lines.append("  Seattle: 0.000003 (98% hydro)")
    lines.append("  NYC: 0.000085 (mixed grid)")
    lines.append("  Denver: 0.000138 (coal region)")
    lines.append("  Chicago: 0.000165 (coal heavy)")

    if ghg > 0:
        lines.append("")
        lines.append(f"THIS BUILDING: {ghg:,.1f} tCO2e/yr")

    lines.append("")
    lines.append("(Source: <a href='https://www.epa.gov/egrid' target='_blank'>EPA eGRID 2023</a>)")

    return '\n'.join(lines)

def get_carbon_reduction_tooltip(row):
    """Brief explanation of carbon emissions calculation methodology."""
    return "Carbon emissions from electricity vary dramatically by region—Seattle's hydro grid produces 29x less carbon per kWh than coal-heavy St. Louis. Gas emissions are standard combustion rates. We use EPA eGRID regional factors for your building's location. (EPA eGRID 2023)"

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
        return f"{law} provides {bldg_type}s alternative compliance pathways."

    if sqft > 0 and sqft < min_sqft:
        return f"{law} covers buildings over {min_sqft:,} sqft—this one's below threshold."

    if city == 'New York':
        return "NYC Local Law 97 sets annual carbon emission limits for buildings over 25,000 sqft. Buildings exceeding the cap pay $268 per metric ton over the limit. ODCV reduces emissions by cutting HVAC energy waste—which directly lowers your carbon footprint and fine exposure. (NYC Local Law 97)"
    elif city == 'Boston':
        return "Boston's BERDO 2.0 sets emissions limits for buildings over 20,000 sqft with penalties of $234 per excess metric ton annually. ODCV reduces emissions by cutting the electricity and gas that generate them. (BERDO 2.0)"
    elif city == 'Cambridge':
        return "Cambridge BEUDO mirrors Boston's BERDO—$234 per ton penalties for excess emissions. ODCV reduces emissions proportionally to energy savings. (Cambridge BEUDO)"
    elif city == 'Washington':
        return "DC BEPS requires buildings over 50,000 sqft to meet an ENERGY STAR score of 71. Buildings below face fines up to $10/sqft (max $7.5M), prorated by how far below target you score. ODCV improves your score by reducing energy use. (DC BEPS)"
    elif city == 'Denver':
        return "Energize Denver fines buildings $0.30 per kBtu per sqft over their EUI target. A building 10 kBtu/sqft over target pays about $3/sqft annually. ODCV directly lowers EUI by reducing HVAC energy waste. (Energize Denver)"
    elif city == 'Seattle':
        return "Seattle BEPS sets emissions intensity targets with penalties up to $10/sqft per 5-year cycle. Since Seattle's grid is 98% hydroelectric, most building emissions come from natural gas—making HVAC gas reduction especially impactful. (Seattle Clean Buildings Act)"
    elif city == 'St. Louis':
        return "St. Louis BEPS sets EUI targets with daily fines of $500 for non-compliance after the grace period—that's $182,500 per year. (St. Louis BEPS)"

    return f"Currently compliant with {law}."


def get_utility_cost_savings_tooltip(row):
    """Brief tooltip for utility cost savings methodology."""
    return "Annual dollar savings from conditioning less empty space. Energy usage comes from city benchmarking filings (LL84, BERDO, etc.) or EPA Portfolio Manager. We determine what portion is HVAC for your building type, apply your ODCV savings rate, then multiply by local utility rates (including taxes and distribution fees). (CBECS 2018, EIA, NREL Utility Rate Database)"


def get_odcv_methodology_tooltip(row):
    """SALES CALL READY tooltip for ODCV Savings % row.

    Chad reads this when energy nerd asks "how did you
    calculate that percentage?" Uses vertical language + formula.
    """
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    type_info = BUILDING_TYPE_INFO.get(bldg_type, DEFAULT_BUILDING_INFO)

    odcv_pct = safe_num(row, 'odcv_hvac_savings_pct', 0) or 0
    vacancy = safe_num(row, 'occ_vacancy_rate', 0) or 0
    utilization = safe_num(row, 'occ_utilization_rate', 0) or 0

    floor_pct = type_info.get('floor', 0.15) * 100
    ceiling_pct = type_info.get('ceiling', 0.35) * 100

    lines = []
    lines.append(f"WHY {odcv_pct*100:.0f}% HVAC SAVINGS?")
    lines.append("")
    lines.append(f"{bldg_type}s: {floor_pct:.0f}-{ceiling_pct:.0f}% typical")
    lines.append("")

    # Building-type explanation in VERTICAL LANGUAGE
    if bldg_type == 'Data Center':
        lines.append("Data centers cool servers, not people.")
        lines.append("Occupancy doesn't affect cooling load.")
        lines.append("ODCV savings: 0%")
        return '\n'.join(lines)

    if bldg_type in ['Office', 'Medical Office', 'Mixed Use']:
        lines.append("THE OPPORTUNITY:")
        if vacancy > 0:
            lines.append(f"  {vacancy*100:.0f}% vacancy (floors still ventilated)")
        if utilization > 0:
            lines.append(f"  {utilization*100:.0f}% utilization (hybrid work)")
        lines.append("")
        lines.append("HVAC runs like building is full")
        lines.append("even when it's half empty.")

    elif bldg_type == 'K-12 School':
        empty_pct = (1 - utilization) * 100 if utilization else 55
        lines.append("THE OPPORTUNITY:")
        lines.append(f"  {empty_pct:.0f}% of year classrooms empty:")
        lines.append("  • After 3pm daily")
        lines.append("  • Weekends")
        lines.append("  • 10+ weeks summer")
        lines.append("")
        lines.append("Highest ceiling (45%) of any type.")

    elif bldg_type == 'Hotel':
        occ = utilization * 100 if utilization else 70
        lines.append("THE OPPORTUNITY:")
        lines.append(f"  {occ:.0f}% room occupancy typical")
        lines.append("  + Guests out during day")
        lines.append("  + Checkout gaps")
        lines.append("")
        lines.append("Room HVAC can match actual guests.")

    elif bldg_type in ['Inpatient Hospital', 'Specialty Hospital']:
        lines.append("CONSTRAINED BY CODE:")
        lines.append("  ASHRAE 170: 15-25 air changes/hr")
        lines.append("  in ORs regardless of occupancy.")
        lines.append("")
        lines.append("Only non-clinical areas qualify.")
        lines.append(f"Max achievable: {ceiling_pct:.0f}%")

    elif bldg_type == 'Retail Store':
        lines.append("THE OPPORTUNITY:")
        lines.append("  Traffic varies throughout day:")
        lines.append("  opening, mid-morning lull, rushes")
        lines.append("")
        lines.append("ODCV matches actual customer traffic.")

    elif bldg_type == 'Gym':
        lines.append("THE OPPORTUNITY:")
        lines.append("  Extreme peak/off-peak:")
        lines.append("  6-8am packed, 10am-4pm empty")
        lines.append("")
        lines.append("Ventilating empty gym = pure waste.")

    elif bldg_type in ['Theater', 'Venue']:
        lines.append("THE OPPORTUNITY:")
        lines.append("  Empty for hours/days between events")
        lines.append("  then full capacity for shows.")
        lines.append("")
        lines.append("Highest variability = high savings.")

    else:
        if utilization > 0:
            empty_pct = (1 - utilization) * 100
            lines.append(f"THE OPPORTUNITY:")
            lines.append(f"  {empty_pct:.0f}% underutilized")
        lines.append("")
        lines.append("ODCV adjusts to actual occupancy.")

    lines.append("")
    lines.append(f"This building: {odcv_pct*100:.0f}%")
    lines.append("")
    lines.append("CALCULATION:")
    lines.append(f"  Floor ({floor_pct:.0f}%) + opportunity score × range")
    lines.append("  Adjusted for climate zone and building efficiency.")
    return '\n'.join(lines)

# Map of dynamic tooltip keys to their generator functions
DYNAMIC_TOOLTIPS = {
    # Impact Section - SALES CALL READY
    'utility_cost_savings': get_utility_cost_savings_tooltip,  # For Utility Cost row - $ talk OK
    'odcv_methodology': get_odcv_methodology_tooltip,  # For ODCV Savings % explanation
    'property_value_increase': get_property_value_tooltip,
    'fine_avoidance': get_fine_avoidance_tooltip,
    'energy_star_score': get_energy_star_tooltip,
    'carbon_reduction': get_carbon_reduction_tooltip,  # NEW: storytelling carbon tooltip
    # Legacy - keep for backward compatibility
    'annual_savings': get_annual_savings_tooltip,
    # Energy Table - ENERGY SAVINGS ONLY (no $ talk)
    'energy_elec_kwh': get_electricity_kwh_tooltip,
    'natural_gas': get_natural_gas_tooltip,
    'fuel_oil': get_fuel_oil_tooltip,
    'district_steam': get_district_steam_tooltip,
    'energy_site_eui': get_site_eui_tooltip,  # NEW: dynamic Site EUI tooltip
    'pct_hvac_elec': get_hvac_pct_tooltip,
    # Electricity Details
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
    """Generate tooltip HTML span. If row is provided and key is dynamic, generates contextual tooltip."""
    # Check if this is a dynamic tooltip that needs row data
    if key in DYNAMIC_TOOLTIPS and row is not None:
        text = DYNAMIC_TOOLTIPS[key](row)
    else:
        text = TOOLTIPS.get(key, '')

    if not text:
        return ''

    # Inject hyperlinks into source references
    html_text = inject_source_links(text)

    return f'<span class="info-tooltip" style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background: linear-gradient(135deg, #0066cc 0%, #004494 100%); color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i<span class="tooltip-content">{html_text}</span></span>'

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
    back_btn = '''<a href="../index.html" onclick="event.preventDefault(); const from = new URLSearchParams(window.location.search).get('from'); window.location.href = '../index.html' + (from === 'cities' ? '#all-buildings' : '#portfolios');" style="position:absolute;left:10px;top:50%;transform:translateY(-50%);color:white;text-decoration:none;font-size:14px;font-weight:600;display:flex;align-items:center;gap:6px;padding:8px 14px;background:rgba(0,0,0,0.3);border-radius:6px;z-index:10;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
        Back
    </a>'''

    html = f"""
    <div class="hero" style="position:relative;text-align:center;padding:20px 80px;">
        {back_btn}
        <h1 style="margin-bottom:0;">{escape(address)}</h1>
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
        html += f"<tr><td>Utility</td><td>{escape(utility)}</td></tr>\n"

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
            html += f'<tr><td>LEED</td><td><a href="{escape(leed_url)}" target="_blank" class="org-logo" data-org-name="LEED {escape(leed_level)}"><img src="{logo_url}" alt="LEED {escape(leed_level)}" style="height:40px;max-width:150px;object-fit:contain;" onerror="this.parentElement.className=\'\';this.parentElement.removeAttribute(\'data-org-name\');this.style.display=\'none\';this.nextElementSibling.style.display=\'inline\';"><span style="display:none;color:#059669;font-weight:600;">{escape(leed_level)}</span></a></td></tr>\n'
        else:
            html += f'<tr><td>LEED</td><td><span class="org-logo" data-org-name="LEED {escape(leed_level)}"><img src="{logo_url}" alt="LEED {escape(leed_level)}" style="height:40px;max-width:150px;object-fit:contain;" onerror="this.parentElement.className=\'\';this.parentElement.removeAttribute(\'data-org-name\');this.style.display=\'none\';this.nextElementSibling.style.display=\'inline\';"><span style="display:none;color:#059669;font-weight:600;">{escape(leed_level)}</span></span></td></tr>\n'

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

    # Electricity
    if elec_kwh:
        current_val = elec_kwh
        new_val = elec_kwh_post
        current_str = f"{format_number(current_val)} kWh"
        new_str = f"{format_number(new_val)} kWh" if new_val else "—"
        if new_val and current_val:
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

    # Natural Gas
    if gas_use and gas_use > 0:
        gas_therms = gas_use / 100
        gas_therms_post = gas_post / 100 if gas_post else None
        current_str = f"{format_number(gas_therms)} therms"
        new_str = f"{format_number(gas_therms_post)} therms" if gas_therms_post else "—"
        if gas_therms_post:
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

    # Fuel Oil
    if fuel_use and fuel_use > 0:
        fuel_gal = fuel_use / 138.5
        fuel_gal_post = fuel_post / 138.5 if fuel_post else None
        current_str = f"{format_number(fuel_gal)} gallons"
        new_str = f"{format_number(fuel_gal_post)} gallons" if fuel_gal_post else "—"
        if fuel_gal_post:
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

    # District Steam
    if steam_use and steam_use > 0:
        steam_mlb = steam_use / 1194
        steam_mlb_post = steam_post / 1194 if steam_post else None
        current_str = f"{format_number(steam_mlb, 2)} Mlb"
        new_str = f"{format_number(steam_mlb_post, 2)} Mlb" if steam_mlb_post else "—"
        if steam_mlb_post:
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
    current_es = safe_num(row, 'energy_star_score')
    post_es = safe_num(row, 'energy_star_score_post_odcv')
    if current_es:
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
                pct = (change / current_es) * 100
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
    if carbon_current and carbon_post:
        carbon_reduction = carbon_current - carbon_post
        pct = (carbon_reduction / carbon_current) * 100
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
