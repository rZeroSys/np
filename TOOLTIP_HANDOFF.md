# TOOLTIP IMPROVEMENT HANDOFF

## WHAT WAS DONE
1. **BPS_TOOLTIP_INFO** (lines 107-199) - DONE ✅
   - Added year references, effective dates, source URLs for all 7 cities

2. **EUI tooltip** (get_site_eui_tooltip, ~line 1195) - DONE ✅
   - Was garbage talking about HVAC gas percentages
   - Fixed to: "Energy Use Intensity measures total annual energy per square foot. Formula: EUI = Annual Energy (kBtu) ÷ Building Area (sq ft). Lower values mean better efficiency. {bldg_type} median: ~{benchmark} kBtu/sq ft/year. (Source: CBECS 2018)"

3. **Load factor tooltip** (get_load_factor_tooltip, ~line 1217) - DONE ✅
   - Was ugly ASCII art with "=====" headers
   - Fixed to readable prose with source link

## WHAT NEEDS TO BE DONE

### 1. get_odcv_savings_tooltip (~line 941-1063) - IN PROGRESS
**Problem:** Fragmented lines like:
```
lines.append(f"Hotels save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC.")
lines.append("Room-level controls adjust to actual guests -")
lines.append("typically 65-75% occupancy. Note: only 20%")
```

**Fix to READABLE PROSE like:**
```python
return f"Hotels save {floor_pct:.0f}-{ceiling_pct:.0f}% on HVAC. Room occupancy typically runs 63-75%, and guests are only in their rooms about 45% of the day—the rest they're out at meetings, sightseeing, or dining. That means most ventilation is conditioning empty rooms. Note: only 20% of gas goes to HVAC; the rest is hot water (42%) and kitchens (33%). (Source: <a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>, <a href='https://str.com/' target='_blank'>STR</a>)"
```

**CRITICAL: ALWAYS ADD SOURCE LINKS** like:
- CBECS: `<a href='https://www.eia.gov/consumption/commercial/' target='_blank'>CBECS 2018</a>`
- CBRE: `<a href='https://www.cbre.com/insights' target='_blank'>CBRE</a>`
- Kastle: `<a href='https://www.kastle.com/safety-wellness/getting-america-back-to-work/' target='_blank'>Kastle Systems</a>`
- STR: `<a href='https://str.com/' target='_blank'>STR</a>`
- NCES: `<a href='https://nces.ed.gov/' target='_blank'>NCES</a>`
- NIC: `<a href='https://www.nic.org/' target='_blank'>NIC MAP Vision</a>`
- Placer.ai: `<a href='https://www.placer.ai/' target='_blank'>Placer.ai</a>`
- ASHRAE: `<a href='https://www.ashrae.org/' target='_blank'>ASHRAE 170</a>`

### 2. Other tooltips to check/improve:
- NEW_COLUMN_SOURCES (~line 631) - add hyperlinks
- get_fine_avoidance_tooltip (~line 1330) - has good sources already
- get_utility_cost_savings_tooltip (~line 1375) - needs market data

## KEY PRINCIPLES - DO NOT VIOLATE

1. **DO NOT GUT** - Keep the story/content, just make it readable prose
2. **ALWAYS SOURCE** - Every tooltip needs (Source: LINK) at the end
3. **READABLE PROSE** - Not telegraph style like "63% × 45% = 72%"
4. **NYC building.py STYLE** - Conversational, like:
   - "Building's 2030 emissions if nothing changes. Lower than 2024 because the law assumes electricity becomes cleaner as renewables increase."

## REFERENCE FILES
- Good tooltip examples: `/Users/forrestmiller/Desktop/New/Scripts/building.py` (lines 1300-1340, 2850-2860)
- Methodology docs with source data: `/Users/forrestmiller/Desktop/nationwide-prospector/docs/methodology/`
- File to edit: `/Users/forrestmiller/Desktop/nationwide-prospector/src/generators/building_report.py`

## SOURCE DATA FROM METHODOLOGY DOCS
- Office vacancy: SF 29%, Seattle 27%, Chicago 22%, NYC 13% (CBRE)
- Office utilization: SF 45%, NYC 55%, national 48% (Kastle)
- Hotel occupancy: national 63%, NYC 87% (STR)
- School utilization: 22-28% of annual hours (NCES)
- Residential care occupancy: Boston 91%, Denver 86%, Atlanta 84% (NIC MAP Vision Q4 2024)
- HVAC percentages by building type: CBECS 2018
