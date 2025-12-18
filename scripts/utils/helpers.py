"""
Helper functions for Nationwide ODCV Prospector Homepage
"""
import re
import math
from html import escape

def attr_escape(text):
    """Escape text for HTML attributes."""
    if text is None or (hasattr(text, '__float__') and math.isnan(float(text))):
        return ""
    return escape(str(text)).replace('"', '&quot;').replace("'", '&#39;')

def js_escape(text):
    """Escape text for JavaScript strings."""
    if text is None or (hasattr(text, '__float__') and math.isnan(float(text))):
        return ""
    return (str(text)
            .replace('\\', '\\\\')
            .replace("'", "\\'")
            .replace('"', '\\"')
            .replace('\n', '\\n')
            .replace('\r', '\\r')
            .replace('\t', '\\t'))

def safe_float(val, default=0.0):
    """Convert value to float, returning default if invalid."""
    if val is None:
        return default
    if isinstance(val, str) and val.strip() in ('', 'NA', 'N/A', 'nan', 'NaN'):
        return default
    try:
        f = float(val)
        if math.isnan(f):
            return default
        return f
    except (ValueError, TypeError):
        return default

def safe_int(val, default=0):
    """Convert value to int, returning default if invalid."""
    return int(safe_float(val, default))

def safe_str(val, default=''):
    """Convert value to string, returning default if NaN/None/empty."""
    import pandas as pd
    if val is None:
        return default
    if isinstance(val, float) and math.isnan(val):
        return default
    try:
        if pd.isna(val):
            return default
    except (ValueError, TypeError):
        pass
    s = str(val).strip()
    if s.lower() in ('nan', 'none', 'null', ''):
        return default
    return s

def normalize_building_type(val):
    """Normalize building type names."""
    if val == 'Event Space':
        return 'Venue'
    return val

def format_currency(amount, decimals=0):
    """Format number as currency string."""
    if amount is None or (isinstance(amount, float) and math.isnan(amount)):
        return '$0'
    if decimals == 0:
        return f'${int(amount):,}'
    return f'${amount:,.{decimals}f}'

def format_number(num, decimals=0):
    """Format number with commas."""
    if num is None or (isinstance(num, float) and math.isnan(num)):
        return '0'
    if decimals == 0:
        return f'{int(num):,}'
    return f'{num:,.{decimals}f}'

def format_sqft(sqft):
    """Format square footage with K/M suffix."""
    sqft = safe_float(sqft)
    if sqft >= 1_000_000:
        return f'{sqft/1_000_000:.1f}M'
    elif sqft >= 10_000:
        return f'{sqft/1_000:.0f}K'
    else:
        return f'{int(sqft):,}'

def format_carbon(tco2e):
    """Format carbon emissions with K/M suffix."""
    tco2e = safe_float(tco2e)
    if tco2e >= 1_000_000:
        return f'{tco2e/1_000_000:.2f}M'
    elif tco2e >= 1_000:
        return f'{tco2e/1_000:.1f}K'
    else:
        return f'{tco2e:.0f}'

def slugify(text):
    """Convert text to URL-safe slug."""
    if not text:
        return ''
    text = str(text).lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')

def vertical_color(vertical):
    """Get color for vertical type."""
    colors = {
        'Commercial': '#1a3870',
        'Education': '#0088ff',
        'Healthcare': '#7ec8ff',
    }
    return colors.get(vertical, '#6b7280')

def building_type_icon(building_type):
    """Get icon/emoji for building type."""
    return '🏢'
