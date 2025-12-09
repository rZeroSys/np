"""
HTML Generator for Nationwide ODCV Prospector Homepage
=======================================================
Generates the complete HTML page with:
- Portfolio Tab: Expandable portfolio cards ranked by OpEx savings
- Building Search Tab: Address search with map
- Vertical toggle filtering
- R-Zero Google authentication
- Auto-backup enabled via Claude Code hooks
"""

import json
import csv
import os
import re
import statistics
from datetime import datetime
import pytz
from html import escape
from src.data.helpers import (
    attr_escape, js_escape, safe_float, safe_int,
    format_currency, format_number, format_sqft, format_carbon,
    slugify, vertical_color, building_type_icon
)
from src.config import LOGO_BACKGROUNDS_PATH

# =============================================================================
# LOGO BACKGROUND CONFIG - loaded from CSV
# =============================================================================

def load_logo_backgrounds():
    """Load logo background requirements from CSV file."""
    csv_path = str(LOGO_BACKGROUNDS_PATH)
    dark_bg_logos = set()

    if os.path.exists(csv_path):
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('background_needed') == 'dark':
                    dark_bg_logos.add(row['filename'])

    return dark_bg_logos

def strip_acronym(name):
    """Remove trailing acronym in parentheses from org name for display."""
    # Match pattern like " (CBRE)" or " (GSA)" at end of string
    return re.sub(r'\s*\([A-Z]+\)\s*$', '', name)

def eui_rating(eui, benchmark):
    """Return full EUI display with number and rating, all in the rating color."""
    if eui is None or benchmark is None or benchmark == 0:
        return f'{eui:.0f}' if eui else ''
    ratio = eui / benchmark
    if ratio <= 1.0:
        return f'<span class="eui-good">{eui:.0f} (Good)</span>'
    elif ratio <= 1.2:
        return f'<span class="eui-ok">{eui:.0f} (OK)</span>'
    else:
        return f'<span class="eui-bad">{eui:.0f} (Bad)</span>'

def savings_color(amount):
    """Return green color based on savings amount - darker = more savings."""
    if amount is None:
        return '#22c55e'  # default medium green
    if amount >= 500000:
        return '#166534'  # dark green
    elif amount >= 100000:
        return '#22c55e'  # medium green
    else:
        return '#4ade80'  # light green

# Load from CSV on module import
WHITE_LOGOS = load_logo_backgrounds()

class NationwideHTMLGenerator:
    """Generates the Nationwide ODCV Prospector HTML page."""

    def __init__(self, config, data):
        """
        Initialize the generator.

        Args:
            config: dict with keys:
                - aws_bucket: S3 bucket URL
                - mapbox_token: Mapbox API token
                - google_api_key: Google API key
                - firebase_config: Firebase configuration
            data: dict from load_all_data() with keys:
                - portfolios: List of portfolio dicts
                - all_buildings: List of building dicts
                - stats: Statistics dict
                - image_map: Image lookup
                - coords_map: Coordinates lookup
        """
        self.config = config
        self.data = data
        self.stats = data['stats']
        self.portfolios = data['portfolios']
        self.all_buildings = data['all_buildings']
        self.logo_mappings = data.get('logo_mappings', {})

    def _get_display_name(self, b):
        """Get clean display name for building."""
        import math
        def safe_str(val):
            """Convert value to string, handling NaN/None."""
            if val is None:
                return ''
            if isinstance(val, float) and math.isnan(val):
                return ''
            return str(val).strip()

        tenant_sub_org = safe_str(b.get('tenant_sub_org'))
        tenant = safe_str(b.get('tenant'))
        property_name = safe_str(b.get('property_name'))

        def clean(s):
            """Strip trailing punct, (R), (TM), and normalize."""
            s = re.sub(r'\s*\((R|TM)\)\s*', '', s)  # Remove trademark
            s = re.sub(r'[.,;:]+$', '', s)  # Remove trailing punct
            return s.strip()

        # Priority 1: tenant_sub_org
        if tenant_sub_org:
            cleaned_sub = clean(tenant_sub_org)
            # If too short (like "W"), use property_name if available
            if len(cleaned_sub) <= 2 and property_name:
                return clean(property_name)
            return cleaned_sub

        # Strip parens from tenant for base comparison
        # "University Of Chicago (UChicago)" → "University Of Chicago"
        base_tenant = re.sub(r'\s*\([^)]+\)\s*$', '', tenant).strip()

        # If tenant too short (<=2 chars), prefer property_name
        if len(base_tenant) <= 2 and property_name:
            return clean(property_name)

        # If both exist, avoid redundancy
        if base_tenant and property_name:
            base_lower = base_tenant.lower()
            p_lower = property_name.lower()

            # If identical or contained, use the more specific one
            if base_lower == p_lower:
                return clean(base_tenant)
            if base_lower in p_lower:
                return clean(property_name)

            # If any word (>3 chars) from tenant in property_name, use property_name
            words = [w for w in re.split(r'\W+', base_lower) if len(w) > 3]
            if any(w in p_lower for w in words):
                return clean(property_name)

            # Just show property name
            return clean(property_name)

        return clean(base_tenant or property_name)

    def _get_org_display_name(self, org_name):
        """Get display name for an organization, fallback to org_name."""
        if not org_name:
            return ''
        info = self.logo_mappings.get(org_name, {})
        return info.get('display_name', org_name)

    def generate(self):
        """Generate the complete HTML page and external data files."""
        # Generate data files (external JS)
        data_files = self._generate_data_files()

        # Generate HTML (without embedded data)
        html = '\n'.join([
            self._generate_head(),
            self._generate_body_start(),
            self._generate_header(),
            self._generate_portfolio_section(),
            self._generate_all_buildings_section(),
            self._generate_map_panel(),
            self._generate_scripts(),
            self._generate_body_end()
        ])

        return html, data_files

    def _generate_data_files(self):
        """Generate external JS data files."""
        # Portfolio buildings - for expanding portfolios
        portfolio_buildings = {
            i: [{
                'id': b.get('building_id', ''),
                'url': b.get('building_url', ''),
                'address': b.get('address', ''),
                'city': b.get('city', ''),
                'state': b.get('state', ''),
                'property_name': self._get_display_name(b),
                'type': b.get('radio_type') or b.get('building_type', ''),
                'vertical': b.get('vertical', ''),
                'sqft': b.get('sqft', 0) or 0,
                'opex': b.get('total_opex', 0) or 0,
                'valuation': b.get('valuation_impact', 0) or 0,
                'carbon': b.get('carbon_reduction', 0) or 0,
                'eui': b.get('site_eui', 0) or 0,
                'eui_benchmark': b.get('eui_benchmark', 0) or 0,
                'image': b.get('image', ''),
            } for b in p['buildings']] for i, p in enumerate(self.portfolios)
        }

        # Map data - for map tab
        map_data = [{
            'id': b['id'],
            'lat': b['lat'],
            'lon': b['lon'],
            'address': b['address'],
            'city': b['city'],
            'state': b['state'],
            'type': b.get('radio_type') or b['type'],
            'vertical': b['vertical'],
            'total_opex': b['total_opex'],
            'image': b['image']
        } for b in self.all_buildings if b['lat'] and b['lon']]

        # Export data - all buildings with full details for CSV export and All Buildings tab
        export_data = [{
            'id': b.get('id', ''),
            'url': b.get('url', ''),
            'address': b.get('address', ''),
            'city': b.get('city', ''),
            'state': b.get('state', ''),
            'property_name': self._get_display_name(b),
            'type': b.get('radio_type') or b.get('building_type', ''),
            'owner': self._get_org_display_name(b.get('owner', '')),
            'tenant': self._get_org_display_name(b.get('tenant', '')),
            'property_manager': self._get_org_display_name(b.get('manager', '')),
            'sqft': b.get('sqft', 0) or 0,
            'year_built': b.get('year_built', ''),
            'opex': b.get('total_opex', 0) or 0,
            'valuation': b.get('valuation_impact', 0) or 0,
            'carbon': b.get('carbon_reduction', 0) or 0,
            'site_eui': b.get('site_eui', 0) or 0,
            'eui_benchmark': b.get('eui_benchmark', 0) or 0,
            'vertical': b.get('vertical', ''),
            'image': b.get('image', '')
        } for b in sorted(self.all_buildings, key=lambda x: x.get('total_opex', 0) or 0, reverse=True)]

        # Portfolio card data - for rendering cards on scroll
        # Calculate total sqft for each portfolio
        portfolio_cards = []
        for i, p in enumerate(self.portfolios):
            total_sqft = sum(b.get('sqft', 0) or 0 for b in p['buildings'])
            portfolio_cards.append({
                'idx': i,
                'org_name': p['org_name'],
                'display_name': p.get('display_name', p['org_name']),
                'logo_file': p.get('logo_file', ''),
                'aws_logo_url': p.get('aws_logo_url', ''),
                'is_white_logo': p.get('logo_file', '') in WHITE_LOGOS,
                'building_count': p['building_count'],
                'total_sqft': total_sqft,
                'median_eui': p.get('median_eui', 0) or 0,
                'median_eui_benchmark': p.get('median_eui_benchmark', 0) or 0,
                'total_valuation': p['total_valuation_impact'],
                'total_carbon': p['total_carbon_reduction'],
                'total_opex': p['total_opex_avoidance'],
                'classification': p.get('classification', ''),
                'verticals': list(p.get('verticals', [])),
                'tenants': p.get('tenants', []),
                'tenant_sub_orgs': p.get('tenant_sub_orgs', []),
                'owners': p.get('owners', []),
                'managers': p.get('managers', []),
            })

        return {
            'portfolio_buildings.js': f'const PORTFOLIO_BUILDINGS = {json.dumps(portfolio_buildings)};',
            'map_data.js': f'MAP_DATA = {json.dumps(map_data)};',
            'portfolio_cards.js': f'const PORTFOLIO_CARDS = {json.dumps(portfolio_cards)};',
            'export_data.js': f'EXPORT_DATA = {json.dumps(export_data)};',
        }

    # =========================================================================
    # HEAD SECTION
    # =========================================================================

    def _generate_head(self):
        """Generate HTML head with styles and dependencies."""
        timestamp = datetime.now(pytz.timezone('America/New_York')).strftime('%Y-%m-%d %H:%M:%S EST')

        return f'''<!DOCTYPE html>
<!-- Nationwide ODCV Prospector - Generated: {timestamp} -->
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nationwide ODCV Prospector | R-Zero</title>
    <link rel="icon" type="image/png" href="https://rzero.com/wp-content/themes/rzero/build/images/favicons/favicon.png">

    <!-- Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">

    <!-- Mapbox -->
    <link href="https://api.mapbox.com/mapbox-gl-js/v3.3.0/mapbox-gl.css" rel="stylesheet">
    <script src="https://api.mapbox.com/mapbox-gl-js/v3.3.0/mapbox-gl.js"></script>

    <script>
function initMap() {{
    window.__googleMapsReady = true;
    // Retry until setupAddressSearch is available (it's defined in body)
    function trySetup() {{
        if (typeof setupAddressSearch === 'function') {{
            setupAddressSearch();
        }} else {{
            setTimeout(trySetup, 50);
        }}
    }}
    trySetup();
}}
</script>
    <script src="https://maps.googleapis.com/maps/api/js?key={self.config['google_api_key']}&libraries=places&callback=initMap" async defer></script>

    {self._generate_styles()}
</head>'''

    def _generate_styles(self):
        """Generate CSS styles."""
        return '''<style>
/* Make Google Places dropdown appear correctly */
.pac-container {
    z-index: 10000 !important;
}

:root {
    --primary: #0066cc;
    --primary-dark: #0052a3;
    --mid-blue: #1b95ff;
    --light-blue: #f0f7fa;
    --success: #16a34a;
    --danger: #dc2626;
    --gray-50: #f9fafb;
    --gray-100: #f3f4f6;
    --gray-200: #e5e7eb;
    --gray-300: #d1d5db;
    --gray-400: #9ca3af;
    --gray-500: #6b7280;
    --gray-600: #4b5563;
    --gray-700: #374151;
    --gray-800: #1f2937;
    --gray-900: #111827;
    --rzero-blue: #0066cc;
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--gray-50);
    color: var(--gray-900);
    line-height: 1.5;
    overflow-x: hidden;
}

/* VERTICAL FILTER BAR - horizontal bar below header */
.vertical-filter-bar {
    position: fixed;
    top: 133px;
    left: 0;
    right: 0;
    background: white;
    border-bottom: 1px solid #ccc;
    padding: 15px 32px;
    z-index: 1000;
}

.vertical-filter-inner {
    max-width: 1272px;
    margin: 0 auto;
    display: flex;
    gap: 10px;
    align-items: center;
    padding: 0;
}

.vertical-btn {
    padding: 10px 20px;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    border: none;
    color: white;
}

.vertical-btn.selected, .building-type-btn.selected {
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}
.building-type-btn.selected {
    outline: 3px solid #FFD700;
    outline-offset: 2px;
    box-shadow: 0 0 12px rgba(255, 215, 0, 0.5);
}
.vertical-btn .btn-x {
    display: none;
    margin-left: 6px;
    font-weight: bold;
    opacity: 0.7;
}
.vertical-btn .btn-x:hover {
    opacity: 1;
}
.vertical-btn.selected .btn-x {
    display: inline;
}

/* Building type filter chip */
.building-type-chip {
    display: none;
    background: #e5e7eb;
    color: #374151;
    padding: 6px 12px 6px 8px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    align-items: center;
    gap: 6px;
    margin-left: 12px;
}
.building-type-chip.visible {
    display: flex;
}
.building-type-chip .chip-x {
    cursor: pointer;
    font-size: 14px;
    font-weight: bold;
    color: #6b7280;
    line-height: 1;
}
.building-type-chip .chip-x:hover {
    color: #111827;
}

/* FILTER DRAWER - slides out from left */
.filter-drawer {
    position: fixed;
    top: 133px;
    left: 0;
    width: 300px;
    height: calc(100vh - 133px);
    background: #f5f5f5;
    z-index: 2000;
    transform: translateX(-100%);
    transition: transform 0.3s ease;
    box-shadow: 4px 0 20px rgba(0,0,0,0.1);
    overflow-y: auto;
    padding: 20px;
}

.filter-drawer.open {
    transform: translateX(0);
}

/* Filter drawer toggle button */
.filter-drawer-toggle {
    position: fixed;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    z-index: 1999;
    background: var(--rzero-blue);
    color: white;
    border: none;
    border-radius: 0 8px 8px 0;
    padding: 16px 10px;
    cursor: pointer;
    writing-mode: vertical-rl;
    text-orientation: mixed;
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 1px;
    box-shadow: 2px 0 8px rgba(0,0,0,0.15);
    transition: background 0.2s, padding-left 0.2s;
}

.filter-drawer-toggle:hover {
    background: #004499;
    padding-left: 14px;
}

.filter-drawer.open + .filter-drawer-toggle,
body.filter-drawer-open .filter-drawer-toggle {
    left: 300px;
}

.filter-drawer-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid #ddd;
}

.filter-drawer-close {
    background: none;
    border: none;
    font-size: 24px;
    cursor: pointer;
    color: #666;
    padding: 0 4px;
    line-height: 1;
}

.filter-drawer-close:hover {
    color: #333;
}

.sidebar-label {
    font-size: 12px;
    font-weight: 600;
    color: #555;
    margin-bottom: 12px;
    text-transform: uppercase;
}

/* Building type filter buttons - vertical list */
.building-type-filters {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.building-type-btn {
    padding: 10px 14px;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
    border: none;
    color: white;
    display: flex;
    justify-content: space-between;
}

.building-type-btn.hidden {
    display: none;
}

/* Header */
.header {
    background: linear-gradient(135deg, var(--rzero-blue) 0%, #004499 100%);
    color: white;
    padding: 24px 32px;
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 1001;
    max-height: 85px;
    overflow: visible;
}

.header-content {
    display: flex;
    align-items: center;
    width: 100%;
}

.header h1 {
    font-size: 20px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 12px;
    white-space: nowrap;
}

.header h1 img {
    height: 36px;
}

.header-subtitle {
    opacity: 0.9;
    font-size: 14px;
    margin-top: 4px;
}

.user-info {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 14px;
}

.user-info img {
    width: 32px;
    height: 32px;
    border-radius: 50%;
}

.logout-btn {
    background: rgba(255,255,255,0.2);
    border: none;
    color: white;
    padding: 6px 12px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
}

.logout-btn:hover {
    background: rgba(255,255,255,0.3);
}

/* Stats Cards */
.stats-section {
    background: white;
    border-bottom: 1px solid var(--gray-200);
    padding: 20px 32px;
}

.stats-grid {
    max-width: 1400px;
    margin: 0 auto;
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 16px;
}

.stat-card {
    background: var(--gray-50);
    border-radius: 12px;
    padding: 16px;
    text-align: center;
}

.stat-value {
    font-size: 28px;
    font-weight: 700;
    color: var(--rzero-blue);
}

.stat-label {
    font-size: 12px;
    color: var(--gray-500);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 4px;
}

/* Main Tabs */
.main-tabs {
    background: white;
    padding: 0 32px;
}

.tabs-container {
    max-width: 1400px;
    margin: 0 auto;
    display: flex;
    gap: 0;
}

.main-tab {
    padding: 14px 24px;
    border: none;
    background: none;
    font-size: 15px;
    font-weight: 600;
    color: var(--gray-500);
    cursor: pointer;
    border-bottom: 3px solid transparent;
    margin-bottom: -1px;
    transition: color 0.2s, border-color 0.2s;
}

.main-tab:hover {
    color: var(--gray-700);
}

.main-tab.active {
    color: var(--rzero-blue);
    border-bottom: 3px solid var(--rzero-blue);
}

/* Tab Content */
.tab-content {
    display: none;
    max-width: 1400px;
    margin: 0 auto;
    padding: 24px 32px;
}

.tab-content.active {
    display: block;
}

/* Hide sidebar/filters when All Buildings tab is active */
body.all-buildings-active .filter-drawer,
body.all-buildings-active .filter-drawer-toggle,
body.all-buildings-active .vertical-filter-bar {
    display: none !important;
}

body.all-buildings-active .portfolio-section {
    display: none !important;
}

body.all-buildings-active .main-tabs {
    left: 0 !important;
}

/* All Buildings Tab Styles */
.all-buildings-section {
    padding: 175px 32px 32px 32px;
    max-width: 1400px;
    margin: 0 auto;
}

.all-buildings-stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 20px;
    margin-bottom: 28px;
}

.ab-stat-card {
    background: white;
    border-radius: 12px;
    padding: 24px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    border: 1px solid var(--gray-200);
    border-left: 4px solid var(--rzero-blue);
    transition: transform 0.2s, box-shadow 0.2s;
}

.ab-stat-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}

.ab-stat-value {
    font-size: 32px;
    font-weight: 700;
    color: var(--rzero-blue);
    margin-bottom: 6px;
}

.ab-stat-value.green { color: var(--success); }

.ab-stat-label {
    font-size: 13px;
    color: var(--gray-500);
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}

.top-cities-section {
    margin-bottom: 24px;
}

.top-cities-header {
    font-size: 14px;
    font-weight: 600;
    color: var(--gray-700);
    margin-bottom: 12px;
}

.top-cities-grid {
    display: flex;
    gap: 12px;
    overflow-x: auto;
    padding-bottom: 8px;
}

.city-tile {
    flex: 0 0 180px;
    padding: 16px;
    background: white;
    border: 2px solid var(--gray-200);
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.2s;
}

.city-tile:hover {
    border-color: var(--rzero-blue);
    box-shadow: 0 4px 12px rgba(0, 102, 204, 0.15);
    transform: translateY(-2px);
}

.city-tile.selected {
    border-color: var(--rzero-blue);
    background: rgba(0, 102, 204, 0.08);
    box-shadow: 0 0 0 3px rgba(0, 102, 204, 0.2);
}

.city-name {
    font-size: 16px;
    font-weight: 600;
    color: var(--gray-900);
    margin-bottom: 6px;
}

.city-stats {
    font-size: 12px;
    color: var(--gray-500);
}

.city-opex {
    font-size: 15px;
    font-weight: 700;
    color: var(--success);
    margin-top: 6px;
}

.ab-filter-bar {
    display: flex;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
    padding: 16px 20px;
    background: var(--gray-50);
    border-radius: 12px;
    margin-bottom: 20px;
    border: 1px solid var(--gray-200);
}

.ab-filter-bar select {
    padding: 10px 14px;
    border: 1px solid var(--gray-300);
    border-radius: 8px;
    font-size: 14px;
    background: white;
    cursor: pointer;
    min-width: 150px;
    transition: border-color 0.2s, box-shadow 0.2s;
}

.ab-filter-bar select:focus {
    border-color: var(--rzero-blue);
    outline: none;
    box-shadow: 0 0 0 3px rgba(0, 102, 204, 0.15);
}

.ab-filter-bar input[type="text"] {
    padding: 10px 14px;
    border: 1px solid var(--gray-300);
    border-radius: 8px;
    font-size: 14px;
    min-width: 220px;
    background: white;
    transition: border-color 0.2s, box-shadow 0.2s;
}

.ab-filter-bar input[type="text"]:focus {
    border-color: var(--rzero-blue);
    outline: none;
    box-shadow: 0 0 0 3px rgba(0, 102, 204, 0.15);
}

.ab-clear-btn {
    padding: 10px 18px;
    background: white;
    border: 1px solid var(--gray-300);
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    color: var(--gray-600);
    transition: all 0.2s;
}

.ab-clear-btn:hover {
    background: var(--gray-100);
    border-color: var(--gray-400);
}

/* City Filter Section */
.city-filter-section {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 16px;
}

.city-filter-label {
    font-size: 12px;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 10px;
}

.city-filter-cards {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: center;
}

.city-filter-card {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: white;
    padding: 6px 12px;
    border-radius: 6px;
    border: 1px solid #cbd5e1;
    cursor: pointer;
    transition: all 0.15s;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

.city-filter-card:hover {
    background: #f1f5f9;
    border-color: #3b82f6;
    box-shadow: 0 2px 4px rgba(59,130,246,0.15);
}

.city-filter-card.selected {
    background: #dbeafe;
    border-color: #3b82f6;
    box-shadow: 0 0 0 2px rgba(59,130,246,0.2);
}

.city-filter-card strong {
    font-size: 13px;
    font-weight: 600;
    color: #1e293b;
}

.city-filter-card .city-count {
    font-size: 11px;
    color: #64748b;
    background: #f1f5f9;
    padding: 2px 6px;
    border-radius: 4px;
}

.city-filter-card.selected .city-count {
    background: #bfdbfe;
    color: #1e40af;
}

.city-filter-card .city-opex {
    font-size: 12px;
    color: #059669;
    font-weight: 600;
}


/* Cities tab */
.cities-header {
    display: grid;
    grid-template-columns: 60px minmax(200px, 2fr) 90px 80px 70px minmax(100px, 1fr) minmax(100px, 1fr) minmax(100px, 1fr) 90px;
    gap: 8px;
    padding: 12px 16px;
    background: #f1f5f9;
    border-bottom: 2px solid #cbd5e1;
    font-size: 11px;
    font-weight: 600;
    color: #475569;
    text-transform: uppercase;
    align-items: center;
}
.cities-header span { cursor: pointer; }
.cities-header span:hover { color: #3b82f6; }

.cities-row {
    display: grid;
    grid-template-columns: 60px minmax(200px, 2fr) 90px 80px 70px minmax(100px, 1fr) minmax(100px, 1fr) minmax(100px, 1fr) 90px;
    gap: 8px;
    padding: 8px 16px;
    border-bottom: 1px solid #e5e7eb;
    cursor: pointer;
    align-items: center;
    background: white;
    font-size: 12px;
}
.cities-row:hover { background: #f8fafc; }
.cities-row .cell {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
}
.cities-row .addr { display: flex; flex-direction: column; overflow: hidden; min-width: 0; }
.cities-row .addr-main { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cities-row .addr-sub { font-size: 11px; color: #6b7280; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.cities-container {
    background: white;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    overflow: hidden;
}

.ab-table-wrapper {
    background: white;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    overflow: hidden;
}

.ab-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

.ab-table thead {
    background: var(--rzero-blue);
    position: sticky;
    top: 0;
    z-index: 10;
}

.ab-table th {
    padding: 14px 12px;
    text-align: left;
    font-weight: 600;
    font-size: 12px;
    color: white;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    cursor: pointer;
    transition: background 0.15s;
    white-space: nowrap;
}

.ab-table th:hover {
    background: #0052a3;
}

.ab-table th::after {
    content: " ⇵";
    opacity: 0.5;
    font-size: 10px;
}

.ab-table th:first-child::after {
    content: "";
}

.ab-table th.sort-asc::after {
    content: " ▲";
    opacity: 1;
}

.ab-table th.sort-desc::after {
    content: " ▼";
    opacity: 1;
}

.ab-table td {
    padding: 12px;
    border-bottom: 1px solid var(--gray-100);
    vertical-align: middle;
}

.ab-table tbody tr {
    cursor: pointer;
    transition: background 0.15s;
}

.ab-table tbody tr:hover {
    background: rgba(0, 102, 204, 0.04);
}

.ab-table .building-thumb {
    width: 70px;
    height: 52px;
    object-fit: cover;
    border-radius: 6px;
}

.ab-table .building-thumb-placeholder {
    width: 70px;
    height: 52px;
    background: var(--gray-100);
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    color: var(--gray-400);
}

.ab-loading-trigger {
    height: 60px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--gray-400);
    font-size: 14px;
}

.ab-empty-state {
    padding: 60px 20px;
    text-align: center;
    color: var(--gray-500);
}

.ab-empty-state h3 {
    margin: 0 0 8px 0;
    color: var(--gray-700);
    font-size: 18px;
}

.ab-empty-state p {
    margin: 0;
    font-size: 14px;
}

/* Vertical Toggle */
.vertical-toggle {
    display: flex;
    gap: 8px;
    margin-bottom: 24px;
    flex-wrap: wrap;
}

/* Filter Bar */
.filter-bar {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 12px 0;
    margin-bottom: 16px;
    border-bottom: 1px solid var(--gray-200);
    flex-wrap: wrap;
}

.filter-group {
    display: flex;
    align-items: center;
    gap: 8px;
}

.filter-label {
    font-size: 13px;
    color: var(--gray-600);
    font-weight: 500;
}

.filter-select {
    padding: 8px 12px;
    border: 1px solid var(--gray-300);
    border-radius: 6px;
    font-size: 13px;
    background: white;
    cursor: pointer;
    min-width: 140px;
}

.filter-select:focus {
    border-color: var(--primary);
    outline: none;
}

.export-btn {
    padding: 10px 16px;
    background: var(--gray-700);
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
}

.export-btn:hover {
    background: var(--gray-800);
}

.export-dropdown {
    position: relative;
    display: inline-block;
    z-index: 1002;
}

.export-menu {
    display: none;
    position: absolute;
    top: 100%;
    right: 0;
    margin-top: 4px;
    background: white;
    border: 1px solid var(--gray-200);
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.2);
    min-width: 200px;
    z-index: 99999;
}

.export-menu.show {
    display: block;
}

.export-menu button {
    display: block;
    width: 100%;
    padding: 12px 16px;
    background: none;
    border: none;
    text-align: left;
    font-size: 14px;
    color: var(--gray-700);
    cursor: pointer;
    transition: background 0.15s;
}

.export-menu button:hover {
    background: var(--gray-100);
}

.export-menu button:first-child {
    border-radius: 8px 8px 0 0;
}

.export-menu button:last-child {
    border-radius: 0 0 8px 8px;
}

.clear-btn {
    padding: 8px 12px;
    background: transparent;
    color: var(--gray-600);
    border: 1px solid var(--gray-300);
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
}

.clear-btn:hover {
    border-color: var(--gray-400);
    color: var(--gray-700);
}

.clear-btn.hidden {
    display: none;
}

.filter-results {
    font-size: 13px;
    color: var(--gray-600);
    margin-left: auto;
}

.filter-results strong {
    color: var(--gray-800);
}

.filter-input {
    padding: 8px 12px;
    border: 1px solid var(--gray-300);
    border-radius: 6px;
    font-size: 13px;
    background: white;
    min-width: 160px;
}

.filter-input:focus {
    border-color: var(--primary);
    outline: none;
}

/* Top Opportunities Tiles */
.top-opportunities {
    display: flex;
    gap: 12px;
    margin-bottom: 20px;
    overflow-x: auto;
    padding: 4px;
}

.opp-tile {
    flex: 0 0 170px;
    padding: 14px;
    background: white;
    border-radius: 10px;
    border: 2px solid var(--gray-200);
    cursor: pointer;
    transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.2s, box-shadow 0.2s;
}

.opp-tile:hover {
    border-color: var(--primary);
    box-shadow: 0 4px 12px rgba(0, 118, 157, 0.15);
    transform: translateY(-1px);
}

.opp-tile.selected {
    border-color: var(--primary);
    background: rgba(0, 118, 157, 0.05);
    transform: translateY(-2px);
    box-shadow: 0 0 0 3px rgba(0, 118, 157, 0.25);
}

.opp-logo {
    width: 36px;
    height: 36px;
    object-fit: contain;
    margin-bottom: 8px;
    border-radius: 6px;
    background: #f5f5f5;
    padding: 2px;
}

.opp-logo.dark-bg {
    background: #222;
}

.opp-logo-placeholder {
    width: 36px;
    height: 36px;
    background: var(--gray-200);
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    color: var(--gray-500);
    margin-bottom: 8px;
}

.opp-name {
    font-weight: 600;
    font-size: 13px;
    color: var(--gray-900);
    margin-bottom: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.opp-stats {
    font-size: 11px;
    color: var(--gray-500);
}

/* Global Search */
.global-search {
    flex: 0 0 400px;
    padding: 10px 14px;
    border: 1px solid var(--gray-300);
    border-radius: 8px;
    font-size: 14px;
    background: white;
    margin-right: 40px;
}

.global-search:focus {
    border-color: var(--primary);
    outline: none;
    box-shadow: 0 0 0 3px rgba(0, 118, 157, 0.1);
}

/* Filter Chips */
.filter-chips {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}

.filter-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 10px;
    background: var(--primary);
    color: white;
    border-radius: 16px;
    font-size: 12px;
    font-weight: 500;
}

.filter-chip .remove {
    cursor: pointer;
    opacity: 0.8;
}

.filter-chip .remove:hover {
    opacity: 1;
}

/* Main Building Table */
.main-table-wrapper {
    overflow-x: auto;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    max-height: 600px;
    overflow-y: auto;
    margin-bottom: 24px;
    background: white;
}

.main-building-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

.main-building-table thead {
    position: sticky;
    top: 0;
    z-index: 10;
}

.main-building-table th {
    background: var(--primary);
    color: white;
    padding: 12px 10px;
    text-align: left;
    font-weight: 600;
    white-space: nowrap;
}

.main-building-table th:hover {
    background: var(--primary-dark);
}

/* Sort arrow states */
.main-building-table th[data-sort]::after {
    content: " ⇵";
    opacity: 0.5;
    font-size: 0.85em;
}

.main-building-table th[data-sort][data-dir="asc"]::after {
    content: " ▲";
    opacity: 1;
}

.main-building-table th[data-sort][data-dir="desc"]::after {
    content: " ▼";
    opacity: 1;
}

.main-building-table td {
    padding: 10px;
    border-bottom: 1px solid var(--gray-100);
    vertical-align: middle;
}

.main-building-table tr:hover td {
    background: rgba(0, 118, 157, 0.04);
}

.main-building-table .building-row {
    transition: background 0.15s ease;
}

.main-building-table .building-row.hidden {
    display: none;
}

.rank-badge {
    display: inline-block;
    background: var(--primary);
    color: white;
    padding: 3px 8px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
}

/* Clickable links with expanded hit targets */
.clickable-link {
    color: var(--primary);
    text-decoration: none;
    cursor: pointer;
    display: inline-block;
    padding: 6px 10px;
    margin: -6px -10px;
    border-radius: 4px;
    transition: background 0.15s ease;
}

.clickable-link:hover {
    background: rgba(0, 118, 157, 0.08);
    text-decoration: underline;
}

.filter-link {
    color: var(--primary);
    text-decoration: none;
    cursor: pointer;
}

.filter-link:hover {
    text-decoration: underline;
}

.carbon-cell {
    text-align: right;
    color: var(--gray-600);
}

.portfolio-section {
    background: var(--gray-50);
    max-width: 1400px;
    margin: 0 auto;
}

.portfolio-sort-header,
.portfolio-header {
    display: grid;
    grid-template-columns: 120px 2fr 1fr 1fr 1fr 1fr 1fr 1fr;
    gap: 12px;
    padding: 8px 20px;
    align-items: center;
}

.portfolio-sort-header {
    background: var(--rzero-blue);
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    position: sticky;
    top: 200px;
    z-index: 100;
}

.sort-col {
    text-align: center;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    font-weight: 600;
    font-size: 12px;
    color: white;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    position: relative;
}
.sort-col[data-total]::before {
    content: attr(data-total);
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    background: #333;
    color: white;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;
    white-space: nowrap;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.2s;
    margin-top: 4px;
    text-transform: none;
    z-index: 1000;
}
.sort-col[data-total]:hover::before {
    opacity: 1;
}
.sort-col:nth-child(6),
.sort-col:nth-child(7),
.sort-col:nth-child(8) {
    justify-content: flex-end;
    text-align: right;
}

/* Portfolio Cards */
.portfolios-list {
    display: flex;
    flex-direction: column;
    gap: 20px;
}

.portfolio-card {
    background: white;
    border-radius: 12px;
    border: 1px solid var(--gray-200);
    transition: box-shadow 0.2s;
    position: relative;
}

.portfolio-card:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}

.org-logo-stack {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
}
.org-logo-stack .org-name-small {
    font-size: 10px;
    font-weight: 600;
    max-width: 120px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: #666;
}

.building-grid-row .address-cell {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.building-grid-row .address-cell small {
    display: block;
    color: #666;
    font-size: 12px;
}

.org-logo {
    width: 48px;
    height: 48px;
    object-fit: contain;
    opacity: 0;
    animation: logoFadeIn 0.3s ease-out forwards;
}

@keyframes logoFadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

.org-logo-placeholder {
    width: 48px;
    height: 48px;
    border-radius: 8px;
    background: var(--gray-200);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    font-weight: 600;
    color: var(--gray-500);
}

.portfolio-name {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding-left: 16px;
    overflow: hidden;
}

.portfolio-name h3 {
    font-size: 16px;
    font-weight: 600;
    color: var(--gray-900);
    margin: 0;
    line-height: 1.3;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.stat-cell {
    font-size: 13px;
    font-weight: 400;
    color: var(--gray-900);
    display: flex;
    align-items: center;
    justify-content: center;
}

.stat-cell.building-count {
    justify-content: center;
}

.stat-cell.valuation-value,
.stat-cell.carbon-value,
.stat-cell.opex-value {
    justify-content: flex-end;
}

.stat-cell.eui-value {
    justify-content: center;
}

.stat-cell.classification-cell {
    justify-content: center;
}

.stat-cell .label {
    font-weight: 400;
    color: var(--gray-500);
    font-size: 11px;
}

.vertical-badges {
    display: flex;
    gap: 4px;
}

.vertical-badge {
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
}

.vertical-badge.commercial { background: #1a3870; color: #ffffff; }
.vertical-badge.education { background: #0088ff; color: #ffffff; }
.vertical-badge.healthcare { background: #7ec8ff; color: #1a3870; }

/* Classification labels - plain text, no background */
.classification-badge {
    font-size: 9px;
    margin-right: 16px;
    font-weight: 600;
    text-transform: uppercase;
    white-space: nowrap;
}
.classification-badge.owner { color: #0066cc; }
.classification-badge.tenant { color: #0066cc; }
.classification-badge.property-manager { color: #1d4ed8; }
.classification-badge.owner-occupier { color: #0052a3; }
.classification-badge.owner-operator { color: #0052a3; }

.stat-cell.classification-cell {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    color: var(--gray-600);
}
.classification-cell.classification-owner { color: var(--primary); }
.classification-cell.classification-tenant { color: var(--gray-700); }
.classification-cell.classification-property-manager { color: var(--primary-dark); }
.classification-cell.classification-owner-occupier { color: var(--gray-600); }
.classification-cell.classification-owner-operator { color: var(--gray-800); }

.expand-arrow {
    position: absolute;
    right: -30px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 14px;
    color: var(--gray-400);
    transition: transform 0.2s;
}

.portfolio-card.expanded .expand-arrow {
    transform: translateY(-50%) rotate(180deg);
}

/* Portfolio Buildings Table */
.portfolio-buildings {
    display: none;
    border-top: 1px solid var(--gray-200);
}

.portfolio-card.expanded .portfolio-buildings {
    display: block;
}

.buildings-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    table-layout: fixed;
}

.buildings-table th {
    background: var(--gray-200);
    padding: 8px 12px;
    text-align: left;
    font-weight: 500;
    font-size: 11px;
    color: var(--gray-700);
    text-transform: uppercase;
    letter-spacing: 0.3px;
    position: sticky;
    top: 0;
    z-index: 1;
}

.buildings-table td {
    padding: 14px 16px;
    border-bottom: 1px solid var(--gray-100);
    vertical-align: middle;
}

.buildings-table tr:hover td {
    background: var(--gray-50);
}

/* Grid-based building rows - 8 columns: same as portfolio-header */
.building-grid-row {
    display: grid;
    grid-template-columns: 120px 2fr 1fr 1fr 1fr 1fr 1fr 1fr;
    gap: 12px;
    padding: 8px 20px;
    border-bottom: 1px solid var(--gray-100);
    cursor: pointer;
    align-items: center;
    background: #fafbfc;
    border-left: 3px solid #e2e8f0;
    box-shadow: inset 0 1px 3px rgba(0,0,0,0.04);
    font-size: 12px;
}
.building-grid-row:hover {
    background: #f1f5f9;
    border-left-color: #3b82f6;
}
.building-grid-row > div:first-child {
    width: 70px;
    min-width: 70px;
    max-width: 70px;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
}
.building-grid-row .stat-cell:first-of-type {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    justify-content: center;
    overflow: hidden;
    min-width: 0;
}

.addr-main {
    font-weight: 400;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
}

.addr-sub {
    font-size: 12px;
    color: #888;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
}

.row-controls {
    display: flex;
    justify-content: center;
    gap: 12px;
    padding: 8px;
    background: #f1f5f9;
    border-top: 1px solid #e2e8f0;
}

.row-arrow {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    background: white;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    font-size: 16px;
    color: #3b82f6;
    cursor: pointer;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    transition: all 0.15s;
}

.row-arrow:hover:not(.disabled) {
    background: #dbeafe;
    border-color: #3b82f6;
    box-shadow: 0 2px 4px rgba(59,130,246,0.2);
}

.row-arrow.disabled {
    color: #cbd5e1;
    cursor: not-allowed;
    background: #f8fafc;
}

.building-rows-container {
    display: contents;
}

.building-thumb {
    width: 60px;
    height: 45px;
    min-width: 60px;
    min-height: 45px;
    max-width: 60px;
    max-height: 45px;
    object-fit: cover;
    border-radius: 4px;
    background: var(--gray-300);
    display: block;
}

.building-thumb-placeholder {
    width: 60px;
    height: 45px;
    border-radius: 4px;
    background: var(--gray-200);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
}

.building-address {
    font-weight: 500;
    color: var(--gray-900);
    white-space: nowrap;
}

.building-address a {
    color: var(--primary);
    text-decoration: none;
}

.building-address a:hover {
    text-decoration: underline;
}

.external-link {
    color: var(--gray-400);
    margin-left: 6px;
    font-size: 11px;
}

.external-link:hover {
    color: var(--primary);
}

.city-state {
    color: var(--gray-500);
    font-size: 12px;
}

.building-type {
    vertical-align: middle;
}

/* Building type badges - site palette only */
.type-badge {
    display: inline-block;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
    line-height: 1.3;
    text-align: center;
}
.type-badge--blue { background: var(--primary); color: #fff; }
.type-badge--blue-light { background: #e5f0ff; color: var(--primary-dark); }
.type-badge--gray-dark { background: var(--gray-700); color: #fff; }
.type-badge--gray-mid { background: var(--gray-400); color: var(--gray-900); }
.type-badge--gray-light { background: var(--gray-200); color: var(--gray-700); }
.type-badge--gray-xlight { background: var(--gray-100); color: var(--gray-600); }

.money-cell {
    font-weight: 500;
    text-align: right;
}

.money-cell.positive {
    color: var(--success);
}

/* EUI Rating Colors */
.eui-good { color: #22c55e; font-weight: 600; }
.eui-ok { color: #f59e0b; font-weight: 600; }
.eui-bad { color: #ef4444; font-weight: 600; }
.eui-cell { text-align: right; white-space: nowrap; }

/* Unbold EUI in portfolio building rows */
.building-grid-row .eui-good,
.building-grid-row .eui-ok,
.building-grid-row .eui-bad {
    font-weight: normal;
}

/* Spiderfy Markers for Stacked Buildings */
.spiderfy-marker { cursor: pointer; }
.spiderfy-pin {
    width: 24px;
    height: 24px;
    background: #0066cc;
    border: 3px solid white;
    border-radius: 50%;
    box-shadow: 0 2px 6px rgba(0,0,0,0.3);
    transition: transform 0.15s ease;
}
.spiderfy-pin:hover { transform: scale(1.2); }
.spiderfy-leg {
    position: absolute;
    background: rgba(0, 102, 204, 0.5);
    height: 2px;
    transform-origin: left center;
}

/* Building Search Tab */
.search-section {
    margin-bottom: 24px;
}

.search-input-container {
    position: relative;
    max-width: 500px;
}

.search-input {
    width: 100%;
    padding: 14px 20px 14px 48px;
    font-size: 15px;
    border: 2px solid var(--gray-200);
    border-radius: 12px;
    outline: none;
    transition: border-color 0.2s;
}

.search-input:focus {
    border-color: var(--primary);
}

.search-icon {
    position: absolute;
    left: 16px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--gray-400);
    font-size: 18px;
}

.search-results {
    display: grid;
    grid-template-columns: 1fr 400px;
    gap: 24px;
    margin-top: 24px;
}

.results-list {
    background: white;
    border-radius: 12px;
    border: 1px solid var(--gray-200);
    overflow: hidden;
}

.results-header {
    padding: 16px 20px;
    border-bottom: 1px solid var(--gray-200);
    font-weight: 600;
    color: var(--gray-700);
}

.results-table-container {
    max-height: 600px;
    overflow-y: auto;
}

.results-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

.results-table th {
    background: var(--gray-100);
    padding: 10px 12px;
    text-align: left;
    font-weight: 600;
    color: var(--gray-600);
    position: sticky;
    top: 0;
}

.results-table td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--gray-100);
}

.results-table tr:hover td {
    background: var(--gray-50);
    cursor: pointer;
}

.distance-cell {
    color: var(--gray-500);
    font-size: 12px;
}

/* Map Container */
.map-container {
    background: white;
    border-radius: 12px;
    border: 1px solid var(--gray-200);
    overflow: hidden;
    height: 600px;
}

#search-map {
    width: 100%;
    height: 100%;
}

/* Map Panel (for full map view) */
.map-panel {
    position: fixed;
    top: 0;
    right: 0;
    width: 50%;
    height: 100%;
    background: white;
    z-index: 2000;
    transform: translateX(100%);
    transition: transform 0.3s ease;
    box-shadow: -4px 0 20px rgba(0,0,0,0.1);
    will-change: transform;
}

.map-panel.open {
    transform: translateX(0);
}

.map-panel-header {
    padding: 16px 20px;
    border-bottom: 1px solid var(--gray-200);
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.map-panel-close {
    background: none;
    border: none;
    font-size: 24px;
    cursor: pointer;
    color: var(--gray-500);
}

.map-panel-actions {
    display: flex;
    align-items: center;
    gap: 12px;
}

.map-panel-reset {
    background: var(--gray-100);
    border: 1px solid var(--gray-300);
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 500;
    color: var(--gray-700);
    cursor: pointer;
    transition: background-color 0.15s ease, color 0.15s ease;
}

.map-panel-reset:hover {
    background: var(--gray-200);
    border-color: var(--gray-400);
}

/* Address Search Form Styling - Exact match to NYC */
.form-group {
    margin-bottom: 1.5rem;
}

.form-group label {
    display: block;
    margin-bottom: 0.3rem;
    font-weight: bold;
    font-size: 15px;
    color: #1a202c;
}

#full-map {
    height: calc(100% - 130px);
}

/* Pin Highlight on Table Row */
tr.pin-highlight {
    background: rgba(0, 118, 157, 0.15) !important;
    outline: 2px solid rgba(0, 118, 157, 0.4);
}

/* Cluster Styling */
.mapboxgl-popup {
    z-index: 1001;
}

/* Building Popup */
.mapboxgl-popup {
    max-width: 320px;
}

.mapboxgl-popup-content {
    padding: 0;
    border-radius: 12px;
    overflow: hidden;
}

.popup-content {
    padding: 16px;
}

.popup-content h4 {
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 4px;
}

.popup-content p {
    font-size: 12px;
    color: var(--gray-500);
    margin-bottom: 8px;
}

.popup-stats {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    font-size: 12px;
}

.popup-stat {
    background: var(--gray-50);
    padding: 8px;
    border-radius: 6px;
}

.popup-stat .label {
    color: var(--gray-500);
    font-size: 10px;
    text-transform: uppercase;
}

.popup-stat .value {
    font-weight: 600;
    color: var(--gray-900);
}

/* Responsive */
@media (max-width: 1200px) {
    .header h1 {
        font-size: 24px;
    }
    .vertical-filter-bar {
        padding-left: 320px;
    }
    .btn-count {
        display: none;
    }
    .stats-grid {
        grid-template-columns: repeat(3, 1fr);
    }

    .search-results {
        grid-template-columns: 1fr;
    }

    .map-container {
        height: 400px;
    }
}

@media (max-width: 600px) {
    /* Hide filter drawer toggle on small screens */
    .filter-drawer-toggle {
        display: none;
    }

    /* Header stays compact */
    .header {
        padding: 12px 16px;
    }

    /* Hide title on mobile */
    .header h1 {
        display: none;
    }

    /* Center the header content */
    .header-content {
        justify-content: center;
    }

    /* Center and expand search box */
    .global-search {
        flex: 1;
        max-width: 400px;
        margin: 0 auto;
    }

    /* Hide export dropdown on mobile */
    .export-dropdown {
        display: none;
    }

    /* Hide filter chips on mobile */
    .filter-chips {
        display: none;
    }

    /* Vertical filter bar uses full width */
    .vertical-filter-bar {
        padding: 12px 16px;
        overflow-x: auto;
        top: 65px;
    }

    /* Smaller vertical buttons on mobile */
    .vertical-btn {
        padding: 8px 12px;
        font-size: 12px;
        white-space: nowrap;
    }

    /* Hide counts on mobile */
    .btn-count {
        display: none;
    }

}

@media (max-width: 768px) {
    .header h1 {
        font-size: 20px;
    }
    .vertical-filter-bar {
        padding-left: 310px;
    }
    .stats-grid {
        grid-template-columns: repeat(2, 1fr);
    }

    .stat-cell {
        display: none;
    }

    .stat-cell.building-count {
        display: block;
        grid-column: 2;
        grid-row: 2;
        font-size: 12px;
        text-align: left;
    }

}

/* Loading spinner */
.loading {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 40px;
    color: var(--gray-500);
}

.loading::after {
    content: '';
    width: 24px;
    height: 24px;
    border: 3px solid var(--gray-200);
    border-top-color: var(--primary);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin-left: 12px;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

/* Hidden */
.hidden {
    display: none !important;
}

/* Filtered out - used for optimized filtering */
.filtered-out {
    display: none !important;
}
</style>'''

    # =========================================================================
    # BODY SECTIONS
    # =========================================================================

    def _generate_body_start(self):
        """Generate opening body tag with left sidebar."""
        sidebar_html = self._generate_left_sidebar()
        return f'<body>\n{sidebar_html}'

    def _generate_left_sidebar(self):
        """Generate vertical filter bar AND left sidebar with building type filters."""
        by_vertical = self.stats.get('by_vertical', {})
        total = self.stats.get('total_buildings', 0)
        radio_counts = self.stats.get('radio_type_counts', {})
        types_by_vertical = self.stats.get('types_by_vertical', {})

        # Colors: bg color for each vertical
        colors = {
            'all': '#6b7280',       # grey
            'Commercial': '#1e3a5f', # dark navy
            'Education': '#0077cc',  # blue
            'Healthcare': '#5ba3d9', # light blue
        }

        # Vertical buttons HTML (for top bar)
        vertical_html = []
        for v in ['Commercial', 'Education', 'Healthcare']:
            count = by_vertical.get(v, {}).get('building_count', 0)
            vertical_html.append(
                f'<button class="vertical-btn" data-vertical="{v}" '
                f'onclick="selectVertical(\'{v}\')" style="background:{colors[v]}">'
                f'{v} <span class="btn-count">({count:,})</span>'
                f'<span class="btn-x" onclick="event.stopPropagation(); selectVertical(\'all\')">✕</span></button>'
            )

        # Map building types to their vertical
        type_to_vertical = {}
        for vertical, types in types_by_vertical.items():
            for t in types:
                type_to_vertical[t] = vertical

        # Sort building types: by vertical order, then by count descending
        vertical_order = {'Commercial': 0, 'Education': 1, 'Healthcare': 2}
        sorted_types = sorted(
            radio_counts.items(),
            key=lambda x: (vertical_order.get(type_to_vertical.get(x[0], 'Commercial'), 99), -x[1])
        )

        # Building type buttons HTML (for sidebar)
        building_html = []
        for btype, count in sorted_types:
            if not btype or btype == 'radio_button_building_type':
                continue
            v = type_to_vertical.get(btype, 'Commercial')
            bg = colors.get(v, colors['Commercial'])
            building_html.append(
                f'<button class="building-type-btn" data-type="{attr_escape(btype)}" '
                f'data-vertical="{v}" onclick="toggleBuildingType(this)" '
                f'style="background:{bg}">{escape(btype)} <span>({count:,})</span></button>'
            )

        # Return BOTH the vertical filter bar AND the filter drawer
        return f'''<div class="vertical-filter-bar">
    <div class="vertical-filter-inner">
        {''.join(vertical_html)}
        <div id="building-type-chip" class="building-type-chip">
            <span class="chip-x" onclick="clearBuildingTypeFilter()">&times;</span>
            <span class="chip-text"></span>
        </div>
        <div class="export-dropdown" style="margin-left: auto;">
            <button class="export-btn" onclick="toggleExportMenu(event)">
                <span style="font-size: 14px;">&#8595;</span> Export CSV
            </button>
            <div id="export-menu" class="export-menu">
                <button onclick="exportAllBuildingsCSV()">All Buildings</button>
                <button onclick="exportFilteredCSV()">Filtered Results</button>
                <button onclick="exportPortfolioCSV()">Portfolio Summaries</button>
            </div>
        </div>
    </div>
</div>
<div class="filter-drawer" id="filter-drawer">
    <div class="filter-drawer-header">
        <span class="sidebar-label">Filter by Building Type</span>
        <button class="filter-drawer-close" onclick="toggleFilterDrawer()">&times;</button>
    </div>
    <div class="building-type-filters">
        {''.join(building_html)}
    </div>
</div>
<button class="filter-drawer-toggle" onclick="toggleFilterDrawer()">Filters</button>'''

    def _generate_body_end(self):
        """Generate closing body and html tags."""
        return '</body>\n</html>'

    def _generate_header(self):
        """Generate page header with tab bar."""
        return '''
<header class="header">
    <div class="header-content">
        <h1>
            <a href="https://rzero.com" target="_blank" style="display: flex; align-items: center;">
                <img src="https://rzero.com/wp-content/themes/rzero/build/images/favicons/favicon.png" alt="R-Zero">
            </a>
            Nationwide ODCV Prospector
        </h1>
        <input type="text" id="global-search" class="global-search" placeholder="Search owner, tenant, brand..." oninput="globalSearch(this.value)" style="margin-left: 40px;">
        <div id="filter-chips" class="filter-chips"></div>
        <div style="margin-left: auto; display: flex; gap: 12px; align-items: center; margin-right: 85px;">
            <button onclick="openMapPanel()" style="
                background: #0066cc;
                color: white;
                border: none;
                padding: 8px 14px;
                border-radius: 6px;
                font-weight: 500;
                cursor: pointer;
                display: flex;
                align-items: center;
                gap: 6px;
                font-size: 13px;
                transition: background 0.2s;
            " onmouseover="this.style.background='#0052a3'" onmouseout="this.style.background='#0066cc'">
                <span style="font-size: 14px;">&#128506;</span> View Map
            </button>
        </div>
    </div>
</header>
<div class="main-tabs" style="position: fixed; top: 85px; left: 0; right: 0; z-index: 1002; background: white; border-bottom: 1px solid var(--gray-200); padding: 0 32px;">
    <div style="max-width: 1400px; margin: 0 auto; display: flex; gap: 0;">
        <button class="main-tab active" data-tab="portfolios" onclick="switchMainTab('portfolios')">Portfolios</button>
        <button class="main-tab" data-tab="all-buildings" onclick="switchMainTab('all-buildings')">Cities</button>
    </div>
</div>'''

    # =========================================================================
    # PORTFOLIO SECTION
    # =========================================================================

    def _generate_portfolio_section(self):
        """Generate the Portfolio section with first 20 cards only (rest load on scroll)."""
        # Only render first 100 portfolio cards - rest load via JS on scroll
        INITIAL_LOAD = 100
        portfolio_cards = []
        for i, p in enumerate(self.portfolios[:INITIAL_LOAD]):
            portfolio_cards.append(self._generate_portfolio_card(p, i))

        # Get total opex for initial display
        total_opex = self.stats.get('total_opex_avoidance', 0)
        def fmt_money_global(n):
            if n >= 1_000_000_000:
                return f'${n/1_000_000_000:.1f}B'
            if n >= 1_000_000:
                return f'${int(n/1_000_000)}M'
            if n >= 1_000:
                return f'${int(n/1_000)}K'
            return f'${int(n):,}'

        # Calculate totals for rollup stats
        total_valuation = sum(p.get('total_valuation_impact', 0) or 0 for p in self.portfolios)
        total_carbon = sum(p.get('total_carbon_reduction', 0) or 0 for p in self.portfolios)

        def fmt_valuation(n):
            if n >= 1e9: return f'${n/1e9:.1f}B'
            if n >= 1e6: return f'${int(n/1e6)}M'
            return f'${int(n):,}'

        def fmt_carbon(n):
            if n >= 1e6: return f'{n/1e6:.1f}M'
            if n >= 1e3: return f'{int(n/1e3)}K'
            return f'{int(n):,}'

        def fmt_sqft(n):
            if n >= 1e9: return f'{n/1e9:.1f}B'
            if n >= 1e6: return f'{n/1e6:.0f}M'
            if n >= 1e3: return f'{int(n/1e3)}K'
            return f'{int(n):,}'

        # Calculate totals for column headers
        num_portfolios = len(self.portfolios)
        total_buildings = self.stats.get('total_buildings', 0)
        total_sqft = sum(p.get('total_sqft', 0) or 0 for p in self.portfolios)

        return f'''
<div id="portfolios-tab" class="tab-content active">
<div class="portfolio-section" style="padding: 210px 32px 20px 32px;">
    <div class="portfolio-sort-header">
        <span class="sort-col" id="header-org-col"></span>
        <span class="sort-col" onclick="sortPortfolios('buildings')" style="cursor:pointer" data-total="{total_buildings:,} Total Buildings">Buildings <span class="sort-indicator">↕</span></span>
        <span class="sort-col" onclick="sortPortfolios('classification')" style="cursor:pointer">Type <span class="sort-indicator">↕</span></span>
        <span class="sort-col" onclick="sortPortfolios('sqft')" style="cursor:pointer" data-total="{fmt_sqft(total_sqft)} Total Sq Ft">Sq Ft <span class="sort-indicator">↕</span></span>
        <span class="sort-col" onclick="sortPortfolios('eui')" style="cursor:pointer">EUI <span class="sort-indicator">↕</span></span>
        <span class="sort-col" onclick="sortPortfolios('valuation')" style="cursor:pointer" data-total="{fmt_valuation(total_valuation)} Total Val. Impact">Val. Impact <span class="sort-indicator">↕</span></span>
        <span class="sort-col" onclick="sortPortfolios('carbon')" style="cursor:pointer" data-total="{fmt_carbon(total_carbon)} Total tCO2e/yr">tCO2e/yr <span class="sort-indicator">↕</span></span>
        <span class="sort-col" onclick="sortPortfolios('opex')" style="cursor:pointer" data-total="{fmt_money_global(total_opex)} Total Savings/yr">Savings/yr <span class="sort-indicator">↕</span></span>
    </div>
    <div class="portfolios-list" id="portfolios-list">
        {''.join(portfolio_cards)}
    </div>
    <div id="load-more-trigger" style="height:1px;"></div>
</div>
</div>'''

    def _generate_all_buildings_section(self):
        """Generate the All Buildings tab with filterable table of all buildings."""
        bucket = self.config['aws_bucket']

        # Calculate summary stats
        total_buildings = len(self.all_buildings)
        total_opex = sum(b.get('total_opex', 0) or 0 for b in self.all_buildings)
        total_carbon = sum(b.get('carbon_reduction', 0) or 0 for b in self.all_buildings)
        total_sqft = sum(b.get('sqft', 0) or 0 for b in self.all_buildings)

        # Calculate top 5 cities by OpEx (from portfolio buildings only)
        city_stats = {}
        for p in self.portfolios:
            for b in p.get('buildings', []):
                city = b.get('city', '')
                if city:
                    if city not in city_stats:
                        city_stats[city] = {'count': 0, 'opex': 0}
                    city_stats[city]['count'] += 1
                    city_stats[city]['opex'] += b.get('total_opex', 0) or 0

        top_cities = sorted(city_stats.items(), key=lambda x: x[1]['opex'], reverse=True)[:5]

        # Format functions
        def fmt_money(n):
            if n >= 1_000_000_000:
                return f'${n/1_000_000_000:.1f}B'
            if n >= 1_000_000:
                return f'${int(n/1_000_000)}M'
            if n >= 1_000:
                return f'${int(n/1_000)}K'
            return f'${int(n):,}'

        def fmt_num(n):
            if n >= 1_000_000_000:
                return f'{n/1_000_000_000:.1f}B'
            if n >= 1_000_000:
                return f'{int(n/1_000_000)}M'
            if n >= 1_000:
                return f'{int(n/1_000)}K'
            return f'{int(n):,}'

        # Generate city filter cards HTML - compact chips
        city_cards = []
        for city, stats in top_cities:
            city_cards.append(f'''<div class="city-filter-card" onclick="filterByCity('{escape(city)}')"><strong>{escape(city)}</strong><span class="city-count">{stats['count']:,}</span><span class="city-opex">{fmt_money(stats['opex'])}</span></div>''')

        return f'''
<div id="all-buildings-tab" class="tab-content">
<div class="all-buildings-section" style="padding: 210px 32px 20px 32px;">
    <!-- City Filter -->
    <div class="city-filter-section">
        <div class="city-filter-label">Filter by City</div>
        <div class="city-filter-cards">{''.join(city_cards)}</div>
    </div>

    <!-- Cities Table -->
    <div class="cities-container">
        <div class="cities-header">
            <span></span>
            <span onclick="sortAllBuildings('address')">Address</span>
            <span onclick="sortAllBuildings('type')">Type</span>
            <span onclick="sortAllBuildings('sqft')">Sq Ft</span>
            <span onclick="sortAllBuildings('eui')">EUI</span>
            <span onclick="sortAllBuildings('owner')">Owner</span>
            <span onclick="sortAllBuildings('tenant')">Tenant</span>
            <span onclick="sortAllBuildings('property_manager')">Prop Mgr</span>
            <span onclick="sortAllBuildings('opex')">OpEx <span id="cities-total-opex" style="font-weight:700;color:#059669;"></span></span>
        </div>
        <div id="cities-rows" style="max-height:calc(100vh - 340px);overflow-y:auto;">
            <div id="cities-list"></div>
            <div class="ab-loading-trigger" id="ab-loading-trigger">Loading more...</div>
        </div>
    </div>
</div>
</div>'''

    def _generate_main_building_table(self):
        """Generate main building table rows (top 1000 by OpEx)."""
        bucket = self.config['aws_bucket']

        # Sort all buildings by total_opex descending, take top 1000
        sorted_buildings = sorted(
            self.all_buildings,
            key=lambda x: safe_float(x.get('total_opex', 0)),
            reverse=True
        )[:1000]

        rows = []
        for rank, b in enumerate(sorted_buildings, 1):
            # Thumbnail
            if b.get('image'):
                thumb = f'<img src="{bucket}/thumbnails/{attr_escape(b["image"])}" alt="" class="building-thumb" loading="lazy" decoding="async">'
            else:
                icon = building_type_icon(b.get('building_type', ''))
                thumb = f'<div class="building-thumb-placeholder">{icon}</div>'

            # Format values
            opex = safe_float(b.get('total_opex', 0))
            carbon = safe_float(b.get('carbon_reduction', 0))

            if opex >= 1_000_000:
                opex_str = f'${opex/1_000_000:.2f}M'
            elif opex >= 1_000:
                opex_str = f'${opex/1_000:.0f}K'
            else:
                opex_str = f'${opex:,.0f}'

            carbon_str = format_carbon(carbon)

            address = escape(b.get('address', 'Unknown'))
            city = escape(b.get('city', ''))
            state = escape(b.get('state', ''))
            btype = escape(b.get('building_type', ''))
            owner_raw = b.get('owner', '') or b.get('org_name', '')
            owner = escape(self._get_org_display_name(owner_raw))
            manager = escape(b.get('manager', ''))
            tenant = escape(b.get('tenant', ''))
            sub_org = escape(b.get('sub_org', ''))
            vertical = b.get('vertical', '')

            # Data attributes for filtering + row click to external URL
            building_id = b.get('id', '')
            building_url = b.get('url', '')
            row_click = f'''onclick="if (!event.target.closest('a, .clickable-link')) window.open('{attr_escape(building_url)}', '_blank')" style="cursor:pointer"''' if building_url else ''
            row = f'''<tr class="building-row" data-id="{attr_escape(building_id)}" data-city="{attr_escape(city)}" data-type="{attr_escape(btype)}" data-owner="{attr_escape(owner)}" data-manager="{attr_escape(manager)}" data-tenant="{attr_escape(tenant)}" data-sub-org="{attr_escape(sub_org)}" data-vertical="{attr_escape(vertical)}" data-opex="{opex}" data-rank="{rank}" {row_click}>
    <td>{thumb}</td>
    <td><span class="rank-badge">#{rank}</span></td>
    <td><span class="building-address">{address}</span><br><span class="city-state">{city}, {state}</span></td>
    <td><a href="javascript:void(0)" onclick="event.stopPropagation(); filterPortfoliosByCity('{js_escape(city)}')" class="clickable-link">{city}</a></td>
    <td><a href="javascript:void(0)" onclick="event.stopPropagation(); filterByType('{js_escape(btype)}')" class="clickable-link">{btype}</a></td>
    <td><a href="javascript:void(0)" onclick="event.stopPropagation(); filterByOwner('{js_escape(owner)}')" class="clickable-link">{owner}</a></td>
    <td class="money-cell positive">{opex_str}</td>
    <td class="carbon-cell">{carbon_str}</td>
</tr>'''
            rows.append(row)

        return '\n'.join(rows)

    def _generate_portfolio_card(self, portfolio, index):
        """Generate a single portfolio card."""
        p = portfolio
        bucket = self.config['aws_bucket']

        # Logo - eager loading for first 500, lazy for rest
        # Use aws_logo_url if available, otherwise fall back to constructing from logo_file
        logo_url = p.get('aws_logo_url', '')
        if not logo_url and p['logo_file']:
            logo_url = f"{bucket}/logos/{p['logo_file']}"

        if logo_url:
            logo_class = 'org-logo dark-bg' if p['logo_file'] in WHITE_LOGOS else 'org-logo'
            # Always eager load logos - they're small and critical for UX
            logo_html = f'<img src="{attr_escape(logo_url)}" alt="" class="{logo_class}" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'"><div class="org-logo-placeholder" style="display:none">{p["org_name"][0].upper()}</div>'
        else:
            logo_html = f'<div class="org-logo-placeholder">{p["org_name"][0].upper()}</div>'


        # Stats
        def fmt_money(n):
            if n >= 1_000_000_000:
                return f'${n/1_000_000_000:.1f}B'
            if n >= 1_000_000:
                return f'${int(n/1_000_000)}M'
            if n >= 1_000:
                return f'${int(n/1_000)}K'
            return f'${int(n):,}'

        # Calculate total sqft for display
        total_sqft = sum(b.get('sqft', 0) or 0 for b in p['buildings'])

        verticals_data = ','.join(p['verticals'])
        cities_data = ','.join(p.get('cities', []))
        types_data = ','.join(p.get('building_types', []))
        radio_types_data = ','.join(p.get('radio_types', []))
        tenants_data = ','.join(p.get('tenants', []))
        sub_orgs_data = ','.join(p.get('tenant_sub_orgs', []))

        # Classification (for sortable column)
        classification = p.get('classification', '')

        # Median EUI with rating
        median_eui = p.get('median_eui')
        median_eui_benchmark = p.get('median_eui_benchmark')
        if median_eui:
            eui_display = eui_rating(median_eui, median_eui_benchmark)
        else:
            eui_display = '-'

        # Format median sqft
        def fmt_sqft(sqft):
            sqft = sqft or 0
            if sqft >= 1_000_000:
                return f'{sqft/1_000_000:.1f}M'
            elif sqft >= 10_000:
                return f'{sqft/1_000:.0f}K'
            elif sqft > 0:
                return f'{int(sqft):,}'
            return '-'

        sqft_display = fmt_sqft(total_sqft)

        return f'''
<div class="portfolio-card" data-idx="{index}" data-org="{attr_escape(p['org_name'])}" data-verticals="{verticals_data}" data-cities="{cities_data}" data-types="{types_data}" data-radio-types="{radio_types_data}" data-tenants="{attr_escape(tenants_data)}" data-sub-orgs="{attr_escape(sub_orgs_data)}" data-buildings="{p['building_count']}" data-total-buildings="{p['building_count']}" data-sqft="{total_sqft}" data-eui="{p.get('median_eui', 0) or 0}" data-opex="{p['total_opex_avoidance']}" data-valuation="{p['total_valuation_impact']}" data-carbon="{p['total_carbon_reduction']}" data-classification="{attr_escape(classification)}">
    <div class="portfolio-header" onclick="togglePortfolio(this)">
        <div class="org-logo-stack">
            <span class="org-name-small" title="{attr_escape(p.get('display_name', p['org_name']))}">{escape(p.get('display_name', p['org_name']))}</span>
            {logo_html}
        </div>
        <span class="stat-cell building-count"><span class="building-count-value">{p['building_count']}</span></span>
        <span class="stat-cell classification-cell classification-{classification.replace('/', '-').replace(' ', '-') if classification else 'none'}">{classification.replace('/', '<br>').replace(' ', '<br>') if classification else '-'}</span>
        <span class="stat-cell sqft-value">{sqft_display}</span>
        <span class="stat-cell eui-value">{eui_display}</span>
        <span class="stat-cell valuation-value">{fmt_money(p['total_valuation_impact'])}</span>
        <span class="stat-cell carbon-value">{format_carbon(p['total_carbon_reduction'])}</span>
        <span class="stat-cell opex-value">{fmt_money(p['total_opex_avoidance'])}</span>
    </div>
    <div class="portfolio-buildings">
        <div class="building-rows-container"></div>
    </div>
</div>'''

    def _generate_building_row(self, b):
        """Generate a building table row."""
        bucket = self.config['aws_bucket']

        # Thumbnail
        if b.get('image'):
            thumb = f'<img src="{bucket}/thumbnails/{attr_escape(b["image"])}" alt="" class="building-thumb" loading="lazy" decoding="async">'
        else:
            icon = building_type_icon(b['building_type'])
            thumb = f'<div class="building-thumb-placeholder">{icon}</div>'

        # City, State
        city = b.get('city', '') or ''
        state = b.get('state', '') or ''
        city_state = f"{city}, {state}" if city and state else ''

        # Address - strip city/state if present to avoid duplication
        address_text = b['address'] if b['address'] else 'Unknown'
        if city and address_text != 'Unknown':
            # Remove city, state, and zip from end of address
            import re
            pattern = rf',?\s*{re.escape(city)},?\s*{re.escape(state)}[,\s]*\d{{5}}(-\d{{4}})?$'
            address_text = re.sub(pattern, '', address_text, flags=re.IGNORECASE).strip().rstrip(',')
        address_html = f'<span class="building-address">{escape(address_text)}</span>'

        # External link
        if b['building_url']:
            address_html += f' <a href="{attr_escape(b["building_url"])}" target="_blank" class="external-link" title="View source">↗</a>'

        # Money formatting
        def fmt_money(n):
            if n >= 1_000_000_000:
                return f'${n/1_000_000_000:.1f}B'
            if n >= 1_000_000:
                return f'${int(n/1_000_000)}M'
            if n >= 1_000:
                return f'${int(n/1_000)}K'
            return f'${int(n):,}'

        radio_type = b.get('radio_type', '')
        building_id = attr_escape(b['building_id'].replace('/', '_').replace('\\', '_'))
        opex_value = b.get('total_opex', 0)
        valuation_value = b.get('valuation_impact', 0)
        carbon_value = b.get('carbon_reduction', 0)
        odcv_pct = b.get('total_building_cost_savings_pct', 0)
        odcv_pct_display = f"{odcv_pct*100:.0f}%" if odcv_pct else "-"

        # EUI with rating
        site_eui = b.get('site_eui')
        eui_benchmark = b.get('eui_benchmark')
        if site_eui:
            eui_display = eui_rating(site_eui, eui_benchmark)
        else:
            eui_display = "-"

        # Sqft formatting
        def fmt_sqft(sqft):
            sqft = sqft or 0
            if sqft >= 1_000_000:
                return f'{sqft/1_000_000:.1f}M'
            elif sqft >= 10_000:
                return f'{sqft/1_000:.0f}K'
            elif sqft > 0:
                return f'{int(sqft):,}'
            return '-'

        # Building type badge formatter
        def fmt_building_type(btype):
            if not btype:
                return '<span class="type-badge default">-</span>'
            # Map type to CSS class
            btype_lower = btype.lower()
            if 'office' in btype_lower and 'medical' not in btype_lower:
                css_class = 'office'
            elif 'hotel' in btype_lower:
                css_class = 'hotel'
            elif 'retail' in btype_lower or 'consumer' in btype_lower:
                css_class = 'retail'
            elif 'grocery' in btype_lower or 'supercenter' in btype_lower:
                css_class = 'grocery'
            elif 'gym' in btype_lower:
                css_class = 'gym'
            elif 'hospital' in btype_lower or 'clinic' in btype_lower:
                css_class = 'hospital'
            elif 'medical' in btype_lower or 'lab' in btype_lower:
                css_class = 'medical'
            elif 'higher' in btype_lower:
                css_class = 'higher-ed'
            elif 'k-12' in btype_lower or 'k12' in btype_lower:
                css_class = 'k12'
            elif 'library' in btype_lower or 'museum' in btype_lower:
                css_class = 'library'
            elif 'event' in btype_lower:
                css_class = 'event'
            elif 'mixed' in btype_lower:
                css_class = 'mixed'
            elif 'mall' in btype_lower or 'strip' in btype_lower:
                css_class = 'mall'
            elif 'residential' in btype_lower or 'care' in btype_lower:
                css_class = 'residential'
            else:
                css_class = 'default'
            # Replace / with newline for two-word types
            display_text = escape(btype).replace('/', '<br>')
            return f'<span class="type-badge {css_class}">{display_text}</span>'

        sqft_value = b.get('sqft', 0) or 0
        sqft_display = fmt_sqft(sqft_value)
        type_badge = fmt_building_type(b.get('building_type', ''))

        return f'''
<div class="building-grid-row" data-id="{building_id}" data-lat="{b['latitude'] or ''}" data-lon="{b['longitude'] or ''}" data-radio-type="{attr_escape(radio_type)}" data-vertical="{attr_escape(b.get('vertical', ''))}" data-opex="{opex_value}" data-valuation="{valuation_value}" data-carbon="{carbon_value}" data-sqft="{sqft_value}" data-tenant="{attr_escape(b.get('tenant', ''))}" data-sub-org="{attr_escape(b.get('tenant_sub_org', ''))}" onclick="window.location='buildings/{building_id}.html'">
    <div>{thumb}</div>
    <span class="stat-cell">{address_html}</span>
    <span class="stat-cell">{type_badge}</span>
    <span class="stat-cell">{sqft_display}</span>
    <span class="stat-cell">{eui_display}</span>
    <span class="stat-cell valuation-value">{fmt_money(valuation_value)}</span>
    <span class="stat-cell carbon-value">{format_carbon(carbon_value)}</span>
    <span class="stat-cell opex-value">{fmt_money(opex_value)}</span>
</div>'''

    def _generate_map_panel(self):
        """Generate the full map panel (slide-out drawer)."""
        return '''
<div id="map-panel" class="map-panel">
    <div class="map-panel-header">
        <div id="map-panel-title" style="display:flex;align-items:center;gap:12px;font-size:18px;font-weight:600;">All Buildings Map</div>
        <div class="map-panel-actions">
            <button class="map-panel-reset" onclick="resetMap()" title="Reset map to default view">Reset</button>
            <button class="map-panel-close" onclick="closeMapPanel()">&times;</button>
        </div>
    </div>
    <div style="padding: 12px 20px;">
        <input type="text" id="addressAutocomplete" placeholder="Enter an address" style="width: 100%; padding: 0.75rem; border: 1px solid #ccc; border-radius: 4px; font-size: 1rem;">
    </div>
    <div id="full-map"></div>
    <div id="climate-legend" style="
        position: absolute;
        bottom: 30px;
        left: 10px;
        background: rgba(255,255,255,0.95);
        padding: 10px 12px;
        border-radius: 6px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15);
        font-size: 11px;
        z-index: 1;
        transition: opacity 0.3s;
    ">
        <div style="font-weight:600;margin-bottom:6px;">IECC Climate Zone</div>
        <div style="display:flex;flex-direction:column;gap:3px;">
            <div><span style="display:inline-block;width:14px;height:14px;background:#ff4444;border-radius:2px;vertical-align:middle;margin-right:6px;"></span>1 - Very Hot</div>
            <div><span style="display:inline-block;width:14px;height:14px;background:#ff8844;border-radius:2px;vertical-align:middle;margin-right:6px;"></span>2 - Hot</div>
            <div><span style="display:inline-block;width:14px;height:14px;background:#ffcc44;border-radius:2px;vertical-align:middle;margin-right:6px;"></span>3 - Warm</div>
            <div><span style="display:inline-block;width:14px;height:14px;background:#88cc44;border-radius:2px;vertical-align:middle;margin-right:6px;"></span>4 - Mixed</div>
            <div><span style="display:inline-block;width:14px;height:14px;background:#44cc88;border-radius:2px;vertical-align:middle;margin-right:6px;"></span>5 - Cool</div>
            <div><span style="display:inline-block;width:14px;height:14px;background:#4488cc;border-radius:2px;vertical-align:middle;margin-right:6px;"></span>6 - Cold</div>
            <div><span style="display:inline-block;width:14px;height:14px;background:#4444cc;border-radius:2px;vertical-align:middle;margin-right:6px;"></span>7 - Very Cold</div>
            <div><span style="display:inline-block;width:14px;height:14px;background:#8844cc;border-radius:2px;vertical-align:middle;margin-right:6px;"></span>8 - Subarctic</div>
        </div>
    </div>
</div>'''

    # =========================================================================
    # SCRIPTS
    # =========================================================================

    def _generate_scripts(self):
        """Generate all JavaScript code."""
        return f'''
<!-- Load data from external files -->
<script src="data/portfolio_cards.js"></script>
<script src="data/portfolio_buildings.js"></script>
<!-- map_data.js is loaded on-demand when map is opened -->

<script>
// =============================================================================
// CONFIGURATION
// =============================================================================

const CONFIG = {{
    awsBucket: '{self.config["aws_bucket"]}',
    mapboxToken: '{self.config["mapbox_token"]}'
}};

// Track which portfolios have had rows rendered
const loadedPortfolios = new Set();

// =============================================================================
// TAB NAVIGATION
// =============================================================================

function initTabs() {{
    document.querySelectorAll('.main-tab').forEach(tab => {{
        tab.addEventListener('click', function() {{
            const tabId = this.dataset.tab;

            // Update tab buttons
            document.querySelectorAll('.main-tab').forEach(t => t.classList.remove('active'));
            this.classList.add('active');

            // Update tab content
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.getElementById(tabId + '-tab').classList.add('active');
        }});
    }});
}}

// Switch main tab (called from tab buttons)
function switchMainTab(tabId) {{
    // Update tab buttons
    document.querySelectorAll('.main-tab').forEach(t => {{
        t.classList.toggle('active', t.dataset.tab === tabId);
    }});

    // Toggle body class to hide/show sidebar
    document.body.classList.toggle('all-buildings-active', tabId === 'all-buildings');

    // Show/hide tab content
    document.getElementById('portfolios-tab').style.display = tabId === 'portfolios' ? 'block' : 'none';
    document.getElementById('all-buildings-tab').style.display = tabId === 'all-buildings' ? 'block' : 'none';

    // Initialize All Buildings tab on first view
    if (tabId === 'all-buildings' && !window.allBuildingsInitialized) {{
        initAllBuildingsTable();
        window.allBuildingsInitialized = true;
    }}
}}

// =============================================================================
// ALL BUILDINGS TAB
// =============================================================================

let allBuildingsData = [];
let filteredBuildingsData = [];
let abCurrentIndex = 0;
const AB_BATCH_SIZE = 100;
let abSortColumn = 'opex';
let abSortDirection = 'desc';
let abInfiniteScrollObserver = null;
let abSearchTimeout = null;
let selectedCityFilter = null;

function initAllBuildingsTable() {{
    const container = document.getElementById('cities-list');
    container.innerHTML = '<div style="text-align:center;padding:40px;color:#666;">Loading buildings...</div>';

    if (EXPORT_DATA && EXPORT_DATA.length > 0) {{
        onAllBuildingsDataLoaded();
    }} else {{
        const script = document.createElement('script');
        script.src = 'data/export_data.js';
        script.onload = onAllBuildingsDataLoaded;
        script.onerror = function() {{
            container.innerHTML = '<div style="text-align:center;padding:40px;color:#c00;">Failed to load building data</div>';
        }};
        document.head.appendChild(script);
    }}
}}

function onAllBuildingsDataLoaded() {{
    allBuildingsData = EXPORT_DATA;
    // Apply any existing global search filter
    doFilterAllBuildings();
    setupAbInfiniteScroll();
    updateSortIndicators();
}}

function renderAllBuildingsBatch() {{
    const container = document.getElementById('cities-list');
    const trigger = document.getElementById('ab-loading-trigger');

    if (filteredBuildingsData.length === 0) {{
        container.innerHTML = '<div style="text-align:center;padding:40px;color:#666;">No buildings found</div>';
        trigger.style.display = 'none';
        return;
    }}

    const endIndex = Math.min(abCurrentIndex + AB_BATCH_SIZE, filteredBuildingsData.length);
    const fragment = document.createDocumentFragment();

    for (let i = abCurrentIndex; i < endIndex; i++) {{
        const b = filteredBuildingsData[i];
        const row = createAllBuildingsRow(b);
        fragment.appendChild(row);
    }}

    container.appendChild(fragment);
    abCurrentIndex = endIndex;

    if (abCurrentIndex >= filteredBuildingsData.length) {{
        trigger.style.display = 'none';
    }} else {{
        trigger.textContent = `Loading more... (${{abCurrentIndex.toLocaleString()}} of ${{filteredBuildingsData.length.toLocaleString()}})`;
        trigger.style.display = 'block';
    }}
}}

function createAllBuildingsRow(b) {{
    const row = document.createElement('div');
    row.className = 'cities-row';
    row.onclick = function() {{ window.location = 'buildings/' + b.id + '.html'; }};

    const thumb = b.image
        ? `<img src="${{CONFIG.awsBucket}}/thumbnails/${{b.image}}" alt="" class="building-thumb" loading="lazy" onerror="this.style.display='none'">`
        : '<div class="building-thumb-placeholder">🏢</div>';

    const sqft = formatNumber(b.sqft || 0);
    const opex = formatMoney(b.opex || 0);
    const eui = formatEuiRating(b.site_eui, b.eui_benchmark);
    const propertyName = b.property_name || '';

    // Strip zip code from address (remove trailing 5-digit or 5+4 zip)
    let addrClean = (b.address || '').replace(/,?\s*\d{{5}}(-\d{{4}})?$/, '').trim();

    row.innerHTML = `
        <div>${{thumb}}</div>
        <div class="addr"><span class="addr-main">${{escapeHtml(addrClean)}}</span><span class="addr-sub">${{escapeHtml(propertyName)}}</span></div>
        <div class="cell">${{escapeHtml(b.type || '-')}}</div>
        <div class="cell">${{sqft}}</div>
        <div class="cell">${{eui}}</div>
        <div class="cell">${{escapeHtml(b.owner || '-')}}</div>
        <div class="cell">${{escapeHtml(b.tenant || '-')}}</div>
        <div class="cell">${{escapeHtml(b.property_manager || '-')}}</div>
        <div class="cell">${{opex}}</div>
    `;

    return row;
}}

function setupAbInfiniteScroll() {{
    const trigger = document.getElementById('ab-loading-trigger');
    const wrapper = document.getElementById('cities-rows');

    if (abInfiniteScrollObserver) {{
        abInfiniteScrollObserver.disconnect();
    }}

    abInfiniteScrollObserver = new IntersectionObserver((entries) => {{
        if (entries[0].isIntersecting && abCurrentIndex < filteredBuildingsData.length) {{
            renderAllBuildingsBatch();
        }}
    }}, {{ root: wrapper, threshold: 0.1 }});

    abInfiniteScrollObserver.observe(trigger);
}}

// Debounced filter function
function filterAllBuildings() {{
    clearTimeout(abSearchTimeout);
    abSearchTimeout = setTimeout(doFilterAllBuildings, 150);
}}

function doFilterAllBuildings() {{
    // Filter by selected city card AND global search
    filteredBuildingsData = allBuildingsData.filter(b => {{
        // City filter
        if (selectedCityFilter && b.city !== selectedCityFilter) return false;

        // Global search filter
        if (globalQuery) {{
            const searchFields = [
                b.address || '',
                b.city || '',
                b.state || '',
                b.type || '',
                b.owner || ''
            ].join(' ').toLowerCase();
            if (!searchFields.includes(globalQuery)) return false;
        }}
        return true;
    }});

    // Apply current sort
    sortFilteredBuildings();

    // Reset and re-render
    abCurrentIndex = 0;
    document.getElementById('cities-list').innerHTML = '';
    renderAllBuildingsBatch();

    // Update stats
    updateAllBuildingsStats();
}}

function filterByCity(city) {{
    // Check if this city is already selected - click to deselect
    const currentlySelected = document.querySelector('.city-filter-card.selected');
    const isAlreadySelected = currentlySelected &&
        currentlySelected.querySelector('strong')?.textContent === city;

    if (isAlreadySelected) {{
        // Deselect - show all buildings
        selectedCityFilter = null;
        document.querySelectorAll('.city-filter-card').forEach(c => c.classList.remove('selected'));
        doFilterAllBuildings();
        return;
    }}

    // Select this city
    selectedCityFilter = city;
    document.querySelectorAll('.city-filter-card').forEach(c => {{
        c.classList.remove('selected');
        if (c.querySelector('strong')?.textContent === city) {{
            c.classList.add('selected');
        }}
    }});

    doFilterAllBuildings();
}}

function clearAllBuildingsFilters() {{
    // Clear city card selection (but keep global search)
    selectedCityFilter = null;
    document.querySelectorAll('.city-filter-card').forEach(c => c.classList.remove('selected'));

    // Re-filter (will still respect global search)
    doFilterAllBuildings();
}}

function sortAllBuildings(column) {{
    if (abSortColumn === column) {{
        abSortDirection = abSortDirection === 'asc' ? 'desc' : 'asc';
    }} else {{
        abSortColumn = column;
        abSortDirection = column === 'opex' || column === 'carbon' || column === 'sqft' || column === 'eui' ? 'desc' : 'asc';
    }}

    updateSortIndicators();
    sortFilteredBuildings();
    abCurrentIndex = 0;
    document.getElementById('cities-list').innerHTML = '';
    renderAllBuildingsBatch();
}}

function updateSortIndicators() {{
    // Remove all sort classes
    document.querySelectorAll('.ab-table th').forEach(th => {{
        th.classList.remove('sort-asc', 'sort-desc');
    }});

    // Add sort class to current column
    const currentTh = document.querySelector(`.ab-table th[onclick*="${{abSortColumn}}"]`);
    if (currentTh) {{
        currentTh.classList.add(abSortDirection === 'asc' ? 'sort-asc' : 'sort-desc');
    }}
}}

function sortFilteredBuildings() {{
    const col = abSortColumn;
    const dir = abSortDirection === 'asc' ? 1 : -1;

    filteredBuildingsData.sort((a, b) => {{
        let valA = col === 'eui' ? (a.site_eui || 0) : (a[col] || '');
        let valB = col === 'eui' ? (b.site_eui || 0) : (b[col] || '');

        if (typeof valA === 'number' && typeof valB === 'number') {{
            return (valA - valB) * dir;
        }}
        return String(valA).localeCompare(String(valB)) * dir;
    }});
}}

function updateAllBuildingsStats() {{
    // Calculate total OpEx for filtered buildings
    const totalOpex = filteredBuildingsData.reduce((sum, b) => sum + (b.opex || 0), 0);
    const totalEl = document.getElementById('cities-total-opex');
    if (totalEl) {{
        totalEl.textContent = '(' + formatMoney(totalOpex) + ')';
    }}
}}

function formatMoney(n) {{
    if (n >= 1000000000) return '$' + (n / 1000000000).toFixed(1) + 'B';
    if (n >= 1000000) return '$' + Math.round(n / 1000000) + 'M';
    if (n >= 1000) return '$' + Math.round(n / 1000) + 'K';
    return '$' + Math.round(n);
}}

function formatNumber(n) {{
    if (n >= 1000000000) return (n / 1000000000).toFixed(1) + 'B';
    if (n >= 1000000) return Math.round(n / 1000000) + 'M';
    if (n >= 1000) return Math.round(n / 1000) + 'K';
    return n.toLocaleString();
}}

function formatCarbon(n) {{
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return Math.round(n / 1000) + 'K';
    return Math.round(n);
}}

function escapeHtml(str) {{
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}}

// =============================================================================
// FILTERS - OPTIMIZED
// =============================================================================

let activeVertical = 'all';
let selectedBuildingType = null;
let mapUpdateTimeout = null;

function applyFilters() {{
    const cards = document.querySelectorAll('.portfolio-card');
    const container = document.getElementById('portfolios-list');
    if (!container) return;

    const visible = [];
    let totalOpex = 0;
    let totalValuation = 0;
    let totalCarbon = 0;

    cards.forEach(card => {{
        const idx = parseInt(card.dataset.idx);
        let buildings = PORTFOLIO_BUILDINGS[idx] || [];

        // Filter by building type
        if (selectedBuildingType) {{
            buildings = buildings.filter(b => b.type === selectedBuildingType);
        }}
        // Filter by vertical
        if (activeVertical !== 'all') {{
            buildings = buildings.filter(b => b.vertical === activeVertical);
        }}
        // Filter by search
        if (globalQuery) {{
            const orgName = (card.dataset.org || '').toLowerCase();
            if (!orgName.includes(globalQuery)) {{
                buildings = [];
            }}
        }}

        if (buildings.length === 0) {{
            card.classList.add('hidden');
        }} else {{
            card.classList.remove('hidden');
            const opex = buildings.reduce((s, b) => s + (b.opex || 0), 0);
            const valuation = buildings.reduce((s, b) => s + (b.valuation || 0), 0);
            const carbon = buildings.reduce((s, b) => s + (b.carbon || 0), 0);
            const sqft = buildings.reduce((s, b) => s + (b.sqft || 0), 0);

            // Update card display
            const countEl = card.querySelector('.building-count-value');
            const opexEl = card.querySelector('.opex-value');
            const valEl = card.querySelector('.valuation-value');
            const carbonEl = card.querySelector('.carbon-value');
            const sqftEl = card.querySelector('.sqft-value');

            if (countEl) countEl.textContent = buildings.length.toLocaleString();
            if (opexEl) opexEl.textContent = formatMoneyJS(opex);
            if (valEl) valEl.textContent = formatMoneyJS(valuation);
            if (carbonEl) carbonEl.textContent = formatCarbonJS(carbon);
            if (sqftEl) sqftEl.textContent = formatSqftJS(sqft);

            visible.push({{ card, opex }});
            totalOpex += opex;
            totalValuation += valuation;
            totalCarbon += carbon;
        }}
    }});

    // Sort by opex descending and reorder DOM
    visible.sort((a, b) => b.opex - a.opex);
    visible.forEach(v => container.appendChild(v.card));

    // Update counts
    const countEl = document.getElementById('visible-count');
    if (countEl) countEl.textContent = visible.length;

    // Update rollup stats
    const rollupValEl = document.getElementById('rollup-valuation');
    const rollupCarbonEl = document.getElementById('rollup-carbon');
    const rollupOpexEl = document.getElementById('rollup-opex');
    if (rollupValEl) rollupValEl.textContent = formatMoneyJS(totalValuation);
    if (rollupCarbonEl) rollupCarbonEl.textContent = formatCarbonJS(totalCarbon);
    if (rollupOpexEl) rollupOpexEl.textContent = formatMoneyJS(totalOpex);

    // Re-render expanded portfolio
    const expanded = document.querySelector('.portfolio-card.expanded');
    if (expanded) loadPortfolioRows(expanded);
}}

function selectVertical(v) {{
    activeVertical = v;
    document.querySelectorAll('.vertical-btn').forEach(b => {{
        b.classList.toggle('selected', b.dataset.vertical === v);
    }});
    // Show/hide building type buttons based on vertical
    document.querySelectorAll('.building-type-btn').forEach(btn => {{
        const btnVertical = btn.dataset.vertical || '';
        if (v === 'all' || btnVertical === v) {{
            btn.classList.remove('hidden');
        }} else {{
            btn.classList.add('hidden');
            btn.classList.remove('selected');
        }}
    }});
    // Clear building type if it was hidden
    const selected = document.querySelector('.building-type-btn.selected:not(.hidden)');
    selectedBuildingType = selected ? selected.dataset.type : null;
    applyFilters();
}}

function toggleBuildingType(btn) {{
    const wasSelected = btn.classList.contains('selected');
    document.querySelectorAll('.building-type-btn').forEach(b => b.classList.remove('selected'));
    if (!wasSelected) {{
        btn.classList.add('selected');
        selectedBuildingType = btn.dataset.type;
    }} else {{
        selectedBuildingType = null;
    }}
    applyFilters();

    // Update filter chip
    const chip = document.getElementById('building-type-chip');
    if (chip) {{
        if (selectedBuildingType) {{
            chip.querySelector('.chip-text').textContent = selectedBuildingType;
            chip.classList.add('visible');
        }} else {{
            chip.classList.remove('visible');
        }}
    }}

    // Auto-close drawer after selection with brief delay to show feedback
    setTimeout(() => {{
        const drawer = document.getElementById('filter-drawer');
        if (drawer && drawer.classList.contains('open')) {{
            drawer.classList.remove('open');
            document.body.classList.remove('filter-drawer-open');
        }}
    }}, 400);
}}

function clearBuildingTypeFilter() {{
    document.querySelectorAll('.building-type-btn').forEach(b => b.classList.remove('selected'));
    selectedBuildingType = null;
    const chip = document.getElementById('building-type-chip');
    if (chip) chip.classList.remove('visible');
    applyFilters();
}}

function applyMainTableFilters() {{
    const mainTableBody = document.getElementById('main-table-body');
    if (!mainTableBody) return;

    const cityFilterEl = document.getElementById('city-filter');
    const typeFilterEl = document.getElementById('type-filter');
    const cityFilter = cityFilterEl ? cityFilterEl.value : 'all';
    const typeFilter = typeFilterEl ? typeFilterEl.value : 'all';

    const rows = mainTableBody.querySelectorAll('.building-row');
    let visible = 0;

    rows.forEach(row => {{
        const city = row.dataset.city || '';
        const type = row.dataset.type || '';
        const owner = (row.dataset.owner || '').toLowerCase();
        const manager = (row.dataset.manager || '').toLowerCase();
        const tenant = (row.dataset.tenant || '').toLowerCase();
        const subOrg = (row.dataset.subOrg || '').toLowerCase();
        const vertical = row.dataset.vertical || '';
        const radioType = row.dataset.radioType || '';
        const address = (row.cells[2]?.textContent || '').toLowerCase();

        const matchesVertical = activeVertical === 'all' || vertical === activeVertical;
        const matchesCity = cityFilter === 'all' || city === cityFilter;
        const matchesType = typeFilter === 'all' || type === typeFilter;
        const matchesOwner = !selectedOwner || owner.toLowerCase() === selectedOwner.toLowerCase();
        const matchesBuildingType = !selectedBuildingType || radioType === selectedBuildingType;

        const searchText = owner + ' ' + tenant + ' ' + subOrg + ' ' + manager + ' ' +
            city.toLowerCase() + ' ' + type.toLowerCase() + ' ' + address;
        const matchesSearch = !globalQuery || searchText.includes(globalQuery);

        if (matchesVertical && matchesCity && matchesType && matchesOwner && matchesSearch && matchesBuildingType) {{
            row.classList.remove('hidden');
            visible++;
        }} else {{
            row.classList.add('hidden');
        }}
    }});

    const visibleCountEl = document.getElementById('visible-count');
    if (visibleCountEl) visibleCountEl.textContent = visible;
}}

function scheduleMapUpdate() {{
    clearTimeout(mapUpdateTimeout);
    mapUpdateTimeout = setTimeout(() => {{
        const mapPanel = document.getElementById('map-panel');
        if (mapPanel && mapPanel.classList.contains('open')) {{
            updateMapData();
        }}
    }}, 300);
}}

function updatePortfolioStats() {{
    applyFilters();
}}

function formatMoneyJS(n) {{
    if (n >= 1000000000) return '$' + (n/1000000000).toFixed(1) + 'B';
    if (n >= 1000000) return '$' + Math.round(n/1000000) + 'M';
    if (n >= 1000) return '$' + Math.round(n/1000) + 'K';
    return '$' + Math.round(n);
}}

function formatCarbonJS(n) {{
    if (n >= 1000000) return (n/1000000).toFixed(1) + 'M';
    if (n >= 1000) return Math.round(n/1000) + 'K';
    return Math.round(n);
}}

function formatSqftJS(n) {{
    if (!n || n <= 0) return '-';
    if (n >= 1000000) return (n/1000000).toFixed(1) + 'M';
    if (n >= 10000) return Math.round(n/1000) + 'K';
    return Math.round(n).toLocaleString();
}}

function formatEuiRating(eui, benchmark) {{
    if (!eui) return '-';
    const euiRounded = Math.round(eui);
    if (!benchmark || benchmark === 0) return euiRounded;
    const ratio = eui / benchmark;
    if (ratio <= 1.0) return `<span class="eui-good">${{euiRounded}} (Good)</span>`;
    if (ratio <= 1.2) return `<span class="eui-ok">${{euiRounded}} (OK)</span>`;
    return `<span class="eui-bad">${{euiRounded}} (Bad)</span>`;
}}

function formatTypeBadge(type) {{
    if (!type) return '<span class="type-badge type-badge--gray-xlight">-</span>';
    const t = type.toLowerCase();
    let cls = 'type-badge--gray-light';
    if (t.includes('office') && !t.includes('medical')) cls = 'type-badge--blue';
    else if (t.includes('hotel')) cls = 'type-badge--blue-light';
    else if (t.includes('hospital') || t.includes('clinic')) cls = 'type-badge--blue';
    else if (t.includes('medical') || t.includes('lab')) cls = 'type-badge--blue-light';
    else if (t.includes('higher')) cls = 'type-badge--gray-dark';
    else if (t.includes('k-12') || t.includes('k12')) cls = 'type-badge--gray-mid';
    else if (t.includes('gym')) cls = 'type-badge--blue-light';
    else if (t.includes('retail') || t.includes('consumer')) cls = 'type-badge--gray-light';
    else if (t.includes('grocery') || t.includes('supercenter')) cls = 'type-badge--gray-mid';
    else if (t.includes('mall') || t.includes('strip')) cls = 'type-badge--gray-light';
    else if (t.includes('library') || t.includes('museum')) cls = 'type-badge--gray-dark';
    else if (t.includes('event')) cls = 'type-badge--gray-mid';
    else if (t.includes('mixed')) cls = 'type-badge--blue-light';
    else if (t.includes('residential') || t.includes('care')) cls = 'type-badge--gray-xlight';
    // Split on / for two lines
    const display = type.replace(/\\//g, '<br>');
    return `<span class="type-badge ${{cls}}">${{display}}</span>`;
}}

// Global search
let globalQuery = '';
let selectedOwner = '';
let searchMatchingIndices = null;  // null = show all, array = show only these
let filterTimeout = null;

function globalSearch(query) {{
    globalQuery = query.toLowerCase().trim();

    // Search ALL portfolios via PORTFOLIO_CARDS data
    if (!globalQuery) {{
        searchMatchingIndices = null;  // Show all
    }} else {{
        searchMatchingIndices = [];
        PORTFOLIO_CARDS.forEach(p => {{
            const orgMatch = (p.org_name || '').toLowerCase().includes(globalQuery);
            const displayMatch = (p.display_name || '').toLowerCase().includes(globalQuery);
            const tenantMatch = (p.tenants || []).some(t => t.toLowerCase().includes(globalQuery));
            const subOrgMatch = (p.tenant_sub_orgs || []).some(s => s.toLowerCase().includes(globalQuery));
            const ownerMatch = (p.owners || []).some(o => o.toLowerCase().includes(globalQuery));
            const managerMatch = (p.managers || []).some(m => m.toLowerCase().includes(globalQuery));

            if (orgMatch || displayMatch || tenantMatch || subOrgMatch || ownerMatch || managerMatch) {{
                searchMatchingIndices.push(p.idx);
            }}
        }});
    }}

    // Use debounced filter
    clearTimeout(filterTimeout);
    filterTimeout = setTimeout(() => {{
        requestAnimationFrame(() => {{
            applySearchResults();
            // Also filter All Buildings tab if initialized
            if (window.allBuildingsInitialized) {{
                doFilterAllBuildings();
            }}
        }});
    }}, 100);
}}

function applySearchResults() {{
    const container = document.getElementById('portfolios-list');
    if (!container) return;

    // Get all portfolio cards currently in DOM
    const existingCards = container.querySelectorAll('.portfolio-card');
    const existingIndices = new Set();
    existingCards.forEach(card => existingIndices.add(parseInt(card.dataset.idx)));

    if (searchMatchingIndices === null) {{
        // No search - show all existing cards
        existingCards.forEach(card => card.classList.remove('hidden'));
        // Update visible count
        const visibleCountEl = document.getElementById('visible-count');
        if (visibleCountEl) visibleCountEl.textContent = existingCards.length;
    }} else {{
        // Search active - show only matching cards
        const matchSet = new Set(searchMatchingIndices);

        // First, load any matching cards not in DOM yet
        searchMatchingIndices.forEach(idx => {{
            if (!existingIndices.has(idx)) {{
                const p = PORTFOLIO_CARDS[idx];
                if (p) {{
                    container.insertAdjacentHTML('beforeend', renderPortfolioCard(p));
                    existingIndices.add(idx);
                }}
            }}
        }});

        // Now show/hide cards based on match
        container.querySelectorAll('.portfolio-card').forEach(card => {{
            const idx = parseInt(card.dataset.idx);
            if (matchSet.has(idx)) {{
                card.classList.remove('hidden');
            }} else {{
                card.classList.add('hidden');
            }}
        }});

        // Update visible count
        const visibleCountEl = document.getElementById('visible-count');
        if (visibleCountEl) visibleCountEl.textContent = searchMatchingIndices.length;
    }}
    applyFilters();
}}

// Filter by building type (called from table clicks)
function filterByType(type) {{
    // Find and click the matching building type button
    const btn = document.querySelector(`.building-type-btn[data-type="${{type}}"]`);
    if (btn && !btn.classList.contains('hidden')) {{
        toggleBuildingType(btn);
    }}
}}

// Filter portfolios by city (called from table clicks)
function filterPortfoliosByCity(city) {{
    // Put city in search box
    const searchBox = document.getElementById('global-search');
    if (searchBox) {{
        searchBox.value = city;
        globalSearch(city);
    }}
}}

// Filter by owner (called from table clicks)
function filterByOwner(owner) {{
    // Put owner in search box
    const searchBox = document.getElementById('global-search');
    if (searchBox) {{
        searchBox.value = owner;
        globalSearch(owner);
    }}
}}

// Legacy function - redirects to optimized version
function applyAllFilters() {{
    applyFilters();
}}

function updateFilterChips() {{
    const container = document.getElementById('filter-chips');
    let chips = '';

    if (selectedOwner) {{
        chips += `<span class="filter-chip">${{selectedOwner}} <span class="remove" onclick="clearOwnerFilter()">✕</span></span>`;
    }}

    container.innerHTML = chips;
}}

function clearOwnerFilter() {{
    selectedOwner = '';
    document.querySelectorAll('.opp-tile').forEach(t => t.classList.remove('selected'));
    updateFilterChips();
    applyAllFilters();
}}

function clearAllFilters() {{
    activeVertical = 'all';
    selectedOwner = '';
    globalQuery = '';
    selectedBuildingType = null;

    // Reset vertical buttons
    document.querySelectorAll('.vertical-btn').forEach(b => b.classList.remove('selected'));
    document.querySelector('.vertical-btn[data-vertical="all"]')?.classList.add('selected');
    // Reset building type buttons
    document.querySelectorAll('.building-type-btn').forEach(b => {{
        b.classList.remove('selected');
        b.classList.remove('hidden');
    }});

    const cityFilter = document.getElementById('city-filter');
    const typeFilter = document.getElementById('type-filter');
    if (cityFilter) cityFilter.value = 'all';
    if (typeFilter) typeFilter.value = 'all';
    const searchEl = document.getElementById('global-search');
    if (searchEl) searchEl.value = '';
    document.querySelectorAll('.opp-tile').forEach(t => t.classList.remove('selected'));

    updateFilterChips();
    applyFilters();
}}

// =============================================================================
// CSV EXPORT FUNCTIONS
// =============================================================================

// Toggle export dropdown menu
function toggleExportMenu(event) {{
    event.stopPropagation();
    const menu = document.getElementById('export-menu');
    menu.classList.toggle('show');

    // Close menu when clicking elsewhere
    const closeMenu = (e) => {{
        if (!e.target.closest('.export-dropdown')) {{
            menu.classList.remove('show');
            document.removeEventListener('click', closeMenu);
        }}
    }};
    document.addEventListener('click', closeMenu);
}}

// Load export data on demand
let EXPORT_DATA = null;

function loadAllBuildingsForExport() {{
    return new Promise((resolve) => {{
        if (EXPORT_DATA) {{
            resolve(EXPORT_DATA);
            return;
        }}

        // Load via script tag (works with file:// protocol)
        const script = document.createElement('script');
        script.src = 'data/export_data.js';
        script.onload = () => {{
            resolve(EXPORT_DATA);
        }};
        script.onerror = () => {{
            resolve([]);
        }};
        document.head.appendChild(script);
    }});
}}

// Helper: Download CSV
function downloadCSV(rows, filename) {{
    const csv = rows.map(r => r.map(c => '"' + String(c).replace(/"/g, '""') + '"').join(',')).join('\\n');
    const blob = new Blob([csv], {{ type: 'text/csv;charset=utf-8;' }});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    document.getElementById('export-menu').classList.remove('show');
}}

// Export All Buildings - NOW LOADS DATA ON DEMAND
async function exportAllBuildingsCSV() {{
    // Load data on demand when user clicks export
    const data = await loadAllBuildingsForExport();
    if (!data || !data.length) {{ alert('Failed to load data for export.'); return; }}

    const headers = ['Rank', 'Address', 'City', 'State', 'Building Type', 'Owner', 'Square Footage', 'Year Built', 'OpEx Savings ($)', 'Valuation Impact ($)', 'Carbon Reduction (tCO2e)', 'Site EUI', 'Vertical'];
    const rows = [headers];

    data.forEach((b, i) => {{
        rows.push([
            i + 1,
            b.address,
            b.city,
            b.state,
            b.type,
            b.owner,
            b.sqft,
            b.year_built || '',
            (b.opex || 0).toFixed(2),
            (b.valuation || 0).toFixed(2),
            (b.carbon || 0).toFixed(2),
            b.site_eui ? b.site_eui.toFixed(1) : '',
            b.vertical
        ]);
    }});

    downloadCSV(rows, 'all_buildings.csv');
}}

// Export Filtered Results (visible rows from the table)
function exportFilteredCSV() {{
    const headers = ['Rank', 'Address', 'City', 'Building Type', 'Owner', 'OpEx Savings', 'Carbon Reduction'];
    const rows = [headers];

    document.querySelectorAll('#main-table-body .building-row:not(.hidden)').forEach(row => {{
        rows.push([
            row.dataset.rank,
            row.cells[2]?.textContent?.split('\\n')[0]?.trim() || '',
            row.dataset.city,
            row.dataset.type,
            row.dataset.owner,
            row.cells[6]?.textContent?.trim() || '',
            row.cells[7]?.textContent?.trim() || ''
        ]);
    }});

    downloadCSV(rows, 'filtered_buildings.csv');
}}

// Export Portfolio Summaries
function exportPortfolioCSV() {{
    const headers = ['Organization', 'Building Count', 'Classification', 'Total OpEx Savings ($)', 'Total Valuation Impact ($)', 'Total Carbon Reduction (tCO2e)', 'Median EUI', 'Verticals'];
    const rows = [headers];

    PORTFOLIO_CARDS.forEach(p => {{
        rows.push([
            p.org_name || p.display_name || '',
            p.building_count || 0,
            p.classification || '',
            (p.total_opex || 0).toFixed(2),
            (p.total_valuation || 0).toFixed(2),
            (p.total_carbon || 0).toFixed(2),
            p.median_eui ? p.median_eui.toFixed(1) : '',
            Array.isArray(p.verticals) ? p.verticals.join(', ') : (p.verticals || '')
        ]);
    }});

    downloadCSV(rows, 'portfolio_summaries.csv');
}}

// Legacy export functions (kept for backward compatibility)
function exportTableCSV() {{ exportFilteredCSV(); }}
function exportCSV() {{ exportPortfolioCSV(); }}

// =============================================================================
// PORTFOLIO SORTING
// =============================================================================

let portfolioSortDir = {{}};
window.sortPortfolios = function(col) {{
    const container = document.getElementById('portfolios-list');
    const cards = Array.from(container.querySelectorAll('.portfolio-card'));
    portfolioSortDir[col] = !portfolioSortDir[col];

    cards.sort((a, b) => {{
        let aVal, bVal;
        if (col === 'name') {{
            aVal = (a.getAttribute('data-org') || '').toLowerCase();
            bVal = (b.getAttribute('data-org') || '').toLowerCase();
        }} else if (col === 'buildings') {{
            aVal = parseInt(a.getAttribute('data-buildings')) || 0;
            bVal = parseInt(b.getAttribute('data-buildings')) || 0;
        }} else if (col === 'sqft') {{
            aVal = parseFloat(a.getAttribute('data-sqft')) || 0;
            bVal = parseFloat(b.getAttribute('data-sqft')) || 0;
        }} else if (col === 'eui') {{
            aVal = parseFloat(a.getAttribute('data-eui')) || 0;
            bVal = parseFloat(b.getAttribute('data-eui')) || 0;
        }} else if (col === 'opex') {{
            aVal = parseFloat(a.getAttribute('data-opex')) || 0;
            bVal = parseFloat(b.getAttribute('data-opex')) || 0;
        }} else if (col === 'valuation') {{
            aVal = parseFloat(a.getAttribute('data-valuation')) || 0;
            bVal = parseFloat(b.getAttribute('data-valuation')) || 0;
        }} else if (col === 'carbon') {{
            aVal = parseFloat(a.getAttribute('data-carbon')) || 0;
            bVal = parseFloat(b.getAttribute('data-carbon')) || 0;
        }} else if (col === 'classification') {{
            aVal = (a.getAttribute('data-classification') || '').toLowerCase();
            bVal = (b.getAttribute('data-classification') || '').toLowerCase();
        }}
        return portfolioSortDir[col] ? (aVal > bVal ? 1 : -1) : (aVal < bVal ? 1 : -1);
    }});

    container.innerHTML = '';
    cards.forEach(card => container.appendChild(card));
}};

// =============================================================================
// FILTER DRAWER TOGGLE
// =============================================================================

function toggleFilterDrawer() {{
    const drawer = document.getElementById('filter-drawer');
    drawer.classList.toggle('open');
    document.body.classList.toggle('filter-drawer-open');
}}

// =============================================================================
// PORTFOLIO EXPANSION
// =============================================================================

function togglePortfolio(header) {{
    const card = header.closest('.portfolio-card');

    // Collapse all other expanded portfolios (only one open at a time)
    document.querySelectorAll('.portfolio-card.expanded').forEach(c => {{
        if (c !== card) c.classList.remove('expanded');
    }});

    card.classList.toggle('expanded');

    // Load rows ONLY when expanding (not collapsing)
    if (card.classList.contains('expanded')) {{
        loadPortfolioRows(card);  // Renders rows + sets up lazy image loading
        // Capture the portfolio logo URL for map popups
        const logoImg = card.querySelector('.portfolio-header .org-logo');
        expandedPortfolioLogo = logoImg ? logoImg.src : null;
    }} else {{
        expandedPortfolioLogo = null;
    }}

    // Update map if it's open (show portfolio buildings or all buildings)
    if (document.getElementById('map-panel').classList.contains('open')) {{
        updateMapData();
        updateMapTitle();
    }}

}}

// =============================================================================
// STICKY HEADER ORG NAME - shows org name when scrolling through expanded portfolio
// =============================================================================

function updateStickyOrgName() {{
    const headerOrgCol = document.getElementById('header-org-col');
    if (!headerOrgCol) return;

    const expanded = document.querySelector('.portfolio-card.expanded');
    if (!expanded) {{
        headerOrgCol.textContent = '';
        return;
    }}

    const sortHeader = document.querySelector('.portfolio-sort-header');
    const sortHeaderBottom = sortHeader.getBoundingClientRect().bottom;
    const portfolioHeader = expanded.querySelector('.portfolio-header');
    const portfolioHeaderBottom = portfolioHeader.getBoundingClientRect().bottom;

    const portfolioCardBottom = expanded.getBoundingClientRect().bottom;

    // Show org name only when: header scrolled off AND still viewing buildings
    if (portfolioHeaderBottom < sortHeaderBottom && portfolioCardBottom > sortHeaderBottom) {{
        const orgNameSpan = expanded.querySelector('.org-name-small');
        const displayName = orgNameSpan ? orgNameSpan.getAttribute('title') : '';
        headerOrgCol.textContent = displayName;
    }} else {{
        headerOrgCol.textContent = '';
    }}
}}

window.addEventListener('scroll', updateStickyOrgName, {{ passive: true }});

// =============================================================================
// ADDRESS SEARCH (NYC-style with 200ft radius)
// =============================================================================

let addressMarker = null;
let searchMarkers = [];
let selectedAddressLocation = null;
const SEARCH_RADIUS_METERS = 61; // 200 feet in meters

// Setup Google Places Autocomplete - simple like /Users/forrestmiller/Desktop/index.html
function setupAddressSearch() {{
    const input = document.getElementById('addressAutocomplete');
    if (!input) return;

    if (typeof google !== 'undefined' && google.maps && google.maps.places) {{
        const autocomplete = new google.maps.places.Autocomplete(input, {{
            types: ['address'],
            componentRestrictions: {{ country: 'us' }}
        }});

        autocomplete.addListener('place_changed', function() {{
            const place = autocomplete.getPlace();
            if (place && place.geometry) {{
                const lat = place.geometry.location.lat();
                const lng = place.geometry.location.lng();
                showNearbyBuildings(lat, lng);
            }}
        }});
    }}
}}

// Haversine distance in meters
function haversineMeters(lat1, lon1, lat2, lon2) {{
    const R = 6371000; // Earth radius in meters
    const toRad = (d) => d * Math.PI / 180;
    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a = Math.sin(dLat/2)**2 + Math.cos(toRad(lat1))*Math.cos(toRad(lat2))*Math.sin(dLon/2)**2;
    return 2 * R * Math.asin(Math.sqrt(a));
}}

// Create GeoJSON circle for radius visualization
function createGeoJSONCircle(center, radiusInKm, points = 64) {{
    const coords = {{ latitude: center[1], longitude: center[0] }};
    const km = radiusInKm;
    const ret = [];
    const distanceX = km / (111.320 * Math.cos(coords.latitude * Math.PI / 180));
    const distanceY = km / 110.574;
    for (let i = 0; i < points; i++) {{
        const theta = (i / points) * (2 * Math.PI);
        const x = distanceX * Math.cos(theta);
        const y = distanceY * Math.sin(theta);
        ret.push([coords.longitude + x, coords.latitude + y]);
    }}
    ret.push(ret[0]);
    return {{ type: 'Feature', geometry: {{ type: 'Polygon', coordinates: [ret] }} }};
}}

// Find and display nearby buildings
function showNearbyBuildings(lat, lng) {{
    // Wait for map to be ready (like NYC implementation)
    const waitForMapAndShow = () => {{
        if (fullMap && fullMap.isStyleLoaded()) {{
            doShowNearbyBuildings(lat, lng);
        }} else if (fullMap) {{
            fullMap.once('load', () => doShowNearbyBuildings(lat, lng));
        }} else {{
            // Map not initialized yet, try again in 100ms
            setTimeout(waitForMapAndShow, 100);
        }}
    }};

    if (!fullMap) {{
        initFullMap();
        waitForMapAndShow();
        return;
    }}

    if (!fullMap.isStyleLoaded()) {{
        fullMap.once('load', () => doShowNearbyBuildings(lat, lng));
        return;
    }}

    doShowNearbyBuildings(lat, lng);
}}

function doShowNearbyBuildings(lat, lng) {{
    if (!fullMap) return;

    // Clear existing markers
    searchMarkers.forEach(m => m.remove());
    searchMarkers = [];
    if (addressMarker) {{
        addressMarker.remove();
        addressMarker = null;
    }}

    // Remove existing radius circle
    if (fullMap.getLayer('radius-circle-layer')) {{
        fullMap.removeLayer('radius-circle-layer');
    }}
    if (fullMap.getSource('radius-circle')) {{
        fullMap.removeSource('radius-circle');
    }}

    // Add 200ft radius circle
    const circleFeature = createGeoJSONCircle([lng, lat], SEARCH_RADIUS_METERS / 1000);
    fullMap.addSource('radius-circle', {{
        type: 'geojson',
        data: {{ type: 'FeatureCollection', features: [circleFeature] }}
    }});
    fullMap.addLayer({{
        id: 'radius-circle-layer',
        type: 'fill',
        source: 'radius-circle',
        paint: {{
            'fill-color': '#1b95ff',
            'fill-opacity': 0.15
        }}
    }});

    // Calculate distances for all buildings (MAP_DATA loaded on demand)
    if (!MAP_DATA) {{ return; }}
    const buildingsWithDistance = MAP_DATA.map(b => {{
        const dist = haversineMeters(lat, lng, b.lat, b.lon);
        return {{ ...b, distance: dist }};
    }}).sort((a, b) => a.distance - b.distance);

    // Find buildings within 200ft (61 meters)
    const nearbyBuildings = buildingsWithDistance.filter(b => b.distance <= SEARCH_RADIUS_METERS);

    if (nearbyBuildings.length > 0) {{
        // Show buildings within radius as blue pins
        nearbyBuildings.forEach((b, idx) => {{
            const el = document.createElement('div');
            el.style.cssText = 'width:20px;height:20px;background:#0066cc;border-radius:50%;border:3px solid white;cursor:pointer;box-shadow:0 2px 6px rgba(0,0,0,0.3);';

            const popup = new mapboxgl.Popup({{ offset: 25 }}).setHTML(`
                <div style="padding:8px;">
                    <h4 style="margin:0 0 4px 0;font-size:14px;">${{b.address}}</h4>
                    <p style="margin:0 0 8px 0;color:#666;font-size:12px;">${{b.city}}, ${{b.state}} • ${{b.type}}</p>
                    <div style="font-size:12px;">
                        <div><strong>Distance:</strong> ${{(b.distance * 3.28084).toFixed(0)}} ft</div>
                        <div><strong>OpEx Savings:</strong> ${{formatMoney(b.total_opex)}}/yr</div>
                    </div>
                </div>
            `);

            const marker = new mapboxgl.Marker(el)
                .setLngLat([b.lon, b.lat])
                .setPopup(popup)
                .addTo(fullMap);

            searchMarkers.push(marker);
        }});

        // Fly to center of results
        if (nearbyBuildings.length === 1) {{
            fullMap.flyTo({{ center: [nearbyBuildings[0].lon, nearbyBuildings[0].lat], zoom: 18 }});
        }} else {{
            const bounds = new mapboxgl.LngLatBounds();
            nearbyBuildings.forEach(b => bounds.extend([b.lon, b.lat]));
            fullMap.fitBounds(bounds, {{ padding: 60, maxZoom: 18 }});
        }}
    }} else {{
        // No buildings within 200ft - show 10 nearest as blue pins
        const nearest = buildingsWithDistance.slice(0, 10);

        nearest.forEach((b, idx) => {{
            const el = document.createElement('div');
            el.style.cssText = 'width:16px;height:16px;background:#0066cc;border-radius:50%;border:2px solid white;cursor:pointer;';

            const distFeet = (b.distance * 3.28084).toFixed(0);
            const distMiles = (b.distance / 1609.34).toFixed(2);
            const distDisplay = b.distance < 1609 ? `${{distFeet}} ft` : `${{distMiles}} mi`;

            const popup = new mapboxgl.Popup({{ offset: 25 }}).setHTML(`
                <div style="padding:8px;">
                    <h4 style="margin:0 0 4px 0;font-size:14px;">${{b.address}}</h4>
                    <p style="margin:0 0 8px 0;color:#666;font-size:12px;">${{b.city}}, ${{b.state}} • ${{b.type}}</p>
                    <div style="font-size:12px;">
                        <div><strong>Distance:</strong> ${{distDisplay}}</div>
                        <div><strong>OpEx Savings:</strong> ${{formatMoney(b.total_opex)}}/yr</div>
                    </div>
                </div>
            `);

            const marker = new mapboxgl.Marker(el)
                .setLngLat([b.lon, b.lat])
                .setPopup(popup)
                .addTo(fullMap);

            searchMarkers.push(marker);
        }});

        // Add black marker for searched address
        const addrEl = document.createElement('div');
        addrEl.style.cssText = 'width:24px;height:24px;background:#1f2937;border-radius:50%;border:3px solid white;box-shadow:0 2px 6px rgba(0,0,0,0.3);';
        addressMarker = new mapboxgl.Marker(addrEl)
            .setLngLat([lng, lat])
            .setPopup(new mapboxgl.Popup().setHTML('<div style="font-weight:600;padding:4px;">Searched Address</div>'))
            .addTo(fullMap);

        // Fit bounds to show address and nearest buildings
        const bounds = new mapboxgl.LngLatBounds();
        bounds.extend([lng, lat]);
        nearest.slice(0, 5).forEach(b => bounds.extend([b.lon, b.lat]));
        fullMap.fitBounds(bounds, {{ padding: 60, maxZoom: 16 }});
    }}
}}

// =============================================================================
// UTILITIES
// =============================================================================

function toRad(deg) {{
    return deg * Math.PI / 180;
}}

function savingsColor(amount) {{
    // Green gradient: darker = more savings
    if (amount >= 500000) return '#166534';  // dark green
    if (amount >= 100000) return '#22c55e';  // medium green
    return '#4ade80';  // light green
}}

// =============================================================================
// MAP PANEL - Full Interactive Map with Clustering
// =============================================================================

// Load map data on demand (if not already loaded via script tag)
let MAP_DATA = null;

function loadMapData() {{
    return new Promise((resolve) => {{
        if (MAP_DATA) {{
            resolve();
            return;
        }}

        // Load via script tag (works with file:// protocol)
        const script = document.createElement('script');
        script.src = 'data/map_data.js';
        script.onload = () => {{
            resolve();
        }};
        script.onerror = () => {{
            MAP_DATA = [];
            resolve();
        }};
        document.head.appendChild(script);
    }});
}}

let fullMap = null;
let expandedPortfolioLogo = null;  // Track current expanded portfolio's logo URL

// Get buildings filtered by current context (expanded portfolio + active filters)
function getFilteredBuildingsForMap() {{
    // Map data loaded on demand - return empty if not loaded yet
    if (!MAP_DATA) return [];

    // Check if a portfolio is expanded
    const expandedPortfolio = document.querySelector('.portfolio-card.expanded');

    let buildingIds = null;
    if (expandedPortfolio) {{
        // Get building IDs from PORTFOLIO_BUILDINGS data (not DOM)
        const idx = parseInt(expandedPortfolio.dataset.idx);
        if (!isNaN(idx) && PORTFOLIO_BUILDINGS[idx]) {{
            buildingIds = new Set(PORTFOLIO_BUILDINGS[idx].map(b => b.id));
        }} else {{
            buildingIds = new Set();
        }}
    }}

    // Filter MAP_DATA array (loaded on demand)
    return MAP_DATA.filter(b => {{
        // Must have coordinates
        if (!b.lat || !b.lon) return false;

        // If portfolio expanded, must be in that portfolio
        if (buildingIds && !buildingIds.has(b.id)) return false;

        // Apply current filters (vertical, building type)
        if (activeVertical !== 'all' && b.vertical !== activeVertical) return false;
        if (selectedBuildingType && b.type !== selectedBuildingType) return false;

        return true;
    }});
}}

// Build GeoJSON from buildings array (optionally filtered)
function buildingsGeoJSON(buildings = null) {{
    const data = buildings || getFilteredBuildingsForMap();

    // Group buildings by coordinates to detect stacked pins
    const coordMap = {{}};
    data.forEach(b => {{
        const key = `${{b.lat}},${{b.lon}}`;
        if (!coordMap[key]) coordMap[key] = [];
        coordMap[key].push(b);
    }});

    return {{
        type: 'FeatureCollection',
        features: data.map(b => {{
            const key = `${{b.lat}},${{b.lon}}`;
            const stack = coordMap[key];
            return {{
                type: 'Feature',
                properties: {{
                    id: b.id,
                    address: b.address,
                    city: b.city,
                    state: b.state,
                    type: b.type,
                    vertical: b.vertical,
                    opex: b.total_opex,
                    image: b.image,
                    url: b.url,
                    stackCount: stack.length,
                    stackKey: key
                }},
                geometry: {{
                    type: 'Point',
                    coordinates: [b.lon, b.lat]
                }}
            }};
        }})
    }};
}}

// Update map data based on current context
function updateMapData() {{
    if (!fullMap || !fullMap.getSource('buildings')) return;

    const filteredBuildings = getFilteredBuildingsForMap();
    const geojson = buildingsGeoJSON(filteredBuildings);

    fullMap.getSource('buildings').setData(geojson);

    // Fit bounds to filtered buildings
    if (filteredBuildings.length > 0 && filteredBuildings.length < 5000) {{
        const bounds = new mapboxgl.LngLatBounds();
        filteredBuildings.forEach(b => bounds.extend([b.lon, b.lat]));
        fullMap.fitBounds(bounds, {{ padding: 50, maxZoom: 15 }});
    }}
}}

const CLIMATE_ZONES = {{"type":"FeatureCollection","features":[{{"type":"Feature","id":"01","properties":{{"name":"Alabama","density":94.65,"zone":3}},"geometry":{{"type":"Polygon","coordinates":[[[-87.359296,35.00118],[-85.606675,34.984749],[-85.431413,34.124869],[-85.184951,32.859696],[-85.069935,32.580372],[-84.960397,32.421541],[-85.004212,32.322956],[-84.889196,32.262709],[-85.058981,32.13674],[-85.053504,32.01077],[-85.141136,31.840985],[-85.042551,31.539753],[-85.113751,31.27686],[-85.004212,31.003013],[-85.497137,30.997536],[-87.600282,30.997536],[-87.633143,30.86609],[-87.408589,30.674397],[-87.446927,30.510088],[-87.37025,30.427934],[-87.518128,30.280057],[-87.655051,30.247195],[-87.90699,30.411504],[-87.934375,30.657966],[-88.011052,30.685351],[-88.10416,30.499135],[-88.137022,30.318396],[-88.394438,30.367688],[-88.471115,31.895754],[-88.241084,33.796253],[-88.098683,34.891641],[-88.202745,34.995703],[-87.359296,35.00118]]]}}}},{{"type":"Feature","id":"02","properties":{{"name":"Alaska","density":1.264,"zone":7}},"geometry":{{"type":"MultiPolygon","coordinates":[[[[-131.602021,55.117982],[-131.569159,55.28229],[-131.355558,55.183705],[-131.38842,55.01392],[-131.645836,55.035827],[-131.602021,55.117982]]],[[[-131.832052,55.42469],[-131.645836,55.304197],[-131.749898,55.128935],[-131.832052,55.189182],[-131.832052,55.42469]]],[[[-132.976733,56.437924],[-132.735747,56.459832],[-132.631685,56.421493],[-132.664547,56.273616],[-132.878148,56.240754],[-133.069841,56.333862],[-132.976733,56.437924]]],[[[-133.595627,56.350293],[-133.162949,56.317431],[-133.05341,56.125739],[-132.620732,55.912138],[-132.472854,55.780691],[-132.4619,55.671152],[-132.357838,55.649245],[-132.341408,55.506844],[-132.166146,55.364444],[-132.144238,55.238474],[-132.029222,55.276813],[-131.97993,55.178228],[-131.958022,54.789365],[-132.029222,54.701734],[-132.308546,54.718165],[-132.385223,54.915335],[-132.483808,54.898904],[-132.686455,55.046781],[-132.746701,54.997489],[-132.916486,55.046781],[-132.889102,54.898904],[-132.73027,54.937242],[-132.626209,54.882473],[-132.675501,54.679826],[-132.867194,54.701734],[-133.157472,54.95915],[-133.239626,55.090597],[-133.223195,55.22752],[-133.453227,55.216566],[-133.453227,55.320628],[-133.277964,55.331582],[-133.102702,55.42469],[-133.17938,55.588998],[-133.387503,55.62186],[-133.420365,55.884753],[-133.497042,56.0162],[-133.639442,55.923092],[-133.694212,56.070969],[-133.546335,56.142169],[-133.666827,56.311955],[-133.595627,56.350293]]],[[[-133.738027,55.556137],[-133.546335,55.490413],[-133.414888,55.572568],[-133.283441,55.534229],[-133.420365,55.386352],[-133.633966,55.430167],[-133.738027,55.556137]]],[[[-133.907813,56.930849],[-134.050213,57.029434],[-133.885905,57.095157],[-133.343688,57.002049],[-133.102702,57.007526],[-132.932917,56.82131],[-132.620732,56.667956],[-132.653593,56.55294],[-132.817901,56.492694],[-133.042456,56.520078],[-133.201287,56.448878],[-133.420365,56.492694],[-133.66135,56.448878],[-133.710643,56.684386],[-133.688735,56.837741],[-133.869474,56.843218],[-133.907813,56.930849]]],[[[-134.115936,56.48174],[-134.25286,56.558417],[-134.400737,56.722725],[-134.417168,56.848695],[-134.296675,56.908941],[-134.170706,56.848695],[-134.143321,56.952757],[-133.748981,56.772017],[-133.710643,56.596755],[-133.847566,56.574848],[-133.935197,56.377678],[-133.836612,56.322908],[-133.957105,56.092877],[-134.110459,56.142169],[-134.132367,55.999769],[-134.230952,56.070969],[-134.291198,56.350293],[-134.115936,56.48174]]],[[[-134.636246,56.28457],[-134.669107,56.169554],[-134.806031,56.235277],[-135.178463,56.67891],[-135.413971,56.810356],[-135.331817,56.914418],[-135.424925,57.166357],[-135.687818,57.369004],[-135.419448,57.566174],[-135.298955,57.48402],[-135.063447,57.418296],[-134.849846,57.407343],[-134.844369,57.248511],[-134.636246,56.728202],[-134.636246,56.28457]]],[[[-134.712923,58.223407],[-134.373353,58.14673],[-134.176183,58.157683],[-134.187137,58.081006],[-133.902336,57.807159],[-134.099505,57.850975],[-134.148798,57.757867],[-133.935197,57.615466],[-133.869474,57.363527],[-134.083075,57.297804],[-134.154275,57.210173],[-134.499322,57.029434],[-134.603384,57.034911],[-134.6472,57.226604],[-134.575999,57.341619],[-134.608861,57.511404],[-134.729354,57.719528],[-134.707446,57.829067],[-134.784123,58.097437],[-134.91557,58.212453],[-134.953908,58.409623],[-134.712923,58.223407]]],[[[-135.857603,57.330665],[-135.715203,57.330665],[-135.567326,57.149926],[-135.633049,57.023957],[-135.857603,56.996572],[-135.824742,57.193742],[-135.857603,57.330665]]],[[[-136.279328,58.206976],[-135.978096,58.201499],[-135.780926,58.28913],[-135.496125,58.168637],[-135.64948,58.037191],[-135.59471,57.987898],[-135.45231,58.135776],[-135.107263,58.086483],[-134.91557,57.976944],[-135.025108,57.779775],[-134.937477,57.763344],[-134.822462,57.500451],[-135.085355,57.462112],[-135.572802,57.675713],[-135.556372,57.456635],[-135.709726,57.369004],[-135.890465,57.407343],[-136.000004,57.544266],[-136.208128,57.637374],[-136.366959,57.829067],[-136.569606,57.916698],[-136.558652,58.075529],[-136.421728,58.130299],[-136.377913,58.267222],[-136.279328,58.206976]]],[[[-147.079854,60.200582],[-147.501579,59.948643],[-147.53444,59.850058],[-147.874011,59.784335],[-147.80281,59.937689],[-147.435855,60.09652],[-147.205824,60.271782],[-147.079854,60.200582]]],[[[-147.561825,60.578491],[-147.616594,60.370367],[-147.758995,60.156767],[-147.956165,60.227967],[-147.791856,60.474429],[-147.561825,60.578491]]],[[[-147.786379,70.245291],[-147.682318,70.201475],[-147.162008,70.15766],[-146.888161,70.185044],[-146.510252,70.185044],[-146.099482,70.146706],[-145.858496,70.168614],[-145.622988,70.08646],[-145.195787,69.993352],[-144.620708,69.971444],[-144.461877,70.026213],[-144.078491,70.059075],[-143.914183,70.130275],[-143.497935,70.141229],[-143.503412,70.091936],[-143.25695,70.119321],[-142.747594,70.042644],[-142.402547,69.916674],[-142.079408,69.856428],[-142.008207,69.801659],[-141.712453,69.790705],[-141.433129,69.697597],[-141.378359,69.63735],[-141.208574,69.686643],[-141.00045,69.648304],[-141.00045,60.304644],[-140.53491,60.22249],[-140.474664,60.310121],[-139.987216,60.184151],[-139.696939,60.342983],[-139.088998,60.359413],[-139.198537,60.091043],[-139.045183,59.997935],[-138.700135,59.910304],[-138.623458,59.767904],[-137.604747,59.242118],[-137.445916,58.908024],[-137.265177,59.001132],[-136.827022,59.159963],[-136.580559,59.16544],[-136.465544,59.285933],[-136.476498,59.466672],[-136.301236,59.466672],[-136.25742,59.625503],[-135.945234,59.663842],[-135.479694,59.800766],[-135.025108,59.565257],[-135.068924,59.422857],[-134.959385,59.280456],[-134.701969,59.247595],[-134.378829,59.033994],[-134.400737,58.973748],[-134.25286,58.858732],[-133.842089,58.727285],[-133.173903,58.152206],[-133.075318,57.998852],[-132.867194,57.845498],[-132.560485,57.505928],[-132.253777,57.21565],[-132.368792,57.095157],[-132.05113,57.051341],[-132.127807,56.876079],[-131.870391,56.804879],[-131.837529,56.602232],[-131.580113,56.613186],[-131.087188,56.405062],[-130.78048,56.366724],[-130.621648,56.268139],[-130.468294,56.240754],[-130.424478,56.142169],[-130.101339,56.114785],[-130.002754,55.994292],[-130.150631,55.769737],[-130.128724,55.583521],[-129.986323,55.276813],[-130.095862,55.200136],[-130.336847,54.920812],[-130.687372,54.718165],[-130.785957,54.822227],[-130.917403,54.789365],[-131.010511,54.997489],[-130.983126,55.08512],[-131.092665,55.189182],[-130.862634,55.298721],[-130.928357,55.337059],[-131.158389,55.200136],[-131.284358,55.287767],[-131.426759,55.238474],[-131.843006,55.457552],[-131.700606,55.698537],[-131.963499,55.616383],[-131.974453,55.49589],[-132.182576,55.588998],[-132.226392,55.704014],[-132.083991,55.829984],[-132.127807,55.955953],[-132.324977,55.851892],[-132.522147,56.076446],[-132.642639,56.032631],[-132.719317,56.218847],[-132.527624,56.339339],[-132.341408,56.339339],[-132.396177,56.487217],[-132.297592,56.67891],[-132.450946,56.673433],[-132.768609,56.837741],[-132.993164,57.034911],[-133.51895,57.177311],[-133.507996,57.577128],[-133.677781,57.62642],[-133.639442,57.790728],[-133.814705,57.834544],[-134.072121,58.053622],[-134.143321,58.168637],[-134.586953,58.206976],[-135.074401,58.502731],[-135.282525,59.192825],[-135.38111,59.033994],[-135.337294,58.891593],[-135.140124,58.617746],[-135.189417,58.573931],[-135.05797,58.349376],[-135.085355,58.201499],[-135.277048,58.234361],[-135.430402,58.398669],[-135.633049,58.426053],[-135.91785,58.382238],[-135.912373,58.617746],[-136.087635,58.814916],[-136.246466,58.75467],[-136.876314,58.962794],[-136.931084,58.902547],[-136.586036,58.836824],[-136.317666,58.672516],[-136.213604,58.667039],[-136.180743,58.535592],[-136.043819,58.382238],[-136.388867,58.294607],[-136.591513,58.349376],[-136.59699,58.212453],[-136.859883,58.316515],[-136.947514,58.393192],[-137.111823,58.393192],[-137.566409,58.590362],[-137.900502,58.765624],[-137.933364,58.869686],[-138.11958,59.02304],[-138.634412,59.132579],[-138.919213,59.247595],[-139.417615,59.379041],[-139.746231,59.505011],[-139.718846,59.641934],[-139.625738,59.598119],[-139.5162,59.68575],[-139.625738,59.88292],[-139.488815,59.992458],[-139.554538,60.041751],[-139.801,59.833627],[-140.315833,59.696704],[-140.92925,59.745996],[-141.444083,59.871966],[-141.46599,59.970551],[-141.706976,59.948643],[-141.964392,60.019843],[-142.539471,60.085566],[-142.873564,60.091043],[-143.623905,60.036274],[-143.892275,59.997935],[-144.231845,60.140336],[-144.65357,60.206059],[-144.785016,60.29369],[-144.834309,60.441568],[-145.124586,60.430614],[-145.223171,60.299167],[-145.738004,60.474429],[-145.820158,60.551106],[-146.351421,60.408706],[-146.608837,60.238921],[-146.718376,60.397752],[-146.608837,60.485383],[-146.455483,60.463475],[-145.951604,60.578491],[-146.017328,60.666122],[-146.252836,60.622307],[-146.345944,60.737322],[-146.565022,60.753753],[-146.784099,61.044031],[-146.866253,60.972831],[-147.172962,60.934492],[-147.271547,60.972831],[-147.375609,60.879723],[-147.758995,60.912584],[-147.775426,60.808523],[-148.032842,60.781138],[-148.153334,60.819476],[-148.065703,61.005692],[-148.175242,61.000215],[-148.350504,60.803046],[-148.109519,60.737322],[-148.087611,60.594922],[-147.939734,60.441568],[-148.027365,60.277259],[-148.219058,60.332029],[-148.273827,60.249875],[-148.087611,60.217013],[-147.983549,59.997935],[-148.251919,59.95412],[-148.399797,59.997935],[-148.635305,59.937689],[-148.755798,59.986981],[-149.067984,59.981505],[-149.05703,60.063659],[-149.204907,60.008889],[-149.287061,59.904827],[-149.418508,59.997935],[-149.582816,59.866489],[-149.511616,59.806242],[-149.741647,59.729565],[-149.949771,59.718611],[-150.031925,59.61455],[-150.25648,59.521442],[-150.409834,59.554303],[-150.579619,59.444764],[-150.716543,59.450241],[-151.001343,59.225687],[-151.308052,59.209256],[-151.406637,59.280456],[-151.592853,59.159963],[-151.976239,59.253071],[-151.888608,59.422857],[-151.636669,59.483103],[-151.47236,59.472149],[-151.423068,59.537872],[-151.127313,59.669319],[-151.116359,59.778858],[-151.505222,59.63098],[-151.828361,59.718611],[-151.8667,59.778858],[-151.702392,60.030797],[-151.423068,60.211536],[-151.379252,60.359413],[-151.297098,60.386798],[-151.264237,60.545629],[-151.406637,60.720892],[-151.06159,60.786615],[-150.404357,61.038554],[-150.245526,60.939969],[-150.042879,60.912584],[-149.741647,61.016646],[-150.075741,61.15357],[-150.207187,61.257632],[-150.47008,61.246678],[-150.656296,61.29597],[-150.711066,61.252155],[-151.023251,61.180954],[-151.165652,61.044031],[-151.477837,61.011169],[-151.800977,60.852338],[-151.833838,60.748276],[-152.080301,60.693507],[-152.13507,60.578491],[-152.310332,60.507291],[-152.392486,60.304644],[-152.732057,60.173197],[-152.567748,60.069136],[-152.704672,59.915781],[-153.022334,59.888397],[-153.049719,59.691227],[-153.345474,59.620026],[-153.438582,59.702181],[-153.586459,59.548826],[-153.761721,59.543349],[-153.72886,59.433811],[-154.117723,59.368087],[-154.1944,59.066856],[-153.750768,59.050425],[-153.400243,58.968271],[-153.301658,58.869686],[-153.444059,58.710854],[-153.679567,58.612269],[-153.898645,58.606793],[-153.920553,58.519161],[-154.062953,58.4863],[-153.99723,58.376761],[-154.145107,58.212453],[-154.46277,58.059098],[-154.643509,58.059098],[-154.818771,58.004329],[-154.988556,58.015283],[-155.120003,57.955037],[-155.081664,57.872883],[-155.328126,57.829067],[-155.377419,57.708574],[-155.547204,57.785251],[-155.73342,57.549743],[-156.045606,57.566174],[-156.023698,57.440204],[-156.209914,57.473066],[-156.34136,57.418296],[-156.34136,57.248511],[-156.549484,56.985618],[-156.883577,56.952757],[-157.157424,56.832264],[-157.20124,56.766541],[-157.376502,56.859649],[-157.672257,56.607709],[-157.754411,56.67891],[-157.918719,56.657002],[-157.957058,56.514601],[-158.126843,56.459832],[-158.32949,56.48174],[-158.488321,56.339339],[-158.208997,56.295524],[-158.510229,55.977861],[-159.375585,55.873799],[-159.616571,55.594475],[-159.676817,55.654722],[-159.643955,55.829984],[-159.813741,55.857368],[-160.027341,55.791645],[-160.060203,55.720445],[-160.394296,55.605429],[-160.536697,55.473983],[-160.580512,55.567091],[-160.668143,55.457552],[-160.865313,55.528752],[-161.232268,55.358967],[-161.506115,55.364444],[-161.467776,55.49589],[-161.588269,55.62186],[-161.697808,55.517798],[-161.686854,55.408259],[-162.053809,55.074166],[-162.179779,55.15632],[-162.218117,55.03035],[-162.470057,55.052258],[-162.508395,55.249428],[-162.661749,55.293244],[-162.716519,55.222043],[-162.579595,55.134412],[-162.645319,54.997489],[-162.847965,54.926289],[-163.00132,55.079643],[-163.187536,55.090597],[-163.220397,55.03035],[-163.034181,54.942719],[-163.373752,54.800319],[-163.14372,54.76198],[-163.138243,54.696257],[-163.329936,54.74555],[-163.587352,54.614103],[-164.085754,54.61958],[-164.332216,54.531949],[-164.354124,54.466226],[-164.638925,54.389548],[-164.847049,54.416933],[-164.918249,54.603149],[-164.710125,54.663395],[-164.551294,54.88795],[-164.34317,54.893427],[-163.894061,55.041304],[-163.532583,55.046781],[-163.39566,54.904381],[-163.291598,55.008443],[-163.313505,55.128935],[-163.105382,55.183705],[-162.880827,55.183705],[-162.579595,55.446598],[-162.245502,55.682106],[-161.807347,55.89023],[-161.292514,55.983338],[-161.078914,55.939523],[-160.87079,55.999769],[-160.816021,55.912138],[-160.931036,55.813553],[-160.805067,55.736876],[-160.766728,55.857368],[-160.509312,55.868322],[-160.438112,55.791645],[-160.27928,55.76426],[-160.273803,55.857368],[-160.536697,55.939523],[-160.558604,55.994292],[-160.383342,56.251708],[-160.147834,56.399586],[-159.830171,56.541986],[-159.326293,56.667956],[-158.959338,56.848695],[-158.784076,56.782971],[-158.641675,56.810356],[-158.701922,56.925372],[-158.658106,57.034911],[-158.378782,57.264942],[-157.995396,57.41282],[-157.688688,57.609989],[-157.705118,57.719528],[-157.458656,58.497254],[-157.07527,58.705377],[-157.119086,58.869686],[-158.039212,58.634177],[-158.32949,58.661562],[-158.40069,58.760147],[-158.564998,58.803962],[-158.619768,58.913501],[-158.767645,58.864209],[-158.860753,58.694424],[-158.701922,58.480823],[-158.893615,58.387715],[-159.0634,58.420577],[-159.392016,58.760147],[-159.616571,58.929932],[-159.731586,58.929932],[-159.808264,58.803962],[-159.906848,58.782055],[-160.054726,58.886116],[-160.235465,58.902547],[-160.317619,59.072332],[-160.854359,58.88064],[-161.33633,58.743716],[-161.374669,58.667039],[-161.752577,58.552023],[-161.938793,58.656085],[-161.769008,58.776578],[-161.829255,59.061379],[-161.955224,59.36261],[-161.703285,59.48858],[-161.911409,59.740519],[-162.092148,59.88292],[-162.234548,60.091043],[-162.448149,60.178674],[-162.502918,59.997935],[-162.760334,59.959597],[-163.171105,59.844581],[-163.66403,59.795289],[-163.9324,59.806242],[-164.162431,59.866489],[-164.189816,60.02532],[-164.386986,60.074613],[-164.699171,60.29369],[-164.962064,60.337506],[-165.268773,60.578491],[-165.060649,60.68803],[-165.016834,60.890677],[-165.175665,60.846861],[-165.197573,60.972831],[-165.120896,61.076893],[-165.323543,61.170001],[-165.34545,61.071416],[-165.591913,61.109754],[-165.624774,61.279539],[-165.816467,61.301447],[-165.920529,61.416463],[-165.915052,61.558863],[-166.106745,61.49314],[-166.139607,61.630064],[-165.904098,61.662925],[-166.095791,61.81628],[-165.756221,61.827233],[-165.756221,62.013449],[-165.674067,62.139419],[-165.044219,62.539236],[-164.912772,62.659728],[-164.819664,62.637821],[-164.874433,62.807606],[-164.633448,63.097884],[-164.425324,63.212899],[-164.036462,63.262192],[-163.73523,63.212899],[-163.313505,63.037637],[-163.039658,63.059545],[-162.661749,63.22933],[-162.272887,63.486746],[-162.075717,63.514131],[-162.026424,63.448408],[-161.555408,63.448408],[-161.13916,63.503177],[-160.766728,63.771547],[-160.766728,63.837271],[-160.952944,64.08921],[-160.974852,64.237087],[-161.26513,64.395918],[-161.374669,64.532842],[-161.078914,64.494503],[-160.79959,64.609519],[-160.783159,64.719058],[-161.144637,64.921705],[-161.413007,64.762873],[-161.664946,64.790258],[-161.900455,64.702627],[-162.168825,64.680719],[-162.234548,64.620473],[-162.541257,64.532842],[-162.634365,64.384965],[-162.787719,64.324718],[-162.858919,64.49998],[-163.045135,64.538319],[-163.176582,64.401395],[-163.253259,64.467119],[-163.598306,64.565704],[-164.304832,64.560227],[-164.80871,64.450688],[-165.000403,64.434257],[-165.411174,64.49998],[-166.188899,64.576658],[-166.391546,64.636904],[-166.484654,64.735489],[-166.413454,64.872412],[-166.692778,64.987428],[-166.638008,65.113398],[-166.462746,65.179121],[-166.517516,65.337952],[-166.796839,65.337952],[-167.026871,65.381768],[-167.47598,65.414629],[-167.711489,65.496784],[-168.072967,65.578938],[-168.105828,65.682999],[-167.541703,65.819923],[-166.829701,66.049954],[-166.3313,66.186878],[-166.046499,66.110201],[-165.756221,66.09377],[-165.690498,66.203309],[-165.86576,66.21974],[-165.88219,66.312848],[-165.186619,66.466202],[-164.403417,66.581218],[-163.981692,66.592172],[-163.751661,66.553833],[-163.872153,66.389525],[-163.828338,66.274509],[-163.915969,66.192355],[-163.768091,66.060908],[-163.494244,66.082816],[-163.149197,66.060908],[-162.749381,66.088293],[-162.634365,66.039001],[-162.371472,66.028047],[-162.14144,66.077339],[-161.840208,66.02257],[-161.549931,66.241647],[-161.341807,66.252601],[-161.199406,66.208786],[-161.128206,66.334755],[-161.528023,66.395002],[-161.911409,66.345709],[-161.87307,66.510017],[-162.174302,66.68528],[-162.502918,66.740049],[-162.601503,66.89888],[-162.344087,66.937219],[-162.015471,66.778388],[-162.075717,66.652418],[-161.916886,66.553833],[-161.571838,66.438817],[-161.489684,66.55931],[-161.884024,66.718141],[-161.714239,67.002942],[-161.851162,67.052235],[-162.240025,66.991988],[-162.639842,67.008419],[-162.700088,67.057712],[-162.902735,67.008419],[-163.740707,67.128912],[-163.757138,67.254881],[-164.009077,67.534205],[-164.211724,67.638267],[-164.534863,67.725898],[-165.192096,67.966884],[-165.493328,68.059992],[-165.794559,68.081899],[-166.243668,68.246208],[-166.681824,68.339316],[-166.703731,68.372177],[-166.375115,68.42147],[-166.227238,68.574824],[-166.216284,68.881533],[-165.329019,68.859625],[-164.255539,68.930825],[-163.976215,68.985595],[-163.532583,69.138949],[-163.110859,69.374457],[-163.023228,69.609966],[-162.842489,69.812613],[-162.470057,69.982398],[-162.311225,70.108367],[-161.851162,70.311014],[-161.779962,70.256245],[-161.396576,70.239814],[-160.837928,70.343876],[-160.487404,70.453415],[-159.649432,70.792985],[-159.33177,70.809416],[-159.298908,70.760123],[-158.975769,70.798462],[-158.658106,70.787508],[-158.033735,70.831323],[-157.420318,70.979201],[-156.812377,71.285909],[-156.565915,71.351633],[-156.522099,71.296863],[-155.585543,71.170894],[-155.508865,71.083263],[-155.832005,70.968247],[-155.979882,70.96277],[-155.974405,70.809416],[-155.503388,70.858708],[-155.476004,70.940862],[-155.262403,71.017539],[-155.191203,70.973724],[-155.032372,71.148986],[-154.566832,70.990155],[-154.643509,70.869662],[-154.353231,70.8368],[-154.183446,70.7656],[-153.931507,70.880616],[-153.487874,70.886093],[-153.235935,70.924431],[-152.589656,70.886093],[-152.26104,70.842277],[-152.419871,70.606769],[-151.817408,70.546523],[-151.773592,70.486276],[-151.187559,70.382214],[-151.182082,70.431507],[-150.760358,70.49723],[-150.355064,70.491753],[-150.349588,70.436984],[-150.114079,70.431507],[-149.867617,70.508184],[-149.462323,70.519138],[-149.177522,70.486276],[-148.78866,70.404122],[-148.607921,70.420553],[-148.350504,70.305537],[-148.202627,70.349353],[-147.961642,70.316491],[-147.786379,70.245291]]],[[[-152.94018,58.026237],[-152.945657,57.982421],[-153.290705,58.048145],[-153.044242,58.305561],[-152.819688,58.327469],[-152.666333,58.562977],[-152.496548,58.354853],[-152.354148,58.426053],[-152.080301,58.311038],[-152.080301,58.152206],[-152.480117,58.130299],[-152.655379,58.059098],[-152.94018,58.026237]]],[[[-153.958891,57.538789],[-153.67409,57.670236],[-153.931507,57.69762],[-153.936983,57.812636],[-153.723383,57.889313],[-153.570028,57.834544],[-153.548121,57.719528],[-153.46049,57.796205],[-153.455013,57.96599],[-153.268797,57.889313],[-153.235935,57.998852],[-153.071627,57.933129],[-152.874457,57.933129],[-152.721103,57.993375],[-152.469163,57.889313],[-152.469163,57.599035],[-152.151501,57.620943],[-152.359625,57.42925],[-152.74301,57.505928],[-152.60061,57.379958],[-152.710149,57.275896],[-152.907319,57.325188],[-152.912796,57.128019],[-153.214027,57.073249],[-153.312612,56.991095],[-153.498828,57.067772],[-153.695998,56.859649],[-153.849352,56.837741],[-154.013661,56.744633],[-154.073907,56.969187],[-154.303938,56.848695],[-154.314892,56.919895],[-154.523016,56.991095],[-154.539447,57.193742],[-154.742094,57.275896],[-154.627078,57.511404],[-154.227261,57.659282],[-153.980799,57.648328],[-153.958891,57.538789]]],[[[-154.53397,56.602232],[-154.742094,56.399586],[-154.807817,56.432447],[-154.53397,56.602232]]],[[[-155.634835,55.923092],[-155.476004,55.912138],[-155.530773,55.704014],[-155.793666,55.731399],[-155.837482,55.802599],[-155.634835,55.923092]]],[[[-159.890418,55.28229],[-159.950664,55.068689],[-160.257373,54.893427],[-160.109495,55.161797],[-160.005433,55.134412],[-159.890418,55.28229]]],[[[-160.520266,55.358967],[-160.33405,55.358967],[-160.339527,55.249428],[-160.525743,55.128935],[-160.690051,55.211089],[-160.794113,55.134412],[-160.854359,55.320628],[-160.79959,55.380875],[-160.520266,55.358967]]],[[[-162.256456,54.981058],[-162.234548,54.893427],[-162.349564,54.838658],[-162.437195,54.931766],[-162.256456,54.981058]]],[[[-162.415287,63.634624],[-162.563165,63.536039],[-162.612457,63.62367],[-162.415287,63.634624]]],[[[-162.80415,54.488133],[-162.590549,54.449795],[-162.612457,54.367641],[-162.782242,54.373118],[-162.80415,54.488133]]],[[[-165.548097,54.29644],[-165.476897,54.181425],[-165.630251,54.132132],[-165.685021,54.252625],[-165.548097,54.29644]]],[[[-165.73979,54.15404],[-166.046499,54.044501],[-166.112222,54.121178],[-165.980775,54.219763],[-165.73979,54.15404]]],[[[-166.364161,60.359413],[-166.13413,60.397752],[-166.084837,60.326552],[-165.88219,60.342983],[-165.685021,60.277259],[-165.646682,59.992458],[-165.750744,59.89935],[-166.00816,59.844581],[-166.062929,59.745996],[-166.440838,59.855535],[-166.6161,59.850058],[-166.994009,59.992458],[-167.125456,59.992458],[-167.344534,60.074613],[-167.421211,60.206059],[-167.311672,60.238921],[-166.93924,60.206059],[-166.763978,60.310121],[-166.577762,60.321075],[-166.495608,60.392275],[-166.364161,60.359413]]],[[[-166.375115,54.01164],[-166.210807,53.934962],[-166.5449,53.748746],[-166.539423,53.715885],[-166.117699,53.852808],[-166.112222,53.776131],[-166.282007,53.683023],[-166.555854,53.622777],[-166.583239,53.529669],[-166.878994,53.431084],[-167.13641,53.425607],[-167.306195,53.332499],[-167.623857,53.250345],[-167.793643,53.337976],[-167.459549,53.442038],[-167.355487,53.425607],[-167.103548,53.513238],[-167.163794,53.611823],[-167.021394,53.715885],[-166.807793,53.666592],[-166.785886,53.732316],[-167.015917,53.754223],[-167.141887,53.825424],[-167.032348,53.945916],[-166.643485,54.017116],[-166.561331,53.880193],[-166.375115,54.01164]]],[[[-168.790446,53.157237],[-168.40706,53.34893],[-168.385152,53.431084],[-168.237275,53.524192],[-168.007243,53.568007],[-167.886751,53.518715],[-167.842935,53.387268],[-168.270136,53.244868],[-168.500168,53.036744],[-168.686384,52.965544],[-168.790446,53.157237]]],[[[-169.74891,52.894344],[-169.705095,52.795759],[-169.962511,52.790282],[-169.989896,52.856005],[-169.74891,52.894344]]],[[[-170.148727,57.221127],[-170.28565,57.128019],[-170.313035,57.221127],[-170.148727,57.221127]]],[[[-170.669036,52.697174],[-170.603313,52.604066],[-170.789529,52.538343],[-170.816914,52.636928],[-170.669036,52.697174]]],[[[-171.742517,63.716778],[-170.94836,63.5689],[-170.488297,63.69487],[-170.280174,63.683916],[-170.093958,63.612716],[-170.044665,63.492223],[-169.644848,63.4265],[-169.518879,63.366254],[-168.99857,63.338869],[-168.686384,63.295053],[-168.856169,63.147176],[-169.108108,63.180038],[-169.376478,63.152653],[-169.513402,63.08693],[-169.639372,62.939052],[-169.831064,63.075976],[-170.055619,63.169084],[-170.263743,63.180038],[-170.362328,63.2841],[-170.866206,63.415546],[-171.101715,63.421023],[-171.463193,63.306007],[-171.73704,63.366254],[-171.852055,63.486746],[-171.742517,63.716778]]],[[[-172.432611,52.390465],[-172.41618,52.275449],[-172.607873,52.253542],[-172.569535,52.352127],[-172.432611,52.390465]]],[[[-173.626584,52.14948],[-173.495138,52.105664],[-173.122706,52.111141],[-173.106275,52.07828],[-173.549907,52.028987],[-173.626584,52.14948]]],[[[-174.322156,52.280926],[-174.327632,52.379511],[-174.185232,52.41785],[-173.982585,52.319265],[-174.059262,52.226157],[-174.179755,52.231634],[-174.141417,52.127572],[-174.333109,52.116618],[-174.738403,52.007079],[-174.968435,52.039941],[-174.902711,52.116618],[-174.656249,52.105664],[-174.322156,52.280926]]],[[[-176.469116,51.853725],[-176.288377,51.870156],[-176.288377,51.744186],[-176.518409,51.760617],[-176.80321,51.61274],[-176.912748,51.80991],[-176.792256,51.815386],[-176.775825,51.963264],[-176.627947,51.968741],[-176.627947,51.859202],[-176.469116,51.853725]]],[[[-177.153734,51.946833],[-177.044195,51.897541],[-177.120872,51.727755],[-177.274226,51.678463],[-177.279703,51.782525],[-177.153734,51.946833]]],[[[-178.123152,51.919448],[-177.953367,51.913971],[-177.800013,51.793479],[-177.964321,51.651078],[-178.123152,51.919448]]],[[[-187.107557,52.992929],[-187.293773,52.927205],[-187.304726,52.823143],[-188.90491,52.762897],[-188.642017,52.927205],[-188.642017,53.003883],[-187.107557,52.992929]]]]}}}},{{"type":"Feature","id":"04","properties":{{"name":"Arizona","density":57.05,"zone":3}},"geometry":{{"type":"Polygon","coordinates":[[[-109.042503,37.000263],[-109.04798,31.331629],[-111.074448,31.331629],[-112.246513,31.704061],[-114.815198,32.492741],[-114.72209,32.717295],[-114.524921,32.755634],[-114.470151,32.843265],[-114.524921,33.029481],[-114.661844,33.034958],[-114.727567,33.40739],[-114.524921,33.54979],[-114.497536,33.697668],[-114.535874,33.933176],[-114.415382,34.108438],[-114.256551,34.174162],[-114.136058,34.305608],[-114.333228,34.448009],[-114.470151,34.710902],[-114.634459,34.87521],[-114.634459,35.00118],[-114.574213,35.138103],[-114.596121,35.324319],[-114.678275,35.516012],[-114.738521,36.102045],[-114.371566,36.140383],[-114.251074,36.01989],[-114.152489,36.025367],[-114.048427,36.195153],[-114.048427,37.000263],[-110.499369,37.00574],[-109.042503,37.000263]]]}}}},{{"type":"Feature","id":"05","properties":{{"name":"Arkansas","density":56.43,"zone":3}},"geometry":{{"type":"Polygon","coordinates":[[[-94.473842,36.501861],[-90.152536,36.496384],[-90.064905,36.304691],[-90.218259,36.184199],[-90.377091,35.997983],[-89.730812,35.997983],[-89.763673,35.811767],[-89.911551,35.756997],[-89.944412,35.603643],[-90.130628,35.439335],[-90.114197,35.198349],[-90.212782,35.023087],[-90.311367,34.995703],[-90.251121,34.908072],[-90.409952,34.831394],[-90.481152,34.661609],[-90.585214,34.617794],[-90.568783,34.420624],[-90.749522,34.365854],[-90.744046,34.300131],[-90.952169,34.135823],[-90.891923,34.026284],[-91.072662,33.867453],[-91.231493,33.560744],[-91.056231,33.429298],[-91.143862,33.347144],[-91.089093,33.13902],[-91.16577,33.002096],[-93.608485,33.018527],[-94.041164,33.018527],[-94.041164,33.54979],[-94.183564,33.593606],[-94.380734,33.544313],[-94.484796,33.637421],[-94.430026,35.395519],[-94.616242,36.501861],[-94.473842,36.501861]]]}}}},{{"type":"Feature","id":"06","properties":{{"name":"California","density":241.7,"zone":3}},"geometry":{{"type":"Polygon","coordinates":[[[-123.233256,42.006186],[-122.378853,42.011663],[-121.037003,41.995232],[-120.001861,41.995232],[-119.996384,40.264519],[-120.001861,38.999346],[-118.71478,38.101128],[-117.498899,37.21934],[-116.540435,36.501861],[-115.85034,35.970598],[-114.634459,35.00118],[-114.634459,34.87521],[-114.470151,34.710902],[-114.333228,34.448009],[-114.136058,34.305608],[-114.256551,34.174162],[-114.415382,34.108438],[-114.535874,33.933176],[-114.497536,33.697668],[-114.524921,33.54979],[-114.727567,33.40739],[-114.661844,33.034958],[-114.524921,33.029481],[-114.470151,32.843265],[-114.524921,32.755634],[-114.72209,32.717295],[-116.04751,32.624187],[-117.126467,32.536556],[-117.24696,32.668003],[-117.252437,32.876127],[-117.329114,33.122589],[-117.471515,33.297851],[-117.7837,33.538836],[-118.183517,33.763391],[-118.260194,33.703145],[-118.413548,33.741483],[-118.391641,33.840068],[-118.566903,34.042715],[-118.802411,33.998899],[-119.218659,34.146777],[-119.278905,34.26727],[-119.558229,34.415147],[-119.875891,34.40967],[-120.138784,34.475393],[-120.472878,34.448009],[-120.64814,34.579455],[-120.609801,34.858779],[-120.670048,34.902595],[-120.631709,35.099764],[-120.894602,35.247642],[-120.905556,35.450289],[-121.004141,35.461243],[-121.168449,35.636505],[-121.283465,35.674843],[-121.332757,35.784382],[-121.716143,36.195153],[-121.896882,36.315645],[-121.935221,36.638785],[-121.858544,36.6114],[-121.787344,36.803093],[-121.929744,36.978355],[-122.105006,36.956447],[-122.335038,37.115279],[-122.417192,37.241248],[-122.400761,37.361741],[-122.515777,37.520572],[-122.515777,37.783465],[-122.329561,37.783465],[-122.406238,38.15042],[-122.488392,38.112082],[-122.504823,37.931343],[-122.701993,37.893004],[-122.937501,38.029928],[-122.97584,38.265436],[-123.129194,38.451652],[-123.331841,38.566668],[-123.44138,38.698114],[-123.737134,38.95553],[-123.687842,39.032208],[-123.824765,39.366301],[-123.764519,39.552517],[-123.85215,39.831841],[-124.109566,40.105688],[-124.361506,40.259042],[-124.410798,40.439781],[-124.158859,40.877937],[-124.109566,41.025814],[-124.158859,41.14083],[-124.065751,41.442061],[-124.147905,41.715908],[-124.257444,41.781632],[-124.213628,42.000709],[-123.233256,42.006186]]]}}}},{{"type":"Feature","id":"08","properties":{{"name":"Colorado","density":49.33,"zone":5}},"geometry":{{"type":"Polygon","coordinates":[[[-107.919731,41.003906],[-105.728954,40.998429],[-104.053011,41.003906],[-102.053927,41.003906],[-102.053927,40.001626],[-102.042974,36.994786],[-103.001438,37.000263],[-104.337812,36.994786],[-106.868158,36.994786],[-107.421329,37.000263],[-109.042503,37.000263],[-109.042503,38.166851],[-109.058934,38.27639],[-109.053457,39.125316],[-109.04798,40.998429],[-107.919731,41.003906]]]}}}},{{"type":"Feature","id":"09","properties":{{"name":"Connecticut","density":739.1,"zone":5}},"geometry":{{"type":"Polygon","coordinates":[[[-73.053528,42.039048],[-71.799309,42.022617],[-71.799309,42.006186],[-71.799309,41.414677],[-71.859555,41.321569],[-71.947186,41.338],[-72.385341,41.261322],[-72.905651,41.28323],[-73.130205,41.146307],[-73.371191,41.102491],[-73.655992,40.987475],[-73.727192,41.102491],[-73.48073,41.21203],[-73.55193,41.294184],[-73.486206,42.050002],[-73.053528,42.039048]]]}}}},{{"type":"Feature","id":"10","properties":{{"name":"Delaware","density":464.3,"zone":4}},"geometry":{{"type":"Polygon","coordinates":[[[-75.414089,39.804456],[-75.507197,39.683964],[-75.611259,39.61824],[-75.589352,39.459409],[-75.441474,39.311532],[-75.403136,39.065069],[-75.189535,38.807653],[-75.09095,38.796699],[-75.047134,38.451652],[-75.693413,38.462606],[-75.786521,39.722302],[-75.616736,39.831841],[-75.414089,39.804456]]]}}}},{{"type":"Feature","id":"11","properties":{{"name":"District of Columbia","density":10065,"zone":4}},"geometry":{{"type":"Polygon","coordinates":[[[-77.035264,38.993869],[-76.909294,38.895284],[-77.040741,38.791222],[-77.117418,38.933623],[-77.035264,38.993869]]]}}}},{{"type":"Feature","id":"12","properties":{{"name":"Florida","density":353.4,"zone":2}},"geometry":{{"type":"Polygon","coordinates":[[[-85.497137,30.997536],[-85.004212,31.003013],[-84.867289,30.712735],[-83.498053,30.647012],[-82.216449,30.570335],[-82.167157,30.356734],[-82.046664,30.362211],[-82.002849,30.564858],[-82.041187,30.751074],[-81.948079,30.827751],[-81.718048,30.745597],[-81.444201,30.707258],[-81.383954,30.27458],[-81.257985,29.787132],[-80.967707,29.14633],[-80.524075,28.461713],[-80.589798,28.41242],[-80.56789,28.094758],[-80.381674,27.738757],[-80.091397,27.021277],[-80.03115,26.796723],[-80.036627,26.566691],[-80.146166,25.739673],[-80.239274,25.723243],[-80.337859,25.465826],[-80.304997,25.383672],[-80.49669,25.197456],[-80.573367,25.241272],[-80.759583,25.164595],[-81.077246,25.120779],[-81.170354,25.224841],[-81.126538,25.378195],[-81.351093,25.821827],[-81.526355,25.903982],[-81.679709,25.843735],[-81.800202,26.090198],[-81.833064,26.292844],[-82.041187,26.517399],[-82.09048,26.665276],[-82.057618,26.878877],[-82.172634,26.917216],[-82.145249,26.791246],[-82.249311,26.758384],[-82.566974,27.300601],[-82.692943,27.437525],[-82.391711,27.837342],[-82.588881,27.815434],[-82.720328,27.689464],[-82.851774,27.886634],[-82.676512,28.434328],[-82.643651,28.888914],[-82.764143,28.998453],[-82.802482,29.14633],[-82.994175,29.179192],[-83.218729,29.420177],[-83.399469,29.518762],[-83.410422,29.66664],[-83.536392,29.721409],[-83.640454,29.885717],[-84.02384,30.104795],[-84.357933,30.055502],[-84.341502,29.902148],[-84.451041,29.929533],[-84.867289,29.743317],[-85.310921,29.699501],[-85.299967,29.80904],[-85.404029,29.940487],[-85.924338,30.236241],[-86.29677,30.362211],[-86.630863,30.395073],[-86.910187,30.373165],[-87.518128,30.280057],[-87.37025,30.427934],[-87.446927,30.510088],[-87.408589,30.674397],[-87.633143,30.86609],[-87.600282,30.997536],[-85.497137,30.997536]]]}}}},{{"type":"Feature","id":"13","properties":{{"name":"Georgia","density":169.5,"zone":3}},"geometry":{{"type":"Polygon","coordinates":[[[-83.109191,35.00118],[-83.322791,34.787579],[-83.339222,34.683517],[-83.005129,34.469916],[-82.901067,34.486347],[-82.747713,34.26727],[-82.714851,34.152254],[-82.55602,33.94413],[-82.325988,33.81816],[-82.194542,33.631944],[-81.926172,33.462159],[-81.937125,33.347144],[-81.761863,33.160928],[-81.493493,33.007573],[-81.42777,32.843265],[-81.416816,32.629664],[-81.279893,32.558464],[-81.121061,32.290094],[-81.115584,32.120309],[-80.885553,32.032678],[-81.132015,31.693108],[-81.175831,31.517845],[-81.279893,31.364491],[-81.290846,31.20566],[-81.400385,31.13446],[-81.444201,30.707258],[-81.718048,30.745597],[-81.948079,30.827751],[-82.041187,30.751074],[-82.002849,30.564858],[-82.046664,30.362211],[-82.167157,30.356734],[-82.216449,30.570335],[-83.498053,30.647012],[-84.867289,30.712735],[-85.004212,31.003013],[-85.113751,31.27686],[-85.042551,31.539753],[-85.141136,31.840985],[-85.053504,32.01077],[-85.058981,32.13674],[-84.889196,32.262709],[-85.004212,32.322956],[-84.960397,32.421541],[-85.069935,32.580372],[-85.184951,32.859696],[-85.431413,34.124869],[-85.606675,34.984749],[-84.319594,34.990226],[-83.618546,34.984749],[-83.109191,35.00118]]]}}}},{{"type":"Feature","id":"15","properties":{{"name":"Hawaii","density":214.1,"zone":1}},"geometry":{{"type":"MultiPolygon","coordinates":[[[[-155.634835,18.948267],[-155.881297,19.035898],[-155.919636,19.123529],[-155.886774,19.348084],[-156.062036,19.73147],[-155.925113,19.857439],[-155.826528,20.032702],[-155.897728,20.147717],[-155.87582,20.26821],[-155.596496,20.12581],[-155.284311,20.021748],[-155.092618,19.868393],[-155.092618,19.736947],[-154.807817,19.523346],[-154.983079,19.348084],[-155.295265,19.26593],[-155.514342,19.134483],[-155.634835,18.948267]]],[[[-156.587823,21.029505],[-156.472807,20.892581],[-156.324929,20.952827],[-156.00179,20.793996],[-156.051082,20.651596],[-156.379699,20.580396],[-156.445422,20.60778],[-156.461853,20.783042],[-156.631638,20.821381],[-156.697361,20.919966],[-156.587823,21.029505]]],[[[-156.982162,21.210244],[-157.080747,21.106182],[-157.310779,21.106182],[-157.239579,21.221198],[-156.982162,21.210244]]],[[[-157.951581,21.697691],[-157.842042,21.462183],[-157.896811,21.325259],[-158.110412,21.303352],[-158.252813,21.582676],[-158.126843,21.588153],[-157.951581,21.697691]]],[[[-159.468693,22.228955],[-159.353678,22.218001],[-159.298908,22.113939],[-159.33177,21.966061],[-159.446786,21.872953],[-159.764448,21.987969],[-159.726109,22.152277],[-159.468693,22.228955]]]]}}}},{{"type":"Feature","id":"16","properties":{{"name":"Idaho","density":19.15,"zone":5}},"geometry":{{"type":"Polygon","coordinates":[[[-116.04751,49.000239],[-116.04751,47.976051],[-115.724371,47.696727],[-115.718894,47.42288],[-115.527201,47.302388],[-115.324554,47.258572],[-115.302646,47.187372],[-114.930214,46.919002],[-114.886399,46.809463],[-114.623506,46.705401],[-114.612552,46.639678],[-114.322274,46.645155],[-114.464674,46.272723],[-114.492059,46.037214],[-114.387997,45.88386],[-114.568736,45.774321],[-114.497536,45.670259],[-114.546828,45.560721],[-114.333228,45.456659],[-114.086765,45.593582],[-113.98818,45.703121],[-113.807441,45.604536],[-113.834826,45.522382],[-113.736241,45.330689],[-113.571933,45.128042],[-113.45144,45.056842],[-113.456917,44.865149],[-113.341901,44.782995],[-113.133778,44.772041],[-113.002331,44.448902],[-112.887315,44.394132],[-112.783254,44.48724],[-112.471068,44.481763],[-112.241036,44.569394],[-112.104113,44.520102],[-111.868605,44.563917],[-111.819312,44.509148],[-111.616665,44.547487],[-111.386634,44.75561],[-111.227803,44.580348],[-111.047063,44.476286],[-111.047063,42.000709],[-112.164359,41.995232],[-114.04295,41.995232],[-117.027882,42.000709],[-117.027882,43.830007],[-116.896436,44.158624],[-116.97859,44.240778],[-117.170283,44.257209],[-117.241483,44.394132],[-117.038836,44.750133],[-116.934774,44.782995],[-116.830713,44.930872],[-116.847143,45.02398],[-116.732128,45.144473],[-116.671881,45.319735],[-116.463758,45.61549],[-116.545912,45.752413],[-116.78142,45.823614],[-116.918344,45.993399],[-116.92382,46.168661],[-117.055267,46.343923],[-117.038836,46.426077],[-117.044313,47.762451],[-117.033359,49.000239],[-116.04751,49.000239]]]}}}},{{"type":"Feature","id":"17","properties":{{"name":"Illinois","density":231.5,"zone":5}},"geometry":{{"type":"Polygon","coordinates":[[[-90.639984,42.510065],[-88.788778,42.493634],[-87.802929,42.493634],[-87.83579,42.301941],[-87.682436,42.077386],[-87.523605,41.710431],[-87.529082,39.34987],[-87.63862,39.169131],[-87.512651,38.95553],[-87.49622,38.780268],[-87.62219,38.637868],[-87.655051,38.506421],[-87.83579,38.292821],[-87.950806,38.27639],[-87.923421,38.15042],[-88.000098,38.101128],[-88.060345,37.865619],[-88.027483,37.799896],[-88.15893,37.657496],[-88.065822,37.482234],[-88.476592,37.389126],[-88.514931,37.285064],[-88.421823,37.153617],[-88.547792,37.071463],[-88.914747,37.224817],[-89.029763,37.213863],[-89.183118,37.038601],[-89.133825,36.983832],[-89.292656,36.994786],[-89.517211,37.279587],[-89.435057,37.34531],[-89.517211,37.537003],[-89.517211,37.690357],[-89.84035,37.903958],[-89.949889,37.88205],[-90.059428,38.013497],[-90.355183,38.216144],[-90.349706,38.374975],[-90.179921,38.632391],[-90.207305,38.725499],[-90.10872,38.845992],[-90.251121,38.917192],[-90.470199,38.961007],[-90.585214,38.867899],[-90.661891,38.928146],[-90.727615,39.256762],[-91.061708,39.470363],[-91.368417,39.727779],[-91.494386,40.034488],[-91.50534,40.237135],[-91.417709,40.379535],[-91.401278,40.560274],[-91.121954,40.669813],[-91.09457,40.823167],[-90.963123,40.921752],[-90.946692,41.097014],[-91.111001,41.239415],[-91.045277,41.414677],[-90.656414,41.463969],[-90.344229,41.589939],[-90.311367,41.743293],[-90.179921,41.809016],[-90.141582,42.000709],[-90.168967,42.126679],[-90.393521,42.225264],[-90.420906,42.329326],[-90.639984,42.510065]]]}}}},{{"type":"Feature","id":"18","properties":{{"name":"Indiana","density":181.7,"zone":5}},"geometry":{{"type":"Polygon","coordinates":[[[-85.990061,41.759724],[-84.807042,41.759724],[-84.807042,41.694001],[-84.801565,40.500028],[-84.817996,39.103408],[-84.894673,39.059592],[-84.812519,38.785745],[-84.987781,38.780268],[-85.173997,38.68716],[-85.431413,38.730976],[-85.42046,38.533806],[-85.590245,38.451652],[-85.655968,38.325682],[-85.83123,38.27639],[-85.924338,38.024451],[-86.039354,37.958727],[-86.263908,38.051835],[-86.302247,38.166851],[-86.521325,38.040881],[-86.504894,37.931343],[-86.729448,37.893004],[-86.795172,37.991589],[-87.047111,37.893004],[-87.129265,37.788942],[-87.381204,37.93682],[-87.512651,37.903958],[-87.600282,37.975158],[-87.682436,37.903958],[-87.934375,37.893004],[-88.027483,37.799896],[-88.060345,37.865619],[-88.000098,38.101128],[-87.923421,38.15042],[-87.950806,38.27639],[-87.83579,38.292821],[-87.655051,38.506421],[-87.62219,38.637868],[-87.49622,38.780268],[-87.512651,38.95553],[-87.63862,39.169131],[-87.529082,39.34987],[-87.523605,41.710431],[-87.42502,41.644708],[-87.118311,41.644708],[-86.822556,41.759724],[-85.990061,41.759724]]]}}}},{{"type":"Feature","id":"19","properties":{{"name":"Iowa","density":54.81,"zone":5}},"geometry":{{"type":"Polygon","coordinates":[[[-91.368417,43.501391],[-91.215062,43.501391],[-91.204109,43.353514],[-91.056231,43.254929],[-91.176724,43.134436],[-91.143862,42.909881],[-91.067185,42.75105],[-90.711184,42.636034],[-90.639984,42.510065],[-90.420906,42.329326],[-90.393521,42.225264],[-90.168967,42.126679],[-90.141582,42.000709],[-90.179921,41.809016],[-90.311367,41.743293],[-90.344229,41.589939],[-90.656414,41.463969],[-91.045277,41.414677],[-91.111001,41.239415],[-90.946692,41.097014],[-90.963123,40.921752],[-91.09457,40.823167],[-91.121954,40.669813],[-91.401278,40.560274],[-91.417709,40.379535],[-91.527248,40.412397],[-91.729895,40.615043],[-91.833957,40.609566],[-93.257961,40.582182],[-94.632673,40.571228],[-95.7664,40.587659],[-95.881416,40.719105],[-95.826646,40.976521],[-95.925231,41.201076],[-95.919754,41.453015],[-96.095016,41.540646],[-96.122401,41.67757],[-96.062155,41.798063],[-96.127878,41.973325],[-96.264801,42.039048],[-96.44554,42.488157],[-96.631756,42.707235],[-96.544125,42.855112],[-96.511264,43.052282],[-96.434587,43.123482],[-96.560556,43.222067],[-96.527695,43.397329],[-96.582464,43.479483],[-96.451017,43.501391],[-91.368417,43.501391]]]}}}},{{"type":"Feature","id":"20","properties":{{"name":"Kansas","density":35.09,"zone":4}},"geometry":{{"type":"Polygon","coordinates":[[[-101.90605,40.001626],[-95.306337,40.001626],[-95.207752,39.908518],[-94.884612,39.831841],[-95.109167,39.541563],[-94.983197,39.442978],[-94.824366,39.20747],[-94.610765,39.158177],[-94.616242,37.000263],[-100.087706,37.000263],[-102.042974,36.994786],[-102.053927,40.001626],[-101.90605,40.001626]]]}}}},{{"type":"Feature","id":"21","properties":{{"name":"Kentucky","density":110,"zone":4}},"geometry":{{"type":"Polygon","coordinates":[[[-83.903347,38.769315],[-83.678792,38.632391],[-83.519961,38.703591],[-83.142052,38.626914],[-83.032514,38.725499],[-82.890113,38.758361],[-82.846298,38.588575],[-82.731282,38.561191],[-82.594358,38.424267],[-82.621743,38.123036],[-82.50125,37.931343],[-82.342419,37.783465],[-82.293127,37.668449],[-82.101434,37.553434],[-81.969987,37.537003],[-82.353373,37.268633],[-82.720328,37.120755],[-82.720328,37.044078],[-82.868205,36.978355],[-82.879159,36.890724],[-83.070852,36.852385],[-83.136575,36.742847],[-83.673316,36.600446],[-83.689746,36.584015],[-84.544149,36.594969],[-85.289013,36.627831],[-85.486183,36.616877],[-86.592525,36.655216],[-87.852221,36.633308],[-88.071299,36.677123],[-88.054868,36.496384],[-89.298133,36.507338],[-89.418626,36.496384],[-89.363857,36.622354],[-89.215979,36.578538],[-89.133825,36.983832],[-89.183118,37.038601],[-89.029763,37.213863],[-88.914747,37.224817],[-88.547792,37.071463],[-88.421823,37.153617],[-88.514931,37.285064],[-88.476592,37.389126],[-88.065822,37.482234],[-88.15893,37.657496],[-88.027483,37.799896],[-87.934375,37.893004],[-87.682436,37.903958],[-87.600282,37.975158],[-87.512651,37.903958],[-87.381204,37.93682],[-87.129265,37.788942],[-87.047111,37.893004],[-86.795172,37.991589],[-86.729448,37.893004],[-86.504894,37.931343],[-86.521325,38.040881],[-86.302247,38.166851],[-86.263908,38.051835],[-86.039354,37.958727],[-85.924338,38.024451],[-85.83123,38.27639],[-85.655968,38.325682],[-85.590245,38.451652],[-85.42046,38.533806],[-85.431413,38.730976],[-85.173997,38.68716],[-84.987781,38.780268],[-84.812519,38.785745],[-84.894673,39.059592],[-84.817996,39.103408],[-84.43461,39.103408],[-84.231963,38.895284],[-84.215533,38.807653],[-83.903347,38.769315]]]}}}},{{"type":"Feature","id":"22","properties":{{"name":"Louisiana","density":105,"zone":2}},"geometry":{{"type":"Polygon","coordinates":[[[-93.608485,33.018527],[-91.16577,33.002096],[-91.072662,32.887081],[-91.143862,32.843265],[-91.154816,32.640618],[-91.006939,32.514649],[-90.985031,32.218894],[-91.105524,31.988862],[-91.341032,31.846462],[-91.401278,31.621907],[-91.499863,31.643815],[-91.516294,31.27686],[-91.636787,31.265906],[-91.565587,31.068736],[-91.636787,30.997536],[-89.747242,30.997536],[-89.845827,30.66892],[-89.681519,30.449842],[-89.643181,30.285534],[-89.522688,30.181472],[-89.818443,30.044549],[-89.84035,29.945964],[-89.599365,29.88024],[-89.495303,30.039072],[-89.287179,29.88024],[-89.30361,29.754271],[-89.424103,29.699501],[-89.648657,29.748794],[-89.621273,29.655686],[-89.69795,29.513285],[-89.506257,29.387316],[-89.199548,29.348977],[-89.09001,29.2011],[-89.002379,29.179192],[-89.16121,29.009407],[-89.336472,29.042268],[-89.484349,29.217531],[-89.851304,29.310638],[-89.851304,29.480424],[-90.032043,29.425654],[-90.021089,29.283254],[-90.103244,29.151807],[-90.23469,29.129899],[-90.333275,29.277777],[-90.563307,29.283254],[-90.645461,29.129899],[-90.798815,29.086084],[-90.963123,29.179192],[-91.09457,29.190146],[-91.220539,29.436608],[-91.445094,29.546147],[-91.532725,29.529716],[-91.620356,29.73784],[-91.883249,29.710455],[-91.888726,29.836425],[-92.146142,29.715932],[-92.113281,29.622824],[-92.31045,29.535193],[-92.617159,29.579009],[-92.97316,29.715932],[-93.2251,29.776178],[-93.767317,29.726886],[-93.838517,29.688547],[-93.926148,29.787132],[-93.690639,30.143133],[-93.767317,30.334826],[-93.696116,30.438888],[-93.728978,30.575812],[-93.630393,30.679874],[-93.526331,30.93729],[-93.542762,31.15089],[-93.816609,31.556184],[-93.822086,31.775262],[-94.041164,31.994339],[-94.041164,33.018527],[-93.608485,33.018527]]]}}}},{{"type":"Feature","id":"23","properties":{{"name":"Maine","density":43.04,"zone":6}},"geometry":{{"type":"Polygon","coordinates":[[[-70.703921,43.057759],[-70.824413,43.128959],[-70.807983,43.227544],[-70.966814,43.34256],[-71.032537,44.657025],[-71.08183,45.303304],[-70.649151,45.440228],[-70.720352,45.511428],[-70.556043,45.664782],[-70.386258,45.735983],[-70.41912,45.796229],[-70.260289,45.889337],[-70.309581,46.064599],[-70.210996,46.327492],[-70.057642,46.415123],[-69.997395,46.694447],[-69.225147,47.461219],[-69.044408,47.428357],[-69.033454,47.242141],[-68.902007,47.176418],[-68.578868,47.285957],[-68.376221,47.285957],[-68.233821,47.357157],[-67.954497,47.198326],[-67.790188,47.066879],[-67.779235,45.944106],[-67.801142,45.675736],[-67.456095,45.604536],[-67.505388,45.48952],[-67.417757,45.379982],[-67.488957,45.281397],[-67.346556,45.128042],[-67.16034,45.160904],[-66.979601,44.804903],[-67.187725,44.646072],[-67.308218,44.706318],[-67.406803,44.596779],[-67.549203,44.624164],[-67.565634,44.531056],[-67.75185,44.54201],[-68.047605,44.328409],[-68.118805,44.476286],[-68.222867,44.48724],[-68.173574,44.328409],[-68.403606,44.251732],[-68.458375,44.377701],[-68.567914,44.311978],[-68.82533,44.311978],[-68.830807,44.459856],[-68.984161,44.426994],[-68.956777,44.322932],[-69.099177,44.103854],[-69.071793,44.043608],[-69.258008,43.923115],[-69.444224,43.966931],[-69.553763,43.840961],[-69.707118,43.82453],[-69.833087,43.720469],[-69.986442,43.742376],[-70.030257,43.851915],[-70.254812,43.676653],[-70.194565,43.567114],[-70.358873,43.528776],[-70.369827,43.435668],[-70.556043,43.320652],[-70.703921,43.057759]]]}}}},{{"type":"Feature","id":"24","properties":{{"name":"Maryland","density":596.3,"zone":4}},"geometry":{{"type":"MultiPolygon","coordinates":[[[[-75.994645,37.95325],[-76.016553,37.95325],[-76.043938,37.95325],[-75.994645,37.95325]]],[[[-79.477979,39.722302],[-75.786521,39.722302],[-75.693413,38.462606],[-75.047134,38.451652],[-75.244304,38.029928],[-75.397659,38.013497],[-75.671506,37.95325],[-75.885106,37.909435],[-75.879629,38.073743],[-75.961783,38.139466],[-75.846768,38.210667],[-76.000122,38.374975],[-76.049415,38.303775],[-76.257538,38.320205],[-76.328738,38.500944],[-76.263015,38.500944],[-76.257538,38.736453],[-76.191815,38.829561],[-76.279446,39.147223],[-76.169907,39.333439],[-76.000122,39.366301],[-75.972737,39.557994],[-76.098707,39.536086],[-76.104184,39.437501],[-76.367077,39.311532],[-76.443754,39.196516],[-76.460185,38.906238],[-76.55877,38.769315],[-76.514954,38.539283],[-76.383508,38.380452],[-76.399939,38.259959],[-76.317785,38.139466],[-76.3616,38.057312],[-76.591632,38.216144],[-76.920248,38.292821],[-77.018833,38.446175],[-77.205049,38.358544],[-77.276249,38.479037],[-77.128372,38.632391],[-77.040741,38.791222],[-76.909294,38.895284],[-77.035264,38.993869],[-77.117418,38.933623],[-77.248864,39.026731],[-77.456988,39.076023],[-77.456988,39.223901],[-77.566527,39.306055],[-77.719881,39.322485],[-77.834897,39.601809],[-78.004682,39.601809],[-78.174467,39.694917],[-78.267575,39.61824],[-78.431884,39.623717],[-78.470222,39.514178],[-78.765977,39.585379],[-78.963147,39.437501],[-79.094593,39.470363],[-79.291763,39.300578],[-79.488933,39.20747],[-79.477979,39.722302]]]]}}}},{{"type":"Feature","id":"25","properties":{{"name":"Massachusetts","density":840.2,"zone":5}},"geometry":{{"type":"Polygon","coordinates":[[[-70.917521,42.887974],[-70.818936,42.871543],[-70.780598,42.696281],[-70.824413,42.55388],[-70.983245,42.422434],[-70.988722,42.269079],[-70.769644,42.247172],[-70.638197,42.08834],[-70.660105,41.962371],[-70.550566,41.929509],[-70.539613,41.814493],[-70.260289,41.715908],[-69.937149,41.809016],[-70.008349,41.672093],[-70.484843,41.5516],[-70.660105,41.546123],[-70.764167,41.639231],[-70.928475,41.611847],[-70.933952,41.540646],[-71.120168,41.496831],[-71.196845,41.67757],[-71.22423,41.710431],[-71.328292,41.781632],[-71.383061,42.01714],[-71.530939,42.01714],[-71.799309,42.006186],[-71.799309,42.022617],[-73.053528,42.039048],[-73.486206,42.050002],[-73.508114,42.08834],[-73.267129,42.745573],[-72.456542,42.729142],[-71.29543,42.696281],[-71.185891,42.789389],[-70.917521,42.887974]]]}}}},{{"type":"Feature","id":"26","properties":{{"name":"Michigan","density":173.9,"zone":5}},"geometry":{{"type":"MultiPolygon","coordinates":[[[[-83.454238,41.732339],[-84.807042,41.694001],[-84.807042,41.759724],[-85.990061,41.759724],[-86.822556,41.759724],[-86.619909,41.891171],[-86.482986,42.115725],[-86.357016,42.252649],[-86.263908,42.444341],[-86.209139,42.718189],[-86.231047,43.013943],[-86.526801,43.594499],[-86.433693,43.813577],[-86.499417,44.07647],[-86.269385,44.34484],[-86.220093,44.569394],[-86.252954,44.689887],[-86.088646,44.73918],[-86.066738,44.903488],[-85.809322,44.947303],[-85.612152,45.128042],[-85.628583,44.766564],[-85.524521,44.750133],[-85.393075,44.930872],[-85.387598,45.237581],[-85.305444,45.314258],[-85.031597,45.363551],[-85.119228,45.577151],[-84.938489,45.75789],[-84.713934,45.768844],[-84.461995,45.653829],[-84.215533,45.637398],[-84.09504,45.494997],[-83.908824,45.484043],[-83.596638,45.352597],[-83.4871,45.358074],[-83.317314,45.144473],[-83.454238,45.029457],[-83.322791,44.88158],[-83.273499,44.711795],[-83.333745,44.339363],[-83.536392,44.246255],[-83.585684,44.054562],[-83.82667,43.988839],[-83.958116,43.758807],[-83.908824,43.671176],[-83.667839,43.589022],[-83.481623,43.714992],[-83.262545,43.972408],[-82.917498,44.070993],[-82.747713,43.994316],[-82.643651,43.851915],[-82.539589,43.435668],[-82.523158,43.227544],[-82.413619,42.975605],[-82.517681,42.614127],[-82.681989,42.559357],[-82.687466,42.690804],[-82.797005,42.652465],[-82.922975,42.351234],[-83.125621,42.236218],[-83.185868,42.006186],[-83.437807,41.814493],[-83.454238,41.732339]]],[[[-85.508091,45.730506],[-85.49166,45.610013],[-85.623106,45.588105],[-85.568337,45.75789],[-85.508091,45.730506]]],[[[-87.589328,45.095181],[-87.742682,45.199243],[-87.649574,45.341643],[-87.885083,45.363551],[-87.791975,45.500474],[-87.781021,45.675736],[-87.989145,45.796229],[-88.10416,45.922199],[-88.531362,46.020784],[-88.662808,45.987922],[-89.09001,46.135799],[-90.119674,46.338446],[-90.229213,46.508231],[-90.415429,46.568478],[-90.026566,46.672539],[-89.851304,46.793032],[-89.413149,46.842325],[-89.128348,46.990202],[-88.996902,46.995679],[-88.887363,47.099741],[-88.575177,47.247618],[-88.416346,47.373588],[-88.180837,47.455742],[-87.956283,47.384542],[-88.350623,47.077833],[-88.443731,46.973771],[-88.438254,46.787555],[-88.246561,46.929956],[-87.901513,46.908048],[-87.633143,46.809463],[-87.392158,46.535616],[-87.260711,46.486323],[-87.008772,46.530139],[-86.948526,46.469893],[-86.696587,46.437031],[-86.159846,46.667063],[-85.880522,46.68897],[-85.508091,46.678016],[-85.256151,46.754694],[-85.064458,46.760171],[-85.02612,46.480847],[-84.82895,46.442508],[-84.63178,46.486323],[-84.549626,46.4206],[-84.418179,46.502754],[-84.127902,46.530139],[-84.122425,46.179615],[-83.990978,46.031737],[-83.793808,45.993399],[-83.7719,46.091984],[-83.580208,46.091984],[-83.476146,45.987922],[-83.563777,45.911245],[-84.111471,45.976968],[-84.374364,45.933153],[-84.659165,46.053645],[-84.741319,45.944106],[-84.70298,45.850998],[-84.82895,45.872906],[-85.015166,46.00983],[-85.338305,46.091984],[-85.502614,46.097461],[-85.661445,45.966014],[-85.924338,45.933153],[-86.209139,45.960537],[-86.324155,45.905768],[-86.351539,45.796229],[-86.663725,45.703121],[-86.647294,45.834568],[-86.784218,45.861952],[-86.838987,45.725029],[-87.069019,45.719552],[-87.17308,45.659305],[-87.326435,45.423797],[-87.611236,45.122565],[-87.589328,45.095181]]],[[[-88.805209,47.976051],[-89.057148,47.850082],[-89.188594,47.833651],[-89.177641,47.937713],[-88.547792,48.173221],[-88.668285,48.008913],[-88.805209,47.976051]]]]}}}},{{"type":"Feature","id":"27","properties":{{"name":"Minnesota","density":67.14,"zone":6}},"geometry":{{"type":"Polygon","coordinates":[[[-92.014696,46.705401],[-92.091373,46.749217],[-92.29402,46.667063],[-92.29402,46.075553],[-92.354266,46.015307],[-92.639067,45.933153],[-92.869098,45.719552],[-92.885529,45.577151],[-92.770513,45.566198],[-92.644544,45.440228],[-92.75956,45.286874],[-92.737652,45.117088],[-92.808852,44.750133],[-92.545959,44.569394],[-92.337835,44.552964],[-92.233773,44.443425],[-91.927065,44.333886],[-91.877772,44.202439],[-91.592971,44.032654],[-91.43414,43.994316],[-91.242447,43.775238],[-91.269832,43.616407],[-91.215062,43.501391],[-91.368417,43.501391],[-96.451017,43.501391],[-96.451017,45.297827],[-96.681049,45.412843],[-96.856311,45.604536],[-96.582464,45.818137],[-96.560556,45.933153],[-96.598895,46.332969],[-96.719387,46.437031],[-96.801542,46.656109],[-96.785111,46.924479],[-96.823449,46.968294],[-96.856311,47.609096],[-97.053481,47.948667],[-97.130158,48.140359],[-97.16302,48.545653],[-97.097296,48.682577],[-97.228743,49.000239],[-95.152983,49.000239],[-95.152983,49.383625],[-94.955813,49.372671],[-94.824366,49.295994],[-94.69292,48.775685],[-94.588858,48.715438],[-94.260241,48.699007],[-94.221903,48.649715],[-93.838517,48.627807],[-93.794701,48.518268],[-93.466085,48.545653],[-93.466085,48.589469],[-93.208669,48.644238],[-92.984114,48.62233],[-92.726698,48.540176],[-92.655498,48.436114],[-92.50762,48.447068],[-92.370697,48.222514],[-92.304974,48.315622],[-92.053034,48.359437],[-92.009219,48.266329],[-91.713464,48.200606],[-91.713464,48.112975],[-91.565587,48.041775],[-91.264355,48.080113],[-91.083616,48.178698],[-90.837154,48.238944],[-90.749522,48.091067],[-90.579737,48.123929],[-90.377091,48.091067],[-90.141582,48.112975],[-89.873212,47.987005],[-89.615796,48.008913],[-89.637704,47.954144],[-89.971797,47.828174],[-90.437337,47.729589],[-90.738569,47.625527],[-91.171247,47.368111],[-91.357463,47.20928],[-91.642264,47.028541],[-92.091373,46.787555],[-92.014696,46.705401]]]}}}},{{"type":"Feature","id":"28","properties":{{"name":"Mississippi","density":63.5,"zone":3}},"geometry":{{"type":"Polygon","coordinates":[[[-88.471115,34.995703],[-88.202745,34.995703],[-88.098683,34.891641],[-88.241084,33.796253],[-88.471115,31.895754],[-88.394438,30.367688],[-88.503977,30.323872],[-88.744962,30.34578],[-88.843547,30.411504],[-89.084533,30.367688],[-89.418626,30.252672],[-89.522688,30.181472],[-89.643181,30.285534],[-89.681519,30.449842],[-89.845827,30.66892],[-89.747242,30.997536],[-91.636787,30.997536],[-91.565587,31.068736],[-91.636787,31.265906],[-91.516294,31.27686],[-91.499863,31.643815],[-91.401278,31.621907],[-91.341032,31.846462],[-91.105524,31.988862],[-90.985031,32.218894],[-91.006939,32.514649],[-91.154816,32.640618],[-91.143862,32.843265],[-91.072662,32.887081],[-91.16577,33.002096],[-91.089093,33.13902],[-91.143862,33.347144],[-91.056231,33.429298],[-91.231493,33.560744],[-91.072662,33.867453],[-90.891923,34.026284],[-90.952169,34.135823],[-90.744046,34.300131],[-90.749522,34.365854],[-90.568783,34.420624],[-90.585214,34.617794],[-90.481152,34.661609],[-90.409952,34.831394],[-90.251121,34.908072],[-90.311367,34.995703],[-88.471115,34.995703]]]}}}},{{"type":"Feature","id":"29","properties":{{"name":"Missouri","density":87.26,"zone":4}},"geometry":{{"type":"Polygon","coordinates":[[[-91.833957,40.609566],[-91.729895,40.615043],[-91.527248,40.412397],[-91.417709,40.379535],[-91.50534,40.237135],[-91.494386,40.034488],[-91.368417,39.727779],[-91.061708,39.470363],[-90.727615,39.256762],[-90.661891,38.928146],[-90.585214,38.867899],[-90.470199,38.961007],[-90.251121,38.917192],[-90.10872,38.845992],[-90.207305,38.725499],[-90.179921,38.632391],[-90.349706,38.374975],[-90.355183,38.216144],[-90.059428,38.013497],[-89.949889,37.88205],[-89.84035,37.903958],[-89.517211,37.690357],[-89.517211,37.537003],[-89.435057,37.34531],[-89.517211,37.279587],[-89.292656,36.994786],[-89.133825,36.983832],[-89.215979,36.578538],[-89.363857,36.622354],[-89.418626,36.496384],[-89.484349,36.496384],[-89.539119,36.496384],[-89.533642,36.249922],[-89.730812,35.997983],[-90.377091,35.997983],[-90.218259,36.184199],[-90.064905,36.304691],[-90.152536,36.496384],[-94.473842,36.501861],[-94.616242,36.501861],[-94.616242,37.000263],[-94.610765,39.158177],[-94.824366,39.20747],[-94.983197,39.442978],[-95.109167,39.541563],[-94.884612,39.831841],[-95.207752,39.908518],[-95.306337,40.001626],[-95.552799,40.264519],[-95.7664,40.587659],[-94.632673,40.571228],[-93.257961,40.582182],[-91.833957,40.609566]]]}}}},{{"type":"Feature","id":"30","properties":{{"name":"Montana","density":6.858,"zone":6}},"geometry":{{"type":"Polygon","coordinates":[[[-104.047534,49.000239],[-104.042057,47.861036],[-104.047534,45.944106],[-104.042057,44.996596],[-104.058488,44.996596],[-105.91517,45.002073],[-109.080842,45.002073],[-111.05254,45.002073],[-111.047063,44.476286],[-111.227803,44.580348],[-111.386634,44.75561],[-111.616665,44.547487],[-111.819312,44.509148],[-111.868605,44.563917],[-112.104113,44.520102],[-112.241036,44.569394],[-112.471068,44.481763],[-112.783254,44.48724],[-112.887315,44.394132],[-113.002331,44.448902],[-113.133778,44.772041],[-113.341901,44.782995],[-113.456917,44.865149],[-113.45144,45.056842],[-113.571933,45.128042],[-113.736241,45.330689],[-113.834826,45.522382],[-113.807441,45.604536],[-113.98818,45.703121],[-114.086765,45.593582],[-114.333228,45.456659],[-114.546828,45.560721],[-114.497536,45.670259],[-114.568736,45.774321],[-114.387997,45.88386],[-114.492059,46.037214],[-114.464674,46.272723],[-114.322274,46.645155],[-114.612552,46.639678],[-114.623506,46.705401],[-114.886399,46.809463],[-114.930214,46.919002],[-115.302646,47.187372],[-115.324554,47.258572],[-115.527201,47.302388],[-115.718894,47.42288],[-115.724371,47.696727],[-116.04751,47.976051],[-116.04751,49.000239],[-111.50165,48.994762],[-109.453274,49.000239],[-104.047534,49.000239]]]}}}},{{"type":"Feature","id":"31","properties":{{"name":"Nebraska","density":23.97,"zone":5}},"geometry":{{"type":"Polygon","coordinates":[[[-103.324578,43.002989],[-101.626726,42.997512],[-98.499393,42.997512],[-98.466531,42.94822],[-97.951699,42.767481],[-97.831206,42.866066],[-97.688806,42.844158],[-97.217789,42.844158],[-96.692003,42.657942],[-96.626279,42.515542],[-96.44554,42.488157],[-96.264801,42.039048],[-96.127878,41.973325],[-96.062155,41.798063],[-96.122401,41.67757],[-96.095016,41.540646],[-95.919754,41.453015],[-95.925231,41.201076],[-95.826646,40.976521],[-95.881416,40.719105],[-95.7664,40.587659],[-95.552799,40.264519],[-95.306337,40.001626],[-101.90605,40.001626],[-102.053927,40.001626],[-102.053927,41.003906],[-104.053011,41.003906],[-104.053011,43.002989],[-103.324578,43.002989]]]}}}},{{"type":"Feature","id":"32","properties":{{"name":"Nevada","density":24.8,"zone":3}},"geometry":{{"type":"Polygon","coordinates":[[[-117.027882,42.000709],[-114.04295,41.995232],[-114.048427,37.000263],[-114.048427,36.195153],[-114.152489,36.025367],[-114.251074,36.01989],[-114.371566,36.140383],[-114.738521,36.102045],[-114.678275,35.516012],[-114.596121,35.324319],[-114.574213,35.138103],[-114.634459,35.00118],[-115.85034,35.970598],[-116.540435,36.501861],[-117.498899,37.21934],[-118.71478,38.101128],[-120.001861,38.999346],[-119.996384,40.264519],[-120.001861,41.995232],[-118.698349,41.989755],[-117.027882,42.000709]]]}}}},{{"type":"Feature","id":"33","properties":{{"name":"New Hampshire","density":147,"zone":6}},"geometry":{{"type":"Polygon","coordinates":[[[-71.08183,45.303304],[-71.032537,44.657025],[-70.966814,43.34256],[-70.807983,43.227544],[-70.824413,43.128959],[-70.703921,43.057759],[-70.818936,42.871543],[-70.917521,42.887974],[-71.185891,42.789389],[-71.29543,42.696281],[-72.456542,42.729142],[-72.544173,42.80582],[-72.533219,42.953697],[-72.445588,43.008466],[-72.456542,43.150867],[-72.379864,43.572591],[-72.204602,43.769761],[-72.116971,43.994316],[-72.02934,44.07647],[-72.034817,44.322932],[-71.700724,44.41604],[-71.536416,44.585825],[-71.629524,44.750133],[-71.4926,44.914442],[-71.503554,45.013027],[-71.361154,45.270443],[-71.131122,45.243058],[-71.08183,45.303304]]]}}}},{{"type":"Feature","id":"34","properties":{{"name":"New Jersey","density":1189,"zone":4}},"geometry":{{"type":"Polygon","coordinates":[[[-74.236547,41.14083],[-73.902454,40.998429],[-74.022947,40.708151],[-74.187255,40.642428],[-74.274886,40.489074],[-74.001039,40.412397],[-73.979131,40.297381],[-74.099624,39.760641],[-74.411809,39.360824],[-74.614456,39.245808],[-74.795195,38.993869],[-74.888303,39.158177],[-75.178581,39.240331],[-75.534582,39.459409],[-75.55649,39.607286],[-75.561967,39.629194],[-75.507197,39.683964],[-75.414089,39.804456],[-75.145719,39.88661],[-75.129289,39.963288],[-74.82258,40.127596],[-74.773287,40.215227],[-75.058088,40.417874],[-75.069042,40.543843],[-75.195012,40.576705],[-75.205966,40.691721],[-75.052611,40.866983],[-75.134765,40.971045],[-74.882826,41.179168],[-74.828057,41.288707],[-74.69661,41.359907],[-74.236547,41.14083]]]}}}},{{"type":"Feature","id":"35","properties":{{"name":"New Mexico","density":17.16,"zone":4}},"geometry":{{"type":"Polygon","coordinates":[[[-107.421329,37.000263],[-106.868158,36.994786],[-104.337812,36.994786],[-103.001438,37.000263],[-103.001438,36.501861],[-103.039777,36.501861],[-103.045254,34.01533],[-103.067161,33.002096],[-103.067161,31.999816],[-106.616219,31.999816],[-106.643603,31.901231],[-106.528588,31.786216],[-108.210008,31.786216],[-108.210008,31.331629],[-109.04798,31.331629],[-109.042503,37.000263],[-107.421329,37.000263]]]}}}},{{"type":"Feature","id":"36","properties":{{"name":"New York","density":412.3,"zone":5}},"geometry":{{"type":"Polygon","coordinates":[[[-73.343806,45.013027],[-73.332852,44.804903],[-73.387622,44.618687],[-73.294514,44.437948],[-73.321898,44.246255],[-73.436914,44.043608],[-73.349283,43.769761],[-73.404052,43.687607],[-73.245221,43.523299],[-73.278083,42.833204],[-73.267129,42.745573],[-73.508114,42.08834],[-73.486206,42.050002],[-73.55193,41.294184],[-73.48073,41.21203],[-73.727192,41.102491],[-73.655992,40.987475],[-73.22879,40.905321],[-73.141159,40.965568],[-72.774204,40.965568],[-72.587988,40.998429],[-72.28128,41.157261],[-72.259372,41.042245],[-72.100541,40.992952],[-72.467496,40.845075],[-73.239744,40.625997],[-73.562884,40.582182],[-73.776484,40.593136],[-73.935316,40.543843],[-74.022947,40.708151],[-73.902454,40.998429],[-74.236547,41.14083],[-74.69661,41.359907],[-74.740426,41.431108],[-74.89378,41.436584],[-75.074519,41.60637],[-75.052611,41.754247],[-75.173104,41.869263],[-75.249781,41.863786],[-75.35932,42.000709],[-79.76278,42.000709],[-79.76278,42.252649],[-79.76278,42.269079],[-79.149363,42.55388],[-79.050778,42.690804],[-78.853608,42.783912],[-78.930285,42.953697],[-79.012439,42.986559],[-79.072686,43.260406],[-78.486653,43.375421],[-77.966344,43.369944],[-77.75822,43.34256],[-77.533665,43.233021],[-77.391265,43.276836],[-76.958587,43.271359],[-76.695693,43.34256],[-76.41637,43.523299],[-76.235631,43.528776],[-76.230154,43.802623],[-76.137046,43.961454],[-76.3616,44.070993],[-76.312308,44.196962],[-75.912491,44.366748],[-75.764614,44.514625],[-75.282643,44.848718],[-74.828057,45.018503],[-74.148916,44.991119],[-73.343806,45.013027]]]}}}},{{"type":"Feature","id":"37","properties":{{"name":"North Carolina","density":198.2,"zone":4}},"geometry":{{"type":"Polygon","coordinates":[[[-80.978661,36.562108],[-80.294043,36.545677],[-79.510841,36.5402],[-75.868676,36.551154],[-75.75366,36.151337],[-76.032984,36.189676],[-76.071322,36.140383],[-76.410893,36.080137],[-76.460185,36.025367],[-76.68474,36.008937],[-76.673786,35.937736],[-76.399939,35.987029],[-76.3616,35.943213],[-76.060368,35.992506],[-75.961783,35.899398],[-75.781044,35.937736],[-75.715321,35.696751],[-75.775568,35.581735],[-75.89606,35.570781],[-76.147999,35.324319],[-76.482093,35.313365],[-76.536862,35.14358],[-76.394462,34.973795],[-76.279446,34.940933],[-76.493047,34.661609],[-76.673786,34.694471],[-76.991448,34.667086],[-77.210526,34.60684],[-77.555573,34.415147],[-77.82942,34.163208],[-77.971821,33.845545],[-78.179944,33.916745],[-78.541422,33.851022],[-79.675149,34.80401],[-80.797922,34.820441],[-80.781491,34.935456],[-80.934845,35.105241],[-81.038907,35.044995],[-81.044384,35.149057],[-82.276696,35.198349],[-82.550543,35.160011],[-82.764143,35.066903],[-83.109191,35.00118],[-83.618546,34.984749],[-84.319594,34.990226],[-84.29221,35.225734],[-84.09504,35.247642],[-84.018363,35.41195],[-83.7719,35.559827],[-83.498053,35.565304],[-83.251591,35.718659],[-82.994175,35.773428],[-82.775097,35.997983],[-82.638174,36.063706],[-82.610789,35.965121],[-82.216449,36.156814],[-82.03571,36.118475],[-81.909741,36.304691],[-81.723525,36.353984],[-81.679709,36.589492],[-80.978661,36.562108]]]}}}},{{"type":"Feature","id":"38","properties":{{"name":"North Dakota","density":9.916,"zone":6}},"geometry":{{"type":"Polygon","coordinates":[[[-97.228743,49.000239],[-97.097296,48.682577],[-97.16302,48.545653],[-97.130158,48.140359],[-97.053481,47.948667],[-96.856311,47.609096],[-96.823449,46.968294],[-96.785111,46.924479],[-96.801542,46.656109],[-96.719387,46.437031],[-96.598895,46.332969],[-96.560556,45.933153],[-104.047534,45.944106],[-104.042057,47.861036],[-104.047534,49.000239],[-97.228743,49.000239]]]}}}},{{"type":"Feature","id":"39","properties":{{"name":"Ohio","density":281.9,"zone":5}},"geometry":{{"type":"Polygon","coordinates":[[[-80.518598,41.978802],[-80.518598,40.636951],[-80.666475,40.582182],[-80.595275,40.472643],[-80.600752,40.319289],[-80.737675,40.078303],[-80.830783,39.711348],[-81.219646,39.388209],[-81.345616,39.344393],[-81.455155,39.410117],[-81.57017,39.267716],[-81.685186,39.273193],[-81.811156,39.0815],[-81.783771,38.966484],[-81.887833,38.873376],[-82.03571,39.026731],[-82.221926,38.785745],[-82.172634,38.632391],[-82.293127,38.577622],[-82.331465,38.446175],[-82.594358,38.424267],[-82.731282,38.561191],[-82.846298,38.588575],[-82.890113,38.758361],[-83.032514,38.725499],[-83.142052,38.626914],[-83.519961,38.703591],[-83.678792,38.632391],[-83.903347,38.769315],[-84.215533,38.807653],[-84.231963,38.895284],[-84.43461,39.103408],[-84.817996,39.103408],[-84.801565,40.500028],[-84.807042,41.694001],[-83.454238,41.732339],[-83.065375,41.595416],[-82.933929,41.513262],[-82.835344,41.589939],[-82.616266,41.431108],[-82.479343,41.381815],[-82.013803,41.513262],[-81.739956,41.485877],[-81.444201,41.672093],[-81.011523,41.852832],[-80.518598,41.978802],[-80.518598,41.978802]]]}}}},{{"type":"Feature","id":"40","properties":{{"name":"Oklahoma","density":55.22,"zone":3}},"geometry":{{"type":"Polygon","coordinates":[[[-100.087706,37.000263],[-94.616242,37.000263],[-94.616242,36.501861],[-94.430026,35.395519],[-94.484796,33.637421],[-94.868182,33.74696],[-94.966767,33.861976],[-95.224183,33.960561],[-95.289906,33.87293],[-95.547322,33.878407],[-95.602092,33.933176],[-95.8376,33.834591],[-95.936185,33.889361],[-96.149786,33.840068],[-96.346956,33.686714],[-96.423633,33.774345],[-96.631756,33.845545],[-96.850834,33.845545],[-96.922034,33.960561],[-97.173974,33.736006],[-97.256128,33.861976],[-97.371143,33.823637],[-97.458774,33.905791],[-97.694283,33.982469],[-97.869545,33.851022],[-97.946222,33.987946],[-98.088623,34.004376],[-98.170777,34.113915],[-98.36247,34.157731],[-98.488439,34.064623],[-98.570593,34.146777],[-98.767763,34.135823],[-98.986841,34.223454],[-99.189488,34.2125],[-99.260688,34.404193],[-99.57835,34.415147],[-99.698843,34.382285],[-99.923398,34.573978],[-100.000075,34.563024],[-100.000075,36.501861],[-101.812942,36.501861],[-103.001438,36.501861],[-103.001438,37.000263],[-102.042974,36.994786],[-100.087706,37.000263]]]}}}},{{"type":"Feature","id":"41","properties":{{"name":"Oregon","density":40.33,"zone":4}},"geometry":{{"type":"Polygon","coordinates":[[[-123.211348,46.174138],[-123.11824,46.185092],[-122.904639,46.08103],[-122.811531,45.960537],[-122.762239,45.659305],[-122.247407,45.549767],[-121.809251,45.708598],[-121.535404,45.725029],[-121.217742,45.670259],[-121.18488,45.604536],[-120.637186,45.746937],[-120.505739,45.697644],[-120.209985,45.725029],[-119.963522,45.823614],[-119.525367,45.911245],[-119.125551,45.933153],[-118.988627,45.998876],[-116.918344,45.993399],[-116.78142,45.823614],[-116.545912,45.752413],[-116.463758,45.61549],[-116.671881,45.319735],[-116.732128,45.144473],[-116.847143,45.02398],[-116.830713,44.930872],[-116.934774,44.782995],[-117.038836,44.750133],[-117.241483,44.394132],[-117.170283,44.257209],[-116.97859,44.240778],[-116.896436,44.158624],[-117.027882,43.830007],[-117.027882,42.000709],[-118.698349,41.989755],[-120.001861,41.995232],[-121.037003,41.995232],[-122.378853,42.011663],[-123.233256,42.006186],[-124.213628,42.000709],[-124.356029,42.115725],[-124.432706,42.438865],[-124.416275,42.663419],[-124.553198,42.838681],[-124.454613,43.002989],[-124.383413,43.271359],[-124.235536,43.55616],[-124.169813,43.8081],[-124.060274,44.657025],[-124.076705,44.772041],[-123.97812,45.144473],[-123.939781,45.659305],[-123.994551,45.944106],[-123.945258,46.113892],[-123.545441,46.261769],[-123.370179,46.146753],[-123.211348,46.174138]]]}}}},{{"type":"Feature","id":"42","properties":{{"name":"Pennsylvania","density":284.3,"zone":5}},"geometry":{{"type":"Polygon","coordinates":[[[-79.76278,42.252649],[-79.76278,42.000709],[-75.35932,42.000709],[-75.249781,41.863786],[-75.173104,41.869263],[-75.052611,41.754247],[-75.074519,41.60637],[-74.89378,41.436584],[-74.740426,41.431108],[-74.69661,41.359907],[-74.828057,41.288707],[-74.882826,41.179168],[-75.134765,40.971045],[-75.052611,40.866983],[-75.205966,40.691721],[-75.195012,40.576705],[-75.069042,40.543843],[-75.058088,40.417874],[-74.773287,40.215227],[-74.82258,40.127596],[-75.129289,39.963288],[-75.145719,39.88661],[-75.414089,39.804456],[-75.616736,39.831841],[-75.786521,39.722302],[-79.477979,39.722302],[-80.518598,39.722302],[-80.518598,40.636951],[-80.518598,41.978802],[-80.518598,41.978802],[-80.332382,42.033571],[-79.76278,42.269079],[-79.76278,42.252649]]]}}}},{{"type":"Feature","id":"44","properties":{{"name":"Rhode Island","density":1006,"zone":5}},"geometry":{{"type":"MultiPolygon","coordinates":[[[[-71.196845,41.67757],[-71.120168,41.496831],[-71.317338,41.474923],[-71.196845,41.67757]]],[[[-71.530939,42.01714],[-71.383061,42.01714],[-71.328292,41.781632],[-71.22423,41.710431],[-71.344723,41.726862],[-71.448785,41.578985],[-71.481646,41.370861],[-71.859555,41.321569],[-71.799309,41.414677],[-71.799309,42.006186],[-71.530939,42.01714]]]]}}}},{{"type":"Feature","id":"45","properties":{{"name":"South Carolina","density":155.4,"zone":3}},"geometry":{{"type":"Polygon","coordinates":[[[-82.764143,35.066903],[-82.550543,35.160011],[-82.276696,35.198349],[-81.044384,35.149057],[-81.038907,35.044995],[-80.934845,35.105241],[-80.781491,34.935456],[-80.797922,34.820441],[-79.675149,34.80401],[-78.541422,33.851022],[-78.716684,33.80173],[-78.935762,33.637421],[-79.149363,33.380005],[-79.187701,33.171881],[-79.357487,33.007573],[-79.582041,33.007573],[-79.631334,32.887081],[-79.866842,32.755634],[-79.998289,32.613234],[-80.206412,32.552987],[-80.430967,32.399633],[-80.452875,32.328433],[-80.660998,32.246279],[-80.885553,32.032678],[-81.115584,32.120309],[-81.121061,32.290094],[-81.279893,32.558464],[-81.416816,32.629664],[-81.42777,32.843265],[-81.493493,33.007573],[-81.761863,33.160928],[-81.937125,33.347144],[-81.926172,33.462159],[-82.194542,33.631944],[-82.325988,33.81816],[-82.55602,33.94413],[-82.714851,34.152254],[-82.747713,34.26727],[-82.901067,34.486347],[-83.005129,34.469916],[-83.339222,34.683517],[-83.322791,34.787579],[-83.109191,35.00118],[-82.764143,35.066903]]]}}}},{{"type":"Feature","id":"46","properties":{{"name":"South Dakota","density":98.07,"zone":6}},"geometry":{{"type":"Polygon","coordinates":[[[-104.047534,45.944106],[-96.560556,45.933153],[-96.582464,45.818137],[-96.856311,45.604536],[-96.681049,45.412843],[-96.451017,45.297827],[-96.451017,43.501391],[-96.582464,43.479483],[-96.527695,43.397329],[-96.560556,43.222067],[-96.434587,43.123482],[-96.511264,43.052282],[-96.544125,42.855112],[-96.631756,42.707235],[-96.44554,42.488157],[-96.626279,42.515542],[-96.692003,42.657942],[-97.217789,42.844158],[-97.688806,42.844158],[-97.831206,42.866066],[-97.951699,42.767481],[-98.466531,42.94822],[-98.499393,42.997512],[-101.626726,42.997512],[-103.324578,43.002989],[-104.053011,43.002989],[-104.058488,44.996596],[-104.042057,44.996596],[-104.047534,45.944106]]]}}}},{{"type":"Feature","id":"47","properties":{{"name":"Tennessee","density":88.08,"zone":4}},"geometry":{{"type":"Polygon","coordinates":[[[-88.054868,36.496384],[-88.071299,36.677123],[-87.852221,36.633308],[-86.592525,36.655216],[-85.486183,36.616877],[-85.289013,36.627831],[-84.544149,36.594969],[-83.689746,36.584015],[-83.673316,36.600446],[-81.679709,36.589492],[-81.723525,36.353984],[-81.909741,36.304691],[-82.03571,36.118475],[-82.216449,36.156814],[-82.610789,35.965121],[-82.638174,36.063706],[-82.775097,35.997983],[-82.994175,35.773428],[-83.251591,35.718659],[-83.498053,35.565304],[-83.7719,35.559827],[-84.018363,35.41195],[-84.09504,35.247642],[-84.29221,35.225734],[-84.319594,34.990226],[-85.606675,34.984749],[-87.359296,35.00118],[-88.202745,34.995703],[-88.471115,34.995703],[-90.311367,34.995703],[-90.212782,35.023087],[-90.114197,35.198349],[-90.130628,35.439335],[-89.944412,35.603643],[-89.911551,35.756997],[-89.763673,35.811767],[-89.730812,35.997983],[-89.533642,36.249922],[-89.539119,36.496384],[-89.484349,36.496384],[-89.418626,36.496384],[-89.298133,36.507338],[-88.054868,36.496384]]]}}}},{{"type":"Feature","id":"48","properties":{{"name":"Texas","density":98.07,"zone":3}},"geometry":{{"type":"Polygon","coordinates":[[[-101.812942,36.501861],[-100.000075,36.501861],[-100.000075,34.563024],[-99.923398,34.573978],[-99.698843,34.382285],[-99.57835,34.415147],[-99.260688,34.404193],[-99.189488,34.2125],[-98.986841,34.223454],[-98.767763,34.135823],[-98.570593,34.146777],[-98.488439,34.064623],[-98.36247,34.157731],[-98.170777,34.113915],[-98.088623,34.004376],[-97.946222,33.987946],[-97.869545,33.851022],[-97.694283,33.982469],[-97.458774,33.905791],[-97.371143,33.823637],[-97.256128,33.861976],[-97.173974,33.736006],[-96.922034,33.960561],[-96.850834,33.845545],[-96.631756,33.845545],[-96.423633,33.774345],[-96.346956,33.686714],[-96.149786,33.840068],[-95.936185,33.889361],[-95.8376,33.834591],[-95.602092,33.933176],[-95.547322,33.878407],[-95.289906,33.87293],[-95.224183,33.960561],[-94.966767,33.861976],[-94.868182,33.74696],[-94.484796,33.637421],[-94.380734,33.544313],[-94.183564,33.593606],[-94.041164,33.54979],[-94.041164,33.018527],[-94.041164,31.994339],[-93.822086,31.775262],[-93.816609,31.556184],[-93.542762,31.15089],[-93.526331,30.93729],[-93.630393,30.679874],[-93.728978,30.575812],[-93.696116,30.438888],[-93.767317,30.334826],[-93.690639,30.143133],[-93.926148,29.787132],[-93.838517,29.688547],[-94.002825,29.68307],[-94.523134,29.546147],[-94.70935,29.622824],[-94.742212,29.787132],[-94.873659,29.672117],[-94.966767,29.699501],[-95.016059,29.557101],[-94.911997,29.496854],[-94.895566,29.310638],[-95.081782,29.113469],[-95.383014,28.867006],[-95.985477,28.604113],[-96.045724,28.647929],[-96.226463,28.582205],[-96.23194,28.642452],[-96.478402,28.598636],[-96.593418,28.724606],[-96.664618,28.697221],[-96.401725,28.439805],[-96.593418,28.357651],[-96.774157,28.406943],[-96.801542,28.226204],[-97.026096,28.039988],[-97.256128,27.694941],[-97.404005,27.333463],[-97.513544,27.360848],[-97.540929,27.229401],[-97.425913,27.262263],[-97.480682,26.99937],[-97.557359,26.988416],[-97.562836,26.840538],[-97.469728,26.758384],[-97.442344,26.457153],[-97.332805,26.353091],[-97.30542,26.161398],[-97.217789,25.991613],[-97.524498,25.887551],[-97.650467,26.018997],[-97.885976,26.06829],[-98.198161,26.057336],[-98.466531,26.221644],[-98.669178,26.238075],[-98.822533,26.369522],[-99.030656,26.413337],[-99.173057,26.539307],[-99.266165,26.840538],[-99.446904,27.021277],[-99.424996,27.174632],[-99.50715,27.33894],[-99.479765,27.48134],[-99.605735,27.640172],[-99.709797,27.656603],[-99.879582,27.799003],[-99.934351,27.979742],[-100.082229,28.14405],[-100.29583,28.280974],[-100.399891,28.582205],[-100.498476,28.66436],[-100.629923,28.905345],[-100.673738,29.102515],[-100.799708,29.244915],[-101.013309,29.370885],[-101.062601,29.458516],[-101.259771,29.535193],[-101.413125,29.754271],[-101.851281,29.803563],[-102.114174,29.792609],[-102.338728,29.869286],[-102.388021,29.765225],[-102.629006,29.732363],[-102.809745,29.524239],[-102.919284,29.190146],[-102.97953,29.184669],[-103.116454,28.987499],[-103.280762,28.982022],[-103.527224,29.135376],[-104.146119,29.381839],[-104.266611,29.513285],[-104.507597,29.639255],[-104.677382,29.924056],[-104.688336,30.181472],[-104.858121,30.389596],[-104.896459,30.570335],[-105.005998,30.685351],[-105.394861,30.855136],[-105.602985,31.085167],[-105.77277,31.167321],[-105.953509,31.364491],[-106.205448,31.468553],[-106.38071,31.731446],[-106.528588,31.786216],[-106.643603,31.901231],[-106.616219,31.999816],[-103.067161,31.999816],[-103.067161,33.002096],[-103.045254,34.01533],[-103.039777,36.501861],[-103.001438,36.501861],[-101.812942,36.501861]]]}}}},{{"type":"Feature","id":"49","properties":{{"name":"Utah","density":34.3,"zone":5}},"geometry":{{"type":"Polygon","coordinates":[[[-112.164359,41.995232],[-111.047063,42.000709],[-111.047063,40.998429],[-109.04798,40.998429],[-109.053457,39.125316],[-109.058934,38.27639],[-109.042503,38.166851],[-109.042503,37.000263],[-110.499369,37.00574],[-114.048427,37.000263],[-114.04295,41.995232],[-112.164359,41.995232]]]}}}},{{"type":"Feature","id":"50","properties":{{"name":"Vermont","density":67.73,"zone":6}},"geometry":{{"type":"Polygon","coordinates":[[[-71.503554,45.013027],[-71.4926,44.914442],[-71.629524,44.750133],[-71.536416,44.585825],[-71.700724,44.41604],[-72.034817,44.322932],[-72.02934,44.07647],[-72.116971,43.994316],[-72.204602,43.769761],[-72.379864,43.572591],[-72.456542,43.150867],[-72.445588,43.008466],[-72.533219,42.953697],[-72.544173,42.80582],[-72.456542,42.729142],[-73.267129,42.745573],[-73.278083,42.833204],[-73.245221,43.523299],[-73.404052,43.687607],[-73.349283,43.769761],[-73.436914,44.043608],[-73.321898,44.246255],[-73.294514,44.437948],[-73.387622,44.618687],[-73.332852,44.804903],[-73.343806,45.013027],[-72.308664,45.002073],[-71.503554,45.013027]]]}}}},{{"type":"Feature","id":"51","properties":{{"name":"Virginia","density":204.5,"zone":4}},"geometry":{{"type":"MultiPolygon","coordinates":[[[[-75.397659,38.013497],[-75.244304,38.029928],[-75.375751,37.860142],[-75.512674,37.799896],[-75.594828,37.569865],[-75.802952,37.197433],[-75.972737,37.120755],[-76.027507,37.257679],[-75.939876,37.564388],[-75.671506,37.95325],[-75.397659,38.013497]]],[[[-76.016553,37.95325],[-75.994645,37.95325],[-76.043938,37.95325],[-76.016553,37.95325]]],[[[-78.349729,39.464886],[-77.82942,39.130793],[-77.719881,39.322485],[-77.566527,39.306055],[-77.456988,39.223901],[-77.456988,39.076023],[-77.248864,39.026731],[-77.117418,38.933623],[-77.040741,38.791222],[-77.128372,38.632391],[-77.248864,38.588575],[-77.325542,38.446175],[-77.281726,38.342113],[-77.013356,38.374975],[-76.964064,38.216144],[-76.613539,38.15042],[-76.514954,38.024451],[-76.235631,37.887527],[-76.3616,37.608203],[-76.246584,37.389126],[-76.383508,37.285064],[-76.399939,37.159094],[-76.273969,37.082417],[-76.410893,36.961924],[-76.619016,37.120755],[-76.668309,37.065986],[-76.48757,36.95097],[-75.994645,36.923586],[-75.868676,36.551154],[-79.510841,36.5402],[-80.294043,36.545677],[-80.978661,36.562108],[-81.679709,36.589492],[-83.673316,36.600446],[-83.136575,36.742847],[-83.070852,36.852385],[-82.879159,36.890724],[-82.868205,36.978355],[-82.720328,37.044078],[-82.720328,37.120755],[-82.353373,37.268633],[-81.969987,37.537003],[-81.986418,37.454849],[-81.849494,37.285064],[-81.679709,37.20291],[-81.55374,37.208387],[-81.362047,37.339833],[-81.225123,37.235771],[-80.967707,37.290541],[-80.513121,37.482234],[-80.474782,37.421987],[-80.29952,37.509618],[-80.294043,37.690357],[-80.184505,37.849189],[-79.998289,37.997066],[-79.921611,38.177805],[-79.724442,38.364021],[-79.647764,38.594052],[-79.477979,38.457129],[-79.313671,38.413313],[-79.209609,38.495467],[-78.996008,38.851469],[-78.870039,38.763838],[-78.404499,39.169131],[-78.349729,39.464886]]]]}}}},{{"type":"Feature","id":"53","properties":{{"name":"Washington","density":102.6,"zone":4}},"geometry":{{"type":"MultiPolygon","coordinates":[[[[-117.033359,49.000239],[-117.044313,47.762451],[-117.038836,46.426077],[-117.055267,46.343923],[-116.92382,46.168661],[-116.918344,45.993399],[-118.988627,45.998876],[-119.125551,45.933153],[-119.525367,45.911245],[-119.963522,45.823614],[-120.209985,45.725029],[-120.505739,45.697644],[-120.637186,45.746937],[-121.18488,45.604536],[-121.217742,45.670259],[-121.535404,45.725029],[-121.809251,45.708598],[-122.247407,45.549767],[-122.762239,45.659305],[-122.811531,45.960537],[-122.904639,46.08103],[-123.11824,46.185092],[-123.211348,46.174138],[-123.370179,46.146753],[-123.545441,46.261769],[-123.72618,46.300108],[-123.874058,46.239861],[-124.065751,46.327492],[-124.027412,46.464416],[-123.895966,46.535616],[-124.098612,46.74374],[-124.235536,47.285957],[-124.31769,47.357157],[-124.427229,47.740543],[-124.624399,47.88842],[-124.706553,48.184175],[-124.597014,48.381345],[-124.394367,48.288237],[-123.983597,48.162267],[-123.704273,48.167744],[-123.424949,48.118452],[-123.162056,48.167744],[-123.036086,48.080113],[-122.800578,48.08559],[-122.636269,47.866512],[-122.515777,47.882943],[-122.493869,47.587189],[-122.422669,47.318818],[-122.324084,47.346203],[-122.422669,47.576235],[-122.395284,47.800789],[-122.230976,48.030821],[-122.362422,48.123929],[-122.373376,48.288237],[-122.471961,48.468976],[-122.422669,48.600422],[-122.488392,48.753777],[-122.647223,48.775685],[-122.795101,48.8907],[-122.756762,49.000239],[-117.033359,49.000239]]],[[[-122.718423,48.310145],[-122.586977,48.35396],[-122.608885,48.151313],[-122.767716,48.227991],[-122.718423,48.310145]]],[[[-123.025132,48.583992],[-122.915593,48.715438],[-122.767716,48.556607],[-122.811531,48.419683],[-123.041563,48.458022],[-123.025132,48.583992]]]]}}}},{{"type":"Feature","id":"54","properties":{{"name":"West Virginia","density":77.06,"zone":4}},"geometry":{{"type":"Polygon","coordinates":[[[-80.518598,40.636951],[-80.518598,39.722302],[-79.477979,39.722302],[-79.488933,39.20747],[-79.291763,39.300578],[-79.094593,39.470363],[-78.963147,39.437501],[-78.765977,39.585379],[-78.470222,39.514178],[-78.431884,39.623717],[-78.267575,39.61824],[-78.174467,39.694917],[-78.004682,39.601809],[-77.834897,39.601809],[-77.719881,39.322485],[-77.82942,39.130793],[-78.349729,39.464886],[-78.404499,39.169131],[-78.870039,38.763838],[-78.996008,38.851469],[-79.209609,38.495467],[-79.313671,38.413313],[-79.477979,38.457129],[-79.647764,38.594052],[-79.724442,38.364021],[-79.921611,38.177805],[-79.998289,37.997066],[-80.184505,37.849189],[-80.294043,37.690357],[-80.29952,37.509618],[-80.474782,37.421987],[-80.513121,37.482234],[-80.967707,37.290541],[-81.225123,37.235771],[-81.362047,37.339833],[-81.55374,37.208387],[-81.679709,37.20291],[-81.849494,37.285064],[-81.986418,37.454849],[-81.969987,37.537003],[-82.101434,37.553434],[-82.293127,37.668449],[-82.342419,37.783465],[-82.50125,37.931343],[-82.621743,38.123036],[-82.594358,38.424267],[-82.331465,38.446175],[-82.293127,38.577622],[-82.172634,38.632391],[-82.221926,38.785745],[-82.03571,39.026731],[-81.887833,38.873376],[-81.783771,38.966484],[-81.811156,39.0815],[-81.685186,39.273193],[-81.57017,39.267716],[-81.455155,39.410117],[-81.345616,39.344393],[-81.219646,39.388209],[-80.830783,39.711348],[-80.737675,40.078303],[-80.600752,40.319289],[-80.595275,40.472643],[-80.666475,40.582182],[-80.518598,40.636951]]]}}}},{{"type":"Feature","id":"55","properties":{{"name":"Wisconsin","density":105.2,"zone":6}},"geometry":{{"type":"Polygon","coordinates":[[[-90.415429,46.568478],[-90.229213,46.508231],[-90.119674,46.338446],[-89.09001,46.135799],[-88.662808,45.987922],[-88.531362,46.020784],[-88.10416,45.922199],[-87.989145,45.796229],[-87.781021,45.675736],[-87.791975,45.500474],[-87.885083,45.363551],[-87.649574,45.341643],[-87.742682,45.199243],[-87.589328,45.095181],[-87.627666,44.974688],[-87.819359,44.95278],[-87.983668,44.722749],[-88.043914,44.563917],[-87.928898,44.536533],[-87.775544,44.640595],[-87.611236,44.837764],[-87.403112,44.914442],[-87.238804,45.166381],[-87.03068,45.22115],[-87.047111,45.089704],[-87.189511,44.969211],[-87.468835,44.552964],[-87.545512,44.322932],[-87.540035,44.158624],[-87.644097,44.103854],[-87.737205,43.8793],[-87.704344,43.687607],[-87.791975,43.561637],[-87.912467,43.249452],[-87.885083,43.002989],[-87.76459,42.783912],[-87.802929,42.493634],[-88.788778,42.493634],[-90.639984,42.510065],[-90.711184,42.636034],[-91.067185,42.75105],[-91.143862,42.909881],[-91.176724,43.134436],[-91.056231,43.254929],[-91.204109,43.353514],[-91.215062,43.501391],[-91.269832,43.616407],[-91.242447,43.775238],[-91.43414,43.994316],[-91.592971,44.032654],[-91.877772,44.202439],[-91.927065,44.333886],[-92.233773,44.443425],[-92.337835,44.552964],[-92.545959,44.569394],[-92.808852,44.750133],[-92.737652,45.117088],[-92.75956,45.286874],[-92.644544,45.440228],[-92.770513,45.566198],[-92.885529,45.577151],[-92.869098,45.719552],[-92.639067,45.933153],[-92.354266,46.015307],[-92.29402,46.075553],[-92.29402,46.667063],[-92.091373,46.749217],[-92.014696,46.705401],[-91.790141,46.694447],[-91.09457,46.864232],[-90.837154,46.95734],[-90.749522,46.88614],[-90.886446,46.754694],[-90.55783,46.584908],[-90.415429,46.568478]]]}}}},{{"type":"Feature","id":"56","properties":{{"name":"Wyoming","density":5.851,"zone":6}},"geometry":{{"type":"Polygon","coordinates":[[[-109.080842,45.002073],[-105.91517,45.002073],[-104.058488,44.996596],[-104.053011,43.002989],[-104.053011,41.003906],[-105.728954,40.998429],[-107.919731,41.003906],[-109.04798,40.998429],[-111.047063,40.998429],[-111.047063,42.000709],[-111.047063,44.476286],[-111.05254,45.002073],[-109.080842,45.002073]]]}}}},{{"type":"Feature","id":"72","properties":{{"name":"Puerto Rico","density":1082,"zone":1}},"geometry":{{"type":"Polygon","coordinates":[[[-66.448338,17.984326],[-66.771478,18.006234],[-66.924832,17.929556],[-66.985078,17.973372],[-67.209633,17.956941],[-67.154863,18.19245],[-67.269879,18.362235],[-67.094617,18.515589],[-66.957694,18.488204],[-66.409999,18.488204],[-65.840398,18.433435],[-65.632274,18.367712],[-65.626797,18.203403],[-65.730859,18.186973],[-65.834921,18.017187],[-66.234737,17.929556],[-66.448338,17.984326]]]}}}}]}};

// Initialize the full map with clustering - NOW LOADS DATA ON DEMAND
async function initFullMap() {{
    if (fullMap) return;

    // Show loading message in map container
    const mapContainer = document.getElementById('full-map');
    if (mapContainer) {{
        mapContainer.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#666;">Loading map data...</div>';
    }}

    // Load map data on demand (only when user clicks map tab)
    await loadMapData();

    // Clear loading message
    if (mapContainer) {{
        mapContainer.innerHTML = '';
    }}

    mapboxgl.accessToken = CONFIG.mapboxToken;
    fullMap = new mapboxgl.Map({{
        container: 'full-map',
        style: 'mapbox://styles/mapbox/light-v11',
        center: [-98.5795, 39.8283],  // US center
        zoom: 3
    }});

    fullMap.addControl(new mapboxgl.NavigationControl(), 'top-right');

    fullMap.on('load', () => {{
        const geojson = buildingsGeoJSON();

        // Add climate zones source and layers (behind buildings)
        fullMap.addSource('climate-zones', {{
            type: 'geojson',
            data: CLIMATE_ZONES
        }});

        // Climate zone fill layer
        fullMap.addLayer({{
            id: 'climate-zone-fill',
            type: 'fill',
            source: 'climate-zones',
            paint: {{
                'fill-color': [
                    'match', ['get', 'zone'],
                    1, '#ff4444',
                    2, '#ff8844',
                    3, '#ffcc44',
                    4, '#88cc44',
                    5, '#44cc88',
                    6, '#4488cc',
                    7, '#4444cc',
                    8, '#8844cc',
                    '#cccccc'
                ],
                'fill-opacity': [
                    'interpolate', ['linear'], ['zoom'],
                    3, 0.4,
                    5, 0.2,
                    7, 0
                ]
            }}
        }});

        // Climate zone boundary outlines
        fullMap.addLayer({{
            id: 'climate-zone-outline',
            type: 'line',
            source: 'climate-zones',
            paint: {{
                'line-color': '#ffffff',
                'line-width': 1,
                'line-opacity': [
                    'interpolate', ['linear'], ['zoom'],
                    3, 0.6,
                    5, 0.3,
                    7, 0
                ]
            }}
        }});

        // Add clustered source
        fullMap.addSource('buildings', {{
            type: 'geojson',
            data: geojson,
            cluster: true,
            clusterMaxZoom: 14,
            clusterRadius: 50
        }});

        // Cluster circles - color by count
        fullMap.addLayer({{
            id: 'clusters',
            type: 'circle',
            source: 'buildings',
            filter: ['has', 'point_count'],
            paint: {{
                'circle-color': ['step', ['get', 'point_count'],
                    '#1b95ff', 100,    // < 100: mid blue
                    '#0066cc', 500,    // < 500: primary blue
                    '#0052a3'          // 500+: dark blue
                ],
                'circle-radius': ['step', ['get', 'point_count'],
                    18, 100,
                    24, 500,
                    32
                ],
                'circle-stroke-width': 2,
                'circle-stroke-color': '#ffffff'
            }}
        }});

        // Cluster count labels - BIG and BOLD
        fullMap.addLayer({{
            id: 'cluster-count',
            type: 'symbol',
            source: 'buildings',
            filter: ['has', 'point_count'],
            layout: {{
                'text-field': '{{point_count_abbreviated}}',
                'text-size': ['step', ['get', 'point_count'], 14, 100, 16, 500, 18],
                'text-font': ['DIN Offc Pro Bold', 'Arial Unicode MS Bold'],
                'text-allow-overlap': true
            }},
            paint: {{
                'text-color': '#ffffff',
                'text-halo-color': '#0052a3',
                'text-halo-width': 1.5
            }}
        }});

        // Individual pins (unclustered)
        fullMap.addLayer({{
            id: 'unclustered-point',
            type: 'circle',
            source: 'buildings',
            filter: ['!', ['has', 'point_count']],
            paint: {{
                'circle-color': '#0066cc',
                'circle-radius': 8,
                'circle-stroke-width': 2,
                'circle-stroke-color': '#ffffff'
            }}
        }});

        // Hover highlight layer (orange ring behind hovered pin)
        fullMap.addLayer({{
            id: 'hover-highlight',
            type: 'circle',
            source: 'buildings',
            filter: ['==', ['get', 'id'], ''],
            paint: {{
                'circle-radius': 14,
                'circle-color': '#ff6600',
                'circle-stroke-width': 3,
                'circle-stroke-color': '#ffffff',
                'circle-opacity': 0.8
            }}
        }});

        // Badge showing count for stacked pins (multiple buildings at same location)
        fullMap.addLayer({{
            id: 'stacked-count',
            type: 'symbol',
            source: 'buildings',
            filter: ['all',
                ['!', ['has', 'point_count']],
                ['>', ['get', 'stackCount'], 1]
            ],
            layout: {{
                'text-field': ['get', 'stackCount'],
                'text-font': ['DIN Offc Pro Medium', 'Arial Unicode MS Bold'],
                'text-size': 10,
                'text-offset': [0.7, -0.7],
                'text-anchor': 'bottom-left'
            }},
            paint: {{
                'text-color': '#ffffff',
                'text-halo-color': '#0066cc',
                'text-halo-width': 2
            }}
        }});

        // Fade climate legend when zoomed in
        fullMap.on('zoom', () => {{
            const zoom = fullMap.getZoom();
            const legend = document.getElementById('climate-legend');
            if (legend) {{
                if (zoom >= 7) {{
                    legend.style.opacity = '0';
                    legend.style.pointerEvents = 'none';
                }} else if (zoom >= 5) {{
                    legend.style.opacity = '0.5';
                    legend.style.pointerEvents = 'auto';
                }} else {{
                    legend.style.opacity = '1';
                    legend.style.pointerEvents = 'auto';
                }}
            }}
        }});

        setupMapInteractions(fullMap);
    }});
}}

// Spiderfy: spread out stacked pins at same location
let spiderfiedMarkers = [];

function spiderfyStack(stackKey, centerLng, centerLat, map) {{
    clearSpiderfy();

    // Get all buildings at this location (MAP_DATA loaded on demand)
    if (!MAP_DATA) return;
    const stackedBuildings = MAP_DATA.filter(b => `${{b.lat}},${{b.lon}}` === stackKey);
    if (stackedBuildings.length <= 1) return;

    // Calculate positions in a circle
    const radius = 0.00015;  // ~15 meters at equator
    const angleStep = (2 * Math.PI) / stackedBuildings.length;

    stackedBuildings.forEach((b, i) => {{
        const angle = i * angleStep - Math.PI / 2;  // Start from top
        const offsetLng = centerLng + radius * Math.cos(angle);
        const offsetLat = centerLat + radius * Math.sin(angle);

        // Create marker element
        const el = document.createElement('div');
        el.className = 'spiderfy-marker';
        el.innerHTML = '<div class="spiderfy-pin"></div>';

        // Create popup
        const spiderLogoHtml = expandedPortfolioLogo
            ? `<div style="background:#f3f4f6;padding:8px 12px;display:flex;align-items:center;border-radius:6px 6px 0 0;"><img src="${{expandedPortfolioLogo}}" style="height:28px;max-width:100px;object-fit:contain;" onerror="this.parentElement.style.display='none'"></div>`
            : '';
        const imgHtml = b.image
            ? `<img src="${{CONFIG.awsBucket}}/thumbnails/${{b.image}}" style="width:100%;height:80px;object-fit:cover;${{expandedPortfolioLogo ? '' : 'border-radius:6px 6px 0 0;'}}">`
            : '';
        const popup = new mapboxgl.Popup({{ offset: 25, closeButton: true }})
            .setHTML(`
                <div style="min-width:200px;">
                    ${{spiderLogoHtml}}
                    ${{imgHtml}}
                    <div style="padding:10px;">
                        <div style="font-weight:600;color:#0066cc;">${{b.address}}</div>
                        <div style="color:#666;font-size:12px;">${{b.city}}, ${{b.state}}</div>
                        <div style="color:#666;font-size:12px;">${{b.type}}</div>
                        <div style="color:${{savingsColor(b.total_opex)}};font-weight:600;margin-top:6px;">${{formatMoney(b.total_opex)}}/yr</div>
                        <div style="font-size:11px;color:#999;margin-top:4px;">Click pin to view details</div>
                    </div>
                </div>
            `);

        // Create and add marker
        const marker = new mapboxgl.Marker(el)
            .setLngLat([offsetLng, offsetLat])
            .setPopup(popup)
            .addTo(map);

        // Click to navigate
        el.addEventListener('click', (e) => {{
            e.stopPropagation();
            window.location.href = `buildings/${{b.id}}.html`;
        }});

        spiderfiedMarkers.push(marker);
    }});

    // Zoom in slightly to show spread
    map.easeTo({{
        center: [centerLng, centerLat],
        zoom: Math.max(map.getZoom(), 17)
    }});
}}

function clearSpiderfy() {{
    spiderfiedMarkers.forEach(m => m.remove());
    spiderfiedMarkers = [];
}}

// Setup map interactions: popups, hover, click
function setupMapInteractions(map) {{
    // Popup for hovering unclustered pins
    const popup = new mapboxgl.Popup({{
        closeButton: false,
        closeOnClick: false,
        offset: [0, -12],
        maxWidth: '280px'
    }});

    // Track hovered building to avoid redundant updates
    let hoveredId = null;

    // Use mousemove for smoother hover detection (like NYC implementation)
    map.on('mousemove', 'unclustered-point', (e) => {{
        map.getCanvas().style.cursor = 'pointer';
        const props = e.features[0].properties;
        const coords = e.features[0].geometry.coordinates.slice();

        // Skip if same building (avoid redundant popup updates)
        if (hoveredId === props.id) return;
        hoveredId = props.id;

        // Update hover highlight layer
        if (map.getLayer('hover-highlight')) {{
            map.setFilter('hover-highlight', ['==', ['get', 'id'], props.id]);
        }}

        // Portfolio logo header (shown when a portfolio is expanded)
        const logoHtml = expandedPortfolioLogo
            ? `<div style="background:#f3f4f6;padding:8px 12px;display:flex;align-items:center;border-radius:6px 6px 0 0;"><img src="${{expandedPortfolioLogo}}" style="height:32px;max-width:120px;object-fit:contain;" onerror="this.parentElement.style.display='none'"></div>`
            : '';

        const imgHtml = props.image
            ? `<img src="${{CONFIG.awsBucket}}/thumbnails/${{props.image}}" style="width:100%;height:100px;object-fit:cover;${{expandedPortfolioLogo ? '' : 'border-radius:6px 6px 0 0;'}}">`
            : '';

        popup.setLngLat(coords)
            .setHTML(`
                <div style="min-width:220px;cursor:pointer;" onclick="window.location.href='buildings/${{props.id}}.html'">
                    ${{logoHtml}}
                    ${{imgHtml}}
                    <div style="padding:12px;">
                        <div style="font-weight:600;font-size:14px;margin-bottom:4px;color:#0066cc;">${{props.address}}</div>
                        <div style="color:#666;font-size:12px;margin-bottom:8px;">${{props.city}}, ${{props.state}} &bull; ${{props.type}}</div>
                        <div style="color:${{savingsColor(props.opex)}};font-weight:600;font-size:14px;padding-top:8px;border-top:1px solid #eee;">
                            ${{formatMoney(props.opex)}}/yr savings
                        </div>
                        <div style="font-size:11px;color:#999;margin-top:6px;text-align:center;">Click for details &rarr;</div>
                    </div>
                </div>
            `)
            .addTo(map);

        // Highlight table row
        highlightTableRow(props.id);
    }});

    map.on('mouseleave', 'unclustered-point', () => {{
        map.getCanvas().style.cursor = '';
        hoveredId = null;
        popup.remove();
        clearTableHighlight();
        // Clear hover highlight
        if (map.getLayer('hover-highlight')) {{
            map.setFilter('hover-highlight', ['==', ['get', 'id'], '']);
        }}
    }});

    // Click pin → spiderfy if stacked, else navigate to building
    map.on('click', 'unclustered-point', (e) => {{
        const props = e.features[0].properties;
        const coords = e.features[0].geometry.coordinates;

        // If multiple buildings at this location, spiderfy them
        if (props.stackCount > 1) {{
            spiderfyStack(props.stackKey, coords[0], coords[1], map);
            return;
        }}

        // Single building → navigate
        window.location.href = `buildings/${{props.id}}.html`;
    }});

    // Click elsewhere on map → clear spiderfied markers
    map.on('click', (e) => {{
        // Only clear if not clicking on a feature
        const features = map.queryRenderedFeatures(e.point, {{ layers: ['unclustered-point', 'clusters'] }});
        if (features.length === 0) {{
            clearSpiderfy();
        }}
    }});

    // Click cluster → zoom in
    map.on('click', 'clusters', (e) => {{
        const features = map.queryRenderedFeatures(e.point, {{ layers: ['clusters'] }});
        const clusterId = features[0].properties.cluster_id;
        map.getSource('buildings').getClusterExpansionZoom(clusterId, (err, zoom) => {{
            if (!err) {{
                map.easeTo({{
                    center: features[0].geometry.coordinates,
                    zoom: zoom
                }});
            }}
        }});
    }});

    // Cursor pointer on clusters
    map.on('mouseenter', 'clusters', () => {{
        map.getCanvas().style.cursor = 'pointer';
    }});
    map.on('mouseleave', 'clusters', () => {{
        map.getCanvas().style.cursor = '';
    }});
}}

// Highlight table row when hovering pin
function highlightTableRow(buildingId) {{
    clearTableHighlight();
    const row = document.querySelector(`tr[data-id="${{buildingId}}"]`);
    if (row) {{
        row.classList.add('pin-highlight');
        row.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
    }}
}}

// Clear table row highlight
function clearTableHighlight() {{
    document.querySelectorAll('tr.pin-highlight').forEach(r => {{
        r.classList.remove('pin-highlight');
    }});
}}

// Open map panel (lazy init)
function openMapPanel() {{
    document.getElementById('map-panel').classList.add('open');
    updateMapTitle();
    // Initialize map on first open (lazy load for performance)
    setTimeout(() => {{
        initFullMap();
        if (fullMap) {{
            fullMap.resize();
            // Update map data based on current context (expanded portfolio + filters)
            if (fullMap.isStyleLoaded()) {{
                updateMapData();
            }} else {{
                fullMap.once('load', updateMapData);
            }}
        }}
    }}, 350); // Wait for CSS transition
}}

function closeMapPanel() {{
    document.getElementById('map-panel').classList.remove('open');
}}

function resetMap() {{
    if (!fullMap) return;

    // Clear address search input
    const addressInput = document.getElementById('addressAutocomplete');
    if (addressInput) addressInput.value = '';

    // Remove address marker and search markers
    if (addressMarker) {{ addressMarker.remove(); addressMarker = null; }}
    searchMarkers.forEach(m => m.remove());
    searchMarkers = [];
    selectedAddressLocation = null;

    // Remove radius circle
    if (fullMap.getLayer('radius-circle-layer')) fullMap.removeLayer('radius-circle-layer');
    if (fullMap.getSource('radius-circle')) fullMap.removeSource('radius-circle');

    // Clear spiderfied markers
    clearSpiderfy();

    // Reset map view to initial USA view
    fullMap.flyTo({{
        center: [-98.5795, 39.8283],
        zoom: 3,
        duration: 1000
    }});

    // Collapse expanded portfolios
    document.querySelectorAll('.portfolio-card.expanded').forEach(card => {{
        card.classList.remove('expanded');
    }});
    expandedPortfolioLogo = null;  // Clear portfolio logo

    // Reset filter states
    activeVertical = 'all';
    selectedBuildingType = null;
    globalQuery = '';
    selectedOwner = '';

    // Reset UI controls
    document.querySelectorAll('.vertical-btn').forEach(b => b.classList.remove('selected'));
    const allBtn = document.querySelector('.vertical-btn[data-vertical="all"]');
    if (allBtn) allBtn.classList.add('selected');
    document.querySelectorAll('.building-type-btn').forEach(b => {{
        b.classList.remove('selected');
        b.classList.remove('hidden');
    }});
    document.querySelectorAll('.opp-tile').forEach(t => t.classList.remove('selected'));
    const searchInput = document.getElementById('global-search');
    if (searchInput) searchInput.value = '';

    // Apply filters and update map
    updateFilterChips();
    applyFilters();
    updatePortfolioStats();
    updateMapTitle();
    updateMapData();
}}

// Update map title based on expanded portfolio
function updateMapTitle() {{
    const titleEl = document.getElementById('map-panel-title');
    if (!titleEl) return;

    const expandedPortfolio = document.querySelector('.portfolio-card.expanded');
    if (expandedPortfolio && expandedPortfolioLogo) {{
        const orgName = expandedPortfolio.getAttribute('data-org');
        titleEl.innerHTML = `<img src="${{expandedPortfolioLogo}}" style="height:32px;max-width:100px;object-fit:contain;" onerror="this.style.display='none'"><span>${{orgName}} Buildings</span>`;
    }} else if (expandedPortfolio) {{
        const orgName = expandedPortfolio.getAttribute('data-org');
        titleEl.innerHTML = `<span>${{orgName}} Buildings</span>`;
    }} else {{
        titleEl.innerHTML = 'All Buildings Map';
    }}
}}

// =============================================================================
// SMART IMAGE LOADING
// =============================================================================

const imageLoader = {{
    loaded: new Set(),
    loading: new Set(),

    load(img) {{
        if (this.loaded.has(img) || this.loading.has(img)) return;
        if (!img.dataset.src) return;
        this.loading.add(img);
        const src = img.dataset.src;
        const preload = new Image();
        preload.onload = () => {{
            img.src = src;
            img.removeAttribute('data-src');
            this.loading.delete(img);
            this.loaded.add(img);
        }};
        preload.onerror = () => this.loading.delete(img);
        preload.src = src;
    }},

    loadCard(card) {{
        if (!card) return;
        card.querySelectorAll('img[data-src]').forEach(img => this.load(img));
    }}
}};

// Track how many buildings shown per portfolio
const portfolioBuildingCounts = {{}};
const BUILDINGS_PER_BATCH = 10;

// Load building rows into a portfolio card - with Show More pagination
function loadPortfolioRows(card, loadMore = false) {{
    const idx = parseInt(card.dataset.idx);
    const container = card.querySelector('.building-rows-container');
    if (!container) return;

    // Use embedded data - NO fetch, NO waiting
    let buildings = PORTFOLIO_BUILDINGS[idx];
    if (!buildings || !buildings.length) return;

    // Filter by selected building type if active
    if (selectedBuildingType) {{
        buildings = buildings.filter(b => b.type === selectedBuildingType);
    }}
    // Filter by active vertical if not 'all'
    if (activeVertical && activeVertical !== 'all') {{
        buildings = buildings.filter(b => b.vertical === activeVertical);
    }}

    if (!buildings.length) {{
        container.innerHTML = '';
        return;
    }}

    // Track shown count
    if (!loadMore) {{
        portfolioBuildingCounts[idx] = BUILDINGS_PER_BATCH;
    }} else {{
        portfolioBuildingCounts[idx] = (portfolioBuildingCounts[idx] || BUILDINGS_PER_BATCH) + BUILDINGS_PER_BATCH;
    }}
    const showCount = Math.min(portfolioBuildingCounts[idx], buildings.length);
    const buildingsToShow = buildings.slice(0, showCount);

    // Generate grid rows
    const bucket = CONFIG.awsBucket;
    const html = buildingsToShow.map(b => {{
        const thumb = b.image
            ? `<img src="${{bucket}}/thumbnails/${{b.image}}" class="building-thumb" alt="" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'" loading="eager"><div class="building-thumb-placeholder" style="display:none">🏢</div>`
            : `<div class="building-thumb-placeholder">🏢</div>`;
        // Strip zip code and city/state from address (show only street address)
        let addrClean = (b.address || '').replace(/,?\\s*\\d{{5}}(-\\d{{4}})?$/, '').trim();
        // Also strip ", City, ST" or ", City ST" pattern from end
        if (b.city && b.state) {{
            const cityStatePattern = new RegExp(',?\\\\s*' + b.city.replace(/[.*+?^${{}}()|[\\\\]\\\\\\\\]/g, '\\\\\\\\$&') + ',?\\\\s*' + b.state + '\\\\s*$', 'i');
            addrClean = addrClean.replace(cityStatePattern, '').trim();
        }}
        const cityState = b.city && b.state ? `${{b.city}}, ${{b.state}}` : '';
        const sqft = b.sqft >= 1000000 ? `${{(b.sqft/1000000).toFixed(1)}}M` : b.sqft >= 10000 ? `${{Math.round(b.sqft/1000)}}K` : b.sqft > 0 ? Math.round(b.sqft).toLocaleString() : '-';
        const eui = formatEuiRating(b.eui, b.eui_benchmark);
        const opex = b.opex >= 1000000000 ? `$${{(b.opex/1000000000).toFixed(1)}}B` : b.opex >= 1000000 ? `$${{Math.round(b.opex/1000000)}}M` : b.opex >= 1000 ? `$${{Math.round(b.opex/1000)}}K` : `$${{Math.round(b.opex)}}`;
        const val = b.valuation >= 1000000000 ? `$${{(b.valuation/1000000000).toFixed(1)}}B` : b.valuation >= 1000000 ? `$${{Math.round(b.valuation/1000000)}}M` : b.valuation >= 1000 ? `$${{Math.round(b.valuation/1000)}}K` : `$${{Math.round(b.valuation)}}`;
        const carbon = b.carbon >= 1000000 ? `${{(b.carbon/1000000).toFixed(1)}}M` : b.carbon >= 1000 ? `${{Math.round(b.carbon/1000)}}K` : Math.round(b.carbon || 0);

        const extLink = b.url ? `<a href="${{b.url}}" target="_blank" onclick="event.stopPropagation()" style="margin-left:4px;color:var(--primary)">↗</a>` : '';
        const addrLine1 = b.property_name ? `${{addrClean}}, ${{cityState}}` : addrClean;
        const addrLine2 = b.property_name ? b.property_name : cityState;
        return `<div class="building-grid-row" data-radio-type="${{b.type}}" data-vertical="${{b.vertical}}" data-sqft="${{b.sqft}}" data-opex="${{b.opex}}" data-valuation="${{b.valuation}}" data-carbon="${{b.carbon}}" onclick="window.location='buildings/${{b.id}}.html'">
            <div>${{thumb}}</div>
            <span class="stat-cell"><span class="addr-main">${{addrLine1}}${{extLink}}</span><span class="addr-sub">${{addrLine2}}</span></span>
            <span class="stat-cell">${{b.type || '-'}}</span>
            <span class="stat-cell">${{sqft}}</span>
            <span class="stat-cell">${{eui}}</span>
            <span class="stat-cell valuation-value">${{val}}</span>
            <span class="stat-cell carbon-value">${{carbon}}</span>
            <span class="stat-cell opex-value">${{opex}}</span>
        </div>`;
    }}).join('');

    const remaining = buildings.length - showCount;

    // Simple control bar: ▲ (collapse) and ▼ (show more)
    const showLess = `<span class="row-arrow" onclick="event.stopPropagation(); showLessBuildings(this.closest('.portfolio-card'))">▲</span>`;
    const showMore = remaining > 0
        ? `<span class="row-arrow" onclick="event.stopPropagation(); loadPortfolioRows(this.closest('.portfolio-card'), true)">▼</span>`
        : `<span class="row-arrow disabled">▼</span>`;
    const controlBar = `<div class="row-controls">${{showLess}}${{showMore}}</div>`;

    container.innerHTML = html + controlBar;
    loadedPortfolios.add(idx);
}}

// Show less - ALWAYS collapse the portfolio (hide all building rows)
function showLessBuildings(card) {{
    card.classList.remove('expanded');
    expandedPortfolioLogo = null;
    if (document.getElementById('map-panel').classList.contains('open')) {{
        updateMapData();
        updateMapTitle();
    }}
}}

// =============================================================================
// INITIALIZATION - NOTHING auto-loads, user action triggers everything
// =============================================================================

// Preload a portfolio's images
const preloadedIdx = new Set();
function preloadPortfolio(idx) {{
    if (preloadedIdx.has(idx)) return;
    preloadedIdx.add(idx);
    const buildings = PORTFOLIO_BUILDINGS[idx];
    if (!buildings) return;
    const bucket = CONFIG.awsBucket;
    buildings.forEach(b => {{
        if (b.image) {{
            const img = new Image();
            img.src = bucket + '/thumbnails/' + b.image;
        }}
    }});
}}

// =============================================================================
// INFINITE SCROLL - Load more portfolio cards as user scrolls
// =============================================================================

let loadedCardCount = 100;  // First 100 loaded in HTML
const CARDS_PER_BATCH = 50;
let isLoadingMore = false;

function renderPortfolioCard(p) {{
    const bucket = CONFIG.awsBucket;
    const logoClass = p.is_white_logo ? 'org-logo dark-bg' : 'org-logo';
    const logoUrl = p.aws_logo_url || (p.logo_file ? `${{bucket}}/logos/${{p.logo_file}}` : '');
    const logoHtml = logoUrl
        ? `<img src="${{logoUrl}}" alt="" class="${{logoClass}}" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><div class="org-logo-placeholder" style="display:none">${{p.org_name[0].toUpperCase()}}</div>`
        : `<div class="org-logo-placeholder">${{p.org_name[0].toUpperCase()}}</div>`;

    return `<div class="portfolio-card" data-idx="${{p.idx}}" data-org="${{p.org_name}}" data-buildings="${{p.building_count}}" data-sqft="${{p.total_sqft || 0}}" data-eui="${{p.median_eui}}" data-valuation="${{p.total_valuation}}" data-carbon="${{p.total_carbon}}" data-opex="${{p.total_opex}}">
        <div class="portfolio-header" onclick="togglePortfolio(this)">
            <div class="org-logo-stack">
                <span class="org-name-small" title="${{p.display_name || p.org_name}}">${{p.display_name || p.org_name}}</span>
                ${{logoHtml}}
            </div>
            <span class="stat-cell building-count">${{p.building_count}}</span>
            <span class="stat-cell classification-cell">${{(p.classification || '-').replace(/\\//g, '<br>').replace(/ /g, '<br>')}}</span>
            <span class="stat-cell sqft-value">${{formatSqftJS(p.total_sqft)}}</span>
            <span class="stat-cell eui-value">${{formatEuiRating(p.median_eui, p.median_eui_benchmark)}}</span>
            <span class="stat-cell valuation-value">${{formatMoney(p.total_valuation)}}</span>
            <span class="stat-cell carbon-value">${{formatCarbon(p.total_carbon)}}</span>
            <span class="stat-cell opex-value">${{formatMoney(p.total_opex)}}</span>
        </div>
        <div class="portfolio-buildings">
            <div class="building-rows-container"></div>
        </div>
    </div>`;
}}

function loadMorePortfolios() {{
    if (isLoadingMore || loadedCardCount >= PORTFOLIO_CARDS.length) return;
    isLoadingMore = true;

    const list = document.getElementById('portfolios-list');
    const endIdx = Math.min(loadedCardCount + CARDS_PER_BATCH, PORTFOLIO_CARDS.length);

    // Get existing card indices to avoid duplicates
    const existingIndices = new Set();
    list.querySelectorAll('.portfolio-card').forEach(c => existingIndices.add(parseInt(c.dataset.idx)));

    for (let i = loadedCardCount; i < endIdx; i++) {{
        if (!existingIndices.has(i)) {{
            const card = PORTFOLIO_CARDS[i];
            list.insertAdjacentHTML('beforeend', renderPortfolioCard(card));
        }}
    }}

    // Add hover listeners to new cards
    list.querySelectorAll('.portfolio-card').forEach(card => {{
        if (!card.dataset.hoverBound) {{
            card.dataset.hoverBound = 'true';
            card.addEventListener('mouseenter', function() {{
                const idx = parseInt(this.dataset.idx);
                if (!isNaN(idx)) preloadPortfolio(idx);
            }});
        }}
    }});

    loadedCardCount = endIdx;
    isLoadingMore = false;
    applyFilters();
}}

document.addEventListener('DOMContentLoaded', function() {{
    initTabs();
    selectVertical('all');
    selectVertical('all');

    // Preload logos for first 1000 portfolios for instant display
    PORTFOLIO_CARDS.slice(0, 1000).forEach(p => {{
        const logoUrl = p.aws_logo_url || (p.logo_file ? CONFIG.awsBucket + '/logos/' + p.logo_file : '');
        if (logoUrl) {{
            const img = new Image();
            img.src = logoUrl;
        }}
    }});

    // Pre-load building rows AND images for first 5 portfolios
    const first5Cards = Array.from(document.querySelectorAll('.portfolio-card')).slice(0, 5);
    first5Cards.forEach(card => {{
        const idx = parseInt(card.dataset.idx);
        if (!isNaN(idx)) {{
            // Load the building rows into DOM
            loadPortfolioRows(card);
            // Preload all images for this portfolio
            const buildings = PORTFOLIO_BUILDINGS[idx];
            if (buildings) {{
                const bucket = CONFIG.awsBucket;
                buildings.forEach(b => {{
                    if (b.image) {{
                        const img = new Image();
                        img.src = bucket + '/thumbnails/' + b.image;
                    }}
                }});
            }}
        }}
    }});

    // On HOVER: preload that portfolio's images (before user clicks)
    document.querySelectorAll('.portfolio-card').forEach(card => {{
        card.addEventListener('mouseenter', function() {{
            const idx = parseInt(this.dataset.idx);
            if (!isNaN(idx)) preloadPortfolio(idx);
        }});
    }});

    // Infinite scroll - load more as user scrolls
    const trigger = document.getElementById('load-more-trigger');
    if (trigger) {{
        const observer = new IntersectionObserver((entries) => {{
            if (entries[0].isIntersecting) loadMorePortfolios();
        }}, {{ rootMargin: '500px' }});
        observer.observe(trigger);
    }}
}});
</script>'''


# =============================================================================
# TEST
# =============================================================================

if __name__ == '__main__':
    # Quick test with mock data
    from src.data.loader import load_all_data

    config = {
        'aws_bucket': 'https://nationwide-odcv-images.s3.us-east-2.amazonaws.com',
        'mapbox_token': 'pk.eyJ1IjoiZm1pbGxlcnJ6ZXJvIiwiYSI6ImNtY2NnZGl6dTAxMzkya29qeHl6c2tibDgifQ.8h1GAYRfrv-fldoXorqFlw',
        'google_api_key': 'AIzaSyDvGee7gI4jQO3OjGXhtkMmWRP865F2kAU',
        'firebase_config': {
            'apiKey': 'AIzaSyDJlvljO528jQV30jUofDYLqWo9zSY46JY',
            'authDomain': 'nyc-odcv-prospector.firebaseapp.com',
            'projectId': 'nyc-odcv-prospector',
            'storageBucket': 'nyc-odcv-prospector.appspot.com',
            'messagingSenderId': '847399012345',
            'appId': '1:847399012345:web:abcd1234'
        }
    }

    data = load_all_data()
    generator = NationwideHTMLGenerator(config, data)
    html, data_files = generator.generate()

    # Save the HTML file
    base_dir = os.path.dirname(__file__)
    output_path = os.path.join(base_dir, 'nationwide_index.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    # Save data files
    data_dir = os.path.join(base_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)
    for filename, content in data_files.items():
        filepath = os.path.join(data_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Saved {filename}: {os.path.getsize(filepath) / 1024:.1f} KB")

    print(f"Generated {len(html):,} characters of HTML")
    print(f"Saved to: {output_path}")
    print(f"File size: {os.path.getsize(output_path) / 1024:.1f} KB")
    print(f"Portfolios: {len(data['portfolios'])}")
    print(f"Buildings: {len(data['all_buildings'])}")
