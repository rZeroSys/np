# CRITICAL - DO NOT CHANGE THESE VALUES

## Button/Layout Alignment - LOCKED IN

These values are carefully calibrated to align the UI elements. DO NOT MODIFY:

### 1. `.vertical-filter-inner` (line ~374)
```css
max-width: 1272px;
padding: 0;
```

### 2. Map button container (line ~2365)
```css
margin-right: 85px;
```

### 3. Filter drawer close button (line ~2341)
```html
<button class="filter-drawer-close" onclick="toggleFilterDrawer()">&times;</button>
```

## If alignment breaks
Restore from backup:
```bash
cp backup/html_generator_WORKING_20251208_161703.py src/generators/html_generator.py
```

## DO NOT
- Change max-width values without checking alignment
- Change margin-right on the Map button container
- Remove the filter drawer close button

---

## Useful Scripts

### Regenerate & Push to GitHub (One Command)
```bash
./scripts/regenerate_and_push.sh "Your commit message"
```
This script:
1. Regenerates homepage (index.html)
2. Regenerates all building reports (~23,881 files)
3. Commits and pushes to GitHub

### Manual Commands (if needed)
```bash
# Regenerate homepage only
python3 -m src.generators.html_generator

# Regenerate building reports only
python3 -m src.generators.building_report

# Regenerate portfolio reports only
python3 -m src.generators.portfolio_report
```
