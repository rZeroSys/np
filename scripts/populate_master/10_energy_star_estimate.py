#!/usr/bin/env python3
"""
Estimated Energy Star Score After ODCV
=======================================
Calculates estimated new Energy Star score for buildings after applying ODCV
HVAC savings, based on EPA's efficiency ratio methodology.

Adds column: energy_star_score_post_odcv

Based on EPA Portfolio Manager methodology:
- Efficiency Ratio = Actual Source EUI / Predicted Source EUI
- Score maps to percentile via gamma distribution
- Reducing EUI improves efficiency ratio, thus improving score

Usage: python3 08_energy_star_estimate.py
"""

import pandas as pd
import numpy as np
from datetime import datetime
from scipy import stats

# =============================================================================
# CONFIGURATION
# =============================================================================

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.config import PORTFOLIO_DATA_PATH

INPUT_FILE = str(PORTFOLIO_DATA_PATH)

# Gamma distribution parameters by building type (from EPA technical references)
# Format: {'building_type': (shape, scale)}
# These approximate the efficiency ratio distributions from CBECS data
GAMMA_PARAMS = {
    'Office':               (2.0, 0.42),
    'Medical Office':       (2.1, 0.40),
    'Bank Branch':          (2.0, 0.42),
    'Courthouse':           (2.0, 0.45),
    'Hotel':                (1.8, 0.48),
    'K-12 School':          (2.2, 0.38),
    'Higher Ed':            (2.0, 0.45),
    'Retail Store':         (1.9, 0.45),
    'Supermarket/Grocery':  (1.8, 0.50),
    'Inpatient Hospital':   (2.3, 0.38),
    'Outpatient Clinic':    (2.1, 0.40),
    'Data Center':          (1.5, 0.55),
    'Warehouse':            (1.7, 0.52),
    'DEFAULT':              (2.0, 0.43),
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def safe_float(val, default=None):
    """Convert value to float, return default if empty or invalid."""
    if val is None or val == '' or (isinstance(val, float) and np.isnan(val)):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def get_gamma_params(building_type):
    """Get gamma distribution parameters for a building type."""
    return GAMMA_PARAMS.get(building_type, GAMMA_PARAMS['DEFAULT'])


def score_to_efficiency_ratio(score, shape, scale):
    """
    Convert Energy Star score to efficiency ratio using inverse gamma CDF.

    Score of 75 means building is better than 75% of peers.
    This corresponds to the 25th percentile of efficiency ratios
    (lower ratio = more efficient).
    """
    if score is None or score <= 0 or score >= 100:
        return None

    # Score X means better than X% of peers
    # So we want the (100-X)th percentile of the efficiency ratio distribution
    percentile = (100 - score) / 100.0

    # Use inverse gamma CDF (ppf = percent point function)
    ratio = stats.gamma.ppf(percentile, a=shape, scale=scale)
    return ratio


def efficiency_ratio_to_score(ratio, shape, scale):
    """
    Convert efficiency ratio to Energy Star score using gamma CDF.

    Lower ratio = better efficiency = higher score.
    """
    if ratio is None or ratio <= 0:
        return None

    # Get cumulative probability (what % of buildings have this ratio or lower)
    cdf = stats.gamma.cdf(ratio, a=shape, scale=scale)

    # Score = percentage of buildings we're better than
    # If 25% have lower ratio, we're better than 75%
    score = (1 - cdf) * 100

    # Clamp to valid range
    return max(1, min(99, round(score)))


def calculate_weighted_hvac_pct(row):
    """
    Calculate the weighted average HVAC percentage across all fuel types.
    Weighted by actual energy consumption of each fuel type.
    """
    elec = safe_float(row.get('energy_elec_kbtu'), 0)
    gas = safe_float(row.get('energy_gas_kbtu'), 0)
    steam = safe_float(row.get('energy_steam_kbtu'), 0)
    fuel_oil = safe_float(row.get('energy_fuel_oil_kbtu'), 0)

    hvac_elec = safe_float(row.get('hvac_pct_elec'), 0)
    hvac_gas = safe_float(row.get('hvac_pct_gas'), 0)
    hvac_steam = safe_float(row.get('hvac_pct_steam'), 0)
    hvac_fuel_oil = safe_float(row.get('hvac_pct_fuel_oil'), 0)

    total_energy = elec + gas + steam + fuel_oil
    if total_energy <= 0:
        return None

    # Weight HVAC percentages by energy consumption
    weighted_hvac = (
        (hvac_elec * elec) +
        (hvac_gas * gas) +
        (hvac_steam * steam) +
        (hvac_fuel_oil * fuel_oil)
    ) / total_energy

    return weighted_hvac


def estimate_post_odcv_score(row):
    """
    Estimate new Energy Star score after applying ODCV savings.

    Method:
    1. Get current score and EUI
    2. Calculate energy reduction from ODCV (affects HVAC portion)
    3. Calculate new EUI
    4. Convert current score to efficiency ratio
    5. Adjust ratio based on EUI change
    6. Convert new ratio back to score
    """
    current_score = safe_float(row.get('energy_star_score'))
    current_eui = safe_float(row.get('energy_site_eui'))
    odcv_savings_pct = safe_float(row.get('odcv_hvac_savings_pct'))
    bldg_type = row.get('bldg_type', '')

    # Need all three values to estimate
    if current_score is None or current_eui is None or current_eui <= 0:
        return None

    if odcv_savings_pct is None or odcv_savings_pct <= 0:
        return current_score  # No savings, score unchanged

    # Get weighted HVAC percentage
    hvac_pct = calculate_weighted_hvac_pct(row)
    if hvac_pct is None or hvac_pct <= 0:
        # Fallback: assume 45% HVAC (typical for commercial buildings)
        hvac_pct = 0.45

    # Calculate energy reduction
    # ODCV saves X% of HVAC energy, which is Y% of total energy
    total_energy_reduction = odcv_savings_pct * hvac_pct

    # Calculate new EUI
    new_eui = current_eui * (1 - total_energy_reduction)

    # Get gamma parameters for this building type
    shape, scale = get_gamma_params(bldg_type)

    # Convert current score to efficiency ratio
    current_ratio = score_to_efficiency_ratio(current_score, shape, scale)
    if current_ratio is None:
        return None

    # New ratio = current ratio * (new EUI / current EUI)
    # Lower EUI means lower ratio (more efficient)
    eui_factor = new_eui / current_eui
    new_ratio = current_ratio * eui_factor

    # Convert new ratio to score
    new_score = efficiency_ratio_to_score(new_ratio, shape, scale)

    return new_score


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("Estimated Energy Star Score After ODCV")
    print("=" * 60)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Load data
    print(f"\nLoading: {INPUT_FILE}")
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    print(f"Loaded {len(df):,} buildings")

    # Count buildings with Energy Star scores
    has_score = df['energy_star_score'].notna().sum()
    print(f"Buildings with Energy Star score: {has_score:,}")

    # Calculate estimated post-ODCV scores
    print("\nCalculating estimated post-ODCV Energy Star scores...")
    df['energy_star_score_post_odcv'] = df.apply(estimate_post_odcv_score, axis=1)

    # Summary statistics
    print("\n" + "-" * 60)
    print("RESULTS SUMMARY")
    print("-" * 60)

    valid_current = df['energy_star_score'].dropna()
    valid_post = df['energy_star_score_post_odcv'].dropna()

    print(f"\nCurrent Energy Star Scores:")
    print(f"  Count:  {len(valid_current):,}")
    print(f"  Mean:   {valid_current.mean():.1f}")
    print(f"  Median: {valid_current.median():.1f}")
    print(f"  Min:    {valid_current.min():.0f}")
    print(f"  Max:    {valid_current.max():.0f}")

    print(f"\nEstimated Post-ODCV Scores:")
    print(f"  Count:  {len(valid_post):,}")
    print(f"  Mean:   {valid_post.mean():.1f}")
    print(f"  Median: {valid_post.median():.1f}")
    print(f"  Min:    {valid_post.min():.0f}")
    print(f"  Max:    {valid_post.max():.0f}")

    # Calculate improvement
    both = df[df['energy_star_score'].notna() & df['energy_star_score_post_odcv'].notna()]
    if len(both) > 0:
        improvement = both['energy_star_score_post_odcv'] - both['energy_star_score']
        print(f"\nScore Improvement:")
        print(f"  Mean improvement:   +{improvement.mean():.1f} points")
        print(f"  Median improvement: +{improvement.median():.1f} points")
        print(f"  Max improvement:    +{improvement.max():.0f} points")

        # Count buildings reaching 75+ threshold
        current_75 = (both['energy_star_score'] >= 75).sum()
        post_75 = (both['energy_star_score_post_odcv'] >= 75).sum()
        print(f"\nBuildings at 75+ (ENERGY STAR certified threshold):")
        print(f"  Current:   {current_75:,} ({100*current_75/len(both):.1f}%)")
        print(f"  Post-ODCV: {post_75:,} ({100*post_75/len(both):.1f}%)")
        print(f"  New qualifiers: +{post_75 - current_75:,}")

    # Save
    print(f"\nSaving to: {INPUT_FILE}")
    df.to_csv(INPUT_FILE, index=False)
    print(f"Saved {len(df):,} buildings")

    print("\n" + "=" * 60)
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)


if __name__ == '__main__':
    main()
