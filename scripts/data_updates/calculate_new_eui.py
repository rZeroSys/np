#!/usr/bin/env python3
"""
Calculate post-ODCV EUI and save to minimal lookup CSV.
Output: id_building, energy_site_eui_post_odcv
"""

import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import PORTFOLIO_DATA_PATH, EUI_POST_ODCV_PATH

INPUT = str(PORTFOLIO_DATA_PATH)
OUTPUT = str(EUI_POST_ODCV_PATH)

df = pd.read_csv(INPUT, low_memory=False)

def calc_new_eui(row):
    try:
        total_energy = float(row['energy_total_kbtu']) if pd.notna(row['energy_total_kbtu']) else 0
        hvac_energy = float(row['hvac_energy_total_kbtu']) if pd.notna(row['hvac_energy_total_kbtu']) else 0
        odcv_pct = float(row['odcv_hvac_savings_pct']) if pd.notna(row['odcv_hvac_savings_pct']) else 0
        sqft = float(row['bldg_sqft']) if pd.notna(row['bldg_sqft']) else 0

        if sqft <= 0 or total_energy <= 0:
            return None

        hvac_reduction = hvac_energy * odcv_pct
        new_total = total_energy - hvac_reduction
        return round(new_total / sqft, 1)
    except:
        return None

df['energy_site_eui_post_odcv'] = df.apply(calc_new_eui, axis=1)

# Save minimal CSV - just ID and new EUI
out = df[['id_building', 'energy_site_eui_post_odcv']].copy()
out.to_csv(OUTPUT, index=False)
print(f"Saved {len(out)} rows to {OUTPUT}")
