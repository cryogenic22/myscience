# Market Zero Quality Scorecard

*Generated: 2026-03-22 02:57 UTC*

## Overall Score: 79.6%

Target: ≥75%

## Completeness by Entity Type

| Entity Type | Total | Overall | Key Missing Fields |
|---|---|---|---|
| drug | 1672 | 54% | brand_name, mechanism_id, approval_date |
| company | 1422 | 32% | ticker, country, region |
| trial | 5197 | 84% | label |
| therapeutic_area | 18 | 100% | none |
| mechanism | 25 | 100% | none |
| article | 1757 | 90% | mesh_terms |

### Field-Level Completeness

**drug** (1672 records)

- `approval_date`: ░░░░░░░░░░░░░░░░░░░░ 4%
- `brand_name`: ░░░░░░░░░░░░░░░░░░░░ 5%
- `mechanism_id`: ███████░░░░░░░░░░░░░ 37%
- `therapeutic_area_id`: ████████████████░░░░ 82%
- `company_id`: ███████████████████░ 98%
- `generic_name`: ████████████████████ 100%

**company** (1422 records)

- `ticker`: ░░░░░░░░░░░░░░░░░░░░ 2%
- `country`: ░░░░░░░░░░░░░░░░░░░░ 2%
- `region`: ░░░░░░░░░░░░░░░░░░░░ 2%
- `market_cap_tier`: ███████████░░░░░░░░░ 56%
- `name`: ████████████████████ 100%

**trial** (5197 records)

- `label`: ░░░░░░░░░░░░░░░░░░░░ 0%
- `phase`: █████████████████░░░ 89%
- `official_title`: ███████████████████░ 99%
- `start_date`: ███████████████████░ 100%
- `sponsor_name`: ████████████████████ 100%
- `status`: ████████████████████ 100%
- `conditions`: ████████████████████ 100%

**therapeutic_area** (18 records)

- `name`: ████████████████████ 100%
- `mesh_id`: ████████████████████ 100%
- `scope_note`: ████████████████████ 100%

**mechanism** (25 records)

- `name`: ████████████████████ 100%
- `mesh_id`: ████████████████████ 100%

**article** (1757 records)

- `mesh_terms`: █████████░░░░░░░░░░░ 48%
- `title`: ████████████████████ 100%
- `pmid`: ████████████████████ 100%
- `journal`: ████████████████████ 100%
- `publication_date`: ████████████████████ 100%

## Cross-Link Density

| Entity Type | Total | Linked | Density | Avg Links |
|---|---|---|---|---|
| drug | 1672 | 1672 | 100% | 87.0 |
| company | 1422 | 1327 | 93% | 5.6 |
| trial | 5197 | 5192 | 100% | 88.0 |
| therapeutic_area | 18 | 15 | 83% | 431.0 |
| mechanism | 25 | 12 | 48% | 51.7 |
| article | 1757 | 0 | 0% | 0.0 |

## Therapeutic Area Coverage

| Therapeutic Area | Linked Entities |
|---|---|
| ✓ Diabetes Mellitus, Type 2 | 2123 |
| ✓ Diabetes Mellitus | 1048 |
| ✓ Hypertension | 932 |
| ✓ Heart Failure | 796 |
| ✓ Coronary Artery Disease | 263 |
| ✓ Obesity | 249 |
| ✓ Diabetes Mellitus, Type 1 | 200 |
| ✓ Renal Insufficiency, Chronic | 164 |
| ✓ Cardiovascular Diseases | 150 |
| ✓ Heart Failure, Systolic | 105 |
| ✓ Atrial Fibrillation | 103 |
| ✓ Heart Failure, Diastolic | 91 |
| ✓ Cardiomyopathies | 81 |
| ✓ Metabolic Syndrome | 80 |
| ✓ Diabetic Nephropathies | 80 |
| ✗ Glucose Metabolism Disorders | 0 |
| ✗ Heart Diseases | 0 |
| ✗ Hyperglycemia | 0 |

## Source Diversity

**drug**: backfill(1060), clinical_trials_gov(546), fda_orange_book(66)
**company**: clinical_trials_gov(1216), fda_orange_book(109), fda_shortages(82), backfill_linkage(10), sec_edgar(5)
**trial**: clinical_trials_gov(5197)
**therapeutic_area**: mesh_ontology(18)
**mechanism**: mesh_ontology(25)
**article**: pubmed(1757)

## Data Freshness

| Entity Type | Latest Update | Days Stale |
|---|---|---|
| drug | 2026-02-21 | 29 |
| company | 2026-02-21 | 29 |
| trial | 2026-02-19 | 31 |
| therapeutic_area | 2026-02-21 | 29 |
| mechanism | 2026-02-21 | 29 |
| article | 2026-02-19 | 30 |

## Quality Rule Scores

| Entity Type | Assessed | Avg Score | Passed | Failed |
|---|---|---|---|---|
| company | 5 | 98% | 13 | 0 |
| drug | 1126 | 64% | 2616 | 3212 |
| event | 533 | 100% | 1599 | 0 |
| literature | 40 | 91% | 76 | 4 |
| trial | 5094 | 98% | 24840 | 630 |
