# Portfolio Identification Methodology

## Definition

A **portfolio organization** is any entity that appears in **3 or more separate building rows** (not 3 mentions total).

**Rules:**
- We count ROWS, not occurrences
- If an org appears in multiple columns of the same row (e.g., as both `building_owner` AND `property_manager`), that still counts as **1 row**
- The org can appear in any combination of `building_owner`, `property_manager`, or `tenant` columns

**Example - NOT a portfolio org:**
| Row | building_owner | property_manager | tenant |
|-----|----------------|------------------|--------|
| 1   | Acme Corp      | Acme Corp        | -      |
| 2   | -              | Acme Corp        | -      |

Acme Corp appears 3 times but only in **2 rows** = NOT a portfolio org

**Example - IS a portfolio org:**
| Row | building_owner | property_manager | tenant |
|-----|----------------|------------------|--------|
| 1   | Acme Corp      | -                | -      |
| 2   | -              | Acme Corp        | -      |
| 3   | -              | -                | Acme Corp |

Acme Corp appears in **3 rows** = IS a portfolio org

## Dataset
- **File:** `merged_property_matches_updated.csv`
- **Total rows:** 26,648
- **Columns used:** `building_owner`, `property_manager`, `tenant`

## Results
- **In portfolio:** 14,839 buildings (55.7%)
- **Not in portfolio:** 11,809 buildings (44.3%)

## Consolidation Rounds

### Round 1: Suffix Normalization
Removed LLC, Inc, Corp, LP suffixes to find duplicate org names.
- 41 mappings, 85 replacements

### Round 2: Rare Words + Management Variations
Used rare word frequency analysis to find brand identifiers. Also normalized "Management" vs "Mgmt" variations.
- 34 mappings, 57 replacements, +22 buildings to portfolios

### Round 3: Signature Words
Frequency analysis of words appearing in only 2-10 org names (signature/brand words).
- 22 mappings, 234 replacements, +16 buildings to portfolios

### Round 4: Cross-Column Brand Matching
Cross-referenced owner/tenant/property_manager with property_name column to find brand matches.
- 11 mappings, 40 replacements, +4 buildings to portfolios

### Round 5: Final Cleanup
LP/LLC/Inc suffix variations, "The" prefix removal, location suffixes, typo fixes.
- 27 mappings, 44 replacements, +10 buildings to portfolios

## Total Impact
- **460 total replacements** across all rounds
- **+52 buildings** added to portfolios (from Round 2 baseline)

## False Positives Removed
The following were identified but NOT consolidated (different entities):
- **Archdiocese:** Each city (Boston, Chicago, NY, etc.) is a separate entity
- **Cornell:** Cornell University vs Weill Cornell Medicine vs Cornell Elementary - different
- **Embarcadero:** Capital Partners, Center, Realty Services, Business Park - different companies
- **MGR:** Different companies using same abbreviation
- **Newmark:** Newmark (company) vs Newmark Theater vs Newmarket Center - different
- **Northeastern:** Illinois University vs Northeastern University - different schools
- **Winter:** M A Winter Company LLC vs Winter Organization - different companies

## Key Consolidation Examples

| Canonical Name | Variants Consolidated |
|----------------|----------------------|
| General Services Administration (GSA) | General Services Administration, US General Services Administration |
| Stream Realty Partners | Stream Realty, Stream Realty Partners LP |
| Healthcare Realty | Healthcare Realty Trust Incorporated |
| JMDH Real Estate | Jmdh Real Estate Of, Jmdh Real Estate Offices LLC, Jmdh Real Estate Of Kansas City LLC, etc. |
| Handler Real Estate Services | Handler Real Estate |
| Utopia Property Management | Utopia Property Management \| Los Angeles Ca, Utopia Property Management \| Emeryville Ca |
| DWS Group | DWS RREEF |
| Karuna Properties | Karuna Properties East, Karuna Properties West |
