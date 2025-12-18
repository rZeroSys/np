"""
Centralized configuration for Nationwide Prospector
====================================================
All file paths and configuration settings in one place.
"""

from pathlib import Path

# =============================================================================
# PROJECT ROOT
# =============================================================================

PROJECT_ROOT = Path(__file__).parent.parent

# =============================================================================
# INPUT DATA PATHS
# =============================================================================

DATA_DIR = PROJECT_ROOT / 'data'
SOURCE_DATA_DIR = DATA_DIR / 'source'

BUILDING_DATA_PATH = SOURCE_DATA_DIR / 'portfolio_data.csv'
PORTFOLIO_DATA_PATH = SOURCE_DATA_DIR / 'portfolio_data.csv'
PORTFOLIO_ORGS_PATH = SOURCE_DATA_DIR / 'portfolio_organizations.csv'

# =============================================================================
# OUTPUT PATHS
# =============================================================================

OUTPUT_DIR = PROJECT_ROOT / 'output'
HTML_OUTPUT_DIR = OUTPUT_DIR / 'html'
BUILDINGS_OUTPUT_DIR = HTML_OUTPUT_DIR / 'buildings'
DATA_OUTPUT_DIR = HTML_OUTPUT_DIR / 'data'
PORTFOLIOS_OUTPUT_DIR = DATA_OUTPUT_DIR / 'portfolios'

# Output files
INDEX_HTML_PATH = HTML_OUTPUT_DIR / 'index.html'
BUILDING_DATA_JS_PATH = DATA_OUTPUT_DIR / 'building_data.js'
EXPORT_DATA_JS_PATH = DATA_OUTPUT_DIR / 'export_data.js'
MAP_DATA_JS_PATH = DATA_OUTPUT_DIR / 'map_data.js'
PORTFOLIO_BUILDINGS_JS_PATH = DATA_OUTPUT_DIR / 'portfolio_buildings.js'
PORTFOLIO_CARDS_JS_PATH = DATA_OUTPUT_DIR / 'portfolio_cards.js'
ALL_BUILDINGS_JSON_PATH = DATA_OUTPUT_DIR / 'all_buildings.json'
SUMMARY_JSON_PATH = DATA_OUTPUT_DIR / 'summary.json'
MAP_MARKERS_JSON_PATH = DATA_OUTPUT_DIR / 'map_markers.json'

# =============================================================================
# ASSET PATHS
# =============================================================================

ASSETS_DIR = PROJECT_ROOT / 'assets'
IMAGES_DIR = ASSETS_DIR / 'images'
THUMBNAILS_DIR = ASSETS_DIR / 'thumbnails'
LOGOS_DIR = ASSETS_DIR / 'logos'

# =============================================================================
# STAGING PATHS
# =============================================================================

STAGING_DIR = PROJECT_ROOT / 'staging'
MISSING_IMAGES_DIR = STAGING_DIR / 'missing_images'

# =============================================================================
# BACKUP PATHS
# =============================================================================

BACKUP_DIR = PROJECT_ROOT / 'BACKUPS_GO_HERE' / 'csv_backups'

# =============================================================================
# CBECS DATA
# =============================================================================

CBECS_DIR = DATA_DIR / 'cbecs'
CBECS_DATA_PATH = CBECS_DIR / 'cbecs2018_final_public.csv'

# =============================================================================
# DERIVED DATA FILES
# =============================================================================

EUI_POST_ODCV_PATH = SOURCE_DATA_DIR / 'eui_post_odcv.csv'
LEED_MATCHES_PATH = SOURCE_DATA_DIR / 'leed_matches.csv'

# =============================================================================
# NYC DATA (External location - special building reports)
# These files live outside the project. Update this path if you move them.
# =============================================================================

NYC_DATA_DIR = Path('/Users/forrestmiller/Desktop/New/data')
NYC_SCRIPTS_DIR = Path('/Users/forrestmiller/Desktop/New/Scripts')

# NYC source files
NYC_10YR_SAVINGS_PATH = NYC_DATA_DIR / '10_year_savings_by_building.csv'
NYC_BUILDINGS_PATH = NYC_DATA_DIR / 'buildings_BIG_with_emails_complete_verified.csv'
NYC_ENERGY_PATH = NYC_DATA_DIR / 'energy_BIG.csv'
NYC_ADDRESSES_PATH = NYC_DATA_DIR / 'all_building_addresses.csv'
NYC_BUILDING_LINKS_PATH = NYC_DATA_DIR / 'TOP_250_BUILDING_LINKS_VALID.csv'
NYC_SCORING_PATH = NYC_DATA_DIR / 'odcv_scoring_CORRECTED.csv'
NYC_HVAC_PATH = NYC_DATA_DIR / 'hvac_office_energy_BIG.csv'
NYC_OFFICE_PATH = NYC_DATA_DIR / 'office_energy_BIG.csv'
NYC_VALUATION_PATH = NYC_DATA_DIR / 'odcv_noi_value_impact_analysis.csv'

# NYC building report script
NYC_BUILDING_SCRIPT = NYC_SCRIPTS_DIR / 'building.py'

# =============================================================================
# AWS S3 CONFIGURATION
# =============================================================================

AWS_BUCKET = 'nationwide-odcv-images'
AWS_REGION = 'us-east-2'
AWS_BASE_URL = f'https://{AWS_BUCKET}.s3.{AWS_REGION}.amazonaws.com'
AWS_LOGOS_PREFIX = 'logos/'
AWS_LOGO_THUMBNAILS_PREFIX = 'logo-thumbnails/'
AWS_IMAGES_PREFIX = 'images/'

# S3 URL patterns
def get_logo_url(filename: str) -> str:
    """Get the S3 URL for a logo file."""
    return f'{AWS_BASE_URL}/{AWS_LOGOS_PREFIX}{filename}'

def get_image_url(filename: str) -> str:
    """Get the S3 URL for an image file."""
    return f'{AWS_BASE_URL}/{AWS_IMAGES_PREFIX}{filename}'

# =============================================================================
# UPLOAD SETTINGS
# =============================================================================

MAX_UPLOAD_WORKERS = 20

