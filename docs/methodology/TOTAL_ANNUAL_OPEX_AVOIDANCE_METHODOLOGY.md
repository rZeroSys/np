# Total Annual OpEx Avoidance Methodology

## What is Total Annual OpEx Avoidance?

**Total Annual OpEx Avoidance** = operating expenses avoided each year from ODCV implementation.

```
total_annual_opex_avoidance = odcv_dollar_savings + fine_avoidance_yr1
```

| Component | What it is |
|-----------|------------|
| `odcv_hvac_savings_annual_usd` | Utility bills not paid (lower energy use) |
| `bps_fine_avoided_yr1_usd` | BPS fines not paid (lower emissions) |

Both are operating expenses (OpEx) the building avoids paying.

---

## Why "OpEx Avoidance" and NOT "Total Benefit"?

The total benefit of ODCV includes:

| Benefit | Column | Included in `savings_opex_avoided_annual_usd`? |
|---------|--------|-------------------------------------------|
| Utility savings | `odcv_hvac_savings_annual_usd` | Yes |
| Fine avoidance | `bps_fine_avoided_yr1_usd` | Yes |
| Property value increase | `val_odcv_impact_usd` | **No** |

Calling it "total benefit" would be wrong because valuation increase is ALSO a benefit.

**"Total Annual OpEx Avoidance"** is accurate - it's specifically the operating expenses avoided, not all benefits.

---

## How It Flows to Valuation

```
total_annual_opex_avoidance     →     odcv_valuation_impact_usd
(annual cash savings)                  (property value increase)
        ↓                                        ↓
   $3.7B/year                    $3.7B / cap_rate = $442M
```

The OpEx avoidance improves NOI, which capitalizes into higher property value.

---

## Example

**Building: 500,000 sqft office in Washington, DC**

| Item | Amount |
|------|--------|
| Utility savings | $300,000/year |
| Fine avoidance | $800,000/year |
| **Total Annual OpEx Avoidance** | **$1,100,000/year** |
| Valuation Impact ($1.1M / 7% cap) | $15,714,286 |

---

## By BPS Law

| Category | Buildings | Avg Utility Savings | Avg Fine Avoidance | Avg OpEx Avoidance |
|----------|-----------|--------------------|--------------------|-------------------|
| NYC LL97 | 3,580 | $125,698 | $11,816 | $137,514 |
| DC BEPS | 1,093 | $138,671 | $441,067 | $579,738 |
| Energize Denver | 739 | $71,225 | $370,169 | $441,394 |
| Seattle BEPS | 731 | $64,278 | $33,463 | $97,741 |
| Boston BERDO | 521 | $200,428 | $12,541 | $212,969 |
| Cambridge BEUDO | 139 | $193,543 | $32,036 | $225,579 |
| St. Louis BEPS | 73 | $80,724 | $7,500 | $88,224 |
| No BPS Law | 19,772 | $102,580 | $0 | $102,580 |

---

## Formula Chain

```
1. odcv_dollar_savings = total_hvac_energy_cost × odcv_savings_pct

2. fine_avoidance_yr1 = (emissions over cap) × penalty rate

3. total_annual_opex_avoidance = odcv_dollar_savings + fine_avoidance_yr1

4. odcv_valuation_impact_usd = total_annual_opex_avoidance / cap_rate

5. post_odcv_valuation_usd = current_valuation_usd + odcv_valuation_impact_usd
```

---

## Data Summary

| Metric | Value |
|--------|-------|
| Total Buildings | 26,648 |
| Total Utility Savings | $2,866,388,079 |
| Total Fine Avoidance | $833,938,936 |
| **Total Annual OpEx Avoidance** | **$3,700,327,015** |
| **Valuation Impact** | **$442,245,942** |

---

## Key Points

1. **Both components are OpEx** - utility costs and fines are operating expenses
2. **Non-BPS buildings** - $0 fine avoidance, so OpEx avoidance = utility savings only
3. **Fine avoidance is Year 1** - BPS caps get stricter over time, so future years will differ
4. **Valuation is separate** - the property value increase is calculated FROM the OpEx avoidance

---

## Related Files

- `ODCV_Valuation_Impact_Methodology.md` - Full valuation methodology
- `NATIONAL_BPS_METHODOLOGY.md` - How fine avoidance is calculated per city

---

*Updated: December 1, 2025*
