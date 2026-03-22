# Market Zero Quality Scorecard

*Generated: 2026-03-22 06:43 UTC*

## Overall Score: 79.7%

Target: ≥75%

## Completeness by Entity Type

| Entity Type | Total | Overall | Key Missing Fields |
|---|---|---|---|
| drug | 1758 | 54% | brand_name, mechanism_id, approval_date |
| company | 1517 | 33% | ticker, country, region |
| trial | 5642 | 84% | label |
| therapeutic_area | 18 | 100% | none |
| mechanism | 25 | 100% | none |
| article | 2709 | 89% | mesh_terms |

### Field-Level Completeness

**drug** (1758 records)

- `approval_date`: ░░░░░░░░░░░░░░░░░░░░ 4%
- `brand_name`: █░░░░░░░░░░░░░░░░░░░ 5%
- `mechanism_id`: ███████░░░░░░░░░░░░░ 35%
- `therapeutic_area_id`: ███████████████░░░░░ 78%
- `company_id`: ███████████████████░ 99%
- `generic_name`: ████████████████████ 100%

**company** (1517 records)

- `ticker`: ░░░░░░░░░░░░░░░░░░░░ 2%
- `country`: ░░░░░░░░░░░░░░░░░░░░ 2%
- `region`: ░░░░░░░░░░░░░░░░░░░░ 2%
- `market_cap_tier`: ███████████░░░░░░░░░ 56%
- `name`: ████████████████████ 100%

**trial** (5642 records)

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

**article** (2709 records)

- `mesh_terms`: █████████░░░░░░░░░░░ 46%
- `title`: ████████████████████ 100%
- `pmid`: ████████████████████ 100%
- `journal`: ████████████████████ 100%
- `publication_date`: ████████████████████ 100%

## Cross-Link Density

| Entity Type | Total | Linked | Density | Avg Links |
|---|---|---|---|---|
| drug | 1758 | 1755 | 100% | 134.6 |
| company | 1517 | 1425 | 94% | 5.7 |
| trial | 5642 | 5641 | 100% | 144.7 |
| therapeutic_area | 18 | 15 | 83% | 452.1 |
| mechanism | 25 | 12 | 48% | 51.7 |
| article | 2709 | 0 | 0% | 0.0 |

## Therapeutic Area Coverage

| Therapeutic Area | Linked Entities |
|---|---|
| ✓ Diabetes Mellitus, Type 2 | 2211 |
| ✓ Diabetes Mellitus | 1048 |
| ✓ Hypertension | 949 |
| ✓ Heart Failure | 810 |
| ✓ Renal Insufficiency, Chronic | 288 |
| ✓ Coronary Artery Disease | 268 |
| ✓ Obesity | 249 |
| ✓ Diabetes Mellitus, Type 1 | 208 |
| ✓ Cardiovascular Diseases | 150 |
| ✓ Heart Failure, Systolic | 114 |
| ✓ Diabetic Nephropathies | 113 |
| ✓ Atrial Fibrillation | 111 |
| ✓ Heart Failure, Diastolic | 96 |
| ✓ Cardiomyopathies | 84 |
| ✓ Metabolic Syndrome | 82 |
| ✗ Hyperglycemia | 0 |
| ✗ Heart Diseases | 0 |
| ✗ Glucose Metabolism Disorders | 0 |

## Source Diversity

**drug**: backfill(1060), clinical_trials_gov(628), fda_orange_book(70)
**company**: clinical_trials_gov(1299), fda_orange_book(111), fda_shortages(85), sec_edgar(12), backfill_linkage(10)
**trial**: clinical_trials_gov(5642)
**therapeutic_area**: mesh_ontology(18)
**mechanism**: mesh_ontology(25)
**article**: pubmed(2709)

## Data Freshness

| Entity Type | Latest Update | Days Stale |
|---|---|---|
| drug | 2026-03-22 | 0 |
| company | 2026-03-22 | 0 |
| trial | 2026-03-22 | 0 |
| therapeutic_area | 2026-03-22 | 0 |
| mechanism | 2026-03-22 | 0 |
| article | 2026-03-22 | 0 |

## Quality Rule Scores

| Entity Type | Assessed | Avg Score | Passed | Failed |
|---|---|---|---|---|
| company | 12 | 99% | 60 | 0 |
| drug | 1130 | 64% | 2646 | 3214 |
| event | 1621 | 100% | 4863 | 0 |
| literature | 40 | 91% | 76 | 4 |
| trial | 5575 | 98% | 28435 | 656 |
