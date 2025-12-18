import pandas as pd
from datetime import datetime, timedelta
import pytz
import requests
import urllib.parse
import os
from dotenv import load_dotenv
import sys
import json
import re
import time
import math
import csv

def escape_js_string(s):
    """Escape a string for safe inclusion in JavaScript single-quoted strings"""
    if not s or pd.isna(s):
        return ''
    return str(s).replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")

def escape_html(s):
    """Escape a string for safe inclusion in HTML"""
    if not s or pd.isna(s):
        return ''
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))

# Load environment variables from .env file
load_dotenv()

# --- News widget config (env-overridable) ---
NEWS_API_BASE = os.getenv("NEWS_API_BASE", "")                 # e.g., "https://news.your-domain.com" (must be HTTPS in prod)
NEWS_REFRESH_TOKEN = os.getenv("NEWS_REFRESH_TOKEN", "")       # optional (public if shipped to JS)
NEWS_MIN_SCORE = float(os.getenv("NEWS_MIN_SCORE", "2.5"))     # v6 optimized threshold for 70%+ coverage
NEWS_MAX_AGE_DAYS = int(os.getenv("NEWS_MAX_AGE_DAYS", "180"))  # 6 months - commercial RE news cycle
NEWS_LIMIT = int(os.getenv("NEWS_LIMIT", "10"))                # fetch up to 10; widget shows 3 by default

# Server key for report generation (air quality API) - unrestricted
SERVER_API_KEY = "AIzaSyCZU0mRkd5VlOXgsLFyH_tzWT3nT6MUZlI"
# OpenWeatherMap API key for air pollution data (30 days historical)
OPENWEATHER_API_KEY = "5d51a9cdc15416f8d1128dc303e552bb"

# PM2.5 cache for proximity-based reuse
PM25_CACHE = {}  # (lat, lon) -> (data, chart_dates, chart_values, chart_labels, avg_pm25, max_pm25)
PROXIMITY_THRESHOLD = 0.002  # ~200 meters in NYC latitude

# Global months array for use throughout the script
months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in km"""
    R = 6371  # Earth's radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def get_neighborhood_from_coords(lat, lon):
    """Determine Manhattan neighborhood from coordinates - matches new 10 neighborhoods"""
    if lat is None or lon is None:
        return "Midtown South"
    
    lat = float(lat)
    lon = float(lon)
    
    # Use same logic as classify_building
    if lat > 40.768:
        return "Uptown"
    
    if lat > 40.755:
        return "Midtown West" if lon < -73.985 else "Midtown East"
    
    if lat > 40.748:
        return "Midtown South"
    
    if lat > 40.735:
        return "Chelsea" if lon < -73.992 else "Union Square"
    
    if lat > 40.728:
        return "Greenwich Village" if lon < -73.995 else "Union Square"
    
    if lat > 40.715:
        return "Tribeca"
    
    return "FiDi"

def get_neighborhood_pollution_factor(neighborhood):
    """Each neighborhood gets different PM2.5 levels - Updated for new neighborhood structure"""
    
    factors = {
        "Midtown West": 1.60,           # Highest pollution - Times Square, heavy traffic, construction
        "Midtown South": 1.45,          # High pollution - Dense commercial, Penn Station area  
        "Midtown East": 1.35,           # High pollution - Grand Central, heavy traffic
        "Chelsea": 1.25,                # Moderate-high pollution - High traffic corridors
        "Union Square": 1.20,           # Moderate pollution - Busy intersection area
        "Greenwich Village": 1.10,      # Moderate pollution - Mixed residential/commercial
        "Tribeca": 0.95,        # Below average - Some waterfront influence
        "FiDi": 0.90,                   # Good air quality - Financial District, some waterfront
        "Uptown": 0.80                  # Best air quality - Less dense, near parks
    }
    
    return factors.get(neighborhood, 1.0)

def apply_neighborhood_variation(base_values, neighborhood_factor, dates):
    """Apply realistic neighborhood-based variation to PM2.5 data"""
    import random
    import math
    
    adjusted_values = []
    
    for i, base_value in enumerate(base_values):
        # Apply randomized neighborhood factor (±15% variation around base factor)
        factor_variation = random.uniform(0.85, 1.15)
        randomized_factor = neighborhood_factor * factor_variation
        adjusted = base_value * randomized_factor
        
        # Add seasonal variation (winter = more pollution due to heating)
        try:
            # Parse date to get month
            date_parts = dates[i].split('-')
            month = int(date_parts[1]) if len(date_parts) >= 2 else 6
            
            # Winter months (Dec, Jan, Feb) have +15% pollution
            # Summer months (Jun, Jul, Aug) have -10% pollution
            if month in [12, 1, 2]:
                seasonal_factor = 1.15
            elif month in [6, 7, 8]:
                seasonal_factor = 0.90
            else:
                seasonal_factor = 1.0
                
            adjusted *= seasonal_factor
        except:
            pass  # If date parsing fails, skip seasonal adjustment
        
        # Add small random daily variation (±5%)
        daily_variation = random.uniform(0.95, 1.05)
        adjusted *= daily_variation
        
        # Ensure minimum value of 2 μg/m³ (never completely clean in NYC)
        adjusted = max(adjusted, 2.0)
        
        adjusted_values.append(round(adjusted, 1))
    
    return adjusted_values

def find_cached_pm25(lat, lon, neighborhood):
    """Find cached PM2.5 data with neighborhood-based variations"""
    cache_key = f"{neighborhood}_{round(lat, 3)}_{round(lon, 3)}"
    
    # Check if we have data for this specific neighborhood
    if cache_key in PM25_CACHE:
        return PM25_CACHE[cache_key]
    
    # If we have base API data from any location, apply neighborhood variation
    if PM25_CACHE:
        base_data = list(PM25_CACHE.values())[0]
        neighborhood_factor = get_neighborhood_pollution_factor(neighborhood)
        
        # Apply neighborhood variation to the base data
        adjusted_values = apply_neighborhood_variation(
            base_data['chart_values'], 
            neighborhood_factor,
            base_data['chart_dates']
        )
        
        # Create new data with neighborhood adjustments
        neighborhood_data = {
            'chart_dates': base_data['chart_dates'].copy(),
            'chart_values': adjusted_values,
            'chart_labels': base_data['chart_labels'].copy(),
            'avg_pm25': round(sum(adjusted_values) / len(adjusted_values), 1) if adjusted_values else 0,
            'max_pm25': round(max(adjusted_values), 1) if adjusted_values else 0
        }
        
        # Cache the neighborhood-specific data
        PM25_CACHE[cache_key] = neighborhood_data
        return neighborhood_data
    
    return None

# Client key for aerial videos (domain-restricted to test and main sites)
# CLIENT_API_KEY = "AIzaSyDQdR4xY0a_qmEsYairsp6r6tXwh5qx_ho"

# AWS S3 bucket URLs
AWS_VIDEO_BUCKET = "https://aerial-videos-forrest.s3.us-east-2.amazonaws.com"
AWS_IMAGES_BUCKET = "https://nyc-odcv-images.s3.us-east-2.amazonaws.com"

# Version tracking for cache busting
# Version with date stamp for tracking updates
version = int(datetime.now().timestamp())
version_date = "2025.08.10"  # Update date for tracking

# Logo mapping function
def find_logo_file(company_name):
    """Find matching logo file for a company name"""
    if pd.isna(company_name) or not company_name:
        return None

    # Clean and convert company name to match logo filename format
    clean_name = company_name.strip()
    clean_name = clean_name.replace("'", "")  # Remove apostrophes
    clean_name = clean_name.replace(" & ", "_")  # Replace " & " with "_"
    clean_name = clean_name.replace(" ", "_")  # Replace spaces with underscores
    logo_filename = f"{clean_name}.png"

    # Check special mappings from JSON
    if clean_name in logo_filename_mapping:
        logo_filename = logo_filename_mapping[clean_name]

    # Return logo filename if it exists in our list
    if logo_filename in logo_available_logos:
        return logo_filename

    return None

# Helper function for safe value extraction
def safe_val(df, bbl, column, default='N/A'):
    if df.empty or column not in df.columns:
        return default
    filtered = df[df['bbl'] == bbl]
    if filtered.empty:
        return default
    val = filtered[column].iloc[0]
    if pd.isna(val):
        return default
    return val

# Determine data path based on current working directory
import os
if os.path.basename(os.getcwd()) == 'Scripts':
    data_path = '../data/'
else:
    data_path = '/Users/forrestmiller/Desktop/New/data/'

# Load logo mappings from JSON file
try:
    with open(data_path + 'logo_mappings.json', 'r') as f:
        logo_config = json.load(f)
        logo_filename_mapping = logo_config['filename_mappings']
        logo_available_logos = logo_config['available_logos']
except Exception as e:
    print(f"Warning: Could not load logo_mappings.json: {e}")
    logo_filename_mapping = {}
    logo_available_logos = []

# Read ALL the CSVs we need - CORRECTED LL97 METHODOLOGY
try:
    scoring = pd.read_csv(data_path + 'odcv_scoring_CORRECTED.csv', encoding='utf-8')
    buildings = pd.read_csv(data_path + 'buildings_BIG_with_emails_complete_verified.csv', encoding='utf-8')
    # ll97 = pd.read_csv(data_path + 'LL97_BIG_CORRECTED.csv')  # DEPRECATED - Now using 10_year_savings_by_building.csv
    
    # Load 10-year savings data - THE ONLY SOURCE for LL97 data
    try:
        ten_year_savings = pd.read_csv('/Users/forrestmiller/Desktop/New/data/10_year_savings_by_building.csv', encoding='utf-8')
    except Exception as e:
        print(f"CRITICAL: {e}")
        sys.exit(1)
    
    system = pd.read_csv(data_path + 'system_BIG.csv', encoding='utf-8')
    energy = pd.read_csv(data_path + 'energy_BIG.csv', encoding='utf-8')
    addresses = pd.read_csv(data_path + 'all_building_addresses.csv', encoding='utf-8')
    hvac = pd.read_csv(data_path + 'hvac_office_energy_BIG.csv', encoding='utf-8')
    office = pd.read_csv(data_path + 'office_energy_BIG.csv', encoding='utf-8')

except FileNotFoundError as e:
    print(f"CRITICAL ERROR: Missing required data file: {e}")
    print("Please ensure all CSV files are in the data/ directory")
    sys.exit(1)
except Exception as e:
    print(f"CRITICAL ERROR: Failed to load data: {e}")
    sys.exit(1)

# Fix encoding issues in owner and property manager names
encoding_fixes = {
    '√©': 'é', '√®': 'î', '√°': 'à', '√¨': 'è', '√¢': 'â',
    '√´': 'ô', '√ª': 'ê', '√ø': 'ø', '√Æ': 'Æ', '√±': 'ñ',
    '√ß': 'ß', '√º': 'ú', '√¯': 'ï', '√ª': 'ê', '√ç': 'ç',
    '√ä': 'ä', '√Ä': 'Ä', '√∂': 'ö', '√Ö': 'Ö', '√ü': 'ü',
    '√Ü': 'Ü', '√•': '•', 'Œ©': 'é', 'Œ†': 'à', 'Œ´': 'ô',
    'â€™': "'", 'â€œ': '"', 'â€': '"', 'â€"': '–', 'â€"': '—',
    'Ã©': 'é', 'Ã¨': 'è', 'Ã ': 'à', 'Ã´': 'ô', 'Ã®': 'î',
    'Ã§': 'ç', 'Ã¼': 'ü', 'Ã¶': 'ö', 'Ã±': 'ñ', 'Ã¡': 'á',
    'Ã­': 'í', 'Ã³': 'ó', 'Ãº': 'ú', 'Ã¤': 'ä'
}

# Apply encoding fixes to buildings dataframe columns
buildings_name_columns = ['ownername', 'property_manager', 'Owner_Contact_Name',
                          'Property_Manager_Contact_Name', 'owner_job_title', 'pm_job_title']
for col in buildings_name_columns:
    if col in buildings.columns:
        for bad, good in encoding_fixes.items():
            buildings[col] = buildings[col].str.replace(bad, good, regex=False)

# Read building heights
heights = pd.read_csv(data_path + 'building_heights.csv', encoding='utf-8')

# Read equipment counts
try:
    equipment_counts = pd.read_csv(data_path + 'equipment_counts.csv', encoding='utf-8')
except:
    equipment_counts = pd.DataFrame()  # Empty dataframe if file not found

# Read EUI data
try:
    eui_data = pd.read_csv(data_path + 'building_office_eui.csv', encoding='utf-8')
except:
    eui_data = pd.DataFrame()  # Empty dataframe if file not found

# Read National EUI comparison data
try:
    national_eui_data = pd.read_csv(data_path + 'new eui national avg.csv', encoding='utf-8')
except:
    national_eui_data = pd.DataFrame()  # Empty dataframe if file not found

# Read Data Center information
try:
    datacenter_data = pd.read_csv(data_path + 'data center estimate.csv', encoding='utf-8')
except:
    datacenter_data = pd.DataFrame()  # Empty dataframe if file not found

# Check which aerial videos exist in S3 and load their URLs
aerial_videos_available = set()
aerial_video_urls = {}
try:
    aerial_df = pd.read_csv(data_path + 'aerial_videos.csv', encoding='utf-8')
    for _, row in aerial_df.iterrows():
        if pd.notna(row['bbl']):
            # Handle Int64 BBL data safely
            bbl = int(row['bbl'])
            aerial_videos_available.add(bbl)
            # Store the AWS URL for this BBL
            if pd.notna(row['aws_url']):
                aerial_video_urls[bbl] = row['aws_url']
except Exception as e:
    print(f"Warning: Could not load aerial_videos.csv: {e}")
    # If no CSV or error, no videos are available
    aerial_videos_available = set()

# Owner and Property Manager contact information is now separated into individual columns in buildings_BIG_with_emails_complete_verified.csv

# Read tenant data
try:
    tenants_df = pd.read_csv(data_path + 'Tenants_Final_Aug 25 - Sheet1.csv', encoding='utf-8')
    # Convert BBL from float to integer for matching
    tenants_df['bbl'] = tenants_df['bbl'].fillna(0).astype(int)
    # Clean sf_occupied column by removing commas and quotes, then convert to numeric
    tenants_df['SF_Occupied_Clean'] = tenants_df['sf_occupied'].astype(str).str.replace(',', '').str.replace('"', '').str.strip()
    tenants_df['SF_Occupied_Clean'] = pd.to_numeric(tenants_df['SF_Occupied_Clean'], errors='coerce')
    # Create SF_Numeric column for backward compatibility
    tenants_df['SF_Numeric'] = tenants_df['SF_Occupied_Clean']

    # Fix encoding issues in tenant names
    if 'tenant' in tenants_df.columns:
        for bad, good in encoding_fixes.items():
            tenants_df['tenant'] = tenants_df['tenant'].str.replace(bad, good, regex=False)

    # Create backward compatibility columns for the new format
    tenants_df['Tenant'] = tenants_df['tenant']  # Map tenant -> Tenant
    tenants_df['Floor'] = tenants_df['floor']    # Map floor -> Floor
    tenants_df['Move In Date'] = tenants_df['move_in_date']  # Map move_in_date -> Move In Date
    
    # Industry column removed - not available in new format
    
    # Classify lease type based on floor (GRND = Retail, others = Commercial)
    tenants_df['is_ground_floor'] = tenants_df['floor'].astype(str).str.contains('GRND', case=False, na=False)
    tenants_df['Lease Type'] = tenants_df['is_ground_floor'].map({True: 'Retail', False: 'Commercial'})
    
except Exception as e:
    tenants_df = pd.DataFrame()

# Read building categorization data for NOI and valuation impact
try:
    categorization_df = pd.read_csv('/Users/forrestmiller/Desktop/New/data/odcv_noi_value_impact_analysis.csv', encoding='utf-8')
    noi_valuation_df = categorization_df
except Exception as e:
    categorization_df = pd.DataFrame()

# Check command line arguments - supports single BBL, multiple BBLs, or batch file
# Usage: python3 building.py BBL [output_dir]
#        python3 building.py --batch bbl1,bbl2,bbl3 [output_dir]
#        python3 building.py --batch-file /path/to/bbls.txt [output_dir]
output_dir_override = None
if len(sys.argv) > 1:
    if sys.argv[1] == '--batch':
        # Batch mode: multiple BBLs comma-separated
        bbls_str = sys.argv[2] if len(sys.argv) > 2 else ''
        target_bbls = [int(b.strip()) for b in bbls_str.split(',') if b.strip()]
        output_dir_override = sys.argv[3] if len(sys.argv) > 3 else None
        scoring = scoring[scoring['bbl'].isin(target_bbls)]
        print(f"BATCH MODE: Generating {len(scoring)} reports")
    elif sys.argv[1] == '--batch-file':
        # Batch file mode: read BBLs from file
        batch_file = sys.argv[2] if len(sys.argv) > 2 else ''
        output_dir_override = sys.argv[3] if len(sys.argv) > 3 else None
        with open(batch_file, 'r') as f:
            target_bbls = [int(line.strip()) for line in f if line.strip().isdigit()]
        scoring = scoring[scoring['bbl'].isin(target_bbls)]
        print(f"BATCH FILE MODE: Generating {len(scoring)} reports from {batch_file}")
    else:
        try:
            target_bbl = int(sys.argv[1])
            output_dir_override = sys.argv[2] if len(sys.argv) > 2 else None
            # Filter scoring to only the requested building
            scoring = scoring[scoring['bbl'] == target_bbl]
            if scoring.empty:
                print(f"Error: Building {target_bbl} not found in scoring data")
                sys.exit(1)
            print(f"Generating report for single building: {target_bbl}")
        except ValueError:
            print(f"Error: Invalid BBL provided: {sys.argv[1]}")
            print("Usage: python3 building.py [BBL] [output_dir]")
            print("       python3 building.py --batch bbl1,bbl2,bbl3 [output_dir]")
            print("       python3 building.py --batch-file /path/to/bbls.txt [output_dir]")
            sys.exit(1)
else:
    print("Generating reports for all buildings...")

# For each building
for count, (i, row) in enumerate(scoring.iterrows(), 1):
    bbl = row['bbl']

    try:
            # Validate required columns exist
            required_cols = ['bbl', 'utility_savings_annual', 'total_score', 'final_rank']
            if not all(col in row.index for col in required_cols):
                print(f"Skipping {bbl} - missing required columns")
                continue
            
            # Get building data
            building = buildings[buildings['bbl'] == bbl]
            if building.empty:
                continue
                
            # Get data from each CSV
            # Get 10-year savings data for this building (ONLY source for LL97)
            building_ten_year = ten_year_savings[ten_year_savings['bbl'] == bbl]
            if building_ten_year.empty:
                print(f"Skipping {bbl} - no 10-year savings data")
                continue
                
            # Use PRECOMPUTED totals from CSV
            savings_1yr = float(building_ten_year['total_1yr'].iloc[0])
            savings_5yr = float(building_ten_year['total_5yr'].iloc[0])
            savings_10yr = float(building_ten_year['total_10yr'].iloc[0])
            # Get annual utility savings directly from CSV
            utility_savings_annual = float(building_ten_year['utility_savings_annual'].iloc[0])
            # Get LL97 values for each period from CSV - handle "NA (City Owned)" strings
            def safe_ll97_float(value):
                if pd.isna(value) or str(value).startswith('NA'):
                    return 'NA (City Owned)'
                try:
                    return float(value)
                except:
                    return 'NA (City Owned)'

            ll97_2026_raw = building_ten_year['ll97_avoidance_2026'].iloc[0]
            ll97_2030_raw = building_ten_year['ll97_avoidance_2030'].iloc[0]
            ll97_2035_raw = building_ten_year['ll97_avoidance_2035'].iloc[0]

            ll97_2026 = safe_ll97_float(ll97_2026_raw)
            ll97_2030 = safe_ll97_float(ll97_2030_raw)
            ll97_2035 = safe_ll97_float(ll97_2035_raw)

            # Get 2026 breakdown for display
            utility_savings_2026 = float(building_ten_year['utility_savings_2026'].iloc[0]) if 'utility_savings_2026' in building_ten_year.columns else savings_1yr * 0.5
            ll97_avoidance_2026 = safe_ll97_float(building_ten_year['ll97_avoidance_2026'].iloc[0]) if 'll97_avoidance_2026' in building_ten_year.columns else savings_1yr * 0.5

            # Get specific year LL97 values for display
            ll97_avoidance_2030 = safe_ll97_float(building_ten_year['ll97_avoidance_2030'].iloc[0])
            
            # These are now the ONLY LL97 values we use
            corrected_ll97_avoidance = ll97_2026
            corrected_ll97_avoidance_2030 = ll97_2030
                
            system_data = system[system['bbl'] == bbl]
            energy_data = energy[energy['bbl'] == bbl]
            address_data = addresses[addresses['bbl'] == bbl]
            
            # Skip if critical data missing
            if energy_data.empty:
                print(f"Skipping {bbl} - missing energy data")
                continue
                
            # Get building height for panorama
            building_height = safe_val(heights, bbl, 'Height Roof', 200)  # Default 200ft
            
            # Get monthly energy data - SIMPLE VERSION
            months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            elec_usage = []
            gas_usage = []
            steam_usage = []
            hvac_pct = []
            odcv_savings = []
            
            for m in months:
                # Safely get values with your data
                hvac_monthly = float(safe_val(energy_data, bbl, f'Elec_HVAC_{m}_2023_kBtu', 0))
                non_hvac = float(safe_val(energy_data, bbl, f'Elec_NonHVAC_{m}_2023_kBtu', 0))
                gas = float(safe_val(energy_data, bbl, f'Gas_{m}_2023_kBtu', 0))
                steam = float(safe_val(energy_data, bbl, f'District_Steam_{m}_2023_kBtu', 0))
                total = hvac_monthly + non_hvac

                elec_usage.append(total)
                gas_usage.append(gas)
                steam_usage.append(steam)
                hvac_pct.append(hvac_monthly/total if total > 0 else 0)
            
            # Calculate annual average HVAC percentage
            annual_avg_hvac_pct = sum(hvac_pct) / len(hvac_pct) if hvac_pct else 0
            
            # Get ODCV savings data from hvac CSV
            hvac_data = hvac[hvac['bbl'] == bbl]
            odcv_elec_savings = []
            odcv_gas_savings = []
            odcv_steam_savings = []
            for m in months:
                val = hvac_data[f'Office_Elec_Savings_ODCV_{m}_USD'].iloc[0] if not hvac_data.empty else 0
                odcv_elec_savings.append(float(val) if pd.notna(val) else 0)
                val = hvac_data[f'Office_Gas_Savings_ODCV_{m}_USD'].iloc[0] if not hvac_data.empty else 0
                odcv_gas_savings.append(float(val) if pd.notna(val) else 0)
                val = hvac_data[f'Office_Steam_Savings_ODCV_{m}_USD'].iloc[0] if not hvac_data.empty else 0
                odcv_steam_savings.append(float(val) if pd.notna(val) else 0)
            
            # Calculate total ODCV savings per month using REAL data
            odcv_savings = []
            for i in range(12):
                monthly_total = odcv_elec_savings[i] + odcv_gas_savings[i] + odcv_steam_savings[i]
                odcv_savings.append(monthly_total)
            
            # Office energy data
            office_data = office[office['bbl'] == bbl]
            office_elec_usage = []
            office_gas_usage = []
            office_steam_usage = []
            for m in months:
                val = office_data[f'Office_Elec_Usage_Current_{m}_kBtu'].iloc[0] if not office_data.empty else 0
                office_elec_usage.append(float(val) if pd.notna(val) else 0)
                val = office_data[f'Office_Gas_Usage_Current_{m}_kBtu'].iloc[0] if not office_data.empty else 0
                office_gas_usage.append(float(val) if pd.notna(val) else 0)
                val = office_data[f'Office_Steam_Usage_Current_{m}_kBtu'].iloc[0] if not office_data.empty else 0
                office_steam_usage.append(float(val) if pd.notna(val) else 0)
            
            # Energy costs
            elec_cost = []
            gas_cost = []
            steam_cost = []
            for m in months:
                elec_cost.append(float(energy_data[f'Elec_HVAC_{m}_2023_Cost_USD'].iloc[0]) + float(energy_data[f'Elec_NonHVAC_{m}_2023_Cost_USD'].iloc[0]) if not energy_data.empty else 0)
                gas_cost.append(float(energy_data[f'Gas_{m}_2023_Cost_USD'].iloc[0]) if not energy_data.empty else 0)
                # Only add steam cost if there's steam usage
                steam_val = float(safe_val(energy_data, bbl, f'District_Steam_{m}_2023_kBtu', 0))
                if steam_val > 0:
                    steam_cost.append(float(energy_data[f'Steam_{m}_2023_Cost_USD'].iloc[0]) if not energy_data.empty else 0)
                else:
                    steam_cost.append(0)  # No cost if no usage
            
            # Office costs
            office_elec_cost = []
            office_gas_cost = []
            office_steam_cost = []
            for m in months:
                val = office_data[f'Office_Elec_Cost_Current_{m}_USD'].iloc[0] if not office_data.empty else 0
                office_elec_cost.append(float(val) if pd.notna(val) else 0)
                val = office_data[f'Office_Gas_Cost_Current_{m}_USD'].iloc[0] if not office_data.empty else 0
                office_gas_cost.append(float(val) if pd.notna(val) else 0)
                val = office_data[f'Office_Steam_Cost_Current_{m}_USD'].iloc[0] if not office_data.empty else 0
                office_steam_cost.append(float(val) if pd.notna(val) else 0)
            
            # Calculate annual cost totals
            annual_building_cost = sum(elec_cost) + sum(gas_cost) + sum(steam_cost)
            annual_office_cost = sum(office_elec_cost) + sum(office_gas_cost) + sum(office_steam_cost)

            # Calculate annual usage totals
            annual_building_usage = sum(elec_usage) + sum(gas_usage) + sum(steam_usage)
            annual_office_usage = sum(office_elec_usage) + sum(office_gas_usage) + sum(office_steam_usage)
            
            # Calculate monthly HVAC costs for new visualization
            monthly_hvac_elec_cost = []
            monthly_hvac_gas_cost = []
            monthly_hvac_steam_cost = []
            monthly_total_hvac_cost = []

            for i, m in enumerate(months):
                # Electric HVAC = office electric cost × HVAC %
                elec_hvac = office_elec_cost[i] * hvac_pct[i] if i < len(hvac_pct) else 0
                # Gas HVAC = office gas cost × 90%
                gas_hvac = office_gas_cost[i] * 0.9
                # Steam HVAC = office steam cost × 90%
                steam_hvac = office_steam_cost[i] * 0.9
                
                monthly_hvac_elec_cost.append(elec_hvac)
                monthly_hvac_gas_cost.append(gas_hvac)
                monthly_hvac_steam_cost.append(steam_hvac)
                monthly_total_hvac_cost.append(elec_hvac + gas_hvac + steam_hvac)

            # Calculate monthly ODCV savings as percentage of monthly HVAC
            monthly_odcv_percentages = []
            for i in range(12):
                if monthly_total_hvac_cost[i] > 0:
                    monthly_percentage = (odcv_savings[i] / monthly_total_hvac_cost[i]) * 100
                    monthly_percentage = min(monthly_percentage, 40.0)  # Cap at 40%
                else:
                    monthly_percentage = 0
                monthly_odcv_percentages.append(monthly_percentage)
            
            # Extract values (default to 'N/A' if missing) - SIMPLE VERSION
            owner = building['ownername'].iloc[0] if not building.empty else 'N/A'
            floors = int(building['numfloors'].iloc[0]) if not building.empty and pd.notna(building['numfloors'].iloc[0]) else 'N/A'
            year_built = building['yearalter'].iloc[0] if not building.empty else 'N/A'
            building_class = safe_val(building, bbl, 'Class', 'N/A')
            
            # Commercial info
            property_manager = safe_val(building, bbl, 'property_manager', 'Unknown')
            pct_leased = int(float(safe_val(building, bbl, '% Leased', 0)))
            
            # Format landlord contact - now using separated columns from enhanced buildings_BIG_with_emails_complete_verified.csv
            
            # Get owner contact info from new separated columns in buildings_BIG_with_emails_complete_verified.csv
            consolidated_owner_phone = None
            consolidated_owner_name = None
            
            # Get owner contact info from new separated columns
            owner_phone = safe_val(building, bbl, 'Owner_Contact_Phone', None)
            owner_name = safe_val(building, bbl, 'Owner_Contact_Name', None)
            owner_email = safe_val(building, bbl, 'Owner_Contact_Email', None)
            owner_confidence = safe_val(building, bbl, 'Owner_Verification_Confidence', None)
            owner_job_title = safe_val(building, bbl, 'owner_job_title', None)

            # Filter emails for HIGH confidence only for Salesify
            high_confidence_owner_email = ""
            if (owner_email and pd.notna(owner_email) and 
                owner_confidence and pd.notna(owner_confidence) and 
                str(owner_confidence).upper() == "HIGH"):
                high_confidence_owner_email = str(owner_email).strip()
            
            # Build consolidated owner contact info
            consolidated_owner_name = None
            consolidated_owner_phone = None

            if owner_name and pd.notna(owner_name):
                consolidated_owner_name = str(owner_name).strip()

            if owner_phone and pd.notna(owner_phone):
                consolidated_owner_phone = str(owner_phone).strip()
            
            # Build landlord contact string using new separated columns
            landlord_contact = 'Unavailable'
            
            # Use primary owner data if available
            if consolidated_owner_name:
                # Add job title in parentheses if available
                name_with_title = consolidated_owner_name
                if owner_job_title and pd.notna(owner_job_title) and str(owner_job_title).strip():
                    name_with_title = f"{consolidated_owner_name} ({str(owner_job_title).strip()})"
                contact_parts = [name_with_title]
                if consolidated_owner_phone:
                    contact_parts.append(consolidated_owner_phone)
                if owner_email and pd.notna(owner_email):
                    contact_parts.append(str(owner_email).strip())
                landlord_contact = ' • '.join(contact_parts)
            elif consolidated_owner_phone:
                # Just phone number available
                contact_parts = [consolidated_owner_phone]
                if owner_email and pd.notna(owner_email):
                    contact_parts.append(str(owner_email).strip())
                landlord_contact = ' • '.join(contact_parts)
            elif owner_email and pd.notna(owner_email):
                # Just email available
                landlord_contact = str(owner_email).strip()
            
            # No fallback column available - landlord_contact remains as set above
            
            # Format property manager contact - using new separated columns
            pm_name = safe_val(building, bbl, 'Property_Manager_Contact_Name', None)
            pm_phone = safe_val(building, bbl, 'Property_Manager_Contact_Phone', None)
            pm_email = safe_val(building, bbl, 'Property_Manager_Contact_Email', None)
            pm_confidence = safe_val(building, bbl, 'Manager_Verification_Confidence', None)
            pm_job_title = safe_val(building, bbl, 'pm_job_title', None)

            # Filter emails for HIGH confidence only for Salesify
            high_confidence_pm_email = ""
            if (pm_email and pd.notna(pm_email) and 
                pm_confidence and pd.notna(pm_confidence) and 
                str(pm_confidence).upper() == "HIGH"):
                high_confidence_pm_email = str(pm_email).strip()
            
            # No secondary PM contact columns available
            
            # Build property manager contact string
            property_manager_contact = 'Unavailable'
            
            # Use primary PM data if available
            if pm_name and pd.notna(pm_name):
                # Add job title in parentheses if available
                name_with_title = str(pm_name).strip()
                if pm_job_title and pd.notna(pm_job_title) and str(pm_job_title).strip():
                    name_with_title = f"{str(pm_name).strip()} ({str(pm_job_title).strip()})"
                contact_parts = [name_with_title]
                if pm_phone and pd.notna(pm_phone):
                    contact_parts.append(str(pm_phone).strip())
                if pm_email and pd.notna(pm_email):
                    contact_parts.append(str(pm_email).strip())
                property_manager_contact = ' • '.join(contact_parts)
            elif pm_phone and pd.notna(pm_phone):
                # Just phone number available
                contact_parts = [str(pm_phone).strip()]
                if pm_email and pd.notna(pm_email):
                    contact_parts.append(str(pm_email).strip())
                property_manager_contact = ' • '.join(contact_parts)
            elif pm_email and pd.notna(pm_email):
                # Just email available
                property_manager_contact = str(pm_email).strip()
            
            # No secondary PM contact columns to check
            # No fallback column needed - PropertyManagerContact has been removed

            # Check for duplicate contacts and merge information
            if landlord_contact != 'Unavailable' and property_manager_contact != 'Unavailable':
                # Extract names from contacts to compare
                owner_contact_name = ""
                manager_contact_name = ""

                # Parse owner contact name
                if consolidated_owner_name:
                    owner_contact_name = consolidated_owner_name.lower().strip()

                # Parse manager contact name
                if pm_name and pd.notna(pm_name):
                    manager_contact_name = str(pm_name).lower().strip()

                # Check if names match (case-insensitive)
                if owner_contact_name and manager_contact_name and owner_contact_name == manager_contact_name:
                    # Names match - merge contact information
                    # Parse both contacts to extract all unique pieces of information
                    owner_parts = landlord_contact.split(' • ')
                    manager_parts = property_manager_contact.split(' • ')

                    # Extract unique phone numbers and emails
                    all_phones = set()
                    all_emails = set()
                    name_with_title = owner_parts[0]  # Use the owner's name/title format

                    for part in owner_parts[1:]:  # Skip name
                        if '@' in part:
                            all_emails.add(part)
                        elif any(c.isdigit() for c in part):  # Likely a phone number
                            all_phones.add(part)

                    for part in manager_parts[1:]:  # Skip name
                        if '@' in part:
                            all_emails.add(part)
                        elif any(c.isdigit() for c in part):  # Likely a phone number
                            all_phones.add(part)

                    # Rebuild the merged contact string
                    merged_parts = [name_with_title]
                    merged_parts.extend(sorted(all_phones))
                    merged_parts.extend(sorted(all_emails))

                    # Update landlord contact with merged info
                    landlord_contact = ' • '.join(merged_parts)
                    # Clear manager contact since it's duplicate
                    property_manager_contact = 'Unavailable'

            # Logo mapping using the same function as homepage
            logo_file = find_logo_file(owner)
            if logo_file:
                # Make Vornado logo bigger
                logo_height = "45px" if "Vornado" in owner else "30px"
                owner_logo = f' <img src="{AWS_IMAGES_BUCKET}/logos/{logo_file}" style="height:{logo_height};margin-left:10px;vertical-align:middle;">'
            else:
                owner_logo = ""
            
            # Manager logo
            manager_logo_file = find_logo_file(property_manager)
            if manager_logo_file:
                # Make Vornado logo bigger
                logo_height = "45px" if "Vornado" in property_manager else "30px"
                manager_logo = f' <img src="{AWS_IMAGES_BUCKET}/logos/{manager_logo_file}" style="height:{logo_height};margin-left:10px;vertical-align:middle;">'
            else:
                manager_logo = ""
            
            # Get detailed BMS info
            has_bas = safe_val(system_data, bbl, 'Has Building Automation', 'N/A')
            heating_automation = safe_val(system_data, bbl, 'Heating Automation', 'N/A')
            cooling_automation = safe_val(system_data, bbl, 'Cooling Automation', 'N/A')
            energy_star = safe_val(building, bbl, 'Latest_ENERGY_STAR_Score', 'N/A')
            # Convert to integer if numeric (remove decimal)
            if energy_star != 'N/A':
                try:
                    energy_star = int(float(energy_star))
                except:
                    pass

            # System info
            heating_type = system_data['Heating System Type'].iloc[0] if not system_data.empty and 'Heating System Type' in system_data.columns else 'N/A'
            cooling_type = system_data['Cooling System Type'].iloc[0] if not system_data.empty and 'Cooling System Type' in system_data.columns else 'N/A'
            
            # Property details
            num_floors = int(building['numfloors'].iloc[0]) if not building.empty and pd.notna(building['numfloors'].iloc[0]) else 'N/A'
            year_built_real = building['yearalter'].iloc[0] if not building.empty else 'N/A'
            total_area = building['total_gross_floor_area'].iloc[0] if not building.empty else 0
            office_sqft = int(float(safe_val(building, bbl, 'office_sqft', 0)))
            office_pct = int(float(safe_val(hvac_data, bbl, 'office_pct_of_building', 0)) * 100)
            office_percentage = (office_sqft / total_area * 100) if total_area > 0 else 0
            year_altered_raw = safe_val(building, bbl, 'yearalter', 'N/A')
            year_altered = int(float(year_altered_raw)) if year_altered_raw != 'N/A' and year_altered_raw != '' else 'N/A'
            total_units = int(safe_val(building, bbl, 'unitstotal', 0))
            # Get elevator count - keep as blank if not provided
            num_elevators_raw = safe_val(building, bbl, 'Number Of Elevators', '')
            num_elevators = int(num_elevators_raw) if num_elevators_raw and str(num_elevators_raw).strip() != '' else None
            opex_per_sqft = safe_val(building, bbl, '2024 Building OpEx/SF', 'N/A')
            typical_floor_sqft = safe_val(building, bbl, 'Typical Floor Sq Ft', 'N/A')
            # Format as comma-separated number if it's numeric
            if typical_floor_sqft != 'N/A':
                try:
                    typical_floor_sqft = f"{int(float(typical_floor_sqft)):,}"
                except:
                    pass
            
            # Get LL97 display values from ten_year_savings data
            # Try to get carbon limits from FIXED file data or set reasonable defaults
            carbon_limit_2024 = float(building_ten_year['carbon_limit_2024_tCO2e'].iloc[0])
            carbon_limit_2030 = float(building_ten_year['carbon_limit_2030_tCO2e'].iloc[0])
            total_carbon_emissions_2024 = float(building_ten_year['total_carbon_emissions_2024_tCO2e'].iloc[0])
            total_carbon_emissions_2030 = float(building_ten_year['total_carbon_emissions_2030_tCO2e'].iloc[0])

            # Calculate carbon reduction from ODCV (applies to both periods)
            # ODCV reduces HVAC energy, which proportionally reduces carbon emissions
            odcv_carbon_reduction_2024 = (utility_savings_annual / annual_building_cost) * total_carbon_emissions_2024 if annual_building_cost > 0 else 0
            odcv_carbon_reduction_2030 = (utility_savings_annual / annual_building_cost) * total_carbon_emissions_2030 if annual_building_cost > 0 else 0

            # Note: corrected_ll97_avoidance and corrected_ll97_avoidance_2030 are set from CSV above
            
            # Get LL33 grade - use REAL data, not fake 'B'
            ll33_grade = safe_val(building, bbl, 'LL33 grade', 'N/A')
            ll33_grade_raw = str(ll33_grade).replace(' ', '').upper() if ll33_grade != 'N/A' else 'NA'
            
            # Get compliance status
            # Compliance is based on whether emissions exceed limits
            compliance_2024 = str(building_ten_year['compliance_2024_status'].iloc[0])
            compliance_2030 = str(building_ten_year['compliance_2030_status'].iloc[0])
            
            # CSV compliance data no longer available - use calculated values
            # compliance_2024 and compliance_2030 are already set based on LL97 avoidance amounts
            
            # Get green rating (LEED, Energy Star certification)
            green_rating = safe_val(building, bbl, 'GreenRating', '')
            
            # Get address and building name
            main_address = address_data['address_from_bbl'].iloc[0] if not address_data.empty else row['address']
            building_name = safe_val(address_data, bbl, 'primary_building_name', '')
            # Get building coordinates from CSV data or use default
            lat = safe_val(building, bbl, 'latitude', 40.7580)
            lon = safe_val(building, bbl, 'longitude', -73.9855)
            
            # Get neighborhood from CSV data for accurate air quality data
            neighborhood = safe_val(building, bbl, 'neighborhood', 'Unknown')

            # Get tenant data for this building
            building_tenants = pd.DataFrame()  # Default empty
            if not tenants_df.empty:
                # Get tenants for this BBL directly
                # Handle both old 'BBL' and new 'bbl' column names
                bbl_col = 'bbl' if 'bbl' in tenants_df.columns else 'BBL'
                building_tenants = tenants_df[tenants_df[bbl_col] == bbl].copy()
                if not building_tenants.empty:
                    # Sort by SF_Numeric (descending) and get top 10
                    building_tenants = building_tenants.sort_values('SF_Numeric', ascending=False).head(10)
            
            # Get equipment counts for this building
            cooling_towers = 0
            water_tanks = 0
            if not equipment_counts.empty:
                equipment_data = equipment_counts[equipment_counts['bbl'] == bbl]
                if not equipment_data.empty:
                    cooling_towers = int(equipment_data['cooling_towers'].iloc[0]) if pd.notna(equipment_data['cooling_towers'].iloc[0]) else 0
                    water_tanks = int(equipment_data['water_tanks'].iloc[0]) if pd.notna(equipment_data['water_tanks'].iloc[0]) else 0
            
            # Get EUI value for this building
            building_eui = 0
            eui_percentile = 0
            eui_benchmark = ""  # Benchmark text from CSV
            eui_benchmark_color = "black"  # Color for benchmark text
            eui_comparison_text = ""  # Empty string when no comparison data
            eui_comparison_status = "unknown"  # Will be "over", "under", or "unknown"

            if not eui_data.empty:
                building_eui_data = eui_data[eui_data['bbl'] == bbl]
                if not building_eui_data.empty:
                    building_eui = float(building_eui_data['building_eui_kBtu_sf_year'].iloc[0])

                    # Get benchmark text if available
                    if 'benchmark' in building_eui_data.columns:
                        eui_benchmark = str(building_eui_data['benchmark'].iloc[0])

                    # Determine color based on benchmark (red = less efficient/above median, green = more efficient/below median)
                    eui_benchmark_color = "black"  # default
                    if eui_benchmark:
                        # Extract percentage from benchmark text (e.g., "55% above avg" or "15% below avg")
                        match = re.search(r'(\d+)%\s+(above|below)', eui_benchmark)
                        if match:
                            pct = int(match.group(1))
                            direction = match.group(2)
                            # Significantly different = more than 15% from median
                            if direction == "above" and pct > 15:
                                eui_benchmark_color = "red"  # Less efficient (higher EUI is worse)
                            elif direction == "below" and pct > 15:
                                eui_benchmark_color = "green"  # More efficient (lower EUI is better)

                    # Calculate percentile rank for this building's EUI (still used for color coding)
                    all_euis = eui_data['building_eui_kBtu_sf_year'].dropna()
                    better_than = (all_euis > building_eui).sum()
                    total = len(all_euis)
                    eui_percentile = int((better_than / total) * 100) if total > 0 else 0

                    # Get national comparison data
                    if not national_eui_data.empty:
                        national_data = national_eui_data[national_eui_data['bbl'] == bbl]
                        if not national_data.empty:
                            comparison_pct = national_data['comparison percentage'].iloc[0]
                            comparison = national_data['comparison'].iloc[0]
                            eui_comparison_status = comparison
                            eui_comparison_text = f"{comparison_pct:.0f}% {comparison} national avg EUI for similar buildings"
                        # No else clause - leave eui_comparison_text as empty string

            # Get data center information
            has_datacenter = False
            datacenter_text = ""
            if not datacenter_data.empty:
                dc_data = datacenter_data[datacenter_data['bbl'] == bbl]
                if not dc_data.empty:
                    dc_sqft = dc_data['Data Center_sqft'].iloc[0]
                    # Check if building has a data center based on sqft > 0
                    if pd.notna(dc_sqft) and dc_sqft > 0:
                        has_datacenter = True
                        # Get energy consumption if available
                        dc_energy = dc_data['Data Center Electricity Use (kBtu)'].iloc[0] if 'Data Center Electricity Use (kBtu)' in dc_data.columns else None

                        # Format the display text with sqft and energy
                        datacenter_text = f"{int(dc_sqft):,} sq ft"
                        if pd.notna(dc_energy) and dc_energy > 0:
                            datacenter_text += f" | {int(dc_energy):,} kBtu/year"

            # Convert to float if they're strings
            try:
                lat = float(lat) if lat != 'N/A' else 40.7580
                lon = float(lon) if lon != 'N/A' else -73.9855
            except (ValueError, TypeError):
                lat, lon = 40.7580, -73.9855
                print(f"Invalid coordinates for {main_address}, using Manhattan center")

            # TURBO MODE: Generate realistic fake PM2.5 data instead of API call
            import random
            random.seed(hash(bbl) % 2**32)  # Consistent per building

            neighborhood_factor = get_neighborhood_pollution_factor(neighborhood)
            chart_dates = []
            chart_values = []
            chart_labels = []

            # Generate 365 days of realistic PM2.5 data
            base_pm25 = 8.5  # NYC baseline
            for day_offset in range(365):
                day = datetime.now() - timedelta(days=365-day_offset)
                chart_dates.append(day.strftime('%Y-%m-%d'))

                # Seasonal variation (winter higher)
                month = day.month
                if month in [12, 1, 2]:
                    seasonal = 1.25
                elif month in [6, 7, 8]:
                    seasonal = 0.85
                else:
                    seasonal = 1.0

                # Daily variation
                daily_var = random.uniform(0.7, 1.4)
                pm25 = base_pm25 * neighborhood_factor * seasonal * daily_var
                pm25 = max(3.0, min(35.0, pm25))  # Clamp realistic range
                chart_values.append(round(pm25, 1))

                # Month labels
                if day.day == 1:
                    chart_labels.append(day.strftime('%b'))
                else:
                    chart_labels.append('')

            avg_pm25 = sum(chart_values) / len(chart_values)
            max_pm25 = max(chart_values)

            # EPA AQI categories for PM2.5
            if avg_pm25 <= 12:
                aqi_color = "#00e400"
            elif avg_pm25 <= 35.4:
                aqi_color = "#FFB300"
            elif avg_pm25 <= 55.4:
                aqi_color = "#ff7e00"
            elif avg_pm25 <= 150.4:
                aqi_color = "#ff0000"
            else:
                aqi_color = "#8f3f97"
            
            # Simple calculations - CORRECTED METHODOLOGY
            total_odcv_savings = row['utility_savings_annual']
            score = row['total_score']
            rank = int(row['final_rank'])
            
            # Get LL97 avoidance value (constant across all years in 10_year_savings_by_building.csv)
            ll97_raw = building_ten_year['ll97_avoidance_2026'].iloc[0] if not building_ten_year.empty else 0
            ll97_annual_avoidance = safe_ll97_float(ll97_raw) if not building_ten_year.empty else 0
            
            # Total annual savings including energy savings and LL97 penalty avoidance
            # Total annual savings = ODCV energy savings + constant LL97 penalty avoidance
            # Use utility_savings_annual from CSV (this is the ODCV savings)
            # Handle case where ll97_2026 might be "NA (City Owned)"
            if isinstance(ll97_2026, str):
                total_annual_savings = utility_savings_annual  # City owned - no LL97 penalty
            else:
                total_annual_savings = utility_savings_annual + ll97_2026  # For 2026
            # Use the corrected 2026 savings from 10_year_savings_by_building.csv
            total_2026_savings = savings_1yr  # This already includes utility + LL97 from CSV
            
            # Calculate NOI and valuation impact from ODCV savings
            noi_impact_percentage = 0
            building_valuation_impact = 0
            cap_rate_median = 0
            category_description = "N/A"
            
            if not categorization_df.empty:
                cat_data = categorization_df[categorization_df['bbl'] == bbl]
                if not cat_data.empty:
                    current_noi = float(cat_data['current_noi'].iloc[0])
                    cap_rate_median = float(cat_data['cap_rate_median'].iloc[0])
                    category_description = "N/A"

                    # Get NOI impact percentage and valuation impact directly from CSV
                    noi_val = cat_data['noi_impact_percentage'].values[0]
                    if isinstance(noi_val, str) and 'City Owned' in str(noi_val):
                        noi_impact_percentage = 'NA (City Owned)'
                    else:
                        noi_impact_percentage = float(noi_val) if noi_val else 0

                    val_impact = cat_data['odcv_value_increase'].values[0]
                    if isinstance(val_impact, str) and 'City Owned' in str(val_impact):
                        building_valuation_impact = 'NA (City Owned)'
                    else:
                        building_valuation_impact = float(val_impact) if val_impact else 0
            
            # Calculate total annual office HVAC costs for Elizabeth's percentage
            total_office_hvac_cost_annual = 0
            for m_idx in range(12):
                # Electric HVAC cost = Office electric cost × HVAC percentage
                monthly_elec_hvac = office_elec_cost[m_idx] * hvac_pct[m_idx] if m_idx < len(hvac_pct) else 0
                # Gas HVAC cost = Office gas cost × 0.9 (90% is HVAC)
                monthly_gas_hvac = office_gas_cost[m_idx] * 0.9
                # Steam HVAC cost = Office steam cost × 0.9 (90% is HVAC)
                monthly_steam_hvac = office_steam_cost[m_idx] * 0.9
                total_office_hvac_cost_annual += monthly_elec_hvac + monthly_gas_hvac + monthly_steam_hvac

            # Calculate ODCV savings as percentage of HVAC costs
            odcv_percentage_of_hvac = (total_odcv_savings / total_office_hvac_cost_annual * 100) if total_office_hvac_cost_annual > 0 else 0
            
            # Calculate annual building cost for Salesify email
            annual_building_cost = sum(elec_cost) + sum(gas_cost) + sum(steam_cost)
            
            # Calculate additional ODCV metrics for summary box
            avg_monthly_hvac_cost = total_office_hvac_cost_annual / 12
            avg_monthly_odcv_savings = total_odcv_savings / 12
            payback_months = (50000 / total_odcv_savings * 12) if total_odcv_savings > 0 else 999  # Assume $50k implementation cost
            if odcv_savings and len(odcv_savings) > 0:
                best_month_idx = odcv_savings.index(max(odcv_savings))
                best_month_name = months[best_month_idx]
                best_month_savings = max(odcv_savings)
            else:
                best_month_idx = 0
                best_month_name = "Jan"
                best_month_savings = 0
            
            # Penalty breakdown for header - SHOW BOTH COMPONENTS
            ll97_display = ll97_avoidance_2026 if isinstance(ll97_avoidance_2026, str) else f"${ll97_avoidance_2026:,.0f}"
            if utility_savings_2026 > 0 or (ll97_avoidance_2026 != 0 and ll97_avoidance_2026 != 'NA (City Owned)'):
                penalty_breakdown_html = f'''<div style="font-size: 0.75em; opacity: 0.9; margin-top: 8px; line-height: 1.4;">
                    <div>Utility Bill Savings: ${utility_savings_2026:,.0f}</div>
                    <div>LL97 Penalty Avoidance: {ll97_display}</div>
                </div>'''
            elif ll97_avoidance_2026 == 'NA (City Owned)':
                penalty_breakdown_html = f'''<div style="font-size: 0.75em; opacity: 0.9; margin-top: 8px; line-height: 1.4;">
                    <div>Utility Bill Savings: ${utility_savings_2026:,.0f}</div>
                    <div>LL97 Penalty: NA (City Owned)</div>
                </div>'''
            else:
                penalty_breakdown_html = ''
            
            # Get owner building count for portfolio score
            owner_building_count = buildings[buildings['ownername'] == owner].shape[0] if owner != 'N/A' else 1
            
            # Simple score breakdown
            cost_savings_score = min(40, total_odcv_savings / 25000)  # Max 40 pts
            bas_score = 30 if has_bas == 'yes' else 0  # 30 pts for BMS
            portfolio_score = 20 if owner_building_count > 5 else 10  # 20 pts for big portfolios
            ease_score = 10 if num_floors < 20 else 5  # 10 pts for smaller buildings
            
            # Energy Star calculations
            energy_star_num = float(energy_star) if energy_star != 'N/A' and energy_star else 0
            target_energy_star = 75  # Target score
            if energy_star_num < 50:
                energy_star_color = '#c41e3a'  # Red
            elif energy_star_num < 75:
                energy_star_color = '#ffc107'  # Yellow
            else:
                energy_star_color = '#38a169'  # Green
            
            # Energy Star comparison
            energy_star_delta = ""
            target_score = None  # Will be set if target exists
            if energy_star != 'N/A' and not pd.isna(energy_star):
                try:
                    current_score = float(energy_star)
                    # Try to get actual target from buildings data
                    target_energy_star_val = safe_val(building, bbl, 'Latest_Target_ENERGY_STAR_Score', 'N/A')
                    if target_energy_star_val != 'N/A':
                        target_score = int(float(target_energy_star_val))
                        # Only calculate delta if we have a target score
                        delta = target_score - current_score
                        if delta > 0:
                            energy_star_delta = f'<div style="color: #c41e3a;">↑ {delta:.0f} points needed</div>'
                        else:
                            energy_star_delta = f'<div style="color: #38a169;">✓ Exceeds target by {abs(delta):.0f} points</div>'
                except:
                    energy_star_delta = ""
            
            # Create BMS text with details
            if has_bas == 'yes':
                has_heating = heating_automation == 'yes'
                has_cooling = cooling_automation == 'yes'
                
                if has_heating and has_cooling:
                    bas_text = '<span style="color: white; font-size: 18px; line-height: 30px; text-shadow: 1px 1px 2px black;">Ventilation</span><span>, </span><span style="color: #ff6600; font-weight: normal; text-shadow: 1px 1px 2px black;">Heating</span><span>, </span><span style="color: #0066cc; font-weight: normal; text-shadow: 1px 1px 2px black;">Cooling</span>'
                elif has_heating:
                    bas_text = '<span style="color: white; font-size: 18px; line-height: 30px; text-shadow: 1px 1px 2px black;">Ventilation</span><span>, </span><span style="color: #ff6600; font-weight: normal; text-shadow: 1px 1px 2px black;">Heating</span>'
                elif has_cooling:
                    bas_text = '<span style="color: white; font-size: 18px; line-height: 30px; text-shadow: 1px 1px 2px black;">Ventilation</span><span>, </span><span style="color: #0066cc; font-weight: normal; text-shadow: 1px 1px 2px black;">Cooling</span>'
                else:
                    bas_text = '<span style="color: white; font-size: 18px; line-height: 30px; text-shadow: 1px 1px 2px black;">Ventilation</span>'
                bas_class = 'bas'
            elif has_bas == 'no':
                bas_text = '<span style="color: #c41e3a; font-weight: 600;">⚠️  Absent</span>'
                bas_class = ''
            else:
                bas_text = '<span style="color: #FFB300; font-weight: 600;">Unknown</span>'
                bas_class = ''
            
            # Green rating badge
            green_rating_badge = ""
            if green_rating and green_rating != 'N/A' and green_rating != '':
                badge_class = 'green-badge'
                if 'Platinum' in green_rating:
                    badge_class = 'green-badge platinum'
                elif 'Gold' in green_rating:
                    badge_class = 'green-badge gold'
                elif 'Silver' in green_rating:
                    badge_class = 'green-badge silver'
                elif 'Certified' in green_rating:
                    badge_class = 'green-badge certified'
                
                green_rating_badge = f' <span class="{badge_class}">{green_rating}</span>'
            
            # Check if building has aerial video
            has_video = bbl in aerial_videos_available

            # 360 panorama disabled
            has_pano = False

            # Check if building has floorplan image in S3
            try:
                result = subprocess.run(
                    ['aws', 's3', 'ls', f's3://nyc-odcv-images/images/{bbl}/{bbl}_floorplan.png'],
                    capture_output=True, text=True, timeout=5
                )
                has_floorplan = result.returncode == 0
            except:
                has_floorplan = False

            # Check if building has 3D model in S3
            try:
                result = subprocess.run(
                    ['aws', 's3', 'ls', f's3://nyc-odcv-images/images/{bbl}/{bbl}_3d.glb'],
                    capture_output=True, text=True, timeout=5
                )
                has_3d = result.returncode == 0
            except:
                has_3d = False

            if has_video:
                # Get the AWS URL for this BBL, fallback to constructed URL if not in CSV
                video_url = aerial_video_urls.get(bbl, f"{AWS_VIDEO_BUCKET}/{bbl}_aerial.mp4")
                aerial_content = f'''<div id="aerial-video-{bbl}" style="width: 100%; height: 100%; background: #000; display: flex; align-items: center; justify-content: center; position: relative;">
                    <video controls autoplay loop muted preload="auto" style="width: 100%; height: 100%; object-fit: contain;"
                           onerror="this.style.display='none'; document.getElementById('video-error-{bbl}').style.display='flex';">
                        <source src="{video_url}" type="video/mp4">
                        Your browser does not support the video tag.
                    </video>
                    <div id="video-error-{bbl}" style="display: none; width: 100%; height: 100%; background: #f0f0f0; align-items: center; justify-content: center; flex-direction: column; position: absolute; top: 0; left: 0;">
                        <div style="text-align: center; color: #666;">
                            <h3>Aerial Video Unavailable</h3>
                            <p>The aerial view for this building is being processed</p>
                            <p style="font-size: 0.9em;">Please check back later</p>
                        </div>
                    </div>
                    <script>
                        // Ensure video autoplays on page load
                        document.addEventListener('DOMContentLoaded', function() {{
                            const video = document.querySelector('#aerial-video-{bbl} video');
                            if (video) {{
                                video.play().catch(e => console.log('Autoplay prevented:', e));
                            }}
                        }});
                    </script>
                </div>'''
            else:
                # No video available - will skip this slide
                aerial_content = None
            
            # Calculate LL97 totals by compliance period from CSV data
            # Period 1: 2026-2029 (same value each year)
            # Calculate totals (LL97 avoidance is constant every year per the data)
            ll97_only_1yr = ll97_annual_avoidance
            ll97_only_5yr = ll97_annual_avoidance * 5  # Same value for 5 years
            ll97_only_10yr = ll97_annual_avoidance * 10  # Same value for 10 years

            # Calculate LL97 chart data
            excess_2024 = max(0, total_carbon_emissions_2024 - carbon_limit_2024)
            excess_2030 = max(0, total_carbon_emissions_2030 - carbon_limit_2030)

            # Calculate max excess first (needed for threshold check)
            max_excess = max(excess_2024, excess_2030)

            # 20th percentile threshold - hide chart for buildings barely over the limit (bottom 20% of non-compliant)
            EXCESS_THRESHOLD_20TH_PERCENTILE = 62.18  # tCO2e

            # Show chart only if:
            # 1. Building is non-compliant in at least one period AND
            # 2. Max excess is above 20th percentile (not just barely over the limit)
            show_ll97_chart = False
            if ((compliance_2024 != 'Compliant' or compliance_2030 != 'Compliant') and
                max_excess >= EXCESS_THRESHOLD_20TH_PERCENTILE):
                show_ll97_chart = True

            # Determine chart scale based on excess emissions level to avoid white space
            if max_excess > 0:
                # Scale based on excess level ranges
                if max_excess <= 1000:
                    chart_max = 1000
                elif max_excess <= 2000:
                    chart_max = 2000
                elif max_excess <= 3000:
                    chart_max = 3000
                elif max_excess <= 5000:
                    chart_max = 5000
                elif max_excess <= 10000:
                    chart_max = 10000
                elif max_excess <= 15000:
                    chart_max = 15000
                elif max_excess <= 20000:
                    chart_max = 20000
                else:
                    chart_max = math.ceil(max_excess / 10000) * 10000
            else:
                chart_max = 1000  # Default scale if no excess

            # Calculate bar heights as percentages
            bar1_height = (excess_2024 / chart_max * 100) if chart_max > 0 else 0
            bar2_height = (excess_2030 / chart_max * 100) if chart_max > 0 else 0

            # Calculate ODCV stripe heights as % of bar
            odcv1_pct = min(100, (odcv_carbon_reduction_2024 / excess_2024 * 100)) if excess_2024 > 0 else 0
            odcv2_pct = min(100, (odcv_carbon_reduction_2030 / excess_2030 * 100)) if excess_2030 > 0 else 0

            # Calculate Y-axis height to match tallest bar
            max_bar_height_pct = max(bar1_height, bar2_height)
            y_axis_height_px = int(260 * max_bar_height_pct / 100) if max_bar_height_pct > 0 else 260
            y_axis_mid_px = int(y_axis_height_px / 2)

            # Create penalty section - CORRECTED METHODOLOGY
            penalty_section = f"""
    <div class="page">
        <h3 class="page-title">LL97 Compliance
            
        </h3>
        <div class="page-content">
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 15px;">
            <div style="border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; background: #f9f9f9;">
                <h4 style="margin: 0 0 12px 0; color: #333; font-size: 16px;">2024-2029 Compliance Period</h4>
                <div class="stat" style="margin-bottom: 8px;">
                    <span class="stat-label">Carbon Limit <span class="info-tooltip" data-tooltip="NYC's legal maximum emissions for office buildings (0.00758 metric tons CO2 per square foot annually). Exceeding this triggers fines." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span>
                    <span class="stat-value">{carbon_limit_2024:,.0f} tCO2e per year</span>
                </div>
                <div class="stat" style="margin-bottom: 8px;">
                    <span class="stat-label">Emissions w/o ODCV <span class="info-tooltip" data-tooltip="Building's projected annual emissions assuming no changes to current operations or equipment. Based on actual energy consumption data." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span>
                    <span class="stat-value">{total_carbon_emissions_2024:,.0f} tCO2e</span>
                </div>
                <div class="stat" style="margin-bottom: 8px;">
                    <span class="stat-label">Emissions w/ ODCV <span class="info-tooltip" data-tooltip="Expected emissions after ODCV reduces heating and cooling energy use. Assumes ODCV is the only improvement made." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span>
                    <span class="stat-value">{(total_carbon_emissions_2024 - odcv_carbon_reduction_2024):,.0f} tCO2e</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Fines Avoided <span class="info-tooltip" data-tooltip="Annual penalty reduction from staying under or closer to the limit. NYC charges $268 per metric ton over the cap." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span>
                    <span class="stat-value"> {corrected_ll97_avoidance if isinstance(corrected_ll97_avoidance, str) else f'${corrected_ll97_avoidance:,.0f}'}{' (already compliant w/o ODCV)' if (isinstance(corrected_ll97_avoidance, str) and corrected_ll97_avoidance == 'NA (City Owned)') or (not isinstance(corrected_ll97_avoidance, str) and corrected_ll97_avoidance == 0) else ''}</span>
                </div>
            </div>
            <div style="border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; background: #f9f9f9;">
                <h4 style="margin: 0 0 12px 0; color: #333; font-size: 16px;">2030-2034 Compliance Period</h4>
                <div class="stat" style="margin-bottom: 8px;">
                    <span class="stat-label">Carbon Limit <span class="info-tooltip" data-tooltip="NYC's 2030 emission cap for offices: 0.00269 metric tons CO2 per square foot. This 65% reduction from 2024 affects most buildings." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span>
                    <span class="stat-value">{carbon_limit_2030:,.0f} tCO2e per year</span>
                </div>
                <div class="stat" style="margin-bottom: 8px;">
                    <span class="stat-label">Emissions w/o ODCV <span class="info-tooltip" data-tooltip="Building's 2030 emissions if nothing changes. Lower than 2024 because the law assumes electricity becomes cleaner as renewables increase." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span>
                    <span class="stat-value">{total_carbon_emissions_2030:,.0f} tCO2e</span>
                </div>
                <div class="stat" style="margin-bottom: 8px;">
                    <span class="stat-label">Emissions w/ ODCV <span class="info-tooltip" data-tooltip="2030 emissions with ODCV installed. Same energy savings as 2024, but carbon reduction varies because electricity gets cleaner while gas doesn't." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span>
                    <span class="stat-value">{(total_carbon_emissions_2030 - odcv_carbon_reduction_2030):,.0f} tCO2e</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Fines Avoided <span class="info-tooltip" data-tooltip="Annual penalty savings for 2030-2034. Stricter limits mean more buildings exceed caps, making ODCV's emission reductions more financially valuable." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span>
                    <span class="stat-value"> {corrected_ll97_avoidance_2030 if isinstance(corrected_ll97_avoidance_2030, str) else f'${corrected_ll97_avoidance_2030:,.0f}'}{' (already compliant w/o ODCV)' if (isinstance(corrected_ll97_avoidance_2030, str) and corrected_ll97_avoidance_2030 == 'NA (City Owned)') or (not isinstance(corrected_ll97_avoidance_2030, str) and corrected_ll97_avoidance_2030 == 0) else ''}</span>
                </div>
            </div>
        </div>
"""

            # Add LL97 chart only if there's meaningful penalty avoidance
            if show_ll97_chart:
                # Position Y-axis label on the left side
                y_axis_label_left = "-10px"

                # Determine compliance status emojis for each period
                emoji_2024 = "✅" if excess_2024 == 0 else "⚠️"
                emoji_2030 = "✅" if excess_2030 == 0 else "⚠️"

                penalty_section += f"""
        <!-- LL97 Excess Emissions Chart -->
        <div style="margin-top: 30px;">
            <h4 style="margin: 0 0 20px 0; color: #333; font-size: 16px; text-align: center;">ODCV LL97 Compliance Impact</h4>
            <div class="ll97-chart" style="position: relative; height: 350px; background: white;">
                <div class="y-axis-title" style="position: absolute; left: {y_axis_label_left}; bottom: 160px; transform: rotate(-90deg); font-size: 12px; font-weight: bold;">tCO2e/yr</div>
                <div class="y-labels" style="position: absolute; left: 55px; bottom: 60px; height: {y_axis_height_px}px;">
                    <div class="y-label-top" style="position: absolute; right: 0; top: 0; font-size: 12px;">--</div>
                    <div class="y-label-mid" style="position: absolute; right: 0; top: {y_axis_mid_px}px; font-size: 12px;">--</div>
                    <div class="y-label-bot" style="position: absolute; right: 0; bottom: 0; font-size: 12px;">0</div>
                </div>
                <div class="bars-area" style="position: absolute; left: 82px; right: 80px; bottom: 60px; height: 260px; display: flex; border-bottom: 2px solid black;">
                    <div class="bar-column" style="flex: 1; position: relative; display: flex; align-items: flex-end;">
                        <div class="orange-bar bar-2024" style="width: 100%; background: #e65100; position: relative; height: 0%;">
                            <div class="striped-top odcv-2024" style="position: absolute; top: 0; left: 0; right: 0; height: 0%; background: #e65100; border-bottom: 2px dashed white;">
                                <div style="position: absolute; top: 0; left: 0; right: 0; bottom: 0; background-image: repeating-linear-gradient(135deg, transparent, transparent 10px, rgba(255, 255, 255, 0.3) 10px, rgba(255, 255, 255, 0.3) 12px);"></div>
                                <div style="position: absolute; top: 0; left: 0; right: 0; bottom: 0;">
                                    <span style="position: absolute; color: white; font-size: 20px; left: 15%; top: 50%; transform: translateY(-50%);">↘</span>
                                    <span style="position: absolute; color: white; font-size: 20px; left: 35%; top: 50%; transform: translateY(-50%);">↘</span>
                                    <span style="position: absolute; color: white; font-size: 20px; left: 55%; top: 50%; transform: translateY(-50%);">↘</span>
                                    <span style="position: absolute; color: white; font-size: 20px; left: 75%; top: 50%; transform: translateY(-50%);">↘</span>
                                </div>
                            </div>
                        </div>
                        <div style="position: absolute; right: 0; bottom: 0; width: 2px; height: {y_axis_height_px}px; background: black;"></div>
                    </div>
                    <div class="bar-column" style="flex: 1; position: relative; display: flex; align-items: flex-end;">
                        <div class="orange-bar bar-2030" style="width: 100%; background: #e65100; position: relative; height: 0%;">
                            <div class="striped-top odcv-2030" style="position: absolute; top: 0; left: 0; right: 0; height: 0%; background: #e65100; border-bottom: 2px dashed white;">
                                <div style="position: absolute; top: 0; left: 0; right: 0; bottom: 0; background-image: repeating-linear-gradient(135deg, transparent, transparent 10px, rgba(255, 255, 255, 0.3) 10px, rgba(255, 255, 255, 0.3) 12px);"></div>
                                <div style="position: absolute; top: 0; left: 0; right: 0; bottom: 0;">
                                    <span style="position: absolute; color: white; font-size: 20px; left: 15%; top: 50%; transform: translateY(-50%);">↘</span>
                                    <span style="position: absolute; color: white; font-size: 20px; left: 35%; top: 50%; transform: translateY(-50%);">↘</span>
                                    <span style="position: absolute; color: white; font-size: 20px; left: 55%; top: 50%; transform: translateY(-50%);">↘</span>
                                    <span style="position: absolute; color: white; font-size: 20px; left: 75%; top: 50%; transform: translateY(-50%);">↘</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="labels" style="position: absolute; left: 82px; right: 80px; bottom: 20px; display: flex;">
                    <div style="flex: 1; text-align: center; font-weight: bold;">{emoji_2024} 2024-2029</div>
                    <div style="flex: 1; text-align: center; font-weight: bold;">{emoji_2030} 2030-2034</div>
                </div>
            </div>
            <div style="text-align: center; margin-top: 20px;">
                <span style="display: inline-block; margin: 0 20px;">
                    <span style="display: inline-block; width: 20px; height: 20px; background: #e65100; vertical-align: middle; margin-right: 5px;"></span>
                    <span>Excess Emissions</span>
                </span>
                <span style="display: inline-block; margin: 0 20px;">
                    <span style="display: inline-block; width: 20px; height: 20px; background: repeating-linear-gradient(135deg, #e65100, #e65100 4px, rgba(255, 255, 255, 0.4) 4px, rgba(255, 255, 255, 0.4) 6px); vertical-align: middle; margin-right: 5px;"></span>
                    <span>ODCV Reduction</span>
                </span>
            </div>
        </div>
"""

            # Close penalty section
            penalty_section += """
        </div>
    </div>
"""

            # Build conditional LL97 chart JavaScript
            if show_ll97_chart:
                ll97_chart_js = f"""
    // Populate LL97 Chart with real data
    document.addEventListener('DOMContentLoaded', function() {{
        // Chart data from Python
        const chartData = {{
            excess_2024: {excess_2024:.2f},
            excess_2030: {excess_2030:.2f},
            bar1_height: {bar1_height:.1f},
            bar2_height: {bar2_height:.1f},
            odcv1_pct: {odcv1_pct:.1f},
            odcv2_pct: {odcv2_pct:.1f},
            max_excess: {max_excess:.2f}
        }};

        // Update bar heights
        const bar2024 = document.querySelector('.bar-2024');
        const bar2030 = document.querySelector('.bar-2030');
        if (bar2024) bar2024.style.height = chartData.bar1_height + '%';
        if (bar2030) bar2030.style.height = chartData.bar2_height + '%';

        // Update ODCV stripe heights
        const odcv2024 = document.querySelector('.odcv-2024');
        const odcv2030 = document.querySelector('.odcv-2030');
        if (odcv2024) odcv2024.style.height = chartData.odcv1_pct + '%';
        if (odcv2030) odcv2030.style.height = chartData.odcv2_pct + '%';

        // Update Y-axis labels to show actual max excess value
        const topLabel = document.querySelector('.y-label-top');
        const midLabel = document.querySelector('.y-label-mid');
        if (topLabel) topLabel.textContent = Math.round(chartData.max_excess/1000) + 'k';
        if (midLabel) midLabel.textContent = Math.round(chartData.max_excess/2000) + 'k';

        // Add tooltips
        if (bar2024) {{
            bar2024.title = `Excess: ${{chartData.excess_2024.toFixed(1)}} tCO2e\\nODCV Reduction: {odcv_carbon_reduction_2024:.1f} tCO2e`;
        }}
        if (bar2030) {{
            bar2030.title = `Excess: ${{chartData.excess_2030.toFixed(1)}} tCO2e\\nODCV Reduction: {odcv_carbon_reduction_2030:.1f} tCO2e`;
        }}
    }});
"""
            else:
                ll97_chart_js = ""

            # EUI will be added to Performance section

            # Calculate value multiplier for tooltip (to avoid f-string formatting issues)
            value_multiplier = f"{1/cap_rate_median:.0f}" if cap_rate_median > 0 else "N/A"
            # Check if building is city owned
            is_city_owned = isinstance(noi_impact_percentage, str) and 'City Owned' in str(noi_impact_percentage)
            
            # Make the HTML with generation timestamp
            generation_time = datetime.now(pytz.timezone('America/New_York')).strftime('%Y-%m-%d %H:%M:%S EST')
            html = f"""<!DOCTYPE html>
<!-- Generated: {generation_time} -->
<!-- Last Updated: September 17, 2025 - Simplified Salesify Email (Utility Only) -->
<!-- Building Report Version: {version} -->
<html>
<head>
    <title>{main_address} - ODCV Analysis (v{version})</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" href="https://rzero.com/wp-content/themes/rzero/build/images/favicons/favicon.png">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --rzero-primary: #0066cc;
            --rzero-secondary: #0052a3;
            --text-light: #6b7280;
            --background: #f4fbfd;
            --card-bg: white;
            --border: #e5e7eb;
        }}
        
        body {{ 
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
            margin: 0; 
            padding: 0 200px; 
            background: var(--background);
            color: #1a202c;
            line-height: 1.6;
            min-height: 100vh;
        }}
        
        /* Header */
        .header {{
            background: white;
            border-bottom: 1px solid var(--border);
            padding: 20px 0;
        }}
        
        .logo-header {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .section-content {{
            /* No styling - just a wrapper */
        }}
        
        .rzero-logo {{
            width: 200px;
            height: 50px;
        }}
        
        h1 {{
            color: var(--rzero-primary);
            margin: 0;
            font-size: 2.5em;
            font-weight: 700;
        }}
        
        /* Building Identity Bar */
        .building-identity {{
            padding: 15px 40px;
            background: #f8f8f8;
            border-bottom: 1px solid #ddd;
            display: flex;
            justify-content: space-between;
            align-items: center;
            max-width: 1200px;
            margin: 0 auto;
        }}

        .neighborhood-badge {{
            font-size: 1.4em;
            color: var(--rzero-primary);
            font-weight: 600;
        }}

        .building-stats {{
            display: flex;
            gap: 20px;
            align-items: center;
        }}

        .stat-item {{
            color: #666;
            font-size: 0.95em;
        }}
        
        /* Green Rating Badges */
        .green-badge {{
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.9em;
            margin-left: 10px;
        }}

        .green-badge.platinum {{
            background: #e5e4e2;
            color: #333;
            border: 1px solid #999;
        }}

        .green-badge.gold {{
            background: #ffd700;
            color: #333;
        }}

        .green-badge.silver {{
            background: #c0c0c0;
            color: #333;
        }}

        .green-badge.certified {{
            background: #28a745;
            color: white;
        }}

        .green-badge:not(.platinum):not(.gold):not(.silver):not(.certified) {{
            background: #17a2b8;
            color: white;
        }}
        
        .container {{ 
            /* Just a wrapper */
        }}
        
        /* Section 0 - Title */
        .title-section {{
            background: url('https://rzero.com/wp-content/uploads/2025/02/bg-cta-bottom.jpg') center/cover;
            color: white;
            padding: 50px 0 20px 0;
            position: relative;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0, 118, 157, 0.08);
            margin-bottom: 30px;
        }}
        
        .title-section > div {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 6rem;
        }}
        
        .back {{ 
            margin: 20px 0; 
            padding: 0 20px;
        }}
        .back a {{ color: var(--rzero-primary); text-decoration: none; font-weight: 500; }}
        .back a:hover {{ text-decoration: underline; }}
        
        /* Section styling */
        .section {{
            background: white;
            border: 1px solid rgba(0, 118, 157, 0.2);
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 30px;
            box-shadow: 0 4px 20px rgba(0, 118, 157, 0.08);
        }}

        .section.collapsed {{
            padding: 8px 14px;      /* tighter */
            margin-bottom: 8px;     /* tighter stack */
            box-shadow: none;       /* flatter look when collapsed */
            border-color: rgba(0, 118, 157, 0.15);
        }}
        .section.collapsed .section-header {{
            font-size: 1.1em;       /* smaller title when collapsed */
            margin: 0;
            padding: 4px 0;
            border: 0;
            line-height: 1.25;
        }}
        .section.collapsed .collapse-arrow {{
            font-size: 18px;        /* smaller chevron */
        }}



        .section-header {{
            font-size: 2em;
            color: var(--rzero-primary);
            position: relative;
            cursor: pointer;
            user-select: none;
            margin-bottom: 40px;
            font-weight: 700;
            padding-bottom: 20px;
            border-bottom: 2px solid rgba(0, 118, 157, 0.2);
            max-width: 100%;
            box-sizing: border-box;
        }}

        .section.collapsed .section-header {{
            margin-bottom: 0;
            padding-bottom: 0;
            border-bottom: none;
        }}
        
        /* L1 Section collapse arrow styling */
        .collapse-arrow {{
            position: absolute;
            top: 50%;
            right: 0;
            transform: translateY(-50%);
            color: var(--rzero-primary);
            font-size: 26px;
            font-weight: bold;
            line-height: 1;
            transition: transform 0.3s ease;
            cursor: pointer;
        }}
        
        .collapse-arrow::before {{
            content: '▼';  /* DOWN arrow when expanded */
        }}
        
        .collapse-arrow.collapsed {{
            transform: translateY(-50%) rotate(90deg);  /* Rotate to RIGHT arrow when collapsed */
        }}
        
        /* Collapsible page content wrapper */
        .page-content {{
            overflow: visible !important;
            z-index: 1;
            transition: max-height 0.3s ease-out;
        }}
        
        .section-content {{
            overflow: hidden;
            transition: max-height 0.3s ease-out;
        }}
        
        .page {{ 
            margin-bottom: 40px;
            max-width: 100%;
            margin: 0 auto;
            padding: 0;
            box-sizing: border-box;
        }}
        .page-title {{ 
            font-size: 1.3em; 
            color: var(--text-dark); 
            margin-bottom: 20px; 
            font-weight: 500;
            position: relative;
            cursor: pointer;
            user-select: none;
            padding-bottom: 12px;
            border-bottom: 1px solid rgba(0, 118, 157, 0.15);
            max-width: 100%;  /* Full width L2 lines */
        }}
        
        /* Stats - Clean Apple-like spacing */
        .stat {{ 
            margin: 20px 0; 
            display: flex; 
            align-items: baseline;
            padding: 8px 0;
        }}
        
        .stat:last-child {{ margin-bottom: 0; }}
        
        .stat-label {{ 
            font-weight: 500; 
            color: #333; 
            min-width: 200px; 
            font-size: 1em;
        }}
        
        .stat-value {{ 
            font-size: 1.1em; 
            color: #555; 
            font-weight: 400;
        }}
        
        .penalty {{ color: #c41e3a; }}
        .savings {{ color: #38a169; }}
        
        /* Highlight boxes */
        .highlight-box {{ 
            background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); 
            padding: 40px; 
            border-radius: 12px; 
            text-align: center; 
            margin: 20px 0;
            border: 1px solid #2196f3;
        }}
        
        .highlight-box h4 {{ 
            margin: 0 0 15px 0; 
            color: var(--rzero-primary); 
            font-size: 1.4em; 
        }}
        
        .highlight-box div {{ 
            margin: 8px 0; 
            font-size: 1.1em; 
        }}
        
        .highlight-score {{ 
            font-size: 3.5em; 
            font-weight: 700; 
            color: var(--rzero-primary); 
            margin: 10px 0; 
        }}
        
        /* Carousel styles */
        .carousel-container {{
            position: relative;
            width: 100%;
            height: 675px;
            overflow: hidden;
            border-radius: 12px;
            margin: 20px 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        .carousel-track {{
            display: flex;
            transition: transform 0.3s ease;
            height: 100%;
        }}
        
        .carousel-slide {{
            min-width: 100%;
            flex: 0 0 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        .carousel-slide img {{
            width: 100%;
            height: 100%;
            object-fit: contain;
            background: #f0f0f0;
        }}
        
        /* Carousel Navigation */
        .fullscreen-btn {{
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(0, 0, 0, 0.6);
            color: white;
            border: none;
            padding: 10px;
            cursor: pointer;
            border-radius: 4px;
            font-size: 20px;
            z-index: 10;
            transition: background 0.3s ease;
        }}
        
        .fullscreen-btn:hover {{
            background: rgba(0, 0, 0, 0.8);
        }}
        
        .download-btn:hover {{
            background: rgba(0, 0, 0, 0.8);
        }}
        
        .carousel-btn {{
            position: absolute;
            top: 50%;
            transform: translateY(-50%);
            background: rgba(0, 0, 0, 0.5);
            color: white;
            border: none;
            padding: 20px;
            cursor: pointer;
            font-size: 24px;
            border-radius: 8px;
            transition: background 0.3s ease;
            z-index: 5;
        }}
        
        .carousel-btn:hover {{
            background: rgba(0, 0, 0, 0.7);
        }}
        
        .carousel-prev {{ left: 20px; }}
        .carousel-next {{ right: 20px; }}
        
        .carousel-dots {{
            position: absolute;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            display: flex;
            gap: 10px;
            z-index: 5;
        }}
        
        .dot {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.5);
            cursor: pointer;
            transition: background 0.3s ease;
        }}
        
        .dot.active {{
            background: white;
        }}
        
        .dot:hover {{
            background: rgba(255, 255, 255, 0.8);
        }}
        
        /* Professional Class Badge from Prospector */
        .class-badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 50px;
            height: 50px;
            border-radius: 50%;
            font-weight: bold;
            font-size: 1.8em;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
            position: relative;
            background: radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.3), transparent);
        }}

        .class-badge::before {{
            content: '';
            position: absolute;
            top: -3px;
            left: -3px;
            right: -3px;
            bottom: -3px;
            border-radius: 50%;
            z-index: -1;
        }}

        .class-A {{ 
            background-color: #FFD700;
            background-image: linear-gradient(135deg, #FFED4E 0%, #FFD700 50%, #B8860B 100%);
            color: #6B4423;
            border: 2px solid #B8860B;
        }}

        .class-B {{ 
            background-color: #C0C0C0;
            background-image: linear-gradient(135deg, #E8E8E8 0%, #C0C0C0 50%, #8B8B8B 100%);
            color: #2C2C2C;
            border: 2px solid #8B8B8B;
        }}

        .class-C {{ 
            background-color: #CD7F32;
            background-image: linear-gradient(135deg, #E89658 0%, #CD7F32 50%, #8B4513 100%);
            color: #4A2511;
            border: 2px solid #8B4513;
        }}

        .class-D, .class-E, .class-F {{ 
            background-color: #8B7355;
            background-image: linear-gradient(135deg, #A0826D 0%, #8B7355 50%, #6B4423 100%);
            color: #FFFFFF;
            border: 2px solid #6B4423;
        }}
        
        /* Energy Grade Styling - NYC LL97 Style */
        .energy-grade {{
            display: inline-block;
            padding: 12px 24px;
            border-radius: 6px;
            font-weight: bold;
            font-size: 1.4em;
            border: 2px solid;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        .grade-A {{ 
            background: #4CAF50; 
            color: white; 
            border-color: #388E3C;
        }}
        .grade-B {{ 
            background: #FFEB3B; 
            color: #333; 
            border-color: #F9A825;
        }}
        .grade-C {{ 
            background: #FF9800; 
            color: white; 
            border-color: #EF6C00;
        }}
        .grade-D {{ 
            background: #F44336; 
            color: white; 
            border-color: #C62828;
        }}
        .grade-F {{ 
            background: #9E9E9E; 
            color: white; 
            border-color: #616161;
        }}
        .grade-N, .grade-NA {{ 
            background: #E1BEE7; 
            color: #4A148C; 
            border-color: #BA68C8;
        }}
        
        /* Carousel Loading Animation */
        .carousel-slide iframe {{
            opacity: 0;
            transition: opacity 0.5s ease;
        }}
        
        .carousel-slide iframe.loaded {{
            opacity: 1;
        }}
        
        /* Videos should be visible immediately */
        .carousel-slide video {{
            opacity: 1;
        }}
        
        
        /* Chart Controls from Prospector */
        .chart-carousel {{ position: relative; }}
        .chart-toggle {{ 
            display: flex; 
            justify-content: center; 
            gap: 10px; 
            margin-bottom: 20px;
        }}
        .toggle-btn {{
            padding: 8px 20px;
            background: #f0f0f0;
            border: 1px solid #ddd;
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.3s ease;
            font-family: inherit;
            font-size: 14px;
        }}
        .toggle-btn.active {{
            background: var(--rzero-primary);
            color: white;
            border-color: var(--rzero-primary);
        }}
        .toggle-btn:hover {{
            opacity: 0.8;
        }}
        
        .dot {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.5);
            cursor: pointer;
        }}
        .dot.active {{
            background: white;
        }}
        
        .fullscreen-btn {{
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(0, 0, 0, 0.6);
            color: white;
            border: none;
            padding: 10px;
            cursor: pointer;
            border-radius: 4px;
            font-size: 20px;
            z-index: 10;
            transition: background 0.3s ease;
        }}

        .fullscreen-btn:hover {{
            background: rgba(0, 0, 0, 0.8);
        }}
        
        /* Salesify button */
        .salesify-btn {{
          font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          background: linear-gradient(180deg, #0ea5e9, #0066cc);
          color: #fff;
          border: none;
          padding: 10px 16px;
          border-radius: 10px;
          font-weight: 700;
          letter-spacing: 0.2px;
          cursor: pointer;
          box-shadow: 0 8px 20px rgba(0,102,204,.25);
          transition: transform .06s ease, filter .15s ease;
          z-index: 100;
          position: relative;
        }}
        .salesify-btn:hover {{ filter: brightness(1.06); transform: translateY(-1px); }}
        .salesify-btn:active {{ transform: translateY(0); }}
        
        .class-badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 50px;
            height: 50px;
            border-radius: 50%;
            font-weight: bold;
            font-size: 1.8em;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
        }}
        
        .class-A {{ 
            background: linear-gradient(135deg, #FFED4E 0%, #FFD700 50%, #B8860B 100%);
            color: #6B4423;
            border: 2px solid #B8860B;
        }}
        
        .class-B {{ 
            background: linear-gradient(135deg, #E8E8E8 0%, #C0C0C0 50%, #8B8B8B 100%);
            color: #2C2C2C;
            border: 2px solid #8B8B8B;
        }}
        
        .class-C {{ 
            background: linear-gradient(135deg, #E89658 0%, #CD7F32 50%, #8B4513 100%);
            color: #4A2511;
            border: 2px solid #8B4513;
        }}
        
        
        .yes {{ color: #38a169; font-weight: bold; }}
        .no {{ color: #c41e3a; font-weight: bold; }}
        .urgent {{ color: #c41e3a; font-weight: bold; }}
        .bas {{ color: #38a169; font-weight: 600; }}
        .no-bas {{ color: #c41e3a; font-weight: 600; }}
        
        /* Info tooltip styles - EXACT SAME AS WORKING RANKINGS TOOLTIP */
        .info-tooltip {{
            position: relative;
            display: inline-block;
        }}

        .info-tooltip-content {{
            display: none;
            position: absolute;
            top: 125%;
            left: 0;
            background-color: #333;
            color: #fff;
            padding: 15px;
            border-radius: 6px;
            font-size: 14px;
            line-height: 1.6;
            width: 500px;
            z-index: 2147483647;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            text-align: left;
        }}

        .info-tooltip:hover .info-tooltip-content {{
            display: block;
        }}

        .info-tooltip-content::before {{
            content: "";
            position: absolute;
            top: -5px;
            left: 20px;
            border: 5px solid transparent;
            border-bottom-color: #333;
        }}
        
        /* Smart positioning for tooltips near viewport edges */
        .stat-card:last-child .info-tooltip-content {{
            left: auto;
            right: 0;
            transform: translateX(0);
        }}

        .stat-card:last-child .info-tooltip-content::before {{
            left: auto;
            right: 20px;
        }}

        /* Ensure parent containers don't clip */
        .stat-card {{
            position: relative;
            z-index: 1;
        }}

        .stat-card:hover {{
            z-index: 1000;
        }}

        /* Ensure tooltips never go below page elements */
        .stat {{
            position: relative;
            z-index: 10;
        }}

        .stat:hover {{
            z-index: 2147483646;
        }}

        .info-tooltip {{
            z-index: 2147483646;
        }}

        .info-tooltip:hover {{
            z-index: 2147483647;
        }}
        
        
        /* Responsive Design */
        @media (max-width: 1400px) {{
            body {{
                padding: 0 100px;
            }}
        }}
        
        @media (max-width: 1024px) {{
            body {{
                padding: 0 50px;
            }}
            
            .title-section {{
                padding: 60px 20px 20px 20px;
            }}
            
            .title-section > div {{
                flex-direction: column;
                gap: 2rem;
                text-align: center;
            }}
            
            .section {{
                padding: 20px;
                margin-bottom: 20px;
            }}
            
            .section-header {{
                font-size: 1.5em;
            }}
        }}
        
        @media (max-width: 768px) {{
            body {{
                padding: 0 20px;
            }}
            
            .title-section {{
                padding: 40px 15px 20px 15px;
            }}
            
            .title-section > div {{
                gap: 1rem;
            }}
            
            .title-section span[style*="font-size: 2.5em"] {{
                font-size: 1.8em !important;
            }}
            
            .section {{
                padding: 15px;
                margin-bottom: 15px;
            }}
            
            .section-header {{
                font-size: 1.3em;
                margin-bottom: 20px;
            }}
            
            .carousel-container {{
                height: 400px;
            }}
            
            .stat {{
                flex-direction: column;
                align-items: flex-start;
            }}
            
            .stat-label {{
                min-width: auto;
                margin-bottom: 5px;
            }}

            .section.collapsed {{ padding: 6px 12px; margin-bottom: 6px; }}
            .section.collapsed .section-header {{ font-size: 1.05em; padding: 2px 0; }}
        }}
        
        @media (max-width: 480px) {{
            body {{
                padding: 0 10px;
            }}
            
            .title-section {{
                padding: 30px 10px 15px 10px;
            }}
            
            .section {{
                padding: 10px;
            }}
            
            .carousel-container {{
                height: 300px;
            }}
        }}

        /* Indeterminate progress bar animation for 3D loading */
        @keyframes indeterminate {{
            0% {{
                transform: translateX(-100%);
            }}
            100% {{
                transform: translateX(300%);
            }}
        }}

        /* Enhanced 3D model loading styles */
        .model-loading-overlay {{
            position: absolute !important;
            top: 0 !important;
            left: 0 !important;
            right: 0 !important;
            bottom: 0 !important;
            background: rgba(255, 255, 255, 0.95) !important;
            z-index: 10000 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }}
    </style>
    <script>
    // Define essential variables and functions early to avoid reference errors

    // Essential variables
    const buildingHasFloorplan = {'true' if has_floorplan else 'false'};
    const buildingHas3D = {'true' if has_3d else 'false'};
    let carouselIndex = {{}};
    let hiddenSlides = {{}};
    let interactiveIndex = 0;

    // Handle missing images by hiding slides
    function handleImageError(img, bbl, imageType) {{
        const slide = img.closest('.carousel-slide');
        if (slide && slide.parentElement) {{
            slide.remove();
        }}
    }}

    // Carousel navigation functions
    function moveCarousel(bbl, direction) {{
        // Will be fully implemented when DOM is ready
        console.log('moveCarousel called for', bbl, direction);
    }}

    function goToSlide(bbl, index) {{
        // Will be fully implemented when DOM is ready
        console.log('goToSlide called for', bbl, index);
    }}

    function downloadImage(button) {{
        // Will be fully implemented when DOM is ready
        console.log('downloadImage called');
    }}

    function toggleFullscreen(button) {{
        // Will be fully implemented when DOM is ready
        console.log('toggleFullscreen called');
    }}

    function moveInteractiveCarousel(bbl, direction) {{
        // Will be fully implemented when DOM is ready
        console.log('moveInteractiveCarousel called for', bbl, direction);
    }}

    function goToInteractiveSlide(bbl, index) {{
        // Will be fully implemented when DOM is ready
        console.log('goToInteractiveSlide called for', bbl, index);
    }}
    </script>
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.css">
    <script src="https://cdn.jsdelivr.net/npm/pannellum@2.5.6/build/pannellum.js"></script>
    <!-- Three.js for 3D Model Viewer -->
    <script src="https://unpkg.com/three@0.147.0/build/three.min.js"></script>
    <script src="https://unpkg.com/three@0.147.0/examples/js/controls/OrbitControls.js"></script>
    <script src="https://unpkg.com/three@0.147.0/examples/js/loaders/GLTFLoader.js"></script>
    <script src="https://accounts.google.com/gsi/client" async defer></script>
    <!-- Firebase (App + Auth + Firestore, compat) -->
    <script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js"></script>
    <script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-auth-compat.js"></script>
    <script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore-compat.js"></script>
    <script>
      window.firebaseConfig = {{
        apiKey: "AIzaSyAsxPRzyj7z6Nk3QPhOBK5CfyblY2LqAjk",
        authDomain: "prospector-leaderl-board.firebaseapp.com",
        projectId: "prospector-leaderl-board",
        storageBucket: "prospector-leaderl-board.firebasestorage.app",
        messagingSenderId: "70489892630",
        appId: "1:70489892630:web:51052e8b0b5da2e6779237"
      }};

      function initFirebase() {{
        if (!window.firebaseAppInitialized && typeof firebase !== 'undefined') {{
          try {{
            firebase.initializeApp(window.firebaseConfig);
            window.db = firebase.firestore();
            window.firebaseAppInitialized = true;
            console.log("Firebase initialized on building page");
          }} catch (e) {{
            console.error("Firebase initialization failed:", e);
            setTimeout(initFirebase, 500);
          }}
        }} else if (typeof firebase === 'undefined') {{
          setTimeout(initFirebase, 100);
        }}
      }}

      initFirebase();

      // Track visit (invisible - no UI)
      setTimeout(function() {{
        if (window.db && window.location.protocol !== 'file:') {{
          const bbl = '{bbl}';
          const buildingName = '{escape_js_string(main_address)}';

          // Track building visit
          const visitDoc = window.db.collection('visits').doc(bbl);
          visitDoc.get().then(doc => {{
            if (doc.exists) {{
              visitDoc.update({{
                count: firebase.firestore.FieldValue.increment(1),
                lastVisit: firebase.firestore.FieldValue.serverTimestamp()
              }});
            }} else {{
              visitDoc.set({{
                bbl: bbl,
                name: buildingName,
                count: 1,
                lastVisit: firebase.firestore.FieldValue.serverTimestamp()
              }});
            }}
          }}).catch(err => {{
            console.log('[Building tracking] Could not record visit');
          }});

          // Auth-based user tracking (names leaderboard)
          (function(){{
            if (typeof firebase === 'undefined' || !firebase.auth || !firebase.firestore) return;
            const db = window.db || firebase.firestore();

            firebase.auth().onAuthStateChanged(async (u)=>{{
              if (!u) return; // only track signed-in users
              const parts = (u.displayName||"").trim().split(/\\s+/);
              const first = parts.length ? parts.slice(0,-1).join(" ") || parts[0] : "";
              const last  = parts.length > 1 ? parts.slice(-1).join(" ") : "";

              const id = u.uid; // use uid as doc id (stable and unique)
              const ref = db.collection('userActivity').doc(id);

              await ref.set({{
                uid: u.uid,
                email: u.email || null,
                displayName: u.displayName || null,
                firstName: first || null,
                lastName: last || null,
                lastActive: firebase.firestore.FieldValue.serverTimestamp()
              }}, {{ merge: true }});

              // increment visit count and track building
              await ref.set({{
                visitCount: firebase.firestore.FieldValue.increment(1),
                buildingsVisited: firebase.firestore.FieldValue.arrayUnion(bbl)
              }}, {{ merge: true }});
            }});
          }})()
        }}
      }}, 1000); // Wait 1 second for Firebase to initialize
    </script>
    <script>
        // Check auth immediately to prevent flash
        (function() {{
            function checkAndSetAuth() {{
                // CONDITIONAL AUTH: Bypass authentication if accessed via file:// protocol
                if (window.location.protocol === 'file:') {{
                    console.log("File protocol detected - bypassing authentication in early check");
                    // Show main content immediately
                    const loginOverlay = document.getElementById("loginOverlay");
                    const mainContent = document.getElementById("mainContent");
                    if (loginOverlay) loginOverlay.style.display = "none";
                    if (mainContent) mainContent.style.display = "block";
                    return;
                }}
                
                const auth = localStorage.getItem("rzeroAuth");
                if (auth) {{
                    try {{
                        const authData = JSON.parse(auth);
                        if (Date.now() < authData.expires) {{
                            // Hide overlay immediately if already authenticated
                            const loginOverlay = document.getElementById("loginOverlay");
                            const mainContent = document.getElementById("mainContent");
                            if (loginOverlay) loginOverlay.style.display = "none";
                            if (mainContent) mainContent.style.display = "block";
                        }}
                    }} catch (e) {{
                        console.error('Error parsing auth data:', e);
                        localStorage.removeItem("rzeroAuth");
                    }}
                }}
            }}
            
            // Check if DOM is ready
            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', checkAndSetAuth);
            }} else {{
                checkAndSetAuth();
            }}
        }})();
    </script>
</head>
<body>
    <!-- Google Sign-In Overlay -->
    <div id="loginOverlay" style="
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: linear-gradient(135deg, #0066cc 0%, #004494 100%);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 10000;
    ">
        <div style="
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            text-align: center;
            max-width: 400px;
            width: 90%;
        ">
            <img src="https://rzero.com/wp-content/uploads/2021/10/rzero-logo-pad.svg" alt="R-Zero Logo" style="width: 150px; margin-bottom: 20px;">
            <h2 style="margin: 0 0 10px 0; color: #333;">NYC ODCV Prospector</h2>
            <p style="color: #666; margin-bottom: 25px;">Sign in with your R-Zero account</p>
            
            <div id="g_id_onload"
                 data-client_id="70489892630-1j0t3rni5a7f07ng3v3k916lunm9n76d.apps.googleusercontent.com"
                 data-callback="handleCredentialResponse"
                 data-auto_prompt="false">
            </div>
            <div style="display: flex; justify-content: center; margin-top: 10px;">
            <div class="g_id_signin"
                 data-type="standard"
                 data-size="large"
                 data-theme="outline"
                 data-text="sign_in_with"
                 data-shape="rectangular"
                 data-logo_alignment="left">
            </div>
            </div>        </div>
    </div>
    <div class="container" id="mainContent" style="display: none;">
        <!-- Navigation Bar -->
        <!-- Section 0.0 - Title -->
        <div class="title-section">
            <div style="display: flex; justify-content: space-between; align-items: center; width: 100%; max-width: 100vw; padding: 0 20px; box-sizing: border-box;">
                <a href="../index.html" style="text-decoration: none; display: block; position: absolute; top: 0; left: 0; z-index: 10;">
                    <div style="padding: 15px 40px; display: flex; align-items: center; gap: 10px; color: white; cursor: pointer; transition: all 0.3s ease;"
                         onmouseover="this.style.background='rgba(255,255,255,0.1)'"
                         onmouseout="this.style.background='transparent'">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="transition: transform 0.3s ease;"
                             onmouseover="this.style.transform='translateX(-5px)'"
                             onmouseout="this.style.transform='translateX(0)'">
                            <path d="M19 12H5M12 19l-7-7 7-7"/>
                        </svg>
                        <span style="font-size: 16px; font-weight: 500; opacity: 0.9;">Back</span>
                    </div>
                </a>
                <div style="flex: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; margin: 0 20px;">
                    <span style="font-size: 2.2em; font-weight: 700; color: white; line-height: 1.2; white-space: nowrap;">{main_address} • {neighborhood}</span>
                    <a href="../methodology.html" style="display: inline-flex; align-items: center; gap: 6px; color: rgba(255,255,255,0.85); text-decoration: none; font-size: 13px; font-weight: 500; margin-top: 12px; padding: 6px 14px; background: rgba(255,255,255,0.15); border-radius: 20px; transition: all 0.2s;"
                       onmouseover="this.style.background='rgba(255,255,255,0.25)'; this.style.color='white'"
                       onmouseout="this.style.background='rgba(255,255,255,0.15)'; this.style.color='rgba(255,255,255,0.85)'">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
                        </svg>
                        View Technical Methodology
                    </a>
                </div>
            </div>
        </div>

        <!-- Financial Impact Section -->
        <div class="section">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h2 class="section-header" style="margin: 0;">Financial Impact</h2>
                    <button id="salesifyBtn" class="salesify-btn" onclick="handleSalesify()">Salesify</button>
                </div>

                <div class="page-content">
                <div class="stat">
                    <span class="stat-label">1 Year Savings <span class="info-tooltip" data-tooltip="Total savings for 2026. Includes both utility bill reduction from ODCV implementation and avoided LL97 carbon emissions penalties." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span><span class="stat-value">${'{:,.0f}'.format(savings_1yr)}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">5 Year Savings <span class="info-tooltip" data-tooltip="Cumulative savings from 2026-2030. Includes both utility bill reduction from ODCV implementation and avoided LL97 carbon emissions penalties across all years." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span><span class="stat-value">${'{:,.0f}'.format(savings_5yr)}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">10 Year Savings <span class="info-tooltip" data-tooltip="Cumulative savings from 2026-2035. Includes both utility bill reduction from ODCV implementation and avoided LL97 carbon emissions penalties across all years." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span><span class="stat-value">${'{:,.0f}'.format(savings_10yr)}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">NOI Lift <span class="info-tooltip" data-tooltip="Increase in office space profitability from implementing ODCV. Includes reduced utility costs and avoided LL97 penalties (weighted average 2026-2036). Operating expenses from latest NYC Dept of Finance guidance for this neighborhood and building class." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span>
                    <span class="stat-value">{'NA (City Owned)' if isinstance(noi_impact_percentage, str) else '{:.1f}% increase'.format(noi_impact_percentage)}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Valuation Lift <span class="info-tooltip" data-tooltip="Calculated by dividing office-only annual ODCV savings by cap rate. Uses 10-year weighted average for LL97 penalties (4 years at 2026 levels, 5 years at 2030 levels, 1 year at 2035 level) to reflect changing carbon limits. Cap rate from latest NYC Dept of Finance guidance for this neighborhood and building class." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span>
                    <span class="stat-value">{'NA (City Owned)' if isinstance(building_valuation_impact, str) else '${:,.0f}'.format(building_valuation_impact) if building_valuation_impact > 0 else 'N/A'}</span>
                </div>
                </div>
        </div>

        <!-- Section 1: General -->
        <div class="section">
                <h2 class="section-header">Image Gallery</h2>
                
                <div class="page">
                <h3 class="page-title" id="image-gallery-title-{bbl}">Static: <span style="color: #555;">Marketing</span>
                    
                </h3>
                <div class="page-content">
                <div class="carousel-container">
                    <div class="carousel-track" id="carousel-{bbl}">
                        <div class="carousel-slide active" data-image-type="hero">
                            <div style="position: relative; width: 100%; height: 100%;">
                                <img src="{AWS_IMAGES_BUCKET}/images/{bbl}/{bbl}_hero.jpg"
                                     style="width: 100%; height: 100%; object-fit: contain; background: #f0f0f0;"
                                     onerror="handleImageError(this, '{bbl}', 'hero')">
                                <button class="download-btn" onclick="downloadImage(this)" title="Download Image" style="position: absolute; top: 20px; left: 20px; background: rgba(0, 0, 0, 0.6); color: white; border: none; padding: 8px 10px; cursor: pointer; border-radius: 4px; font-size: 20px; z-index: 10; transition: background 0.3s ease; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;">⬇</button>
                                <button class="fullscreen-btn" onclick="toggleFullscreen(this)" title="Fullscreen">⛶</button>
                            </div>
                        </div>
                        {f'''<div class="carousel-slide" data-image-type="floorplan">
                            <div style="position: relative; width: 100%; height: 100%;">
                                <img src="{AWS_IMAGES_BUCKET}/images/{bbl}/{bbl}_floorplan.png"
                                     style="width: 100%; height: 100%; object-fit: contain; background: #f0f0f0;"
                                     onerror="handleImageError(this, '{bbl}', 'floorplan')">
                                <button class="download-btn" onclick="downloadImage(this)" title="Download Image" style="position: absolute; top: 20px; left: 20px; background: rgba(0, 0, 0, 0.6); color: white; border: none; padding: 8px 10px; cursor: pointer; border-radius: 4px; font-size: 20px; z-index: 10; transition: background 0.3s ease; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;">⬇</button>
                                <button class="fullscreen-btn" onclick="toggleFullscreen(this)" title="Fullscreen">⛶</button>
                            </div>
                        </div>
                        ''' if has_floorplan else ''}
                        <div class="carousel-slide" data-image-type="roadview">
                            <div style="position: relative; width: 100%; height: 100%;">
                                <img src="{AWS_IMAGES_BUCKET}/images/{bbl}/{bbl}_roadview.jpg" 
                                     style="width: 100%; height: 100%; object-fit: contain; background: #f0f0f0;"
                                     onerror="handleImageError(this, '{bbl}', 'roadview')">
                                <button class="download-btn" onclick="downloadImage(this)" title="Download Image" style="position: absolute; top: 20px; left: 20px; background: rgba(0, 0, 0, 0.6); color: white; border: none; padding: 8px 10px; cursor: pointer; border-radius: 4px; font-size: 20px; z-index: 10; transition: background 0.3s ease; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;">⬇</button>
                                <button class="fullscreen-btn" onclick="toggleFullscreen(this)" title="Fullscreen">⛶</button>
                            </div>
                        </div>
                        <div class="carousel-slide" data-image-type="street">
                            <div style="position: relative; width: 100%; height: 100%;">
                                <img src="{AWS_IMAGES_BUCKET}/images/{bbl}/{bbl}_street.jpg" 
                                     style="width: 100%; height: 100%; object-fit: contain; background: #f0f0f0;"
                                     onerror="handleImageError(this, '{bbl}', 'street')">
                                <button class="download-btn" onclick="downloadImage(this)" title="Download Image" style="position: absolute; top: 20px; left: 20px; background: rgba(0, 0, 0, 0.6); color: white; border: none; padding: 8px 10px; cursor: pointer; border-radius: 4px; font-size: 20px; z-index: 10; transition: background 0.3s ease; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;">⬇</button>
                                <button class="fullscreen-btn" onclick="toggleFullscreen(this)" title="Fullscreen">⛶</button>
                            </div>
                        </div>
                        <div class="carousel-slide" data-image-type="satellite">
                            <div style="position: relative; width: 100%; height: 100%;">
                                <img src="{AWS_IMAGES_BUCKET}/images/{bbl}/{bbl}_satellite.jpg" 
                                     style="width: 100%; height: 100%; object-fit: contain; background: #f0f0f0;"
                                     onerror="handleImageError(this, '{bbl}', 'satellite')">
                                <button class="download-btn" onclick="downloadImage(this)" title="Download Image" style="position: absolute; top: 20px; left: 20px; background: rgba(0, 0, 0, 0.6); color: white; border: none; padding: 8px 10px; cursor: pointer; border-radius: 4px; font-size: 20px; z-index: 10; transition: background 0.3s ease; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;">⬇</button>
                                <button class="fullscreen-btn" onclick="toggleFullscreen(this)" title="Fullscreen">⛶</button>
                            </div>
                        </div>
                        <div class="carousel-slide" data-image-type="equipment">
                            <div style="position: relative; width: 100%; height: 100%;">
                                <img src="{AWS_IMAGES_BUCKET}/images/{bbl}/{bbl}_equipment.jpg" 
                                     style="width: 100%; height: 100%; object-fit: contain; background: #f0f0f0;"
                                     onerror="handleImageError(this, '{bbl}', 'equipment')">
                                <button class="download-btn" onclick="downloadImage(this)" title="Download Image" style="position: absolute; top: 20px; left: 20px; background: rgba(0, 0, 0, 0.6); color: white; border: none; padding: 8px 10px; cursor: pointer; border-radius: 4px; font-size: 20px; z-index: 10; transition: background 0.3s ease; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;">⬇</button>
                                <button class="fullscreen-btn" onclick="toggleFullscreen(this)" title="Fullscreen">⛶</button>
                            </div>
                        </div>
                        <div class="carousel-slide" data-image-type="double">
                            <div style="position: relative; width: 100%; height: 100%;">
                                <img src="{AWS_IMAGES_BUCKET}/images/{bbl}/{bbl}_double.jpg" 
                                     style="width: 100%; height: 100%; object-fit: contain; background: #f0f0f0;"
                                     onerror="handleImageError(this, '{bbl}', 'double')">
                                <button class="download-btn" onclick="downloadImage(this)" title="Download Image" style="position: absolute; top: 20px; left: 20px; background: rgba(0, 0, 0, 0.6); color: white; border: none; padding: 8px 10px; cursor: pointer; border-radius: 4px; font-size: 20px; z-index: 10; transition: background 0.3s ease; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;">⬇</button>
                                <button class="fullscreen-btn" onclick="toggleFullscreen(this)" title="Fullscreen">⛶</button>
                            </div>
                        </div>
                        <div class="carousel-slide" data-image-type="stack">
                            <div style="position: relative; width: 100%; height: 100%;">
                                <img src="{AWS_IMAGES_BUCKET}/images/{bbl}/{bbl}_stack.jpg" 
                                     style="width: 100%; height: 100%; object-fit: contain; background: #f0f0f0;"
                                     onerror="handleImageError(this, '{bbl}', 'stack')">
                                <button class="download-btn" onclick="downloadImage(this)" title="Download Image" style="position: absolute; top: 20px; left: 20px; background: rgba(0, 0, 0, 0.6); color: white; border: none; padding: 8px 10px; cursor: pointer; border-radius: 4px; font-size: 20px; z-index: 10; transition: background 0.3s ease; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;">⬇</button>
                                <button class="fullscreen-btn" onclick="toggleFullscreen(this)" title="Fullscreen">⛶</button>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Navigation arrows -->
                    <button class="carousel-btn carousel-prev" onclick="moveCarousel('{bbl}', -1)">‹</button>
                    <button class="carousel-btn carousel-next" onclick="moveCarousel('{bbl}', 1)">›</button>
                    
                    <div class="carousel-dots" id="carousel-dots-{bbl}">
                        <span class="dot active" onclick="goToSlide('{bbl}', 0)"></span>
                        <span class="dot" onclick="goToSlide('{bbl}', 1)"></span>
                        <span class="dot" onclick="goToSlide('{bbl}', 2)"></span>
                        <span class="dot" onclick="goToSlide('{bbl}', 3)"></span>
                        <span class="dot" onclick="goToSlide('{bbl}', 4)"></span>
                        <span class="dot" onclick="goToSlide('{bbl}', 5)"></span>
                    </div>
                </div>
                </div>
            </div>

            {f'''<div class="page">
                <h3 class="page-title" id="interactive-views-title-{bbl}">Dynamic: <span style="color: #555;">{
                    ('3D Model' if has_3d else
                     ('Drone Footage' if has_video else
                      ('360 Panorama' if has_pano else '')))
                }</span>

                </h3>
                <div class="page-content">
                <div class="carousel-container">
                    <div class="carousel-track" id="interactive-carousel-{bbl}">
                        {'<div class="carousel-slide" data-type="3d"><div id="model-viewer-' + str(bbl) + '" style="width: 100%; height: 675px; background: #ffffff; position: relative;"><div id="model-container-' + str(bbl) + '" style="width: 100%; height: 100%;"></div><div id="model-loading-' + str(bbl) + '" style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-family: Inter, sans-serif; color: #333; font-size: 18px; font-weight: 500; background: rgba(255, 255, 255, 0.95); padding: 20px 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1); z-index: 1000;">Loading 3D Model...</div></div></div>' if has_3d else ''}
                        {'<div class="carousel-slide" data-type="video">' + aerial_content + '</div>' if has_video else ''}
                        {'<div class="carousel-slide" data-type="pano"><div id="panorama-' + str(bbl) + '" style="width: 100%; height: 675px; background: #f0f0f0; position: relative;"><div id="viewer-' + str(bbl) + '" style="width: 100%; height: 100%;"></div></div></div>' if has_pano else ''}
                    </div>

                    {('<!-- Navigation arrows -->' +
                    '<button class="carousel-btn carousel-prev" onclick="moveInteractiveCarousel(\'' + str(bbl) + '\', -1)">‹</button>' +
                    '<button class="carousel-btn carousel-next" onclick="moveInteractiveCarousel(\'' + str(bbl) + '\', 1)">›</button>') if ((has_3d and (has_video or has_pano)) or (has_video and has_pano)) else ''}

                    {('<!-- Navigation Controls -->' +
                    '<!-- Dot Navigation with Labels -->' +
                    '<div class="carousel-dots">' +
                    (('<span class="dot active" onclick="goToInteractiveSlide(\'' + str(bbl) + '\', 0)" title="3D Model"></span>') if has_3d else '') +
                    (('<span class="dot' + ('' if has_3d else ' active') + '" onclick="goToInteractiveSlide(\'' + str(bbl) + '\', ' + ('1' if has_3d else '0') + ')" title="Aerial Video"></span>') if has_video else '') +
                    (('<span class="dot' + ('' if (has_3d or has_video) else ' active') + '" onclick="goToInteractiveSlide(\'' + str(bbl) + '\', ' + (str(sum([has_3d, has_video]))) + ')" title="360° Virtual Tour"></span>') if has_pano else '') +
                    '</div>') if ((has_3d and (has_video or has_pano)) or (has_video and has_pano)) else ''}
                </div>
                </div>
                </div>''' if (has_3d or has_video or has_pano) else ''
            }
            </div>
        </div>

        <!-- Building Overview Section -->
        <div class="section">
                <h2 class="section-header">Building Overview</h2>
                
                <div class="page">
                <h3 class="page-title">Commercial
                    
                </h3>
                <div class="page-content">
                <div class="stat">
                    <span class="stat-label">Class <span class="info-tooltip" data-tooltip="Measure of office property quality. A= premium, B= good, C= basic. Source: CoStar" style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span>
                    <span class="stat-value"><span class="class-badge class-{building_class.replace(' ', '')}">{building_class}</span></span>
                </div>
                {"<div class='stat'><span class='stat-label'>Owner & Manager <span class='info-tooltip' data-tooltip='Data from CoStar' style='display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;'>i</span>: </span><span class='stat-value'>" + escape_html(owner) + owner_logo + "</span></div>" if owner == property_manager else "<div class='stat'><span class='stat-label'>Owner <span class='info-tooltip' data-tooltip='Data from CoStar' style='display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;'>i</span>: </span><span class='stat-value'>" + escape_html(owner) + owner_logo + "</span></div><div class='stat'><span class='stat-label'>Manager <span class='info-tooltip' data-tooltip='Data from CoStar' style='display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;'>i</span>: </span><span class='stat-value'>" + escape_html(property_manager) + manager_logo + "</span></div>"}
                {"<div class='stat'><span class='stat-label'>Owner Contact <span class='info-tooltip' data-tooltip='Email address found through websearhc, validated through email server check, and filtered for current owner/manager org employees (from LinkedIn and company websites)' style='display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;'>i</span>: </span><span class='stat-value'>" + escape_html(landlord_contact) + "</span></div>" if landlord_contact != 'Unavailable' else ""}
                {"<div class='stat'><span class='stat-label'>Manager Contact <span class='info-tooltip' data-tooltip='Email address found through websearhc, validated through email server check, and filtered for current owner/manager org employees (from LinkedIn and company websites)' style='display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;'>i</span>: </span><span class='stat-value'>" + escape_html(property_manager_contact) + "</span></div>" if property_manager_contact != 'Unavailable' else ""}
                <div class="stat">
                    <span class="stat-label">% Leased <span class="info-tooltip" data-tooltip="Data from CoStar" style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span>
                    <span class="stat-value">{pct_leased}%</span>
                </div>
                {"<div class='stat'><span class='stat-label'>OpEx per Sq Ft <span class='info-tooltip' data-tooltip='Fiscal year 2024. Data from CoStar' style='display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;'>i</span>: </span><span class='stat-value'>" + opex_per_sqft + "</span></div>" if opex_per_sqft != 'N/A' else ""}
                </div>
            </div>
            
            <div class="page">
                <h3 class="page-title">Property
                    
                </h3>
                <div class="page-content">
                {"<div class='stat'><span class='stat-label'>Units <span class='info-tooltip' data-tooltip='Data from NYC Department of City Planning. More units = more tenants = greater complexity' style='display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;'>i</span>: </span><span class='stat-value'>" + str(total_units) + "</span></div>" if total_units >= len(building_tenants) else ""}
                <div class="stat">
                    <span class="stat-label">Floors <span class="info-tooltip" data-tooltip="Data from NYC Department of Buildings." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span>
                    <span class="stat-value">{num_floors}</span>
                </div>
                {"<div class='stat'><span class='stat-label'>Avg Floor Sq Ft <span class='info-tooltip' data-tooltip='Data from CoStar' style='display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;'>i</span>: </span><span class='stat-value'>" + typical_floor_sqft + " sq ft</span></div>" if typical_floor_sqft != 'N/A' else ""}
                <div class="stat">
                    <span class="stat-label">Floor Area <span class="info-tooltip" data-tooltip="Square footage of occupiable space. Data from NYC Department of Buildings." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span>
                    <span class="stat-value">{int(total_area):,} sq ft ({office_pct}% office)</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Last Renovated <span class="info-tooltip" data-tooltip="Data from NYC Department of City Planning" style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span>
                    <span class="stat-value">{year_altered}</span>
                </div>
                </div>
            </div>
            
            <div class="page">
                <h3 class="page-title">Equipment
                    
                </h3>
                <div class="page-content">
                <div class="stat">
                    <span class="stat-label">BMS Controls <span class="info-tooltip" data-tooltip="Data from building's most recent LL87 Energy Audit submission (required by NYC law for buildings over 50k sq ft). ODCV relies on BMS to centrally control HVAC based on occupancy" style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span>
                    <span class="stat-value">{bas_text}</span>
                </div>
                {"<div class='stat'><span class='stat-label'>Heating System <span class='info-tooltip' data-tooltip='Primary heating type from LL87 energy audit reports.' style='display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;'>i</span>: </span><span class='stat-value'>" + str(heating_type) + "</span></div>" if heating_type != 'N/A' else ""}
                {"<div class='stat'><span class='stat-label'>Cooling System <span class='info-tooltip' data-tooltip='Primary cooling type from LL87 energy audit reports.' style='display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;'>i</span>: </span><span class='stat-value'>" + str(cooling_type) + "</span></div>" if cooling_type != 'N/A' else ""}
                {"<div class='stat'><span class='stat-label'>Rooftop System <span class='info-tooltip' data-tooltip='Equipment counted from aerial image analysis. More cooling towers indicate centralized HVAC systems ideal for ODCV implementation.' style='display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;'>i</span>: </span><span class='stat-value'>" + ((str(cooling_towers) + (" Cooling Tower" if cooling_towers == 1 else " Cooling Towers")) if cooling_towers > 0 else "") + ((" • " if cooling_towers > 0 and water_tanks > 0 else "") + (str(water_tanks) + (" Water Tank" if water_tanks == 1 else " Water Tanks")) if water_tanks > 0 else "") + "</span></div>" if (cooling_towers > 0 or water_tanks > 0) else ""}
                </div>
            </div>
            </div>
        </div>
        
        {f'''<!-- Major Tenants Section -->
        <div class="section">
                <h2 class="section-header">Major Tenants</h2>
                <div class="page">
                <div style="overflow-x: visible;">
                    <table id="tenantTable-{bbl}" style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                        <thead>
                            <tr style="background: #f8f9fa; border-bottom: 2px solid #e5e7eb;">
                                <th style="padding: 12px; text-align: left; font-weight: 600; color: #374151; cursor: pointer;" onclick="sortTenantTable(0)">Tenant* <span class="sort-indicator">↕</span></th>
                                <th style="padding: 12px; text-align: left; font-weight: 600; color: #374151; cursor: pointer;" onclick="sortTenantTable(1)">Floor <span class="sort-indicator">↕</span></th>
                                <th style="padding: 12px; text-align: left; font-weight: 600; color: #374151; cursor: pointer;" onclick="sortTenantTable(2)">Sq Ft Occupied <span class="sort-indicator">↕</span></th>
                                <th style="padding: 12px; text-align: left; font-weight: 600; color: #374151; cursor: pointer;" onclick="sortTenantTable(3)">Move Date <span class="sort-indicator">↕</span></th>
                            </tr>
                        </thead>
                        <tbody>
                            {"".join([f"""<tr style="border-bottom: 1px solid #e5e7eb;">
                                <td style="padding: 12px; color: #1f2937;">
                                    {escape_html(str(tenant['Tenant']) if pd.notna(tenant['Tenant']) else "Unknown")}
                                </td>
                                <td style="padding: 12px; color: #6b7280;">{escape_html(str(tenant['Floor']))}</td>
                                <td style="padding: 12px; text-align: left; color: #1f2937; font-weight: 500;">{f'{int(float(tenant["SF_Numeric"])):,}' if pd.notna(tenant['SF_Numeric']) and str(tenant['SF_Numeric']).lower() != 'nan' else 'N/A'}</td>
                                <td style="padding: 12px; color: #6b7280;">{escape_html(str(tenant['Move In Date']))}</td>
                            </tr>""" for _, tenant in building_tenants.iterrows()])}
                        </tbody>
                    </table>
                </div>
                <div style="margin-top: 16px; font-size: 0.85em; color: #6b7280;">
                    * Top {len(building_tenants)} tenants by sq ft (source: CoStar)
                </div>
            </div>
            </div>
            </div>
        </div>
        ''' if not building_tenants.empty else ""}
        
        <!-- Section 2: Building -->
        <div class="section">
                <h2 class="section-header">Energy Efficiency</h2>
                
                {'''<!-- Page 2 - Performance -->
                <div class="page">
                <h3 class="page-title">Performance

                </h3>
                <div class="page-content">
''' + (''.join([
    '<div class="stat"><span class="stat-label">ENERGY STAR Score <span class="info-tooltip" data-tooltip="Data from building\'s most recent LL84 report (NYC\'s energy data disclosure law). Score of 75 = better than 75% of similar buildings nationwide." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span><div style="display: flex; align-items: center; gap: 30px;"><svg viewBox="0 0 200 120" style="width: 200px; height: 120px;"><!-- Colored sections --><path d="M 20 100 A 80 80 0 0 1 73 30" fill="none" stroke="#c41e3a" stroke-width="20"/><path d="M 73 30 A 80 80 0 0 1 127 30" fill="none" stroke="#ffc107" stroke-width="20"/><path d="M 127 30 A 80 80 0 0 1 180 100" fill="none" stroke="#38a169" stroke-width="20"/><!-- Score number in center --><text x="100" y="85" text-anchor="middle" font-size="36" font-weight="bold" fill="' + energy_star_color + '">' + str(energy_star) + '</text><!-- Labels --><text x="20" y="115" text-anchor="middle" font-size="12" fill="#666">0</text><text x="180" y="115" text-anchor="middle" font-size="12" fill="#666">100</text></svg>' + (f'<div><div style="font-size: 1.2em; color: #666; font-weight: 500;">Target Score <span class="info-tooltip" data-tooltip="Building owner\'s self-reported target ENERGY STAR score from LL84 filing. Indicates planned efficiency improvements and management commitment." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: {target_score}</div><div style="font-size: 1.1em; margin-top: 5px;">{energy_star_delta}</div></div>' if target_score is not None else '') + '</div></div>' if energy_star != 'N/A' else '',
    f'<div class="stat"><span class="stat-label">LL33 Grade <span class="info-tooltip" data-tooltip="NYC gov\'s most recent energy efficiency letter grade for the building. Under LL33, NYC buildings must post these grades in public view (usually in the lobby). A low grade can jeopardize buildings\' class A status" style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span><span class="stat-value"><span class="energy-grade grade-{ll33_grade_raw}">{ll33_grade}</span></span></div>' if ll33_grade in ['A', 'B', 'C', 'D', 'F'] else '',
    (f'<div class="stat"><span class="stat-label">Building EUI <span class="info-tooltip" data-tooltip="Energy Use Intensity (EUI) measures total annual energy use per square foot. Formula: EUI = Annual Energy (kBtu) ÷ Building Area (sq ft). Lower values mean better efficiency. NYC office median: ~65 kBtu/sq ft/year." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span><span class="stat-value">{building_eui:.1f} kBtu/sf/year' + (f' (<span style="color: black;">{eui_benchmark.replace(" avg", "")} Prospector building median</span>)' if eui_benchmark else '') + '</span></div>') if building_eui > 0 else '',
    '<div class="stat"><span class="stat-label">Data Center <span class="info-tooltip" data-tooltip="Data center presence from LL84 filings. Energy use estimated for some buildings using regression model based on DC square footage and site electricity consumption." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>: </span><span class="stat-value" style="color: #f0ad4e;">' + datacenter_text + '</span></div>' if has_datacenter else ''
])) + '''
                </div>
            </div>''' if (energy_star != 'N/A' or ll33_grade in ['A', 'B', 'C', 'D', 'F'] or building_eui > 0 or has_datacenter) else ''}
            
            {penalty_section}
            </div>
        </div>
        
        <!-- Section 3: Energy Consumption -->
        <div class="section">
                <h2 class="section-header">Energy Consumption</h2>
                
                <div class="page">
                <h3 class="page-title">Usage <span class="info-tooltip" data-tooltip="Building's actual energy usage. Self-reported under LL84 (NYC's energy consumption disclosure law). Publicly available on NYC gov website. Office space percentage of building square footage from NYC Department of Finance" style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>
                    
                </h3>
                <div class="page-content">
            <div class="chart-carousel">
                <div class="chart-toggle">
                    <button class="toggle-btn active" onclick="showChart('usage', 'building')">Building</button>
                    <button class="toggle-btn" onclick="showChart('usage', 'office')">Office</button>
                </div>
                <div id="building_usage_container" class="chart-container">
                    <div id="energy_chart" style="width: 100%; height: 400px;"></div>
                </div>
                <div id="office_usage_container" class="chart-container" style="display: none;">
                    <div id="office_energy_chart" style="width: 100%; height: 400px;"></div>
                </div>
            </div>
            </div>
        </div>
        
        <div class="page">
            <h3 class="page-title">Cost <span class="info-tooltip" data-tooltip="Electricity, steam, and gas usage from building's actual consumption as reported in latest LL84 filing. We calculate costs by running that usage through a model of the building's rate plan (as published by their utility), including demand charges, fees, and taxes." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>
                
            </h3>
            <div class="page-content">
            <div class="chart-carousel">
                <div class="chart-toggle">
                    <button class="toggle-btn active" onclick="showChart('cost', 'building')">Building</button>
                    <button class="toggle-btn" onclick="showChart('cost', 'office')">Office</button>
                </div>
                <div id="building_cost_container" class="chart-container">
                    <div id="energy_cost_chart" style="width: 100%; height: 400px;"></div>
                </div>
                <div id="office_cost_container" class="chart-container" style="display: none;">
                    <div id="office_cost_chart" style="width: 100%; height: 400px;"></div>
                </div>
            </div>
            </div>
            </div>
        </div>
        
        <!-- Section 4: ODCV -->
        <div class="section">
                <h2 class="section-header">HVAC Analysis</h2>
                
                <div class="page">
                </div>
                
                <div class="page">
                <h3 class="page-title">Office Electricity Usage Going to HVAC <span class="info-tooltip" data-tooltip="The HVAC component of office electricity usage is calculated using a baseline method: the lowest-usage shoulder month (when heating and cooling consumption is slim to none) is assumed to represent primarily non-HVAC load (lighting and plug loads), with 15% of that month's electricity allocated to HVAC to account for fan energy. All electricity usage above this baseline during heating and cooling months is attributed to HVAC (i.e., demand varying with weather).

We allocate 90% of gas and steam usage to HVAC, as office buildings have minimal hot-water demand (no showers, limited kitchen use)." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>
                    
                </h3>
                <div class="page-content">
                <div id="hvac_pct_chart" style="width: 100%; height: 400px;"></div>
                </div>
            </div>
            
            <div class="page">
                <h3 class="page-title">Office HVAC Energy Cost & ODCV Savings <span class="info-tooltip" data-tooltip="Savings calculated from two equally-weighted factors: building vacancy and automation capability. Higher vacancy (data from CoStar) means more low-occupancy space where ventilation can be reduced. More centralized controls (data from LL87 energy audit) enable the building to better match heating, cooling, and outdoor air volume to occupancy." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>
                    
                </h3>
                <div class="page-content">
                <div id="hvac_cost_breakdown_chart" style="width: 100%; height: 400px;"></div>
                <div style="text-align: center; margin-top: 15px;">
                    <b style="font-size: 16px; color: #666;">Average Savings: {odcv_percentage_of_hvac:.0f}% of HVAC Cost</b>
                </div>
                </div>
            </div>
            
            <div class="page">
                <h3 class="page-title">Office HVAC ODCV Savings (Cumulative) <span class="info-tooltip" data-tooltip="Cumulative energy savings from the office portion of the building. Hover over a bar to see savings for that month alone" style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>
                    
                </h3>
                <div class="page-content">
                <div id="odcv_savings_chart" style="width: 100%; height: 400px;"></div>
                </div>
            </div>
            
            </div>
        </div>
        
{f'''        <!-- Air Quality Section -->
        <div class="section">
                <h2 class="section-header">Air Quality</h2>
                
                <div class="page">
                <h3 class="page-title">Outdoor PM2.5 Level ({neighborhood}) <span class="info-tooltip" data-tooltip="Outdoor concentration of particles that exacerbate respiratory illness. ODCV cuts particle exposure by reducing outdoor air intake. Data for this building's coordinates and filtered to M-F 8am-6pm (source: OpenWeatherMap)." style="display: inline-block; margin-left: 5px; width: 16px; height: 16px; background-color: #00769d; color: white; border-radius: 50%; text-align: center; line-height: 16px; font-size: 12px; cursor: help; position: relative;">i</span>
                    
                </h3>
                <div class="page-content">
            
            <div class="iaq-summary" style="margin-bottom: 30px;">
                <div class="iaq-stat-grid" style="display: grid; grid-template-columns: repeat({3 if avg_pm25 > 12 else 2}, 1fr); gap: {40 if avg_pm25 > 12 else 80}px; text-align: center; max-width: {600 if avg_pm25 > 12 else 500}px; margin: 0 auto;">
                    <div class="iaq-stat">
                        <div class="iaq-label" style="font-size: 12px; color: #6c757d; margin-bottom: 4px;">Max</div>
                        <div class="iaq-value" style="font-size: 24px; font-weight: bold; color: #c41e3a;">{max_pm25:.1f} μg/m³</div>
                    </div>
                    <div class="iaq-stat">
                        <div class="iaq-label" style="font-size: 12px; color: #6c757d; margin-bottom: 4px;">Average</div>
                        <div class="iaq-value" style="font-size: 24px; font-weight: bold; color: {aqi_color};">{avg_pm25:.1f} μg/m³</div>
                    </div>
                    {"<div class='iaq-stat'><div class='iaq-label' style='font-size: 12px; color: #6c757d; margin-bottom: 4px;'>Good</div><div class='iaq-value' style='font-size: 24px; font-weight: bold; color: #00e400;'>12 μg/m³</div></div>" if avg_pm25 > 12 else ""}
                </div>
            </div>
            
            <div id="pm25_chart" style="width: 100%; height: 400px;"></div>
            </div>
            </div>
        </div>''' if chart_dates else ""}
        
    <script>
    function handleCredentialResponse(response) {{
        // Decode JWT to get user email
        const base64Url = response.credential.split(".")[1];
        const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
        const jsonPayload = decodeURIComponent(atob(base64).split("").map(function(c) {{
            return "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2);
        }}).join(""));
        const userData = JSON.parse(jsonPayload);
        
        // Check if email ends with @rzero.com
        if (userData.email && userData.email.endsWith("@rzero.com")) {{
            // Store auth and show content
            localStorage.setItem("rzeroAuth", JSON.stringify({{
                email: userData.email,
                name: userData.name,
                expires: Date.now() + 86400000 // 24 hours
            }}));
            const loginOverlay = document.getElementById("loginOverlay");
            const mainContent = document.getElementById("mainContent");
            if (loginOverlay) loginOverlay.style.display = "none";
            if (mainContent) mainContent.style.display = "block";
            displayUserInfo();
        }} else {{
            alert("Access restricted to R-Zero employees only (@rzero.com emails)");
            google.accounts.id.disableAutoSelect();
        }}
    }}
    
    // Check existing auth on load
    function checkAuth() {{
        // CONDITIONAL AUTH: Bypass authentication if accessed via file:// protocol
        if (window.location.protocol === 'file:') {{
            console.log("File protocol detected - bypassing authentication");
            const loginOverlay = document.getElementById("loginOverlay");
            const mainContent = document.getElementById("mainContent");
            if (loginOverlay) loginOverlay.style.display = "none";
            if (mainContent) mainContent.style.display = "block";
            // Don't record visits for file:// protocol (local testing)
            return;
        }}
        
        const auth = localStorage.getItem("rzeroAuth");
        if (auth) {{
            const authData = JSON.parse(auth);
            if (Date.now() < authData.expires) {{
                const loginOverlay = document.getElementById("loginOverlay");
                const mainContent = document.getElementById("mainContent");
                if (loginOverlay) loginOverlay.style.display = "none";
                if (mainContent) mainContent.style.display = "block";
                displayUserInfo();
                return;
            }} else {{
                localStorage.removeItem("rzeroAuth");
            }}
        }}
        // Initialize Google Sign-In
        google.accounts.id.initialize({{
            client_id: "70489892630-1j0t3rni5a7f07ng3v3k916lunm9n76d.apps.googleusercontent.com",
            callback: handleCredentialResponse
        }});
        google.accounts.id.renderButton(
            document.querySelector(".g_id_signin"),
            {{ theme: "outline", size: "large" }}
        );
    }}
    
    // Initialize on page load
    window.addEventListener("load", checkAuth);
    
    // Unit conversion functions
    function kBtuToKwh(kbtu) {{ return kbtu / 3.412; }}
    function kBtuToTherms(kbtu) {{ return kbtu / 100; }}
    function kBtuToLbs(kbtu) {{ return kbtu / 1.194; }}
    
    // Toggle chart function
    
    // Display user info
    // Get profile picture URL based on email
    function getProfilePicture(email) {{
        // Mapping of emails to profile picture filenames
        const profileMap = {{
            'apires@rzero.com': 'Andy_Pires.jpg',
            'asalvatore@rzero.com': 'Anthony_Salvatore.jpg',
            'bsiegfried@rzero.com': 'Ben_Siegfried.jpg',
            'ben@rzerosystems.com': 'Benjamin_Boyer.jpg',
            'bgreen@rzero.com': 'Benjamin_Green.jpg',
            'bquan@rzero.com': 'Brenda_Quan.jpg',
            'csutherland@rzero.com': 'Chelsea_Sutherland.jpg',
            'ddufrane@rzero.com': 'Dana_DuFrane.jpg',
            'dmorkarnon@rzero.com': 'Dana_Mor_Karnon.jpg',
            'dcox@rzero.com': 'Dave_Cox.jpg',
            'dnuno@rzero.com': 'David_Nuno.jpg',
            'dseniawski@rzero.com': 'David_Seniawski.jpg',
            'dhess@rzero.com': 'Don_Hess.jpg',
            'doliner@rzero.com': 'Drew_Oliner.jpg',
            'eredmond@rzero.com': 'Elizabeth_Redmond.jpg',
            'efoster@rzero.com': 'Eric_Foster.jpg',
            'fmiller@rzero.com': 'Forrest_Miller.jpg',
            'fstamatatos@rzero.com': 'Francis_Stamatatos.jpg',
            'hsverdlik@rzero.com': 'Hannah_Sverdlik.jpg',
            'igendelman@rzero.com': 'Ilya_Gendelman.jpg',
            'jnuckles@rzero.com': 'Jennifer_Nuckles.jpg',
            'jquiros@rzero.com': 'Jorge_Quiros.jpg',
            'jmunoz@rzero.com': 'Julio_Munoz.jpg',
            'kneff@rzero.com': 'Kim_Neff.jpg',
            'laguilar@rzero.com': 'Luis_Aguilar.jpg',
            'mkulkarni@rzero.com': 'Manali_Kulkarni.jpg',
            'mbuffler@rzero.com': 'Martyn_R._Buffler.jpg',
            'mdharmani@rzero.com': 'Mehak_Dharmani.jpg',
            'mchu@rzero.com': 'Michael_Chu.jpg',
            'mdever@rzero.com': 'Michael_Dever.jpg',
            'mhopps@rzero.com': 'Michael_Hopps.jpg',
            'melafifi@rzero.com': 'Mohamed_El-afifi.jpg',
            'mbarash@rzero.com': 'Monique_Barash.jpg',
            'nalvarado@rzero.com': 'Nelson_Alvarado.jpg',
            'nturizo@rzero.com': 'Nestor_Turizo.jpg',
            'nviscuso@rzero.com': 'Nick_Viscuso.jpg',
            'nvannuil@rzero.com': 'Nicolaas_Van_Nuil.jpg',
            'nbanta@rzero.com': 'Nicole_Dianne_Banta.jpg',
            'ppan@rzero.com': 'Priscilla_Pan.jpg',
            'rmartin@rzero.com': 'Rick_Martin.jpg',
            'skarki@rzero.com': 'Sanjil_Karki.jpg',
            'skurgansky@rzero.com': 'Stas_Kurgansky.jpg',
            'ssnow@rzero.com': 'Stephanie_Snow.jpg',
            'treznik@rzero.com': 'Thomas_Reznik.jpg',
            'tpearce@rzero.com': 'Trish_Pearce.jpg',
            'ukogan@rzero.com': 'Uri_Kogan.jpg',
            'vherico@rzero.com': 'Veronica_Herico.jpg',
            'wiley.wang@rzero.com': 'Wiley_Wang.jpg',
            'wmusat@rzero.com': 'will_musat.jpg'
        }};
        
        const filename = profileMap[email.toLowerCase()];
        return filename ? `./profile-pics/${{filename}}` : null;
    }}
    
    function displayUserInfo() {{
        const auth = localStorage.getItem("rzeroAuth");
        if (auth) {{
            const authData = JSON.parse(auth);
            const userEmail = authData.email;
            const userName = authData.name || userEmail.split("@")[0];
            
            // Update the header banner user info
            const userInfoElement = document.getElementById("userInfo");
            const userNameElement = document.getElementById("userName");
            const userProfilePic = document.getElementById("userProfilePic");
            
            if (userInfoElement && userNameElement && userProfilePic) {{
                userNameElement.textContent = userName;
                const localPic = getProfilePicture(userEmail);
                userProfilePic.src = localPic || authData.picture || './profile-pics/default.jpg';
                userProfilePic.onerror = function() {{ this.src = './profile-pics/default.jpg'; }};
                userInfoElement.style.display = "block";
            }}
        }}
    }}

    // Toggle chart function
    function showChart(type, view) {{
        let buildingContainer, officeContainer;
        
        if (type === 'usage') {{
            buildingContainer = document.getElementById('building_usage_container');
            officeContainer = document.getElementById('office_usage_container');
        }} else if (type === 'cost') {{
            buildingContainer = document.getElementById('building_cost_container');
            officeContainer = document.getElementById('office_cost_container');
        }}
        
        const buttons = event.target.parentElement.querySelectorAll('.toggle-btn');
        
        buttons.forEach(btn => {{
            btn.style.background = '#f0f0f0';
            btn.style.color = '#333';
            btn.style.border = '1px solid #ddd';
            btn.classList.remove('active');
        }});
        
        event.target.classList.add('active');
        event.target.style.background = '#0066cc';
        event.target.style.color = 'white';
        event.target.style.border = 'none';
        
        if (view === 'building') {{
            buildingContainer.style.display = 'block';
            officeContainer.style.display = 'none';
        }} else {{
            buildingContainer.style.display = 'none';
            officeContainer.style.display = 'block';
            
            // Resize the office chart after making it visible
            // This fixes the "squished" chart issue
            setTimeout(() => {{
                try {{
                    if (type === 'usage' && window.Plotly) {{
                        const chartEl = document.getElementById('office_energy_chart');
                        if (chartEl && chartEl.data && chartEl.layout) {{
                            Plotly.Plots.resize(chartEl);
                        }}
                    }} else if (type === 'cost' && window.Plotly) {{
                        const chartEl = document.getElementById('office_cost_chart');
                        if (chartEl && chartEl.data && chartEl.layout) {{
                            Plotly.Plots.resize(chartEl);
                        }}
                    }}
                }} catch (e) {{
                    // Ignore resize errors for hidden/uninitialized charts
                    console.log('Chart resize skipped:', e.message);
                }}
            }}, 10);  // Small delay to ensure DOM update
        }}
    }}
    
    // Additional global variables
    let tenantSortDir = {{}};

    // Salesify Configuration
    const GAS_WEBAPP_URL = 'https://script.google.com/macros/s/AKfycbwEKnYMVnYOYYY0dUnC0WqVJyYxHO-VaS7u4SyoTJ0M3MsZ_5x9e0dJQKPt8l-Xtdo/exec'; // Production Apps Script URL
    const PEER_CSV_URL = 'https://raw.githubusercontent.com/fmillerrzero/nyc-test-site/main/data/building_office_eui.csv';
    const CONTACTS_JSON_URL = 'https://raw.githubusercontent.com/fmillerrzero/nyc-odcv-site/main/data/salesify_recipients.json';
    const BUILDINGS_EMAILS_JSON_URL = 'https://raw.githubusercontent.com/fmillerrzero/nyc-test-site/main/data/building_emails.json';
    const totalODCVSavings = {total_odcv_savings}; // From Python variable

    // Redefine with full implementation now that DOM is ready
    window.handleImageError = function(img, bbl, imageType) {{
        const slide = img.closest('.carousel-slide');
        const track = slide.parentElement;

        // Remove the broken slide
        slide.remove();

        // Update dots
        updateCarouselDots(bbl);

        // Check remaining slides and reset index if needed
        const remainingSlides = track.querySelectorAll('.carousel-slide');
        if (remainingSlides.length > 0) {{
            if (!carouselIndex[bbl] || carouselIndex[bbl] >= remainingSlides.length) {{
                carouselIndex[bbl] = 0;
                track.style.transform = 'translateX(0)';
            }}
        }} else {{
            // No slides left, hide carousel
            track.closest('.carousel-container').style.display = 'none';
        }}

        console.log(`Image not found: ${{bbl}}_${{imageType}}.jpg`);
    }}
    
    // Update dots to only show for visible slides
    function updateCarouselDots(bbl) {{
        const track = document.getElementById(`carousel-${{bbl}}`);
        if (!track) return;
        const slides = Array.from(track.querySelectorAll('.carousel-slide'));
        const dotsContainer = document.getElementById(`carousel-dots-${{bbl}}`);

        if (!dotsContainer) return;

        // Clear existing dots
        dotsContainer.innerHTML = '';

        // Add dots for all remaining slides
        slides.forEach((slide, index) => {{
            const dot = document.createElement('span');
            dot.className = 'dot';
            if (index === carouselIndex[bbl]) dot.classList.add('active');
            dot.onclick = () => goToSlide(bbl, index);
            dotsContainer.appendChild(dot);
        }});
    }}

    window.moveCarousel = function(bbl, direction) {{
        const track = document.getElementById(bbl.includes('carousel') ? bbl : `carousel-${{bbl}}`);
        const slides = Array.from(track.querySelectorAll('.carousel-slide'));

        if (slides.length === 0) return;

        if (!carouselIndex[bbl]) carouselIndex[bbl] = 0;

        // Calculate next index
        let currentIndex = carouselIndex[bbl];
        currentIndex += direction;
        if (currentIndex < 0) currentIndex = slides.length - 1;
        if (currentIndex >= slides.length) currentIndex = 0;

        carouselIndex[bbl] = currentIndex;
        track.style.transform = `translateX(-${{currentIndex * 100}}%)`;

        // Update title based on current slide
        const currentSlide = slides[currentIndex];
        const imageType = currentSlide.getAttribute('data-image-type');
        const actualBbl = bbl.includes('carousel') ? bbl.replace('carousel-', '') : bbl;
        const titleElement = document.getElementById(`image-gallery-title-${{actualBbl}}`);
        if (titleElement) {{
            const imageTypeMap = {{
                'hero': 'Marketing',
                'floorplan': 'Floor Plan',
                'roadview': 'Streetview (Cyclomedia)',
                'street': 'Streetview (Google)',
                'satellite': 'Satellite (Unannotated)',
                'equipment': 'Satellite (Annotated)',
                'double': 'Side-by-Side',
                'stack': 'Stacking Diagram'
            }};
            titleElement.innerHTML = `Static: <span style="color: #555;">${{imageTypeMap[imageType] || 'Unknown'}}</span>`;
        }}
        
        // Update dots for visible slides only
        updateCarouselDots(bbl.includes('carousel') ? bbl.replace('carousel-', '') : bbl);
    }}
    
    window.goToSlide = function(bbl, index) {{
        const track = document.getElementById(`carousel-${{bbl}}`);
        const slides = Array.from(track.querySelectorAll('.carousel-slide'));

        // Make sure target slide exists
        if (slides[index]) {{
            carouselIndex[bbl] = index;
            track.style.transform = `translateX(-${{index * 100}}%)`;

            // Update title based on current slide
            const currentSlide = slides[index];
            const imageType = currentSlide.getAttribute('data-image-type');
            const titleElement = document.getElementById(`image-gallery-title-${{bbl}}`);
            if (titleElement) {{
                const imageTypeMap = {{
                    'hero': 'Marketing',
                    'floorplan': 'Floor Plan',
                    'roadview': 'Streetview (Cyclomedia)',
                    'street': 'Streetview (Google)',
                    'satellite': 'Satellite (Unannotated)',
                    'equipment': 'Satellite (Annotated)',
                    'double': 'Side-by-Side',
                    'stack': 'Stacking Diagram'
                }};
                titleElement.innerHTML = `Static: <span style="color: #555;">${{imageTypeMap[imageType] || 'Unknown'}}</span>`;
            }}
            
            updateCarouselDots(bbl);
        }}
    }}
    
    window.toggleFullscreen = function(button) {{
        const container = button.parentElement;
        const img = container.querySelector('img');
        
        if (!document.fullscreenElement) {{
            if (container.requestFullscreen) {{
                container.requestFullscreen();
            }} else if (container.webkitRequestFullscreen) {{
                container.webkitRequestFullscreen();
            }}
            button.innerHTML = '\u2715';
        }} else {{
            if (document.exitFullscreen) {{
                document.exitFullscreen();
            }}
            button.innerHTML = '\u26f6';
        }}
    }}
    
    window.downloadImage = async function(button) {{
        const img = button.parentElement.querySelector('img');
        const imageUrl = img.src;
        const fileName = imageUrl.split('/').pop();
        
        try {{
            // Fetch the image as a blob
            const response = await fetch(imageUrl);
            const blob = await response.blob();
            
            // Create a blob URL
            const blobUrl = URL.createObjectURL(blob);
            
            // Create and click the download link
            const link = document.createElement('a');
            link.href = blobUrl;
            link.download = fileName;
            link.style.display = 'none';
            document.body.appendChild(link);
            link.click();
            
            // Clean up
            document.body.removeChild(link);
            URL.revokeObjectURL(blobUrl);
        }} catch (error) {{
            console.error('Download failed:', error);
            // Fallback to simple download if fetch fails
            const link = document.createElement('a');
            link.href = imageUrl;
            link.download = fileName;
            link.target = '_self';  // Ensure it doesn't open in new tab
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }}
    }}
    
    // Enhanced Interactive carousel with smooth transitions
    
    window.moveInteractiveCarousel = function(bbl, direction) {{
        const carousel = document.getElementById('interactive-carousel-' + bbl);
        const dots = carousel.parentElement.querySelectorAll('.dot');
        const totalViews = carousel.children.length;
        
        interactiveIndex += direction;
        
        // Handle wrap-around
        if (interactiveIndex < 0) interactiveIndex = totalViews - 1;
        if (interactiveIndex >= totalViews) interactiveIndex = 0;
        
        // Smooth transition with enhanced transform
        carousel.style.transform = `translateX(-${{interactiveIndex * 100}}%)`;
        
        // Update dot indicators with smooth animation
        dots.forEach((dot, i) => {{
            dot.classList.toggle('active', i === interactiveIndex);
        }});
        
        // Add subtle button feedback animation
        const buttons = carousel.parentElement.querySelectorAll('.carousel-btn');
        buttons.forEach(btn => {{
            btn.style.transform = 'scale(0.95)';
            setTimeout(() => btn.style.transform = 'scale(1)', 100);
        }});
        
        // Update title based on current slide
        const currentSlide = carousel.children[interactiveIndex];
        const slideType = currentSlide.getAttribute('data-type');
        const titleElement = document.getElementById(`interactive-views-title-${{bbl}}`);
        if (titleElement) {{
            const typeMap = {{
                '3d': '3D Model',
                'video': 'Drone Footage',
                'pano': '360 Panorama'
            }};
            titleElement.innerHTML = `Dynamic: <span style="color: #555;">${{typeMap[slideType] || 'Unknown'}}</span>`;
        }}

        // Handle 3D model initialization
        if (slideType === '3d') {{
            const containerEl = document.getElementById(`model-container-${{bbl}}`);
            if (containerEl && !containerEl._threeInitialized && !containerEl._loadingInProgress) {{
                // Initialize 3D model when user navigates to it
                window.init3DModel{bbl}();
            }}
        }}

        // Auto-play video when navigating to aerial slide
        if (slideType === 'video') {{
            const video = document.querySelector(`#aerial-video-${{bbl}} video`);
            if (video) {{
                video.play().catch(e => console.log('Autoplay prevented on carousel navigation:', e));
            }}
        }}

        // Handle panorama initialization and rotation
        if (slideType === 'pano') {{
            const viewerEl = document.getElementById(`viewer-${{bbl}}`);
            if (viewerEl && viewerEl.pannellumViewer) {{
                // Start auto rotation when user navigates to panorama
                viewerEl.pannellumViewer.startAutoRotate(-2);
            }}
        }}
        
        // Trigger loading animation for iframes
        const iframe = currentSlide.querySelector('iframe');
        if (iframe && !iframe.classList.contains('loaded')) {{
            setTimeout(() => iframe.classList.add('loaded'), 500);
        }}
    }}
    
    window.goToInteractiveSlide = function(bbl, index) {{
        const direction = index - interactiveIndex;
        interactiveIndex = index;
        moveInteractiveCarousel(bbl, 0);
    }}
    
    
    
    // Tenant table sorting
    function sortTenantTable(col) {{
        // Find the tenant table (there should only be one per page)
        const table = document.querySelector('[id^="tenantTable-"]');
        if (!table) return;
        
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        
        // Toggle sort direction
        tenantSortDir[col] = !tenantSortDir[col];
        
        rows.sort((a, b) => {{
            let aVal, bVal;
            
            if (col === 2) {{
                // SF Occupied - parse number from formatted string
                aVal = parseInt(a.cells[col].textContent.replace(/,/g, '') || '0');
                bVal = parseInt(b.cells[col].textContent.replace(/,/g, '') || '0');
            }} else if (col === 3) {{
                // Move Date - convert to sortable format
                aVal = a.cells[col].textContent.trim();
                bVal = b.cells[col].textContent.trim();
                // Handle N/A values
                if (aVal === 'N/A') aVal = '';
                if (bVal === 'N/A') bVal = '';
                // Convert Mon-YY to YYYY-MM for sorting
                if (aVal && aVal !== 'N/A') {{
                    const [month, year] = aVal.split('-');
                    const monthNum = new Date(month + ' 1, 2000').getMonth() + 1;
                    aVal = `20${{year}}-${{monthNum.toString().padStart(2, '0')}}`;
                }}
                if (bVal && bVal !== 'N/A') {{
                    const [month, year] = bVal.split('-');
                    const monthNum = new Date(month + ' 1, 2000').getMonth() + 1;
                    bVal = `20${{year}}-${{monthNum.toString().padStart(2, '0')}}`;
                }}
            }} else {{
                // Text columns (Tenant, Floor)
                aVal = a.cells[col].textContent.toLowerCase().trim();
                bVal = b.cells[col].textContent.toLowerCase().trim();
            }}
            
            if (tenantSortDir[col]) {{
                return aVal > bVal ? 1 : -1;
            }} else {{
                return aVal < bVal ? 1 : -1;
            }}
        }});
        
        // Clear and rebuild tbody
        tbody.innerHTML = '';
        rows.forEach(row => tbody.appendChild(row));
        
        // Update sort indicators
        const headers = table.querySelectorAll('th');
        headers.forEach((th, idx) => {{
            const indicator = th.querySelector('.sort-indicator');
            if (indicator) {{
                indicator.textContent = idx === col ? (tenantSortDir[col] ? '↑' : '↓') : '↕';
            }}
        }});
    }}
    
    // Salesify Email Draft Handler with AUTO-POPULATED CONTACTS
    async function handleSalesify() {{
        try {{
            // GET BUILDING CONTACTS FOR MATCHING
            const buildingOwner = '{escape_js_string(owner)}'.toLowerCase().trim();
            const propertyManager = '{escape_js_string(property_manager)}'.toLowerCase().trim();
            const ownerEmail = '{escape_js_string(high_confidence_owner_email)}';
            const managerEmail = '{escape_js_string(high_confidence_pm_email)}';
            // ALL visible contact info on the building report (includes emails, phones, etc.)
            const ownerContactInfo = '{escape_js_string(landlord_contact)}';
            const managerContactInfo = '{escape_js_string(property_manager_contact)}';
            const topTenants = {json.dumps([str(tenant['Tenant']).lower().strip() for _, tenant in building_tenants.head(3).iterrows() if pd.notna(tenant['Tenant'])] if not building_tenants.empty else [])};
            
            // FETCH YOUR CONTACTS LIST
            let suggestedEmails = [];
            try {{
                const contactsResponse = await fetch(CONTACTS_JSON_URL);
                const contactsData = await contactsResponse.json();
                
                // Filter contacts for this building's owner, manager, or top tenants
                if (contactsData.contacts) {{
                    console.log('Building contacts to match:');
                    console.log('- Owner:', buildingOwner);
                    console.log('- Manager:', propertyManager);
                    console.log('- Top 3 Tenants:', topTenants);
                    
                    const relevantContacts = contactsData.contacts.filter(c => {{
                        if (!c.email) return false;
                        
                        const emailDomain = c.email.split('@')[1]?.toLowerCase();
                        
                        // Check Owner match
                        if (c.owner) {{
                            const contactOwner = c.owner.toLowerCase().trim();
                            const ownerMatch = contactOwner === buildingOwner;
                            if (ownerMatch) {{
                                console.log('✓ OWNER MATCH:', contactOwner, '→', c.email);
                                return true;
                            }}
                        }}
                        
                        // Check Property Manager match
                        if (c.property_manager) {{
                            const contactManager = c.property_manager.toLowerCase().trim();
                            const managerMatch = contactManager === propertyManager;
                            if (managerMatch) {{
                                console.log('✓ MANAGER MATCH:', contactManager, '→', c.email);
                                return true;
                            }}
                        }}
                        
                        // Check Tenant matches (top 3 tenants only)
                        if (c.tenant) {{
                            const contactTenant = c.tenant.toLowerCase().trim();
                            const tenantMatch = topTenants.includes(contactTenant);
                            if (tenantMatch) {{
                                console.log('✓ TENANT MATCH:', contactTenant, '→', c.email);
                                return true;
                            }}
                        }}
                        
                        return false;
                    }});
                    
                    console.log(`Found ${{relevantContacts.length}} matching contacts for "${{buildingOwner}}"`);
                    if (relevantContacts.length > 0) {{
                        console.log('Matching emails:', relevantContacts.map(c => c.email));
                    }}
                    
                    if (relevantContacts.length > 0) {{
                        // Found matching contacts!
                        suggestedEmails = relevantContacts.map(c => c.email);
                        
                        // Silently populate - no alert needed
                    }}
                    
                    // Fetch building emails JSON to find all HIGH confidence emails for owner and manager orgs
                    try {{
                        const emailsResponse = await fetch(BUILDINGS_EMAILS_JSON_URL);
                        const emailsData = await emailsResponse.json();
                        
                        // Add all HIGH confidence owner emails for this organization
                        if (emailsData.owner_emails && emailsData.owner_emails[buildingOwner]) {{
                            suggestedEmails.push(...emailsData.owner_emails[buildingOwner]);
                        }}
                        
                        // Add all HIGH confidence manager emails for this organization  
                        if (emailsData.manager_emails && emailsData.manager_emails[propertyManager]) {{
                            suggestedEmails.push(...emailsData.manager_emails[propertyManager]);
                        }}
                        
                        console.log(`Found ${{suggestedEmails.length}} HIGH confidence emails for owner "${{buildingOwner}}" and manager "${{propertyManager}}"`);
                        
                    }} catch (err) {{
                        console.log('Could not fetch building emails JSON:', err);
                        // Fallback to single emails if JSON fails
                        if (ownerEmail && ownerEmail.trim()) {{
                            suggestedEmails.push(ownerEmail.trim());
                        }}
                        if (managerEmail && managerEmail.trim()) {{
                            suggestedEmails.push(managerEmail.trim());
                        }}
                    }}
                    
                    // Remove duplicates
                    suggestedEmails = [...new Set(suggestedEmails)];
                }}
            }} catch (err) {{
                console.log('Could not fetch contacts:', err);
                // Continue without auto-population
            }}
            
            // EXTRACT ALL EMAILS FROM VISIBLE CONTACT INFO + SUGGESTED EMAILS
            const buildingEmails = [];
            
            // Function to extract emails from contact strings
            function extractEmails(contactString) {{
                if (!contactString || contactString === 'Unavailable') return [];
                const emailRegex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{{2,}}/g;
                return contactString.match(emailRegex) || [];
            }}
            
            // Extract emails from owner contact info
            const ownerEmails = extractEmails(ownerContactInfo);
            buildingEmails.push(...ownerEmails);
            if (ownerEmails.length > 0) {{
                console.log('Added owner emails:', ownerEmails);
            }}
            
            // Extract emails from manager contact info  
            const managerEmails = extractEmails(managerContactInfo);
            buildingEmails.push(...managerEmails);
            if (managerEmails.length > 0) {{
                console.log('Added manager emails:', managerEmails);
            }}
            
            console.log('All visible building emails:', buildingEmails);
            
            // Combine building emails with suggested emails and remove duplicates
            const allEmails = [...buildingEmails, ...suggestedEmails];
            const uniqueEmails = [...new Set(allEmails.filter(email => email && email.trim()))];
            const to = uniqueEmails.join(', ');
            
            // Collect building data
            const addrFull = '{escape_js_string(main_address)}, {escape_js_string(neighborhood)}';
            const addrShort = '{escape_js_string(main_address)}'.split(',')[0];
            const eui = {building_eui};
            const area = {int(total_area)};
            const annualCost = {annual_building_cost:.0f};
            const annualElecCost = {sum(elec_cost):.0f};
            const annualGasCost = {sum(gas_cost):.0f};
            const annualSteamCost = {sum(steam_cost):.0f};
            const costPerSf = annualCost / area;
            const odcvAnnual = {total_odcv_savings:.0f};
            const hvacPct = {odcv_percentage_of_hvac:.1f};

            // Capture charts as PNG (INCLUDING ODCV!)
            const usagePng = await Plotly.toImage(document.getElementById('energy_chart'), {{
                format: 'png', width: 1100, height: 620, scale: 1.5
            }});
            const costPng = await Plotly.toImage(document.getElementById('energy_cost_chart'), {{
                format: 'png', width: 1100, height: 620, scale: 1.5
            }});
            const odcvPng = await Plotly.toImage(document.getElementById('odcv_savings_chart'), {{
                format: 'png', width: 1100, height: 620, scale: 1.5
            }});
            
            // Fetch peer comparison
            const peers = await fetchPeerComparison(eui, costPerSf);
            
            // Build email
            const subject = buildSubject(addrShort, annualCost, odcvAnnual);
            const htmlBody = buildEmailHTML({{
                addrFull, addrShort, eui, area, annualCost, costPerSf,
                hvacPct, odcvAnnual, peers,
                annualElecCost, annualGasCost, annualSteamCost,
                usageCid: 'usage', costCid: 'cost', odcvCid: 'odcv'
            }});
            
            // Convert charts to embedded images
            const usageImg = await Plotly.toImage(document.getElementById('energy_chart'), {{format: 'png', width: 800, height: 400}});
            const costImg = await Plotly.toImage(document.getElementById('energy_cost_chart'), {{format: 'png', width: 800, height: 400}});
            const odcvImg = await Plotly.toImage(document.getElementById('odcv_savings_chart'), {{format: 'png', width: 800, height: 400}});
            
            // Create clean HTML email with embedded images
            const cleanEmailHtml = `<!DOCTYPE html>
<html>
<head>
    <title>${{subject}}</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; }}
        .email-info {{ background: #f0f0f0; padding: 15px; margin-bottom: 20px; border-radius: 5px; }}
        img {{ max-width: 100%; height: auto; margin: 10px 0; }}
    </style>
</head>
<body>
    <div class="email-info">
        <strong>TO:</strong> ${{to || '[Add recipients]'}}<br>
        <strong>SUBJECT:</strong> ${{subject}}
    </div>
    
    ${{htmlBody.replace('cid:usage', usageImg)
                .replace('cid:cost', costImg)
                .replace('cid:odcv', odcvImg)}}
</body>
</html>`;

            // Download clean HTML file
            const blob = new Blob([cleanEmailHtml], {{ type: 'text/html' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `ODCV_Email_${{'{escape_js_string(main_address)}'.replace(/[^a-zA-Z0-9]/g, '_')}}.html`;
            a.click();
            URL.revokeObjectURL(url);
            
            // Simple instructions
            const recipientCount = to.split(',').filter(e => e.trim()).length;
            alert(`✅ Clean email HTML downloaded!\\\\n\\\\n📧 TO SEND:\\\\n1. Open the HTML file in browser\\\\n2. Select All (Ctrl+A / Cmd+A)\\\\n3. Copy (Ctrl+C / Cmd+C)\\\\n4. Paste into Gmail compose\\\\n\\\\nRecipients: ${{recipientCount || 'Add manually'}}`);
            
        }} catch (err) {{
            console.error(err);
            alert('Salesify error: ' + String(err));
        }}
    }}
    
    // Email builder functions
    function buildSubject(addrShort, annualCost, odcvAnnual) {{
        const totalSavings = Math.round(odcvAnnual);
        const wholeCost = Math.round(annualCost);

        // Format numbers as K or M
        function formatShort(num) {{
            if (num >= 1000000) {{
                return (num / 1000000).toFixed(1).replace(/\\.0$/, '') + 'M';
            }} else if (num >= 1000) {{
                return Math.round(num / 1000) + 'K';
            }}
            return num.toString();
        }}

        return `Spending $${{formatShort(wholeCost)}}/yr on ${{addrShort}} utilities? We can cut that by $${{formatShort(totalSavings)}}`;
    }}
    
    function buildEmailHTML(o) {{
        const usd = (n) => '$' + Math.round(n).toLocaleString();
        const num = (n, d=1) => Number(n).toFixed(d);
        
        // CALCULATIONS THAT MATTER (utility savings only)
        const totalSavings = o.odcvAnnual;
        const dailyWaste = totalSavings ? Math.round(totalSavings/365) : 0;
        const monthlyWaste = totalSavings ? Math.round(totalSavings/12) : 0;
        const co2Saved = totalSavings * 0.0004; // Tons CO2 per dollar saved
        const treesEquivalent = Math.round(co2Saved * 16.5); // Trees needed to absorb same CO2
        const carsOffRoad = Math.round(co2Saved / 4.6); // Cars worth of emissions
        const homesYearEnergy = Math.round(totalSavings / 11000); // Homes powered for a year
        const percentSavings = totalSavings && o.annualCost ? Math.round((totalSavings/o.annualCost)*100) : 0;
        
        return `
        <div style="font-family: Arial, sans-serif; color: #333; max-width: 700px; margin: 0 auto; line-height: 1.6;">
            
            <h2 style="color: #2c5aa0; margin-bottom: 20px; font-size: 24px;">
                Energy Analysis for ${{o.addrShort}}
            </h2>
            
            <p>We've completed an analysis of your building's energy performance and identified significant optimization opportunity using ODCV. ODCV is controlling a building's ventilation, heating, and cooling in real time using actual occupancy counts instead of fixed schedules. That saves energy by reducing airflow and conditioning in low-utilization spaces.</p>
            
            <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #2c5aa0;">
                <h3 style="margin: 0 0 15px 0; color: #2c5aa0;">Current Energy Profile</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                    <div>
                        <div style="font-size: 14px; color: #666;">Annual Energy Cost:</div>
                        <div style="font-size: 28px; font-weight: bold; color: #333;">${{usd(o.annualCost)}}</div>
                    </div>
                    <div>
                        <div style="font-size: 14px; color: #666;">Potential Annual Savings:</div>
                        <div style="font-size: 28px; font-weight: bold; color: #0d7377;">${{usd(totalSavings)}}</div>
                    </div>
                </div>
            </div>
            
            <h3 style="color: #2c5aa0; margin: 30px 0 15px 0;">Energy Performance Data</h3>
            
            <div style="margin: 20px 0;">
                <img src="cid:${{o.costCid}}" alt="Energy Cost Chart" style="max-width: 100%; border: 1px solid #ddd; border-radius: 4px;">
                
                <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-top: 15px;">
                    <h5 style="margin: 0 0 10px 0; color: #2c5aa0;">Annual Energy Costs by Fuel Type</h5>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 5px 0; color: #666;">Electricity:</td>
                            <td style="text-align: right; font-weight: bold;">${{usd(o.annualElecCost)}}</td>
                        </tr>
                        <tr>
                            <td style="padding: 5px 0; color: #666;">Natural Gas:</td>
                            <td style="text-align: right; font-weight: bold;">${{usd(o.annualGasCost)}}</td>
                        </tr>
                        <tr>
                            <td style="padding: 5px 0; color: #666;">Steam:</td>
                            <td style="text-align: right; font-weight: bold;">${{usd(o.annualSteamCost)}}</td>
                        </tr>
                        <tr style="border-top: 2px solid #2c5aa0;">
                            <td style="padding: 8px 0 5px 0; font-weight: bold; color: #2c5aa0;">Total Annual Cost:</td>
                            <td style="text-align: right; font-weight: bold; color: #2c5aa0; font-size: 1.1em;">${{usd(o.annualCost)}}</td>
                        </tr>
                    </table>
                </div>
            </div>
            
            <div style="background: #f0f8f0; padding: 20px; border-radius: 8px; margin: 30px 0; border: 1px solid #d4edda;">
                <img src="cid:${{o.odcvCid}}" alt="ODCV Savings Chart" style="max-width: 100%; border-radius: 4px;">
            </div>
            
            
            <p style="margin: 30px 0 10px 0;">This analysis represents approximately $${{Math.round(totalSavings/365).toLocaleString()}} in daily savings opportunity.</p>
            
            <p style="margin: 10px 0;">Would you like to discuss these findings?</p>
            
        </div>`;
    }}
    
    // Real peer comparison from your 585 buildings
    async function fetchPeerComparison(eui, costPerSf) {{
        try {{
            const response = await fetch(PEER_CSV_URL);
            const text = await response.text();
            const lines = text.trim().split('\\\\n');
            const headers = lines[0].split(',');
            
            // Parse CSV to get EUI values
            const euiCol = headers.indexOf('building_eui_kBtu_sf_year');
            const peers = [];
            
            for (let i = 1; i < lines.length; i++) {{
                const cols = lines[i].split(',');
                const peerEui = parseFloat(cols[euiCol]);
                if (!isNaN(peerEui) && peerEui > 0) {{
                    peers.push(peerEui);
                }}
            }}
            
            // Sort for percentile calculation
            peers.sort((a, b) => a - b);
            const total = peers.length;
            
            // Calculate percentiles
            const median = peers[Math.floor(total * 0.5)];
            const p25 = peers[Math.floor(total * 0.25)];
            const p75 = peers[Math.floor(total * 0.75)];
            
            // Find this building's percentile
            let betterThan = 0;
            for (const peerEui of peers) {{
                if (eui < peerEui) betterThan++;
            }}
            const percentile = Math.round((betterThan / total) * 100);
            
            return {{
                total: total,
                median: median,
                p25: p25,
                p75: p75,
                percentile: percentile,
                costPerSf: costPerSf // Pass through for display
            }};
        }} catch (err) {{
            console.error('Peer comparison error:', err);
            return null;
        }}
    }}
    
    // Energy chart
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    // Building-level fuel usage flags - determine which fuels this building uses
    const buildingUsesElec = {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in elec_usage])}.some(v => v > 0);
    const buildingUsesGas = {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in gas_usage])}.some(v => v > 0);
    const buildingUsesSteam = {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in steam_usage])}.some(v => v > 0);

    const elecData = {{
        x: months,
        y: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in elec_usage])},
        name: 'Elec',
        type: 'scatter',
        mode: 'lines+markers',
        line: {{color: '#0066cc', width: 3}},
        marker: {{size: 8}},
        hovertemplate: '%{{x}}<br>Elec: %{{y:,.0f}} kBtu<br>(%{{customdata:,.0f}} kWh)<extra></extra>',
        customdata: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in elec_usage])}.map(v => kBtuToKwh(v))
    }};
    
    const gasData = {{
        x: months,
        y: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in gas_usage])},
        name: 'Gas',
        type: 'scatter',
        mode: 'lines+markers',
        line: {{color: '#ff6600', width: 3}},
        marker: {{size: 8}},
        hovertemplate: '%{{x}}<br>Gas: %{{y:,.0f}} kBtu<br>(%{{customdata:,.0f}} Therms)<extra></extra>',
        customdata: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in gas_usage])}.map(v => kBtuToTherms(v))
    }};
    
    const steamData = {{
        x: months,
        y: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in steam_usage])},
        name: 'Steam',
        type: 'scatter',
        mode: 'lines+markers',
        line: {{color: '#ffc107', width: 3}},
        marker: {{size: 8}},
        hovertemplate: '%{{x}}<br>Steam: %{{y:,.0f}} kBtu<br>(%{{customdata:,.0f}} lbs)<extra></extra>',
        customdata: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in steam_usage])}.map(v => kBtuToLbs(v))
    }};
    
    const layout = {{
        title: {{
            text: "Whole Building Usage (2023)",
            font: {{size: 20}}
        }},
        yaxis: {{
            title: 'Usage (kBtu)',
            showgrid: false
        }},
        xaxis: {{
            showgrid: false
        }},
        font: {{family: 'Arial, sans-serif'}},
        plot_bgcolor: '#ffffff',
        paper_bgcolor: 'white',
        hovermode: 'x unified'
    }};
    
    // Building usage chart - only show fuels that building uses
    const buildingUsageData = [];
    if (buildingUsesElec) buildingUsageData.push(elecData);
    if (buildingUsesGas) buildingUsageData.push(gasData);
    if (buildingUsesSteam) buildingUsageData.push(steamData);
    
    Plotly.newPlot('energy_chart', buildingUsageData, layout, {{
        modeBarButtonsToRemove: ['zoom2d', 'pan2d', 'select2d', 'lasso2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d', 'hoverClosestCartesian', 'hoverCompareCartesian'],
        displaylogo: false,
        displayModeBar: true
    }});

    // Add annual usage caption below the chart
    document.getElementById('energy_chart').insertAdjacentHTML('afterend',
        '<div style="text-align: center; margin-top: 15px; font-size: 14px; color: #666;"><strong>Annual Usage: ' + ({annual_building_usage:.0f}).toLocaleString() + ' kBtu</strong></div>'
    );

    // Office Energy Chart
    const officeElecData = {{
        x: months,
        y: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in office_elec_usage])},
        name: 'Elec',
        type: 'bar',
        marker: {{color: '#0066cc'}}
    }};
    
    const officeGasData = {{
        x: months,
        y: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in office_gas_usage])},
        name: 'Gas',
        type: 'bar',
        marker: {{color: '#ff6600'}}
    }};
    
    const officeSteamData = {{
        x: months,
        y: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in office_steam_usage])},
        name: 'Steam',
        type: 'bar',
        marker: {{color: '#ffc107'}}
    }};
    
    const officeLayout = {{
        title: {{
            text: "Office Only Usage (2023)",
            font: {{size: 20}}
        }},
        yaxis: {{
            title: 'Usage (kBtu)',
            showgrid: false
        }},
        xaxis: {{
            showgrid: false,
            range: [-0.5, 11.5],  // Force x-axis to show all 12 months with padding
            fixedrange: true
        }},
        barmode: 'group',
        font: {{family: 'Arial, sans-serif'}},
        plot_bgcolor: '#ffffff',
        paper_bgcolor: 'white',
        hovermode: 'x unified'
    }};
    
    // Office usage chart - only show fuels that building uses
    const officeUsageData = [];
    if (buildingUsesElec) officeUsageData.push(officeElecData);
    if (buildingUsesGas) officeUsageData.push(officeGasData);
    if (buildingUsesSteam) officeUsageData.push(officeSteamData);
    
    Plotly.newPlot('office_energy_chart', officeUsageData, officeLayout, {{
        modeBarButtonsToRemove: ['zoom2d', 'pan2d', 'select2d', 'lasso2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d', 'hoverClosestCartesian', 'hoverCompareCartesian'],
        displaylogo: false,
        displayModeBar: true
    }});

    // Add annual usage caption below the chart
    document.getElementById('office_energy_chart').insertAdjacentHTML('afterend',
        '<div style="text-align: center; margin-top: 15px; font-size: 14px; color: #666;"><strong>Annual Usage: ' + ({annual_office_usage:.0f}).toLocaleString() + ' kBtu</strong></div>'
    );

    // Energy Cost Chart
    const elecCost = {{
        x: months, 
        y: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in elec_cost])}, 
        name: 'Elec', 
        type: 'scatter', 
        mode: 'lines+markers', 
        line: {{color: '#0066cc', width: 3}},
        marker: {{size: 8}}
    }};
    
    const gasCost = {{
        x: months, 
        y: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in gas_cost])}, 
        name: 'Gas', 
        type: 'scatter', 
        mode: 'lines+markers', 
        line: {{color: '#ff6600', width: 3}},
        marker: {{size: 8}}
    }};
    
    const steamCostData = {{
        x: months, 
        y: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in steam_cost])}, 
        name: 'Steam', 
        type: 'scatter', 
        mode: 'lines+markers', 
        line: {{color: '#ffc107', width: 3}},
        marker: {{size: 8}}
    }};
    
    const costLayout = {{
        title: {{
            text: "Whole Building Cost (2023)",
            font: {{size: 20}}
        }},
        yaxis: {{
            title: '',
            tickformat: '$,.0f',
            showgrid: false
        }},
        xaxis: {{
            showgrid: false
        }},
        font: {{family: 'Inter, sans-serif'}},
        plot_bgcolor: '#ffffff',
        paper_bgcolor: 'white',
        hovermode: 'x unified'
    }};

    // Building cost chart - only show fuels that building uses
    const buildingCostData = [];
    if (buildingUsesElec) buildingCostData.push(elecCost);
    if (buildingUsesGas) buildingCostData.push(gasCost);
    if (buildingUsesSteam) buildingCostData.push(steamCostData);
    
    Plotly.newPlot('energy_cost_chart', buildingCostData, costLayout, {{
        modeBarButtonsToRemove: ['zoom2d', 'pan2d', 'select2d', 'lasso2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d', 'hoverClosestCartesian', 'hoverCompareCartesian'],
        displaylogo: false,
        displayModeBar: true
    }});

    // Add annual cost caption below the chart
    document.getElementById('energy_cost_chart').insertAdjacentHTML('afterend', 
        '<div style="text-align: center; margin-top: 15px; font-size: 14px; color: #666;"><strong>Annual Cost: $' + ({annual_building_cost:.0f}).toLocaleString() + '</strong></div>'
    );
    
    // Office Cost Chart
    const officeElecCost = {{
        x: months, 
        y: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in office_elec_cost])}, 
        name: 'Elec', 
        type: 'bar', 
        marker: {{color: '#0066cc'}}
    }};
    
    const officeGasCost = {{
        x: months, 
        y: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in office_gas_cost])}, 
        name: 'Gas', 
        type: 'bar', 
        marker: {{color: '#ff6600'}}
    }};
    
    const officeSteamCostData = {{
        x: months, 
        y: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in office_steam_cost])}, 
        name: 'Steam', 
        type: 'bar', 
        marker: {{color: '#ffc107'}}
    }};
    
    const officeCostLayout = {{
        title: {{
            text: "Office Only Cost (2023)",
            font: {{size: 20}}
        }},
        yaxis: {{
            title: '',
            tickformat: '$,.0f',
            showgrid: false
        }},
        xaxis: {{
            showgrid: false,
            range: [-0.5, 11.5],  // Force x-axis to show all 12 months with padding
            fixedrange: true
        }},
        barmode: 'group',
        font: {{family: 'Inter, sans-serif'}},
        plot_bgcolor: '#ffffff',
        paper_bgcolor: 'white',
        hovermode: 'x unified'
    }};

    // Office cost chart - only show fuels that building uses
    const officeCostData = [];
    if (buildingUsesElec) officeCostData.push(officeElecCost);
    if (buildingUsesGas) officeCostData.push(officeGasCost);
    if (buildingUsesSteam) officeCostData.push(officeSteamCostData);
    
    Plotly.newPlot('office_cost_chart', officeCostData, officeCostLayout, {{
        modeBarButtonsToRemove: ['zoom2d', 'pan2d', 'select2d', 'lasso2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d', 'hoverClosestCartesian', 'hoverCompareCartesian'],
        displaylogo: false,
        displayModeBar: true
    }});

    // Add annual cost caption below the chart
    document.getElementById('office_cost_chart').insertAdjacentHTML('afterend', 
        '<div style="text-align: center; margin-top: 15px; font-size: 14px; color: #666;"><strong>Annual Cost: $' + ({annual_office_cost:.0f}).toLocaleString() + '</strong></div>'
    );
    
    // HVAC Percentage Chart with seasonal colors
    const hvacValues = {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in hvac_pct])};
    
    // Create separate traces for each season with filled area only below the curve
    const hvacTraces = [];
    
    // Cool season (Jan-Mar) - Blue
    hvacTraces.push({{
        x: months.slice(0, 3),
        y: hvacValues.slice(0, 3),
        type: 'scatter',
        mode: 'lines',
        fill: 'tozeroy',
        line: {{color: '#1e90ff', width: 3}},
        fillcolor: 'rgba(30, 144, 255, 0.3)',
        showlegend: false,
        hovertemplate: '%{{x}}: %{{y:.1%}}<extra></extra>'
    }});
    
    // Warm season (Apr-Jun) - Yellow
    hvacTraces.push({{
        x: months.slice(3, 6),
        y: hvacValues.slice(3, 6),
        type: 'scatter',
        mode: 'lines',
        fill: 'tozeroy',
        line: {{color: '#daa520', width: 3}},
        fillcolor: 'rgba(255, 215, 0, 0.3)',
        showlegend: false,
        hovertemplate: '%{{x}}: %{{y:.1%}}<extra></extra>'
    }});
    
    // Hot season (Jul-Sep) - Red
    hvacTraces.push({{
        x: months.slice(6, 9),
        y: hvacValues.slice(6, 9),
        type: 'scatter',
        mode: 'lines',
        fill: 'tozeroy',
        line: {{color: '#ff4500', width: 3}},
        fillcolor: 'rgba(255, 69, 0, 0.3)',
        showlegend: false,
        hovertemplate: '%{{x}}: %{{y:.1%}}<extra></extra>'
    }});
    
    // Cold season (Oct-Dec) - Blue
    hvacTraces.push({{
        x: months.slice(9, 12),
        y: hvacValues.slice(9, 12),
        type: 'scatter',
        mode: 'lines',
        fill: 'tozeroy',
        line: {{color: '#1e90ff', width: 3}},
        fillcolor: 'rgba(30, 144, 255, 0.3)',
        showlegend: false,
        hovertemplate: '%{{x}}: %{{y:.1%}}<extra></extra>'
    }});
    
    // Add connecting lines between seasons
    hvacTraces.push({{
        x: months,
        y: hvacValues,
        type: 'scatter',
        mode: 'lines',
        line: {{color: '#2c3e50', width: 3}},
        showlegend: false,
        hovertemplate: '%{{x}}: %{{y:.1%}}<extra></extra>'
    }});
    
    const hvacLayout = {{
        title: {{
            text: "",
            font: {{size: 20}}
        }},
        yaxis: {{
            title: '',
            tickformat: '.0%',
            showgrid: false,
            rangemode: 'tozero',
            range: [0, Math.max(...hvacValues) * 1.2]  // Add space above for labels
        }},
        xaxis: {{
            showgrid: false
        }},
        font: {{family: 'Arial, sans-serif'}},
        plot_bgcolor: '#ffffff',
        paper_bgcolor: 'white',
        hovermode: 'x unified',
        annotations: [
            // Cool label - below the curve
            {{
                x: 1,
                y: 0.05,
                xref: 'x',
                yref: 'paper',
                text: 'Cool',
                showarrow: false,
                font: {{size: 16, color: '#1e90ff', weight: 'bold'}}
            }},
            // Warm label - below the curve
            {{
                x: 4,
                y: 0.05,
                xref: 'x',
                yref: 'paper',
                text: 'Warm',
                showarrow: false,
                font: {{size: 16, color: '#daa520', weight: 'bold'}}
            }},
            // Hot label - below the curve
            {{
                x: 7,
                y: 0.05,
                xref: 'x',
                yref: 'paper',
                text: 'Hot',
                showarrow: false,
                font: {{size: 16, color: '#ff4500', weight: 'bold'}}
            }},
            // Cold label - below the curve
            {{
                x: 10,
                y: 0.05,
                xref: 'x',
                yref: 'paper',
                text: 'Cold',
                showarrow: false,
                font: {{size: 16, color: '#1e90ff', weight: 'bold'}}
            }}
        ]
    }};
    
    Plotly.newPlot('hvac_pct_chart', hvacTraces, hvacLayout, {{
        modeBarButtonsToRemove: ['zoom2d', 'pan2d', 'select2d', 'lasso2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d', 'hoverClosestCartesian', 'hoverCompareCartesian'],
        displaylogo: false,
        displayModeBar: true
    }});
    
    // HVAC Cost Breakdown with ODCV Savings Overlay
    const hvacElecCost = {{
        x: months,
        y: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in monthly_hvac_elec_cost])},
        name: 'HVAC Elec Cost',
        type: 'bar',
        marker: {{color: '#0066cc'}},
        hovertemplate: 'HVAC Elec: $%{{y:,.0f}}<extra></extra>'
    }};

    const hvacGasCost = {{
        x: months,
        y: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in monthly_hvac_gas_cost])},
        name: 'HVAC Gas Cost',
        type: 'bar',
        marker: {{color: '#ff6600'}},
        hovertemplate: 'HVAC Gas: $%{{y:,.0f}}<extra></extra>'
    }};

    const hvacSteamCost = {{
        x: months,
        y: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in monthly_hvac_steam_cost])},
        name: 'HVAC Steam Cost',
        type: 'bar',
        marker: {{color: '#ffc107'}},
        hovertemplate: 'HVAC Steam: $%{{y:,.0f}}<extra></extra>'
    }};

    const odcvSavingsLine = {{
        x: months,
        y: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in odcv_savings])},
        name: 'ODCV Savings',
        type: 'scatter',
        mode: 'lines+markers',
        line: {{color: '#38a169', width: 3, dash: 'dash'}},
        marker: {{size: 10, color: '#38a169'}},
        yaxis: 'y',
        hovertemplate: 'ODCV Saves: $%{{y:,.0f}} (%{{customdata:.1f}}% of HVAC)<extra></extra>',
        customdata: {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in monthly_odcv_percentages])}
    }};

    // HVAC cost breakdown chart - only show fuels that building uses
    const hvacCostData = [];
    if (buildingUsesElec) hvacCostData.push(hvacElecCost);
    if (buildingUsesGas) hvacCostData.push(hvacGasCost);
    if (buildingUsesSteam) hvacCostData.push(hvacSteamCost);
    hvacCostData.push(odcvSavingsLine); // Always show ODCV savings line

    Plotly.newPlot('hvac_cost_breakdown_chart',
        hvacCostData,
        {{
            title: {{
                text: "Monthly HVAC Costs with ODCV Savings Potential",
                font: {{size: 20}}
            }},
            yaxis: {{
                tickformat: '$,.0f',
                showgrid: false
            }},
            xaxis: {{
                showgrid: false
            }},
            barmode: 'stack',
            legend: {{
                orientation: 'h',
                y: -0.15
            }},
            font: {{family: 'Arial, sans-serif'}},
            plot_bgcolor: '#ffffff',
            paper_bgcolor: 'white',
            hovermode: 'x unified'
        }}, {{
            modeBarButtonsToRemove: ['zoom2d', 'pan2d', 'select2d', 'lasso2d', 'autoScale2d', 'resetScale2d'],
            displaylogo: false
        }}
    );
    
    // ODCV Savings Chart
    // Store original monthly values for hover
    const monthlyElecSavings = {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in odcv_elec_savings])};
    const monthlyGasSavings = {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in odcv_gas_savings])};
    const monthlySteamSavings = {json.dumps([float(x) if x and not pd.isna(x) else 0 for x in odcv_steam_savings])};
    
    // Calculate cumulative values for display
    const cumulativeElecSavings = [];
    const cumulativeGasSavings = [];
    const cumulativeSteamSavings = [];
    
    for (let i = 0; i < 12; i++) {{
        cumulativeElecSavings[i] = (i === 0) ? monthlyElecSavings[0] : cumulativeElecSavings[i-1] + monthlyElecSavings[i];
        cumulativeGasSavings[i] = (i === 0) ? monthlyGasSavings[0] : cumulativeGasSavings[i-1] + monthlyGasSavings[i];
        cumulativeSteamSavings[i] = (i === 0) ? monthlySteamSavings[0] : cumulativeSteamSavings[i-1] + monthlySteamSavings[i];
    }}
    
    // Create customdata array with all monthly values for unified hover
    const monthlyTotals = months.map((m, i) => 
        monthlyElecSavings[i] + monthlyGasSavings[i] + monthlySteamSavings[i]
    );
    
    const odcvElecSave = {{
        x: months, 
        y: cumulativeElecSavings, 
        name: 'Elec', 
        type: 'bar', 
        marker: {{color: '#0066cc'}},
        customdata: months.map((m, i) => ({{
            elec: monthlyElecSavings[i],
            gas: monthlyGasSavings[i],
            steam: monthlySteamSavings[i],
            total: monthlyTotals[i]
        }})),
        hovertemplate: 'Elec: $%{{customdata.elec:,.0f}}<extra></extra>'
    }};
    
    const odcvGasSave = {{
        x: months, 
        y: cumulativeGasSavings, 
        name: 'Gas', 
        type: 'bar', 
        marker: {{color: '#ff6600'}},
        customdata: months.map((m, i) => ({{
            elec: monthlyElecSavings[i],
            gas: monthlyGasSavings[i],
            steam: monthlySteamSavings[i],
            total: monthlyTotals[i]
        }})),
        hovertemplate: 'Gas: $%{{customdata.gas:,.0f}}<extra></extra>'
    }};
    
    const odcvSteamSave = {{
        x: months, 
        y: cumulativeSteamSavings, 
        name: 'Steam', 
        type: 'bar', 
        marker: {{color: '#ffc107'}},
        customdata: months.map((m, i) => ({{
            elec: monthlyElecSavings[i],
            gas: monthlyGasSavings[i],
            steam: monthlySteamSavings[i],
            total: monthlyTotals[i]
        }})),
        hovertemplate: 'Steam: $%{{customdata.steam:,.0f}}<extra></extra>'
    }};
    
    const totalSavings = {total_odcv_savings};
    
    // Add invisible trace for monthly total in hover
    const monthlyTotalTrace = {{
        x: months,
        y: months.map(() => 0), // Invisible trace
        name: 'Monthly Total',
        type: 'scatter',
        mode: 'markers',
        marker: {{size: 0, color: 'rgba(0,0,0,0)'}},
        showlegend: false,
        customdata: monthlyTotals,
        hovertemplate: '<b>Monthly Total: $%{{customdata:,.0f}}</b><extra></extra>'
    }};
    
    // ODCV savings chart - only show fuels that building uses
    const odcvSavingsData = [];
    if (buildingUsesElec) odcvSavingsData.push(odcvElecSave);
    if (buildingUsesGas) odcvSavingsData.push(odcvGasSave);
    if (buildingUsesSteam) odcvSavingsData.push(odcvSteamSave);
    odcvSavingsData.push(monthlyTotalTrace); // Always add the total trace for hover
    
    Plotly.newPlot('odcv_savings_chart', odcvSavingsData, {{
        title: {{
            text: "",
            font: {{size: 20}}
        }},
        yaxis: {{
            title: '',
            tickformat: '$,.0f',
            showgrid: false
        }},
        xaxis: {{
            showgrid: false
        }},
        barmode: 'stack',
        font: {{family: 'Arial, sans-serif'}},
        plot_bgcolor: '#ffffff',
        paper_bgcolor: 'white',
        hovermode: 'x unified',
        margin: {{
            l: 60,
            r: 50,
            t: 50,
            b: 80  // Extra bottom margin for annotation
        }},
        annotations: [{{
            text: '<b>Annual Savings: $' + totalSavings.toFixed(0).replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, ',') + '</b>',
            xref: 'paper',
            yref: 'paper',
            x: 0.5,
            y: -0.08,  // Position inside the chart canvas
            xanchor: 'center',
            yanchor: 'top',
            showarrow: false,
            font: {{
                size: 16,
                color: '#666'
            }}
        }}]
    }}, {{
        modeBarButtonsToRemove: ['zoom2d', 'pan2d', 'select2d', 'lasso2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d', 'hoverClosestCartesian', 'hoverCompareCartesian'],
        displaylogo: false,
        displayModeBar: true
    }});
{f'''    
    // EPA Good threshold line
    const goodThreshold = {{
        x: {json.dumps(list(range(len(chart_dates))))},
        y: Array({len(chart_dates)}).fill(12),
        mode: 'lines',
        line: {{color: '#00b300', dash: 'dash', width: 4}},  // Darker green, thicker line
        name: 'Good AQ Threshold (EPA)',
        hoverinfo: 'skip',
        opacity: 1  // Ensure full opacity
    }};

    // Create fill traces for areas above and below threshold
    const dates = {json.dumps(list(range(len(chart_dates))))};  // Use indices for x-axis
    const values = {json.dumps(chart_values)};
    const labels = {json.dumps(chart_labels)};  // Month labels
    const goodThresholdValue = 12;  // EPA Good threshold
    const badThreshold = 35.4;  // EPA Unhealthy for Sensitive Groups threshold
    
    // Create PM2.5 line with fill to zero for blue area
    const pm25Line = {{
        x: dates,
        y: values,
        type: 'scatter',
        mode: 'lines',
        line: {{color: '#0066cc', width: 3}},
        fill: 'tozeroy',
        fillcolor: 'rgba(0, 102, 204, 0.1)',  // Very light blue
        name: 'PM2.5',
        hovertemplate: 'Day %{{x}}<br>PM2.5: %{{y:.1f}} μg/m³<br>(M-F 8am-6pm)<extra></extra>'
    }};
    
    // Order is important: data line and threshold
    Plotly.newPlot('pm25_chart', [pm25Line, goodThreshold], {{
        title: {{
            text: '',
            y: 0.95
        }},
        yaxis: {{
            title: 'PM2.5 (μg/m³)',
            showgrid: false,
            zeroline: false,
            range: [0, {max_pm25 * 1.1 if max_pm25 > 0 else 50}]
        }},
        xaxis: {{
            title: '',
            showgrid: false,
            type: 'linear',
            ticktext: labels,
            tickvals: dates,
            tickangle: 0,
            showticklabels: true,
            range: [0, {len(chart_dates) - 1}]
        }},
        legend: {{
            orientation: 'h',
            x: 0.5,
            xanchor: 'center',
            y: -0.12,
            yanchor: 'top',
            bgcolor: 'transparent',
            borderwidth: 0
        }},
        margin: {{t: 50, r: 50, b: 80, l: 60}},
        plot_bgcolor: '#ffffff',
        paper_bgcolor: '#ffffff',
        font: {{family: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'}},
        hovermode: 'x unified'
    }}, {{
        modeBarButtonsToRemove: ['zoom2d', 'pan2d', 'select2d', 'lasso2d', 'zoomIn2d', 'zoomOut2d', 'autoScale2d', 'resetScale2d', 'hoverClosestCartesian', 'hoverCompareCartesian'],
        displaylogo: false,
        displayModeBar: true
    }});
    
    // Handle window resize for responsive charts
    window.addEventListener('resize', function() {{
        // Resize all Plotly charts when window size changes
        setTimeout(() => {{
            const charts = ['energy_chart', 'office_energy_chart', 'energy_cost_chart', 'office_cost_chart', 'hvac_pct_chart', 'hvac_cost_breakdown_chart', 'odcv_savings_chart', 'pm25_chart'];
            charts.forEach(chartId => {{
                const element = document.getElementById(chartId);
                if (element && window.Plotly) {{
                    Plotly.Plots.resize(element);
                }}
            }});
        }}, 100);
    }});
''' if chart_dates else ""}
    
    // Initialize 360° panorama with Manhattan grid logic
    document.addEventListener('DOMContentLoaded', () => {{
        // Initialize Dynamic carousel title to show the first available slide type
        const interactiveCarousel = document.getElementById('interactive-carousel-{bbl}');
        if (interactiveCarousel && interactiveCarousel.children.length > 0) {{
            const firstSlide = interactiveCarousel.children[0];
            const slideType = firstSlide.getAttribute('data-type');
            const titleElement = document.getElementById('interactive-views-title-{bbl}');
            if (titleElement && slideType) {{
                const typeMap = {{
                    '3d': '3D Model',
                    'video': 'Drone Footage',
                    'pano': '360 Panorama'
                }};
                titleElement.innerHTML = `Dynamic: <span style="color: #555;">${{typeMap[slideType] || 'Unknown'}}</span>`;
            }}
        }}

        // Manhattan grid even/odd logic for yaw
        function getBuildingYaw(address) {{
            const match = address.match(/\\\\b(\\\\d+)/);
            if (!match) return 0;
            
            const buildingNumber = parseInt(match[1]);
            const isEven = buildingNumber % 2 === 0;
            const addressLower = address.toLowerCase();
            
            // Fix the yaw angles to actually look at buildings
            // In pannellum: 0° = North, 90° = East, 180° = South, 270° = West
            
            if (addressLower.includes('street') || addressLower.includes(' st')) {{
                // STREETS run East-West
                // For 111 E 58th St (odd building number), yaw should be -91.56° (looking west)
                // Even building numbers are on SOUTH side, Odd on NORTH side
                return isEven ? 90 : -91.56;
            }} else if (addressLower.includes('avenue') || addressLower.includes(' ave')) {{
                // AVENUES run North-South
                // Even numbers are on WEST side (need to look EAST = 90°)
                // Odd numbers are on EAST side (need to look WEST = 270°)
                return isEven ? 90 : 270;
            }} else if (addressLower.includes('broadway')) {{
                // Broadway runs diagonal NE-SW
                // Even = NW side (look SE = ~135°)
                // Odd = SE side (look NW = ~315°)
                return isEven ? 135 : 315;
            }}
            
            // Default to north-facing
            return 0;
        }}
        
        // Function to initialize panorama
        window.initPanorama = function() {{
            const viewerEl = document.getElementById('viewer-{bbl}');
            if (!viewerEl || viewerEl._pannellumInitialized) return;
            
            const buildingHeight = {building_height};
            const address = "{main_address}";
            
            // Calculate yaw based on address
            const yaw = getBuildingYaw(address);
            
            // Use yaw directly without adjustment
            let adjustedYaw = yaw;
            
            // Calculate pitch based on building height
            // We're at street level looking at buildings
            // Based on ideal pitch for 463.31ft building = 37.03° pitch
            // This gives us 0.0799 degrees per foot of building height
            const pitch = Math.min(buildingHeight * 0.0799, 60);  // Max 60° for very tall buildings
            
            console.log(`Panorama {bbl}: Address="${{address}}", Height=${{buildingHeight}}ft, Yaw=${{yaw}}° (adjusted: ${{adjustedYaw}}°), Pitch=${{pitch}}°`);
            
            try {{
                const viewer = pannellum.viewer('viewer-{bbl}', {{
                    "type": "equirectangular",
                    "panorama": "{AWS_IMAGES_BUCKET}/images/{bbl}/{bbl}_360.jpg",
                    "autoLoad": true,
                    "autoRotate": 0,  // Will be started when user navigates to this slide
                    "pitch": pitch,
                    "yaw": adjustedYaw,
                    "hfov": 120,
                    "maxHfov": 120,
                    "minHfov": 30,
                    "showZoomCtrl": true,
                    "showFullscreenCtrl": true,
                    "mouseZoom": false,
                    "minPitch": -85,
                    "maxPitch": 90
                }});
                viewerEl._pannellumInitialized = true;
                viewerEl.pannellumViewer = viewer;  // Store viewer instance
                window[`panoramaViewer_{bbl}`] = viewer;  // Also store globally for easy access
                console.log('Panorama initialized successfully for BBL {bbl}');
            }} catch (e) {{
                console.error('Failed to initialize panorama:', e);
            }}
        }}
        
        // Initialize based on whether video exists
        const hasVideo = {str(has_video).lower()};
        const has3D = {str(has_3d).lower()};
        if (!hasVideo && !has3D) {{
            setTimeout(window.initPanorama, 500);
        }}

        // Don't initialize immediately if video exists - wait for user to navigate to panorama slide

        // Check network connectivity - just use navigator.onLine
        function checkNetworkConnectivity() {{
            return Promise.resolve(navigator.onLine);
        }}

        // Preload model data
        function preloadModel(url) {{
            return new Promise((resolve, reject) => {{
                const xhr = new XMLHttpRequest();
                xhr.open('GET', url, true);
                xhr.responseType = 'blob';

                xhr.onload = function() {{
                    if (xhr.status === 200) {{
                        const blob = xhr.response;
                        const objectURL = URL.createObjectURL(blob);
                        resolve(objectURL);
                    }} else {{
                        reject(new Error(`HTTP ${{xhr.status}}: ${{xhr.statusText}}`));
                    }}
                }};

                xhr.onerror = function() {{
                    reject(new Error('Network error during preload'));
                }};

                xhr.onprogress = function(e) {{
                    if (e.lengthComputable) {{
                        const percentComplete = (e.loaded / e.total) * 100;
                        // Trigger progress update
                        if (window.onModelPreloadProgress) {{
                            window.onModelPreloadProgress(percentComplete);
                        }}
                    }}
                }};

                xhr.send();
            }});
        }}

        // Function to initialize 3D Model with retry mechanism and network checks
        window.init3DModel{bbl} = async function(retryCount = 0) {{
            const containerEl = document.getElementById('model-container-{bbl}');
            const loadingEl = document.getElementById('model-loading-{bbl}');
            const maxRetries = 3;
            const loadTimeout = 30000; // 30 seconds timeout

            if (!containerEl) return;

            // Check if already loading or initialized
            if (containerEl._loadingInProgress) {{
                console.log('Model already loading for {bbl}');
                return;
            }}

            if (containerEl._threeInitialized && containerEl._modelLoaded) {{
                console.log('Model already loaded for {bbl}');
                return;
            }}

            // Set loading flag IMMEDIATELY to prevent race conditions
            containerEl._loadingInProgress = true;

            console.log(`Starting 3D model initialization for {bbl} (attempt ${{retryCount + 1}}/${{maxRetries + 1}})`);

            // Check network connectivity first
            const isOnline = await checkNetworkConnectivity();
            if (!isOnline && retryCount === 0) {{
                if (loadingEl) {{
                    loadingEl.style.cssText = `
                        display: block !important;
                        position: absolute !important;
                        top: 50% !important;
                        left: 50% !important;
                        transform: translate(-50%, -50%) !important;
                        font-family: Inter, sans-serif !important;
                        color: #333 !important;
                        font-size: 18px !important;
                        font-weight: 500 !important;
                        background: rgba(255, 255, 255, 0.98) !important;
                        padding: 25px 35px !important;
                        border-radius: 12px !important;
                        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
                        z-index: 10000 !important;
                        pointer-events: auto !important;
                        min-width: 200px !important;
                        text-align: center !important;
                    `;
                    loadingEl.innerHTML = `
                        <div style="color: #d32f2f; margin-bottom: 10px;">No Internet Connection</div>
                        <div style="font-size: 14px; color: #666; margin-bottom: 15px;">Please check your connection and try again</div>
                        <button onclick="window.init3DModel{bbl}(0)" style="padding: 8px 16px; background: #00769d; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">Retry</button>
                    `;
                }}
                containerEl._loadingInProgress = false;
                return;
            }}

            // Ensure loading indicator is always visible and properly styled
            if (loadingEl) {{
                loadingEl.style.cssText = `
                    display: block !important;
                    position: absolute !important;
                    top: 50% !important;
                    left: 50% !important;
                    transform: translate(-50%, -50%) !important;
                    font-family: Inter, sans-serif !important;
                    color: #333 !important;
                    font-size: 18px !important;
                    font-weight: 500 !important;
                    background: rgba(255, 255, 255, 0.98) !important;
                    padding: 25px 35px !important;
                    border-radius: 12px !important;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
                    z-index: 10000 !important;
                    pointer-events: none !important;
                    min-width: 200px !important;
                    text-align: center !important;
                `;
                loadingEl.innerHTML = `
                    <div style="margin-bottom: 15px;">Loading 3D Model...</div>
                    <div style="width: 100%; height: 4px; background: #e0e0e0; border-radius: 2px; overflow: hidden;">
                        <div id="progress-bar-{bbl}" style="width: 0%; height: 100%; background: #00769d; transition: width 0.3s ease;"></div>
                    </div>
                    <div id="progress-text-{bbl}" style="margin-top: 10px; font-size: 14px; color: #666;">0%</div>
                `;
            }}

            // Mark as initialized (loading flag already set above)
            containerEl._threeInitialized = true;

            // Set a timeout for the load
            let loadTimeoutId = setTimeout(() => {{
                if (!containerEl._modelLoaded) {{
                    console.error('Model load timeout for {bbl}');
                    handleLoadError('Load timeout exceeded');
                }}
            }}, loadTimeout);

            // Function to handle load errors with retry logic
            function handleLoadError(error) {{
                clearTimeout(loadTimeoutId);
                console.error(`Failed to load 3D model for {bbl}:`, error);

                containerEl._loadingInProgress = false;
                containerEl._threeInitialized = false;

                if (retryCount < maxRetries) {{
                    if (loadingEl) {{
                        loadingEl.innerHTML = `
                            <div style="margin-bottom: 10px;">Retrying...</div>
                            <div style="font-size: 14px; color: #666;">Attempt ${{retryCount + 2}} of ${{maxRetries + 1}}</div>
                        `;
                    }}
                    // Exponential backoff: 1s, 2s, 4s
                    setTimeout(() => {{
                        window.init3DModel{bbl}(retryCount + 1);
                    }}, Math.pow(2, retryCount) * 1000);
                }} else {{
                    if (loadingEl) {{
                        loadingEl.innerHTML = `
                            <div style="color: #d32f2f; margin-bottom: 10px;">Failed to load 3D model</div>
                            <div style="font-size: 14px; color: #666;">Please check your connection and refresh the page</div>
                            <button onclick="window.init3DModel{bbl}(0)" style="margin-top: 15px; padding: 8px 16px; background: #00769d; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">Retry</button>
                        `;
                        loadingEl.style.pointerEvents = 'auto';
                    }}
                }}
            }}

            // Wait for container to have valid dimensions
            if (containerEl.clientWidth === 0 || containerEl.clientHeight === 0) {{
                console.log('Container has 0 dimensions, waiting...');
                setTimeout(() => {{
                    containerEl._loadingInProgress = false;
                    window.init3DModel{bbl}(retryCount);
                }}, 100);
                return;
            }}

            try {{
                // Scene setup
                const scene = new THREE.Scene();
                scene.background = new THREE.Color(0xffffff);

                // Camera setup - use valid dimensions
                const width = containerEl.clientWidth || 600;
                const height = containerEl.clientHeight || 400;
                const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
                camera.position.set(5, 5, 5);

                // Renderer setup
                const renderer = new THREE.WebGLRenderer({{ antialias: true }});
                renderer.setSize(containerEl.clientWidth, containerEl.clientHeight);
                renderer.shadowMap.enabled = true;
                renderer.shadowMap.type = THREE.PCFSoftShadowMap;
                containerEl.appendChild(renderer.domElement);

                // Lighting setup
                const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
                scene.add(ambientLight);

                const directionalLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
                directionalLight1.position.set(10, 10, 10);
                directionalLight1.castShadow = true;
                scene.add(directionalLight1);

                const directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.4);
                directionalLight2.position.set(-10, 10, -10);
                scene.add(directionalLight2);

                // Controls setup
                const controls = new THREE.OrbitControls(camera, renderer.domElement);
                controls.enableDamping = true;
                controls.dampingFactor = 0.05;
                controls.minDistance = 2;
                controls.maxDistance = 30;
                controls.enableZoom = true;
                controls.zoomSpeed = 0.3;  // Reduced zoom speed for more incremental control
                controls.panSpeed = 0.5;  // Reduced pan speed for finer control
                controls.rotateSpeed = 0.5;  // Reduced rotation speed for smoother control

                // Configure mouse buttons
                controls.mouseButtons = {{
                    LEFT: THREE.MOUSE.ROTATE,
                    MIDDLE: THREE.MOUSE.DOLLY,
                    RIGHT: THREE.MOUSE.PAN
                }};

                // Start with controls disabled
                controls.enabled = false;
                let isActivated = false;

                // Activate on click ONLY
                renderer.domElement.addEventListener('click', function() {{
                    if (!isActivated) {{
                        isActivated = true;
                        controls.enabled = true;
                    }}
                }});

                // Deactivate when mouse leaves the entire carousel slide
                const modelViewer = document.getElementById('model-viewer-{bbl}');
                if (modelViewer) {{
                    modelViewer.addEventListener('mouseleave', function() {{
                        if (isActivated) {{
                            isActivated = false;
                            controls.enabled = false;
                        }}
                    }});
                }}

                // Handle scroll based on activation state
                renderer.domElement.addEventListener('wheel', function(e) {{
                    if (isActivated) {{
                        // When activated, prevent page scroll but let OrbitControls handle zoom
                        e.preventDefault();
                        // Removed manual zoom handling - OrbitControls will handle it with zoomSpeed setting
                    }}
                    // When not activated, let page scroll normally
                }}, {{ passive: false }});

                // Auto-rotation setup
                let isAutoRotating = true;
                let rotationSpeed = 0.005; // Slow rotation speed
                let pivotGroup = null; // Store pivot group reference

                // Stop auto-rotation when user interacts
                controls.addEventListener('start', function() {{
                    isAutoRotating = false;
                }});

                // Load GLB model with enhanced progress tracking
                const loader = new THREE.GLTFLoader();
                let currentModel = null;
                let lastProgressUpdate = 0;

                loader.load(
                    '{AWS_IMAGES_BUCKET}/images/{bbl}/{bbl}_3d.glb',
                    function(gltf) {{
                        clearTimeout(loadTimeoutId);
                        console.log('3D model loaded successfully for {bbl}');
                        currentModel = gltf.scene;

                        // Mark as successfully loaded
                        containerEl._modelLoaded = true;
                        containerEl._loadingInProgress = false;

                        // Auto-scale and center the model
                        const box = new THREE.Box3().setFromObject(currentModel);
                        const center = box.getCenter(new THREE.Vector3());
                        const size = box.getSize(new THREE.Vector3());

                        const maxDim = Math.max(size.x, size.y, size.z);
                        const scale = 6 / maxDim;
                        currentModel.scale.setScalar(scale);

                        // Center the model
                        box.setFromObject(currentModel);
                        box.getCenter(center);
                        currentModel.position.sub(center);

                        // Create a pivot group for proper rotation around center
                        pivotGroup = new THREE.Group();
                        pivotGroup.add(currentModel);
                        scene.add(pivotGroup);

                        // Enable shadows
                        currentModel.traverse(function(child) {{
                            if (child.isMesh) {{
                                child.castShadow = true;
                                child.receiveShadow = true;
                            }}
                        }});

                        // Hide loading indicator - force it to hide
                        const loadingIndicator = document.getElementById('model-loading-{bbl}');
                        if (loadingIndicator) {{
                            loadingIndicator.style.display = 'none';
                            loadingIndicator.remove(); // Remove it completely
                        }}

                        // Store references for cleanup
                        containerEl._scene = scene;
                        containerEl._renderer = renderer;
                        containerEl._camera = camera;
                        containerEl._controls = controls;
                        containerEl._model = currentModel;
                        containerEl._handleResize = function() {{
                            camera.aspect = containerEl.clientWidth / containerEl.clientHeight;
                            camera.updateProjectionMatrix();
                            renderer.setSize(containerEl.clientWidth, containerEl.clientHeight);
                        }};

                        // Force resize after short delay to ensure container is visible
                        setTimeout(() => {{
                            if (containerEl.clientWidth > 0 && containerEl.clientHeight > 0) {{
                                containerEl._handleResize();
                            }}
                        }}, 100);
                    }},
                    function(xhr) {{
                        // Enhanced progress callback with visual feedback
                        if (xhr.total && xhr.total > 0) {{
                            const percentComplete = (xhr.loaded / xhr.total) * 100;
                            const roundedPercent = Math.round(percentComplete);

                            // Throttle progress updates to avoid excessive DOM updates
                            const now = Date.now();
                            if (now - lastProgressUpdate > 100 || percentComplete >= 100) {{
                                lastProgressUpdate = now;

                                const progressBar = document.getElementById('progress-bar-{bbl}');
                                const progressText = document.getElementById('progress-text-{bbl}');

                                if (progressBar) {{
                                    progressBar.style.width = roundedPercent + '%';
                                }}
                                if (progressText) {{
                                    progressText.textContent = roundedPercent + '%';
                                }}

                                // If at 100%, show finalizing message
                                if (percentComplete >= 100 && loadingEl) {{
                                    const progressContainer = loadingEl.querySelector('div:first-child');
                                    if (progressContainer) {{
                                        progressContainer.textContent = 'Processing model...';
                                    }}
                                }}
                            }}
                        }} else {{
                            // If total is not available, show indeterminate progress
                            const progressBar = document.getElementById('progress-bar-{bbl}');
                            if (progressBar && !progressBar.classList.contains('indeterminate')) {{
                                progressBar.classList.add('indeterminate');
                                progressBar.style.width = '30%';
                                progressBar.style.animation = 'indeterminate 1.5s infinite';
                            }}
                        }}
                    }},
                    function(error) {{
                        // Use the centralized error handler
                        handleLoadError(error);
                    }}
                );

                // Animation loop
                function animate() {{
                    requestAnimationFrame(animate);

                    // Auto-rotate the pivot group (not the model directly)
                    if (isAutoRotating && pivotGroup) {{
                        pivotGroup.rotation.y += rotationSpeed;
                    }}

                    controls.update();
                    renderer.render(scene, camera);
                }}
                animate();

                // Handle window resize
                function handleResize() {{
                    camera.aspect = containerEl.clientWidth / containerEl.clientHeight;
                    camera.updateProjectionMatrix();
                    renderer.setSize(containerEl.clientWidth, containerEl.clientHeight);
                }}
                window.addEventListener('resize', handleResize);

                // Store cleanup function
                containerEl._cleanup = function() {{
                    window.removeEventListener('resize', handleResize);
                    if (currentModel) {{
                        currentModel.traverse(function(child) {{
                            if (child.geometry) child.geometry.dispose();
                            if (child.material) {{
                                if (Array.isArray(child.material)) {{
                                    child.material.forEach(mat => mat.dispose());
                                }} else {{
                                    child.material.dispose();
                                }}
                            }}
                        }});
                    }}
                    renderer.dispose();
                    controls.dispose();
                }};
            }} catch (error) {{
                // Use the centralized error handler for initialization errors
                handleLoadError(error);
            }}
        }}

        // Smart loading: Load 3D model when carousel is visible or when user navigates to it
        if (has3D) {{
            let modelInitialized = false;

            // Function to check if 3D slide is currently active
            function is3DSlideActive() {{
                const carousel = document.getElementById('interactive-carousel-{bbl}');
                if (!carousel) return false;

                const slides = carousel.querySelectorAll('.carousel-slide');
                const modelSlide = carousel.querySelector('.carousel-slide[data-type="3d"]');
                if (!modelSlide) return false;

                // Check if the 3D slide is the first one (index 0)
                return slides[0] === modelSlide && (!window.interactiveCarouselIndex || window.interactiveCarouselIndex['{bbl}'] === 0);
            }}

            // Initialize model when appropriate
            function initializeWhenReady() {{
                if (!modelInitialized) {{
                    // Check if 3D slide is currently visible
                    if (is3DSlideActive()) {{
                        console.log('3D slide is active, initializing model for {bbl}');
                        window.init3DModel{bbl}();
                        modelInitialized = true;
                    }} else {{
                        // If not visible, wait for carousel navigation
                        console.log('3D slide not active, waiting for navigation for {bbl}');
                    }}
                }}
            }}

            // Start loading based on DOM state
            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', initializeWhenReady);
            }} else {{
                // Small delay to ensure carousel is properly initialized
                setTimeout(initializeWhenReady, 100);
            }}

            // Also initialize when user navigates to 3D slide
            const originalMoveInteractiveCarousel = window.moveInteractiveCarousel;
            window.moveInteractiveCarousel = function(bbl, direction) {{
                if (originalMoveInteractiveCarousel) {{
                    originalMoveInteractiveCarousel(bbl, direction);
                }}

                // Check if we're now on the 3D slide
                if (!modelInitialized && bbl === '{bbl}') {{
                    const currentIndex = window.interactiveCarouselIndex ? window.interactiveCarouselIndex['{bbl}'] || 0 : 0;
                    if (currentIndex === 0 && has3D) {{
                        console.log('Navigated to 3D slide, initializing model for {bbl}');
                        window.init3DModel{bbl}();
                        modelInitialized = true;
                    }}
                }}
            }};
        }}
        
    }});
    
    // sortTenantTable already defined in first script block
    
    </script>
    
    </div><!-- End of container -->
    
    <div style="text-align: center; color: black; font-size: 14px; padding: 20px 0; font-family: 'Inter', sans-serif; border: none !important; box-shadow: none !important; background: transparent;">
        Build: {datetime.now(pytz.timezone('America/Mexico_City')).strftime('%-d %b %Y %I:%M:%S %p CST')}{' | ' + sys.argv[1] if len(sys.argv) > 1 else ''}
        <div style="margin-top: 10px;">
            <a href="https://docs.google.com/spreadsheets/d/1efvF54Fy_155wnrN0lcAUJhCPoosX9bAHzt-W1HDRBI/edit?gid=0#gid=0" target="_blank" style="color: #0066cc; text-decoration: none; margin: 0 10px;">Report an issue</a> |
            <a href="https://docs.google.com/spreadsheets/d/1efvF54Fy_155wnrN0lcAUJhCPoosX9bAHzt-W1HDRBI/edit?gid=2092445270#gid=2092445270" target="_blank" style="color: #0066cc; text-decoration: none; margin: 0 10px;">Request a feature</a>
        </div>
    </div>

    <script>
    // Section collapse functionality
    document.addEventListener('DOMContentLoaded', function() {{
        // Add collapse arrows to all L1 sections except Financial Impact
        const allSectionHeaders = document.querySelectorAll('.section-header');

        allSectionHeaders.forEach(function(header) {{
            // Skip Financial Impact section (no collapse needed)
            if (header.textContent.includes('Financial Impact')) {{
                return;
            }}

            // Add arrows to all sections (except Financial Impact)
                // Create blue triangle arrow (pure CSS)
                const arrow = document.createElement('div');
                // All sections start collapsed
                arrow.className = 'collapse-arrow collapsed';

                // Add arrow to header
                header.style.position = 'relative';
                header.appendChild(arrow);

                // A11y + keyboard support
                header.setAttribute('role', 'button');
                header.setAttribute('tabindex', '0');
                header.setAttribute('aria-expanded', 'false');
                header.title = 'Click to expand/collapse';

                header.addEventListener('keydown', function(e) {{
                    if (e.key === 'Enter' || e.key === ' ') {{
                        e.preventDefault();
                        toggleSection(e);
                    }}
                }});

                // Initially hide all content
                const section = header.parentElement;
                const allContentElements = section.querySelectorAll('.page, div:not(.section-header):not(.collapse-arrow):not(.carousel-track)');

                // Collapse all sections
                section.classList.add('collapsed'); // Add collapsed class to section
                allContentElements.forEach(element => {{
                    element.setAttribute('data-original-display', element.style.display || 'block');
                    element.style.display = 'none';
                }});

                // Function to handle collapse/expand
                function toggleSection(event) {{
                    // Prevent event bubbling
                    event.stopPropagation();

                    const section = header.parentElement;
                    const allContentElements = section.querySelectorAll('.page, div:not(.section-header):not(.collapse-arrow):not(.carousel-track)');

                    if (allContentElements.length > 0) {{
                        const isCollapsed = arrow.classList.contains('collapsed');

                        // Update a11y state (we're about to flip from collapsed->expanded or vice versa)
                        header.setAttribute('aria-expanded', isCollapsed ? 'true' : 'false');

                        // Toggle ALL content elements
                        allContentElements.forEach(element => {{
                            if (isCollapsed) {{
                                element.style.display = element.getAttribute('data-original-display') || 'block';
                            }} else {{
                                element.setAttribute('data-original-display', element.style.display || 'block');
                                element.style.display = 'none';
                            }}
                        }});

                        // Hide all tooltips when expanding section
                        if (isCollapsed) {{
                            const tooltipContents = section.querySelectorAll('.info-tooltip-content');
                            tooltipContents.forEach(content => {{
                                content.style.display = 'none';
                            }});
                        }}

                        // Update arrow state and section collapsed class
                        arrow.classList.toggle('collapsed');
                        section.classList.toggle('collapsed');
                    }}
                }}

                // Add click handler to entire header (not just arrow)
                header.addEventListener('click', toggleSection);
        }});
    }});

    // Tooltip functionality for data-tooltip attributes
    document.addEventListener('DOMContentLoaded', function() {{
        const tooltips = document.querySelectorAll('.info-tooltip[data-tooltip]');
        
        tooltips.forEach(tooltip => {{
            // Create tooltip content element
            const content = document.createElement('div');
            content.className = 'info-tooltip-content';
            content.textContent = tooltip.getAttribute('data-tooltip');
            tooltip.appendChild(content);
            
            // Show on hover
            tooltip.addEventListener('mouseenter', function() {{
                // First show the tooltip to get accurate positioning
                content.style.display = 'block';
                
                // Only adjust positioning if parent section is visible
                const parentSection = tooltip.closest('.section');
                if (parentSection && parentSection.offsetHeight > 0) {{
                    const rect = content.getBoundingClientRect();
                    // Check if tooltip goes off right edge
                    if (rect.right > window.innerWidth) {{
                        content.style.left = 'auto';
                        content.style.right = '0';
                    }}
                    // Check if tooltip goes off bottom
                    if (rect.bottom > window.innerHeight) {{
                        content.style.top = 'auto';
                        content.style.bottom = '125%';
                    }}
                }}
            }});
            
            // Hide on mouse leave
            tooltip.addEventListener('mouseleave', function() {{
                content.style.display = 'none';
                // Reset positioning for next time
                content.style.left = '0';
                content.style.right = 'auto';
                content.style.top = '125%';
                content.style.bottom = 'auto';
            }});
        }});
    }});

    // Simple headline deduplication - hide exact duplicate headlines on page load
    document.addEventListener('DOMContentLoaded', function() {{
        const headlines = document.querySelectorAll('.title');
        const seenHeadlines = new Set();
        
        headlines.forEach(function(headline) {{
            const headlineText = headline.textContent.trim();
            
            if (seenHeadlines.has(headlineText)) {{
                // Hide the duplicate headline's entire news card
                const newsCard = headline.closest('.card');
                if (newsCard) {{
                    newsCard.style.display = 'none';
                }}
            }} else {{
                seenHeadlines.add(headlineText);
            }}
        }});
    }});
{ll97_chart_js}
    </script>
</body>
</html>
"""
    
            # Save to the correct output directory
            output_dir = output_dir_override if output_dir_override else "/Users/forrestmiller/Desktop/New"
            filename = f"NYC_{bbl}.html" if output_dir_override else f"{bbl}.html"
            output_path = f"{output_dir}/{filename}"
            with open(output_path, 'w') as f:
                f.write(html)
            
            # Print every building for live progress
            print(f"✓ {count}/{len(scoring)} NYC_{bbl}", flush=True)
    
    except KeyError as e:
        print(f"⚠️  Missing column for {bbl}: {e}")
        continue
    except Exception as e:
        print(f"❌ Error processing {bbl}: {e}")
        import traceback
        traceback.print_exc()
        continue

print("✓ All building pages done!")

# Skip portfolio analysis if only generating single building
if len(sys.argv) > 1:
    sys.exit(0)

# Print PM2.5 cache statistics
total_buildings = len(scoring)
api_calls_made = len(PM25_CACHE)
api_calls_saved = total_buildings - api_calls_made
if api_calls_saved > 0:
    print(f"\n📊 PM2.5 API Efficiency:")
    print(f"   • Total buildings: {total_buildings}")
    print(f"   • API calls made: {api_calls_made}")
    print(f"   • API calls saved by proximity caching: {api_calls_saved}")
    print(f"   • Savings: {(api_calls_saved/total_buildings*100):.1f}%")

# Generate portfolio summary data
portfolio_data = []
for i, row in scoring.iterrows():
    bbl = row['bbl']

    # Get address from all_building_addresses.csv
    address_row = addresses[addresses['bbl'] == bbl]
    address = address_row['address_from_bbl'].iloc[0] if not address_row.empty else row['address']

    # Get the pre-calculated data
    hvac_data = hvac[hvac['bbl'] == bbl]
    office_data = office[office['bbl'] == bbl]
    
    if not hvac_data.empty and not office_data.empty:
        # Calculate total office HVAC cost
        total_hvac_cost = 0
        for m in months:
            elec_cost = float(office_data[f'Office_Elec_Cost_Current_{m}_USD'].iloc[0]) if f'Office_Elec_Cost_Current_{m}_USD' in office_data.columns and not office_data[f'Office_Elec_Cost_Current_{m}_USD'].isna().all() else 0
            gas_cost = float(office_data[f'Office_Gas_Cost_Current_{m}_USD'].iloc[0]) if f'Office_Gas_Cost_Current_{m}_USD' in office_data.columns and not office_data[f'Office_Gas_Cost_Current_{m}_USD'].isna().all() else 0
            steam_cost = float(office_data[f'Office_Steam_Cost_Current_{m}_USD'].iloc[0]) if f'Office_Steam_Cost_Current_{m}_USD' in office_data.columns and not office_data[f'Office_Steam_Cost_Current_{m}_USD'].isna().all() else 0
            hvac_pct_val = float(hvac_data[f'Elec_HVAC_{m}_2023_Pct'].iloc[0]) if f'Elec_HVAC_{m}_2023_Pct' in hvac_data.columns and not hvac_data[f'Elec_HVAC_{m}_2023_Pct'].isna().all() else 0
            
            total_hvac_cost += elec_cost * hvac_pct_val + gas_cost * 0.9 + steam_cost * 0.9
        
        odcv_savings = float(row['utility_savings_annual'])
        percentage = min(40.0, (odcv_savings / total_hvac_cost * 100)) if total_hvac_cost > 0 else 0
        
        # Handle address that might be NaN/float
        if isinstance(address, str):
            address_clean = address.split(',')[0]  # Just street address
        else:
            address_clean = 'Address not available'

        portfolio_data.append({
            'bbl': bbl,
            'address': address_clean,
            'percentage': percentage,
            'savings': odcv_savings,
            'hvac_cost': total_hvac_cost
        })

# Sort by percentage descending
portfolio_data.sort(key=lambda x: x['percentage'], reverse=True)

# Save to CSV for reference in data directory
import csv
portfolio_csv_path = data_path + 'portfolio_odcv_percentages.csv'
with open(portfolio_csv_path, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['bbl', 'address', 'percentage', 'savings', 'hvac_cost'])
    writer.writeheader()
    writer.writerows(portfolio_data)

print(f"✓ Portfolio analysis saved: Top building saves {portfolio_data[0]['percentage']:.1f}% of HVAC costs")

# Generate portfolio visualization HTML
portfolio_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Portfolio ODCV Savings Analysis</title>
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
</head>
<body>
    <h1>ODCV Savings as % of HVAC Costs - Portfolio View</h1>
    <div id="portfolio_chart" style="width: 100%; height: 600px;"></div>
    <script>
        const data = {json.dumps(portfolio_data[:20])};  // Top 20 buildings
        
        const trace = {{
            x: data.map(d => d.address),
            y: data.map(d => d.percentage),
            type: 'bar',
            marker: {{
                color: data.map(d => d.percentage > 15 ? '#38a169' : d.percentage > 10 ? '#ffc107' : '#0066cc')
            }},
            text: data.map(d => d.percentage.toFixed(1) + '%'),
            textposition: 'outside',
            hovertemplate: '%{{x}}<br>Saves %{{y:.1f}}% of HVAC costs<br>$%{{customdata:,.0f}} annual savings<extra></extra>',
            customdata: data.map(d => d.savings)
        }};
        
        Plotly.newPlot('portfolio_chart', [trace], {{
            title: 'Top 20 Buildings by ODCV Savings Percentage',
            yaxis: {{title: '% of HVAC Costs Saved', range: [0, Math.max(...data.map(d => d.percentage)) * 1.2]}},
            xaxis: {{tickangle: -45}},
            margin: {{b: 150}}
        }});
    </script>
</body>
</html>"""

portfolio_html_path = os.path.join(os.path.dirname(data_path), 'portfolio_odcv_analysis.html')
with open(portfolio_html_path, 'w') as f:
    f.write(portfolio_html)