#!/usr/bin/env python3
"""
Nationwide ODCV Prospector Homepage Generator
=============================================
Main script that generates the nationwide prospector homepage.

Usage:
    python -m src.generators.homepage

Output:
    output/html/index.html
"""

import sys
import os
from pathlib import Path
from datetime import datetime

from src.data.loader import load_all_data
from src.generators.html_generator import NationwideHTMLGenerator
from src.config import (
    INDEX_HTML_PATH, BUILDINGS_OUTPUT_DIR, AWS_BASE_URL
)

# =============================================================================
# CONFIGURATION
# =============================================================================

CONFIG = {
    # AWS S3 bucket for images
    'aws_bucket': AWS_BASE_URL,

    # Mapbox token (same as NYC tool)
    'mapbox_token': 'pk.eyJ1IjoiZm1pbGxlcnJ6ZXJvIiwiYSI6ImNtY2NnZGl6dTAxMzkya29qeHl6c2tibDgifQ.8h1GAYRfrv-fldoXorqFlw',

    # Google API key
    'google_api_key': 'REMOVED_GOOGLE_KEY',

    # Firebase configuration (same project as NYC tool)
    'firebase_config': {
        'apiKey': 'AIzaSyAsxPRzyj7z6Nk3QPhOBK5CfyblY2LqAjk',
        'authDomain': 'prospector-leaderl-board.firebaseapp.com',
        'projectId': 'prospector-leaderl-board',
        'storageBucket': 'prospector-leaderl-board.firebasestorage.app',
        'messagingSenderId': '70489892630',
        'appId': '1:70489892630:web:51052e8b0b5da2e6779237'
    },

    # Output paths
    'output_path': str(INDEX_HTML_PATH),
    'buildings_dir': str(BUILDINGS_OUTPUT_DIR) + '/',
}


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Generate the Nationwide ODCV Prospector homepage."""
    print("=" * 70)
    print("NATIONWIDE ODCV PROSPECTOR - HOMEPAGE GENERATOR")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Step 1: Load all data
    print("Step 1: Loading data...")
    data = load_all_data()
    print()

    # Step 2: Generate HTML
    print("Step 2: Generating HTML...")
    generator = NationwideHTMLGenerator(CONFIG, data)
    html, data_files = generator.generate()
    print(f"  Generated {len(html):,} characters")
    print()

    # Step 3: Write output files
    print("Step 3: Writing output files...")
    output_path = Path(CONFIG['output_path'])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write main HTML
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  Written to: {output_path}")

    # Write data files
    data_dir = output_path.parent / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in data_files.items():
        data_path = data_dir / filename
        with open(data_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  Written to: {data_path}")
    print()

    # Summary
    stats = data['stats']
    print("=" * 70)
    print("GENERATION COMPLETE")
    print("=" * 70)
    print()
    print("Summary:")
    print(f"  Total Buildings:      {stats['total_buildings']:,}")
    print(f"  Total Portfolios:     {len(data['portfolios']):,}")
    print(f"  Total OpEx Avoidance: ${stats['total_opex_avoidance']:,.0f}")
    print(f"  Carbon Reduction:     {stats['total_carbon_reduction']:,.0f} tCO2e")
    print()
    print("By Vertical:")
    for v, v_stats in stats['by_vertical'].items():
        print(f"  {v}: {v_stats['building_count']:,} buildings, ${v_stats['opex_avoidance']:,.0f} OpEx")
    print()
    print(f"Output: {output_path}")
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    main()
