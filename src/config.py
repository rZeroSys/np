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
BUILDINGS_TAB_DATA_PATH = SOURCE_DATA_DIR / 'portfolio_data.csv'
PORTFOLIO_ORGS_PATH = SOURCE_DATA_DIR / 'portfolio_organizations.csv'
LOGO_BACKGROUNDS_PATH = SOURCE_DATA_DIR / 'logo_backgrounds.csv'

# =============================================================================
# OUTPUT PATHS
# =============================================================================

OUTPUT_DIR = PROJECT_ROOT / 'output'
HTML_OUTPUT_DIR = OUTPUT_DIR / 'html'
BUILDINGS_OUTPUT_DIR = HTML_OUTPUT_DIR / 'buildings'
DATA_OUTPUT_DIR = OUTPUT_DIR / 'data'
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
# AWS S3 CONFIGURATION
# =============================================================================

AWS_BUCKET = 'nationwide-odcv-images'
AWS_REGION = 'us-east-2'
AWS_BASE_URL = f'https://{AWS_BUCKET}.s3.{AWS_REGION}.amazonaws.com'
AWS_LOGOS_PREFIX = 'logos/'
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

# =============================================================================
# LEGACY PATH MAPPING (for reference during migration)
# =============================================================================

LEGACY_PATHS = {
    'BUILDING_DATA': '/Users/forrestmiller/Desktop/nationwide propector/FINAL FILE/ANALYSIS STEP II merged_property_matches_updated.csv',
    'PORTFOLIO_ORGS': '/Users/forrestmiller/Desktop/nationwide propector/FINAL FILE/portfolio_organizations.csv',
    'LOGO_BACKGROUNDS': '/Users/forrestmiller/Desktop/nationwide propector/logo_backgrounds.csv',
    'IMAGES': '/Users/forrestmiller/Desktop/nationwide propector/good images',
    'LOGOS': '/Users/forrestmiller/Desktop/nationwide propector/Logos',
    'BUILDINGS_OUTPUT': '/Users/forrestmiller/Desktop/nationwide propector/buildings/',
    'INDEX_HTML': '/Users/forrestmiller/Desktop/nationwide propector/nationwide_index.html',
}
