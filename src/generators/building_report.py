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
    'Office': "HVAC reduced using CBECS fuel splits, CBRE/Cushman vacancy rates, Kastle badge-swipe occupancy data.",
    'Medical Office': "HVAC reduced using CBECS fuel splits, CBRE vacancy data, MGMA exam room utilization benchmarks.",
    'Hotel': "HVAC reduced using CBECS fuel splits, STR room occupancy data, guest presence patterns.",
    'K-12 School': "HVAC reduced using CBECS fuel splits, NCES instructional day requirements, state calendar data.",
    'Higher Ed': "HVAC reduced using CBECS fuel splits, NCES data, semester and break schedules.",
    'Retail Store': "HVAC reduced using CBECS fuel splits, Placer.ai foot traffic data.",
    'Supermarket/Grocery': "HVAC reduced using CBECS fuel splits, Placer.ai traffic patterns.",
    'Restaurant/Bar': "HVAC reduced using CBECS fuel splits. Kitchen exhaust excluded—only dining area HVAC.",
    'Inpatient Hospital': "HVAC reduced using CBECS fuel splits, AHA bed occupancy data. ASHRAE 170 limits applied.",
    'Specialty Hospital': "HVAC reduced using CBECS fuel splits, AHA bed occupancy data. ASHRAE 170 limits applied.",
    'Residential Care': "HVAC reduced using CBECS fuel splits, NIC MAP Vision occupancy data.",
    'Residential Care Facility': "HVAC reduced using CBECS fuel splits, NIC MAP Vision occupancy data.",
    'Mixed Use': "HVAC reduced using CBECS fuel splits, CBRE vacancy, Kastle occupancy for office portion.",
    'Data Center': "No ODCV reduction. Cooling is for equipment heat, not people.",
    'Venue': "HVAC reduced using event schedules, industry utilization data.",
    'Theater': "HVAC reduced using performance schedules, Broadway/regional theater utilization data.",
    'Gym': "HVAC reduced using IHRSA traffic patterns, peak/off-peak utilization data.",
    'Library/Museum': "HVAC reduced using visitor traffic data, collection preservation requirements.",
    'Outpatient Clinic': "HVAC reduced using CBECS fuel splits, MGMA provider productivity benchmarks.",
    'Bank Branch': "HVAC reduced using FDIC transaction trends, branch traffic patterns.",
    'Enclosed Mall': "HVAC reduced using ICSC and Placer.ai traffic data, inline vacancy rates.",
    'Strip Mall': "HVAC reduced using CBRE/CoStar vacancy, retail traffic patterns.",
    'Wholesale Club': "HVAC reduced using member traffic data, sales floor vs back-of-house weighting.",
    'Vehicle Dealership': "HVAC reduced using NADA traffic data, showroom vs service bay weighting.",
    'Event Space': "HVAC reduced using event booking schedules, setup/teardown patterns.",
    'Preschool/Daycare': "HVAC reduced using state licensing data, NAEYC capacity standards.",
    'Laboratory': "HVAC reduced using CBECS fuel splits. Fume hood makeup air limits ODCV opportunity.",
    'Courthouse': "HVAC reduced using court administration docket data, public area patterns.",
    'default': "HVAC reduced using CBECS fuel splits, building type utilization benchmarks.",
}

# CHANGE column: Key insight (WHY) by building type - short punchlines
CHANGE_COLUMN_INSIGHTS = {
    'Office': "Hybrid work + vacancy = 50-60% of ventilation goes to empty space.",
    'Medical Office': "Exam rooms get 2-3x airflow but sit empty between appointments.",
    'Hotel': "63% room occupancy × 45% guest presence = 72% of ventilation wasted.",
    'K-12 School': "180 days × 7 hours = building empty 72-80% of the year.",
    'Higher Ed': "32 weeks in session, 35% classroom use = empty 70-76% of time.",
    'Retail Store': "Built for peak crowds but averages 35-45% capacity.",
    'Supermarket/Grocery': "Long hours with steady traffic. Peaks 80-100%, lulls 15-30%.",
    'Restaurant/Bar': "Kitchen exhaust can't change—savings from dining area (60% of building).",
    'Inpatient Hospital': "Limited opportunity. Savings from admin areas, not clinical spaces.",
    'Specialty Hospital': "Limited opportunity. Savings from admin areas, not clinical spaces.",
    'Residential Care': "Residents present 24/7 (~95%). Limited empty-space opportunity.",
    'Residential Care Facility': "Residents present 24/7 (~95%). Limited empty-space opportunity.",
    'Mixed Use': "Office vacancy + hybrid work patterns apply to commercial floors.",
    'Data Center': "Zero savings. Cooling removes server heat regardless of occupancy.",
    'Venue': "Empty 80%+ of the time. 60-80 events/year = just 300-400 hours of use.",
    'Theater': "8 shows/week × 3 hours = just 21% of weekly hours in use.",
    'Gym': "Packed 6-8am and 5-8pm, nearly empty between. Peak ventilation runs at 2am.",
    'Library/Museum': "Preservation HVAC runs 24/7 but visitors occupy space just 10-15%.",
    'Outpatient Clinic': "Exam rooms ventilated at medical rates, occupied just 25-35% of hours.",
    'Bank Branch': "Open just 45-50 hours/week. 20-40 customers/day in spaces designed for 50.",
    'Enclosed Mall': "Vacancy 15-30%, weekday mornings 10-20%, weekend peaks 60-80%.",
    'Strip Mall': "Individual tenant turnover + retail traffic variability.",
    'Wholesale Club': "30-40% of building is back-of-house with almost nobody in it.",
    'Vehicle Dealership': "Showrooms (40% capacity average) + service bays (60-70% during hours).",
    'Event Space': "2-4 events/week = spaces empty 80%+ of the time.",
    'Preschool/Daycare': "Open ~60 hours/week. Rooms designed for 20 often have 12-15 present.",
    'Laboratory': "Fume hoods require constant exhaust. Limited ODCV opportunity.",
    'Courthouse': "Courtrooms 50-60% utilized. Savings from public waiting areas.",
    'default': "HVAC portion reduced based on building occupancy patterns.",
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
    'owner': "Sources: ENERGY STAR Portfolio Manager, city benchmarking filings, CoStar, SEC 10-K, corporate websites.",
    # 'energy_site_eui' is now a DYNAMIC tooltip - see get_site_eui_tooltip()
    'carbon_reduction': "Less energy used means less carbon emitted. Emissions calculated from your actual electricity, gas, and steam use—converted using EPA's regional grid emission factors.",
    # Electricity Details section (static explanations)
    'energy_rate': "Cost per kWh of electricity. Varies by utility and rate class. Source: NREL utility rate database.",
    'demand_rate': "Cost per kW of peak demand per month. Utilities charge this to cover infrastructure costs for peak capacity.",
    'peak_demand': "Estimated maximum power draw (kW) at any point. Calculated from annual kWh using load factor.",
    'utility_provider': "Electric utility serving this building's location. Rates from NREL utility rate database by ZIP code.",
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
        lines.append(f"Offices save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC.")
        if vacancy > 0 and utilization > 0:
            lines.append(f"This one's {vacancy*100:.0f}% vacant and only {utilization*100:.0f}%")
            lines.append("occupied when leased - that's hybrid work.")
        lines.append("Vacant floors still get full ventilation")
        lines.append("due to fire code and BMS limits.")
        lines.append("ODCV adjusts to actual occupancy.")

    elif bldg_type == 'K-12 School':
        lines.append(f"Schools save {floor_pct:.0f}-{ceiling_pct:.0f}% - highest of any")
        lines.append("building type. Empty after 3pm, weekends")
        lines.append("off, 10+ weeks summer. That's over half")
        lines.append("the year with no one inside but HVAC")
        lines.append("still running at full capacity.")

    elif bldg_type == 'Higher Ed':
        lines.append(f"Universities save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC.")
        lines.append("Semester breaks, variable class schedules,")
        lines.append("summer sessions. Buildings sit empty while")
        lines.append("HVAC runs at design capacity.")

    elif bldg_type == 'Hotel':
        lines.append(f"Hotels save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC.")
        lines.append("Room-level controls adjust to actual guests -")
        lines.append("typically 65-75% occupancy. Note: only 20%")
        lines.append("of gas is HVAC here. Rest is hot water (42%)")
        lines.append("and kitchen (33%).")

    elif bldg_type == 'Retail Store':
        lines.append(f"Retail saves {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC.")
        lines.append("Intra-day variability: opening/closing with")
        lines.append("staff only, mid-morning lulls, lunch and")
        lines.append("evening rushes. ODCV modulates to actual")
        lines.append("customer traffic.")

    elif bldg_type == 'Restaurant/Bar':
        lines.append(f"Restaurants save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC.")
        lines.append("Predictable meal-time peaks but kitchen")
        lines.append("runs constant regardless. Note: only 18%")
        lines.append("of gas is HVAC - 72% is cooking.")

    elif bldg_type == 'Supermarket/Grocery':
        lines.append(f"Supermarkets save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC.")
        lines.append("Long hours with steady traffic limits empty-")
        lines.append("space opportunity. Note: ~40% of electricity")
        lines.append("is refrigeration, not HVAC.")

    elif bldg_type in ['Inpatient Hospital', 'Specialty Hospital']:
        lines.append(f"Hospitals are constrained to {floor_pct:.0f}-{ceiling_pct:.0f}% savings.")
        lines.append("Clinical areas need constant high airflow")
        lines.append("for infection control (ASHRAE 170). Savings")
        lines.append("come from lobbies, offices, and admin spaces.")

    elif bldg_type in ['Residential Care', 'Residential Care Facility']:
        lines.append(f"Residential care: {floor_pct:.0f}-{ceiling_pct:.0f}% savings.")
        lines.append("Residents live here 24/7 - unlike offices")
        lines.append("that empty at night. Savings come from")
        lines.append("common areas with variable occupancy.")

    elif bldg_type == 'Laboratory':
        lines.append(f"Labs are constrained to {floor_pct:.0f}-{ceiling_pct:.0f}% savings.")
        lines.append("Fume hoods require constant exhaust. Many")
        lines.append("labs maintain negative pressure. Safety")
        lines.append("requirements override occupancy sensing.")

    elif bldg_type in ['Theater', 'Venue']:
        lines.append(f"Venues save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC.")
        lines.append("Extreme variability - empty for hours or")
        lines.append("days, then full capacity for events.")
        lines.append("High opportunity during non-event periods.")

    elif bldg_type == 'Gym':
        lines.append(f"Gyms save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC.")
        lines.append("Extreme peak/off-peak: 6-8am packed,")
        lines.append("10am-4pm empty, 5-7pm packed again.")
        lines.append("Dead hours at full ventilation = waste.")

    elif bldg_type == 'Mixed Use':
        lines.append(f"Mixed-use saves {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC.")
        if vacancy > 0:
            lines.append(f"Currently {vacancy*100:.0f}% vacant. Combination of")
        else:
            lines.append("Combination of office, retail, residential.")
        lines.append("Savings vary by tenant mix but centralized")
        lines.append("systems still ventilate vacant spaces.")

    else:
        # Generic fallback
        lines.append(f"{bldg_type}s save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC.")
        lines.append("ODCV adjusts ventilation to actual")
        lines.append("occupancy instead of design capacity.")

    # Add this building's result
    lines.append("")
    lines.append(f"This building: {odcv_pct*100:.0f}% savings")

    return '\n'.join(lines)


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
    """SALESPERSON TALKING POINTS - data sources for Energy Star score."""
    bldg_type = safe_val(row, 'bldg_type', '')
    current_score = safe_num(row, 'energy_star_score', 0) or 0
    eui = safe_num(row, 'energy_site_eui', 0) or 0
    benchmark = safe_num(row, 'energy_eui_benchmark', 0) or 0

    story = f"Score from EPA Portfolio Manager—percentile rank vs all {bldg_type}s nationally. "
    story += f"Benchmark EUI ({benchmark:.0f} kBtu/sqft median) from CBECS 2018 Commercial Buildings Survey by building type. "

    if current_score >= 75:
        story += f"At {current_score:.0f}, already ENERGY STAR certified territory. Pitch: 'Maintain or improve your competitive position.' "
    elif current_score >= 50:
        story += f"At {current_score:.0f}, above median but 25 points from certification. Pitch: 'ODCV could get you there—that's a marketing asset.' "
    else:
        story += f"At {current_score:.0f}, below median. Pitch: 'Every competitor {bldg_type} scores higher—tenants notice.' "

    story += "ODCV improves score by lowering source energy, which is what EPA's regression model weighs."

    return story

def get_electricity_kwh_tooltip(row):
    """ROW tooltip - explains what % of electricity is HVAC (the saveable portion)."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    hvac_pct = safe_num(row, 'hvac_pct_elec', 0) or 0
    non_hvac = 100 - (hvac_pct * 100)

    if bldg_type == 'Data Center':
        return f"HVAC is only {hvac_pct*100:.0f}% of electricity here—the rest ({non_hvac:.0f}%) powers servers and IT equipment. Cooling is driven by server heat loads, not human occupancy. No ODCV opportunity."
    elif bldg_type in ['Supermarket/Grocery']:
        return f"HVAC drives {hvac_pct*100:.0f}% of electricity. The other {non_hvac:.0f}% is refrigeration cases (run 24/7 regardless of shoppers), lighting, and checkout equipment. ODCV only affects the HVAC portion."
    elif bldg_type in ['Inpatient Hospital', 'Specialty Hospital']:
        return f"HVAC accounts for {hvac_pct*100:.0f}% of electricity. The rest powers medical imaging, life support, and 24/7 critical systems. ODCV savings come from non-clinical areas—waiting rooms, admin offices, cafeterias."
    elif bldg_type == 'Hotel':
        return f"HVAC drives {hvac_pct*100:.0f}% of electricity—cooling and ventilating 24/7 whether guests are in-room or not. The rest is lighting, elevators, laundry, and kitchen equipment."
    elif bldg_type in ['Restaurant/Bar']:
        return f"HVAC is {hvac_pct*100:.0f}% of electricity. Kitchen equipment, walk-in refrigeration, and lighting take the rest. ODCV affects dining area HVAC—not kitchen exhaust hoods, which must run at full blast during cooking."
    elif bldg_type in ['K-12 School', 'Higher Ed']:
        return f"HVAC drives {hvac_pct*100:.0f}% of electricity—cooling classrooms, gyms, auditoriums, and cafeterias. The rest is lighting, computers, and food service. Big savings potential because schools sit empty 70-80% of the year."
    else:
        return f"HVAC accounts for {hvac_pct*100:.0f}% of this building's electricity—chillers, cooling towers, air handlers, and ventilation fans. The remaining {non_hvac:.0f}% goes to lighting, plug loads, elevators, and equipment that runs regardless of occupancy."

def get_natural_gas_tooltip(row):
    """ROW tooltip - explains what % of gas is HVAC (heating) vs other uses."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    hvac_pct = safe_num(row, 'hvac_pct_gas', 0) or 0
    non_hvac = 100 - (hvac_pct * 100)

    if bldg_type == 'Hotel':
        return f"Only {hvac_pct*100:.0f}% of hotel gas goes to HVAC (space heating). The other {non_hvac:.0f}% heats domestic hot water for showers and laundry, plus kitchen cooking. ODCV can only reduce the heating portion."
    elif bldg_type in ['Restaurant/Bar']:
        return f"Just {hvac_pct*100:.0f}% of gas is HVAC here. The bulk ({non_hvac:.0f}%) fires cooking equipment—ranges, ovens, grills, fryers. Kitchen gas isn't occupancy-driven; ODCV only affects space heating."
    elif bldg_type in ['Inpatient Hospital', 'Specialty Hospital']:
        return f"HVAC accounts for {hvac_pct*100:.0f}% of gas. The rest goes to sterilization equipment, domestic hot water, and cafeteria kitchens—all running regardless of patient census."
    elif bldg_type in ['K-12 School', 'Higher Ed']:
        return f"Heating drives {hvac_pct*100:.0f}% of gas use. The rest is cafeteria cooking and domestic hot water. With buildings empty 70-80% of the year (nights, weekends, summer), heating empty classrooms is pure waste."
    elif bldg_type in ['Supermarket/Grocery']:
        return f"HVAC is {hvac_pct*100:.0f}% of gas. Some stores use gas for heating; the rest goes to bakery ovens and deli equipment. Refrigeration is electric, not gas."
    else:
        return f"Heating accounts for {hvac_pct*100:.0f}% of this building's gas use—boilers and furnaces warming outdoor air brought in for ventilation. The remaining {non_hvac:.0f}% typically goes to domestic hot water and any process loads."

def get_fuel_oil_tooltip(row):
    """ROW tooltip - explains what % of fuel oil is HVAC (nearly all of it)."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    hvac_pct = safe_num(row, 'hvac_pct_fuel_oil', 0) or 0

    # Fuel oil is almost entirely heating - unlike gas which has cooking/DHW competition
    if hvac_pct >= 0.90:
        return f"Fuel oil is almost pure heating fuel—{hvac_pct*100:.0f}% goes directly to HVAC. Unlike natural gas, there's no cooking or hot water competing for it. When you reduce ventilation, you reduce heating load dollar-for-dollar."
    elif bldg_type in ['Inpatient Hospital', 'Specialty Hospital']:
        return f"In hospitals, {hvac_pct*100:.0f}% of fuel oil is HVAC. The rest runs backup generators and sterilization. Clinical areas have fixed ventilation requirements, but lobbies and admin spaces can reduce heating when empty."
    elif bldg_type == 'Hotel':
        return f"Hotels use {hvac_pct*100:.0f}% of fuel oil for HVAC. Some older hotels still use oil-fired boilers for both heating and domestic hot water—guest showers run regardless of ODCV."
    else:
        return f"Fuel oil is a heating-only fuel—{hvac_pct*100:.0f}% goes to HVAC in this building. No cooking, no process loads competing. Every CFM of outdoor air you don't heat is oil you don't burn."

def get_district_steam_tooltip(row):
    """ROW tooltip - explains that district steam is almost entirely HVAC (heating)."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    city = safe_val(row, 'loc_city', '')
    hvac_pct = safe_num(row, 'hvac_pct_steam', 0) or 0

    # NYC has the largest district steam system in the US
    if 'New York' in city or city == 'NYC':
        return f"District steam is {hvac_pct*100:.0f}% HVAC—a heating-only fuel piped from Con Edison's central plants (the largest district steam system in the US). No cooking, no process loads. When you ventilate less, you heat less outdoor air."
    elif bldg_type in ['Inpatient Hospital', 'Specialty Hospital']:
        return f"In hospitals, {hvac_pct*100:.0f}% of district steam goes to HVAC. Some steam may also run sterilization equipment—but the vast majority heats ventilation air and building spaces."
    else:
        return f"District steam is {hvac_pct*100:.0f}% HVAC—a heating-only fuel piped from central utility plants. Unlike gas, there's no cooking or hot water competing. Reduce ventilation and you reduce heating load directly."

def get_site_eui_tooltip(row):
    """ROW tooltip - explains what EUI is and what drives it for this building type."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    hvac_pct_elec = safe_num(row, 'hvac_pct_elec', 0) or 0
    hvac_pct_gas = safe_num(row, 'hvac_pct_gas', 0) or 0

    # EUI = total energy / sqft - the universal efficiency metric
    if bldg_type == 'Data Center':
        return "EUI (Energy Use Intensity) = total energy per square foot. Data centers have high EUIs driven by server cooling, not occupancy. ODCV doesn't affect equipment heat loads."
    elif bldg_type in ['K-12 School', 'Higher Ed']:
        return f"EUI (Energy Use Intensity) = total energy per square foot. Schools have moderate EUIs with high HVAC share ({hvac_pct_elec*100:.0f}% of electric, {hvac_pct_gas*100:.0f}% of gas). Buildings empty 70-80% of the year—HVAC runs anyway."
    elif bldg_type == 'Hotel':
        return f"EUI (Energy Use Intensity) = total energy per square foot. Hotels have high EUIs but only {hvac_pct_gas*100:.0f}% of gas is HVAC—rest is hot water and kitchens. ODCV affects the HVAC portion, not guest services."
    elif bldg_type in ['Restaurant/Bar']:
        return f"EUI (Energy Use Intensity) = total energy per square foot. Restaurants have high EUIs driven by kitchen equipment—72% of gas is cooking. ODCV affects dining area HVAC ({hvac_pct_elec*100:.0f}% of electric), not kitchen exhaust."
    elif bldg_type in ['Inpatient Hospital', 'Specialty Hospital']:
        return f"EUI (Energy Use Intensity) = total energy per square foot. Hospitals have high EUIs due to 24/7 operation and medical equipment. HVAC is {hvac_pct_elec*100:.0f}% of electric—savings come from non-clinical areas."
    elif bldg_type in ['Office', 'Medical Office']:
        return f"EUI (Energy Use Intensity) = total energy per square foot. Offices have HVAC-dominated energy profiles ({hvac_pct_elec*100:.0f}% of electric, {hvac_pct_gas*100:.0f}% of gas). Big EUI impact when you stop ventilating empty space."
    else:
        return f"EUI (Energy Use Intensity) = total energy per square foot. HVAC accounts for {hvac_pct_elec*100:.0f}% of electricity and {hvac_pct_gas*100:.0f}% of gas—when you reduce ventilation to empty spaces, EUI drops."

def get_hvac_pct_tooltip(row):
    """Comprehensive dynamic tooltip explaining HOW HVAC percentage is determined."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')

    # Get HVAC percentages
    hvac_pct_elec = safe_num(row, 'hvac_pct_elec', 0) or 0
    hvac_pct_gas = safe_num(row, 'hvac_pct_gas', 0) or 0

    # Get building type info
    type_info = BUILDING_TYPE_INFO.get(bldg_type, DEFAULT_BUILDING_INFO)
    type_notes = BUILDING_TYPE_ENERGY_NOTES.get(bldg_type, DEFAULT_ENERGY_NOTES)

    typical_elec = type_info.get('elec_hvac_typical', 0.50) * 100
    typical_gas = type_info.get('gas_hvac_typical', 0.80) * 100

    lines = []
    lines.append("HOW HVAC % IS DETERMINED")
    lines.append("=" * 25)

    lines.append("")
    lines.append(f"BUILDING TYPE: {bldg_type}")

    lines.append("")
    lines.append("BASE VALUES (EIA CBECS 2018):")
    lines.append(f"  Electricity: {typical_elec:.0f}% typical")
    lines.append(f"  Natural Gas: {typical_gas:.0f}% typical")

    lines.append("")
    lines.append("THIS BUILDING:")
    if hvac_pct_elec > 0:
        lines.append(f"  Electricity HVAC: {hvac_pct_elec*100:.0f}%")
    if hvac_pct_gas > 0:
        lines.append(f"  Natural Gas HVAC: {hvac_pct_gas*100:.0f}%")

    lines.append("")
    lines.append("ADJUSTMENTS APPLIED:")
    lines.append("  • Building age (newer = more efficient)")
    lines.append("  • Energy Star score (higher = less waste)")
    lines.append("  • EUI vs. peer median")
    lines.append("  • Climate zone")

    # Building-type specific note
    elec_note = type_notes.get('elec_note', '')
    gas_note = type_notes.get('gas_note', '')

    if elec_note or gas_note:
        lines.append("")
        lines.append(f"NOTE FOR {bldg_type.upper()}:")
        if elec_note:
            # Word wrap
            words = elec_note.split()
            line = ""
            for word in words:
                if len(line) + len(word) + 1 <= 40:
                    line = line + " " + word if line else word
                else:
                    lines.append(f"  {line}")
                    line = word
            if line:
                lines.append(f"  {line}")

    lines.append("")
    lines.append("Source: EIA CBECS 2018 (6,436 buildings)")

    return '\n'.join(lines)

def get_load_factor_tooltip(row):
    """Comprehensive dynamic tooltip explaining load factor."""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')

    # Get values
    load_factor = safe_num(row, 'cost_elec_load_factor', 0) or 0
    kwh = safe_num(row, 'energy_elec_kwh', 0) or 0
    peak_kw = safe_num(row, 'cost_elec_peak_kw', 0) or 0

    # Get building type info
    type_info = BUILDING_TYPE_INFO.get(bldg_type, DEFAULT_BUILDING_INFO)
    type_notes = BUILDING_TYPE_ENERGY_NOTES.get(bldg_type, DEFAULT_ENERGY_NOTES)
    typical_lf = type_info.get('load_factor', 0.45) * 100

    lines = []
    lines.append("WHAT IS LOAD FACTOR?")
    lines.append("=" * 21)

    lines.append("")
    lines.append("Load Factor = Avg Load ÷ Peak Load")

    lines.append("")
    lines.append("TYPICAL VALUES:")
    lines.append("  • 80% = Data centers (constant 24/7)")
    lines.append("  • 65% = Hospitals/Supermarkets (24/7)")
    lines.append("  • 45% = Offices (9-5 peaks)")
    lines.append("  • 35% = Schools (summers empty)")

    lines.append("")
    lines.append(f"THIS BUILDING: {load_factor*100:.0f}%")
    lines.append(f"({bldg_type}s typically: {typical_lf:.0f}%)")

    if kwh > 0 and load_factor > 0:
        lines.append("")
        lines.append("HOW PEAK DEMAND IS ESTIMATED:")
        avg_kw = kwh / 8760
        lines.append(f"  Avg Load = {kwh:,.0f} kWh ÷ 8,760 hrs")
        lines.append(f"           = {avg_kw:,.0f} kW average")
        lines.append(f"  Peak kW = {avg_kw:,.0f} ÷ {load_factor:.2f}")
        lines.append(f"          = {peak_kw:,.0f} kW")

    # Building-type note
    lf_note = type_notes.get('load_factor_note', '')
    if lf_note:
        lines.append("")
        lines.append(f"WHY {bldg_type.upper()}S:")
        words = lf_note.split()
        line = ""
        for word in words:
            if len(line) + len(word) + 1 <= 40:
                line = line + " " + word if line else word
            else:
                lines.append(f"  {line}")
                line = word
        if line:
            lines.append(f"  {line}")

    return '\n'.join(lines)

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
    lines.append("Source: EPA eGRID 2023")

    return '\n'.join(lines)

def get_carbon_reduction_tooltip(row):
    """SALESPERSON TALKING POINTS - data sources for carbon emissions calculation."""
    city = safe_val(row, 'loc_city', '')
    state = safe_val(row, 'loc_state', '')

    # Regional grid context with specific factors
    grid_info = {
        'Seattle': ('0.08 kg CO2/kWh', 'hydro-powered—cleanest major US grid'),
        'Portland': ('0.12 kg CO2/kWh', 'hydro and wind mix'),
        'San Francisco': ('0.21 kg CO2/kWh', 'California renewables mandate'),
        'Los Angeles': ('0.25 kg CO2/kWh', 'LADWP grid'),
        'Denver': ('0.55 kg CO2/kWh', 'Xcel Colorado—coal-heavy'),
        'Chicago': ('0.41 kg CO2/kWh', 'ComEd Midwest grid'),
        'New York': ('0.29 kg CO2/kWh', 'ConEd NYC grid'),
        'Boston': ('0.31 kg CO2/kWh', 'ISO-NE regional grid'),
        'Atlanta': ('0.38 kg CO2/kWh', 'Georgia Power—gas and nuclear'),
        'Washington': ('0.33 kg CO2/kWh', 'PJM regional grid'),
    }

    story = f"Grid emission factor from EPA eGRID 2022—{city}'s actual utility grid, not a national average. "

    if city in grid_info:
        factor, desc = grid_info[city]
        story += f"{city}: {factor} ({desc}). "
    else:
        story += f"Using EPA eGRID regional factor for {state}. "

    story += "Natural gas: 5.3 kg CO2/therm (EIA standard). "
    story += "Pitch: 'These are auditable numbers—same methodology NYC uses for LL97 compliance.'"

    return story

def get_fine_avoidance_tooltip(row):
    """SALESPERSON TALKING POINTS - data sources for BPS fine calculations."""
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
        return "No BPS law here yet. 40+ cities considering them. Pitch: 'NYC was first in 2019, Boston and Denver followed. Get ahead now—savings today are pure utility cost reduction, no regulatory risk.'"

    law = bps_info['law']
    min_sqft = bps_info.get('min_sqft', 0)

    exempt_types = bps_info.get('exempt_types', [])
    if bldg_type in exempt_types or bldg_vertical in exempt_types:
        return f"{law} gives {bldg_type}s alternative compliance pathways. No standard fines, but ODCV still cuts utility bills. Pitch: 'Even without regulatory pressure, the energy savings are real money.'"

    if sqft > 0 and sqft < min_sqft:
        return f"{law} currently covers buildings over {min_sqft:,} sqft—this one's below threshold. Pitch: 'NYC started at 25,000 sqft, cities keep lowering limits. Get ahead now.'"

    if fine_avoided > 0:
        if city == 'New York':
            story = "LL97 fine formula: excess tCO2e × $268/ton (NYC Mayor's Office, Local Law 97 of 2019). "
            story += f"Building's {carbon:.0f} tCO2e exceeds its cap. "
            story += "Pitch: 'This isn't a projection—$268/ton is in the law. No appeals, no exemptions for commercial buildings.'"
            return story

        elif city == 'Boston':
            story = "BERDO 2.0 fine formula: excess tCO2e × $234/ton (City of Boston Environment Dept). "
            story += f"Current: {carbon:.0f} tCO2e for {sqft:,.0f} sqft exceeds threshold. "
            story += "Pitch: 'Caps tighten every 5 years to net-zero by 2050. Early action = compliance runway.'"
            return story

        elif city == 'Cambridge':
            story = "Cambridge BEUDO uses same $234/ton formula as Boston (Cambridge Community Development). "
            story += f"Building at {carbon:.0f} tCO2e exceeds limit. "
            story += "Pitch: 'MIT and Harvard set the sustainability bar here—Cambridge buildings face extra scrutiny.'"
            return story

        elif city == 'Washington':
            story = "DC BEPS uses Energy Star score (DC DOEE), not emissions. Threshold: 71. "
            story += f"Building scores {es_score:.0f}. Penalty: up to $10/sqft. "
            story += "Pitch: 'DC is score-based, not carbon-based. ODCV improves the score by lowering energy use.'"
            return story

        elif city == 'Denver':
            story = "Energize Denver fine formula: (EUI - target) × sqft × $0.30 (Denver CASR Office). "
            story += f"Target: 48.3 kBtu/sqft. Building: {eui:.0f} kBtu/sqft. "
            story += "Pitch: 'EUI-based law. ODCV directly lowers EUI by cutting HVAC waste.'"
            return story

        elif city == 'Seattle':
            story = "Seattle Clean Buildings: emissions intensity targets with $10/sqft penalties (Seattle OSE). "
            story += f"Building at {carbon:.0f} tCO2e for {sqft:,.0f} sqft exceeds threshold. "
            story += "Pitch: 'Seattle also does public disclosure of non-compliance—reputational risk.'"
            return story

        elif city == 'St. Louis':
            story = "St. Louis BEPS: EUI targets by building type, $500/day fines (City of St. Louis). "
            story += f"Building at {eui:.0f} kBtu/sqft. "
            story += "Pitch: 'Daily fines add up fast—$182,500/year if you don't fix it.'"
            return story

    return f"Currently compliant with {law}. Pitch: 'Caps tighten over time. Today's compliance is tomorrow's violation. Lock in savings now for margin against future standards.'"


def get_utility_cost_savings_tooltip(row):
    """SALESPERSON TALKING POINTS - data sources to cite when prospect asks 'where did you get these numbers?'"""
    bldg_type = safe_val(row, 'bldg_type', 'Commercial')
    city = safe_val(row, 'loc_city', '')
    vacancy = safe_num(row, 'occ_vacancy_rate', 0) or 0
    utilization = safe_num(row, 'occ_utilization_rate', 0) or 0

    # Help salesperson explain data credibility - WHERE it comes from, WHY it's specific
    if bldg_type in ['Office', 'Medical Office', 'Mixed Use']:
        story = f"{vacancy*100:.0f}% vacancy from CBRE Q4 2024 {city} office market report—actual market data, not a national average. "
        story += f"{utilization*100:.0f}% desk utilization from Kastle Systems badge swipes for {city}—they track 2,600+ buildings. "
        story += "BMS doesn't know which floors are empty. Ventilates for full capacity. That's the waste."

    elif bldg_type == 'Hotel':
        story = f"{utilization*100:.0f}% occupancy from STR {city} market data—the hotel industry's standard tracking. "
        story += "Guests in rooms ~10 hours/day. Rest of the time rooms sit empty but conditioned."

    elif bldg_type in ['K-12 School', 'Higher Ed']:
        empty_pct = (1 - utilization) * 100 if utilization else 70
        story = f"{empty_pct:.0f}% empty time from NCES instructional day data—actual academic calendar requirements. "
        story += "After 3pm, weekends, summer, holidays—but HVAC runs at design capacity."

    elif bldg_type in ['Inpatient Hospital', 'Specialty Hospital']:
        story = f"{utilization*100:.0f}% utilization from AHA Hospital Statistics—hospital-specific data, not office assumptions. "
        story += "40% non-clinical: waiting rooms, admin, cafeterias. All ventilated at medical-grade 24/7."

    elif bldg_type in ['Theater', 'Venue']:
        story = f"{utilization*100:.0f}% utilization from event schedule data. Venues empty 80%+ of time. "
        story += "~80 events/year = 400 hours out of 8,760. HVAC conditions for full crowd around the clock."

    elif bldg_type in ['Retail Store', 'Supermarket/Grocery', 'Wholesale Club']:
        story = f"{utilization*100:.0f}% average traffic from Placer.ai {city} foot traffic analytics—real location data. "
        story += "20% weekday mornings, 80% Saturday afternoons. HVAC runs at peak all day."

    elif bldg_type == 'Restaurant/Bar':
        story = f"{utilization*100:.0f}% utilization based on meal patterns. Empty at 3pm, packed at 7pm. "
        story += "Kitchen exhaust is code-required. Dining area ventilation is the variable piece."

    elif bldg_type == 'Library/Museum':
        story = f"{utilization*100:.0f}% visitor presence. Collections need 24/7 climate control for preservation. "
        story += "Galleries get full ventilation around the clock for a fraction of visitors."

    else:
        story = f"{utilization*100:.0f}% utilization. Building conditions empty space most of the time. "
        story += "BMS runs at design capacity. Doesn't know when people leave."

    return story


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
    return f'<span class="info-tooltip" data-tooltip="{escape(text)}" style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background: linear-gradient(135deg, #0066cc 0%, #004494 100%); color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>'

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
                img_tag = f'<img src="{logo_url}" alt="{escape(display_name)}" style="height:{height}px;" onerror="this.parentElement.className=\'\';this.parentElement.removeAttribute(\'data-org-name\');this.style.display=\'none\';this.nextElementSibling.style.display=\'inline\';">'
                return f'<a href="{escape(org_url)}" target="_blank" class="org-logo" data-org-name="{escape(display_name)}">{img_tag}{fallback_text}</a>'
            else:
                img_tag = f'<img src="{logo_url}" alt="{escape(display_name)}" style="height:{height}px;" onerror="this.parentElement.className=\'\';this.parentElement.removeAttribute(\'data-org-name\');this.style.display=\'none\';this.nextElementSibling.style.display=\'inline\';">'
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
        return f'<span class="info-tooltip" data-tooltip="{escape(text)}" style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background: linear-gradient(135deg, #0066cc 0%, #004494 100%); color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>'

    html = f"""
    <div class="section">
        <h2>Energy</h2>
        <table>
            <tr>
                <th></th>
                <th>Current{col_tooltip(current_tooltip)}</th>
                <th>New{col_tooltip(new_tooltip)}</th>
                <th>Change{col_tooltip(change_tooltip)}</th>
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
            change_str = f'<td style="color: #0ea5e9; font-weight: 600; background: rgba(14,165,233,0.08);">⚡ -{format_number(change)} kWh</td>'
        else:
            change_str = '<td>—</td>'
        html += f"""
            <tr>
                <td>Electricity{tooltip('energy_elec_kwh', row)}</td>
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
            change_str = f'<td style="color: #f97316; font-weight: 600; background: rgba(249,115,22,0.08);">🔥 -{format_number(change)} therms</td>'
        else:
            change_str = '<td>—</td>'
        html += f"""
            <tr>
                <td>Natural Gas{tooltip('natural_gas', row)}</td>
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
            change_str = f'<td style="color: #f97316; font-weight: 600; background: rgba(249,115,22,0.08);">🛢️ -{format_number(change)} gallons</td>'
        else:
            change_str = '<td>—</td>'
        html += f"""
            <tr>
                <td>Fuel Oil{tooltip('fuel_oil', row)}</td>
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
            change_str = f'<td style="color: #6366f1; font-weight: 600; background: rgba(99,102,241,0.08);">💨 -{format_number(change, 2)} Mlb</td>'
        else:
            change_str = '<td>—</td>'
        html += f"""
            <tr>
                <td>District Steam{tooltip('district_steam', row)}</td>
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
            change_str = f'<td style="color: #8b5cf6; font-weight: 600; background: rgba(139,92,246,0.08);">📉 -{format_number(change, 1)} kBtu/sqft</td>'
        else:
            change_str = '<td>—</td>'
        html += f"""
            <tr>
                <td>Site EUI{tooltip('energy_site_eui', row)}</td>
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

    html = """
    <div class="section">
        <h2>Impact</h2>
        <table>
            <tr>
                <th></th>
                <th>Current</th>
                <th>New</th>
                <th>Change</th>
            </tr>
"""

    # Utility Cost row - uses utility_cost_savings tooltip (SALES CALL READY)
    if total_energy_cost and odcv_savings:
        html += f"""
            <tr>
                <td>Utility Cost{tooltip('utility_cost_savings', row)}</td>
                <td>{format_currency(total_energy_cost)}/yr</td>
                <td>{format_currency(new_utility_cost)}/yr</td>
                <td style="color: #16a34a; font-weight: 600; background: rgba(22,163,74,0.08);">💰 -{format_currency(odcv_savings)}/yr</td>
            </tr>
"""

    # Fine Avoidance row - only show for buildings with fine avoidance
    fine_baseline = safe_num(row, 'bps_fine_baseline_yr1_usd')
    fine_post_odcv = safe_num(row, 'bps_fine_post_odcv_yr1_usd')
    fine_avoided = safe_num(row, 'bps_fine_avoided_yr1_usd')

    if fine_avoided and fine_avoided > 0:
        html += f"""
            <tr>
                <td>Fine Avoidance{tooltip('fine_avoidance', row)}</td>
                <td>{format_currency(fine_baseline)}/yr</td>
                <td>{format_currency(fine_post_odcv)}/yr</td>
                <td style="color: #059669; font-weight: 600; background: rgba(5,150,105,0.08);">🛡️ -{format_currency(fine_avoided)}/yr</td>
            </tr>
"""

    # Property Value row - only show impact, not current/new values
    if val_impact and val_impact > 0:
        html += f"""
            <tr>
                <td>Property Value{tooltip('property_value_increase', row)}</td>
                <td>—</td>
                <td>—</td>
                <td style="color: #f59e0b; font-weight: 600; background: rgba(245,158,11,0.08);">📈 +{format_currency(val_impact)}</td>
            </tr>
"""

    # Energy Star Score row
    current_es = safe_num(row, 'energy_star_score')
    post_es = safe_num(row, 'energy_star_score_post_odcv')
    if current_es:
        current_str = f"{int(current_es)}"
        new_str = f"{int(post_es)}" if post_es else "—"
        if post_es and post_es > current_es:
            change = int(post_es - current_es)
            change_str = f'<td style="color: #eab308; font-weight: 600; background: rgba(234,179,8,0.08);">⭐ +{change}</td>'
        else:
            change_str = '<td>—</td>'
        html += f"""
            <tr>
                <td>Energy Star Score{tooltip('energy_star_score', row)}</td>
                <td>{current_str}</td>
                <td>{new_str}</td>
                {change_str}
            </tr>
"""

    # Carbon Emissions row (last)
    if carbon_current and carbon_post:
        carbon_reduction = carbon_current - carbon_post
        html += f"""
            <tr>
                <td>Carbon Emissions{tooltip('carbon_reduction', row)}</td>
                <td>{format_number(carbon_current, 1)} tCO2e/yr</td>
                <td>{format_number(carbon_post, 1)} tCO2e/yr</td>
                <td style="color: #0d9488; font-weight: 600; background: rgba(13,148,136,0.08);">🌱 -{format_number(carbon_reduction, 1)} tCO2e/yr</td>
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
            background: linear-gradient(135deg, #0066cc 0%, #004494 100%);
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
            background-color: #1a1a2e;
            color: #e8e8e8;
            padding: 14px 18px;
            border-radius: 8px;
            white-space: pre-line;
            width: 420px;
            max-width: 90vw;
            font-size: 11px;
            font-family: 'SF Mono', 'Monaco', 'Consolas', 'Courier New', monospace;
            line-height: 1.6;
            text-align: left;
            z-index: 2147483647;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.3s, visibility 0.3s;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
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
            border-top-color: #1a1a2e;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.3s, visibility 0.3s;
        }}

        .info-tooltip:hover::before {{
            opacity: 1;
            visibility: visible;
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
            .info-tooltip::after {{
                width: 320px;
                font-size: 10px;
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
