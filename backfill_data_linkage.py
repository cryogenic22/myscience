"""
Backfill Tier-1 Data Linkage: OWNS, IN_THERAPEUTIC_AREA, TARGETS_MECHANISM.

Addresses backlog items B1-B4:
  B1: Company-Drug OWNS links
  B2: Drug therapeutic area classification
  B3: Drug mechanism of action classification
  B4: Company name normalisation for sponsors

Strategy:
  - No LLM / embedding calls required (deterministic text matching only)
  - Uses patent applicant_holder, trial sponsor_name, and known pharma name
    variants to link drugs -> companies
  - Uses trial conditions[] text to classify drugs into therapeutic areas
  - Uses known drug-class mappings (GLP-1, DPP-4, SGLT2, etc.) for mechanisms
  - Updates both FK columns (drugs.company_id, etc.) AND entity_links rows

Usage: python backfill_data_linkage.py
"""

import json
import logging
import re
import time

from config import config
from db import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
#  B4 — Company name normalisation map
# ════════════════════════════════════════════════════════════

# Maps common sponsor-name variants -> canonical company name in our DB.
# The canonical names MUST match companies.name exactly.
COMPANY_ALIASES = {
    # Novo Nordisk
    "novo nordisk": "Novo Nordisk A/S",
    "novo nordisk a/s": "Novo Nordisk A/S",
    "novo nordisk as": "Novo Nordisk A/S",
    "novo nordisk pharma": "Novo Nordisk A/S",
    "novo nordisk inc": "Novo Nordisk A/S",
    "novo nordisk inc.": "Novo Nordisk A/S",
    "novo nordisk healthcare ag": "Novo Nordisk A/S",
    "novo nordisk investigational site": "Novo Nordisk A/S",
    # Eli Lilly
    "eli lilly": "Eli Lilly and Company",
    "eli lilly and company": "Eli Lilly and Company",
    "eli lilly & company": "Eli Lilly and Company",
    "lilly": "Eli Lilly and Company",
    "eli lilly and company limited": "Eli Lilly and Company",
    "eli lilly and company (lilly)": "Eli Lilly and Company",
    # Sanofi
    "sanofi": "Sanofi",
    "sanofi-aventis": "Sanofi",
    "sanofi aventis": "Sanofi",
    "sanofi pasteur": "Sanofi",
    "sanofi us": "Sanofi",
    "sanofi-synthelabo": "Sanofi",
    "sanofi winthrop industrie": "Sanofi",
    # AstraZeneca
    "astrazeneca": "AstraZeneca PLC",
    "astrazeneca plc": "AstraZeneca PLC",
    "astrazeneca ab": "AstraZeneca PLC",
    "astrazeneca uk limited": "AstraZeneca PLC",
    "astrazeneca pharmaceuticals lp": "AstraZeneca PLC",
    "medimmune llc": "AstraZeneca PLC",  # subsidiary
    # Pfizer
    "pfizer": "Pfizer Inc.",
    "pfizer inc": "Pfizer Inc.",
    "pfizer inc.": "Pfizer Inc.",
    "pfizer pharmaceuticals": "Pfizer Inc.",
    "pfizer's upjohn": "Pfizer Inc.",
    "wyeth": "Pfizer Inc.",  # acquired by Pfizer
    # Merck
    "merck sharp & dohme": "Merck Sharp & Dohme",
    "merck sharp and dohme": "Merck Sharp & Dohme",
    "merck sharp & dohme corp.": "Merck Sharp & Dohme",
    "merck sharp & dohme llc": "Merck Sharp & Dohme",
    "merck & co., inc.": "Merck Sharp & Dohme",
    "merck & co.": "Merck Sharp & Dohme",
    "merck": "Merck Sharp & Dohme",
    "msd": "Merck Sharp & Dohme",
    # Boehringer Ingelheim
    "boehringer ingelheim": "Boehringer Ingelheim",
    "boehringer ingelheim pharmaceuticals": "Boehringer Ingelheim",
    "boehringer ingelheim pharmaceuticals, inc.": "Boehringer Ingelheim",
    # Johnson & Johnson / Janssen
    "janssen": "Janssen Pharmaceuticals",
    "janssen pharmaceuticals": "Janssen Pharmaceuticals",
    "janssen research & development, llc": "Janssen Pharmaceuticals",
    "janssen-cilag": "Janssen Pharmaceuticals",
    "johnson & johnson": "Janssen Pharmaceuticals",
    # AbbVie
    "abbvie": "AbbVie Inc.",
    "abbvie inc.": "AbbVie Inc.",
    "abbvie inc": "AbbVie Inc.",
    # Amgen
    "amgen": "Amgen Inc.",
    "amgen inc": "Amgen Inc.",
    "amgen inc.": "Amgen Inc.",
    # Bristol-Myers Squibb
    "bristol-myers squibb": "Bristol-Myers Squibb",
    "bristol myers squibb": "Bristol-Myers Squibb",
    "bms": "Bristol-Myers Squibb",
    # Roche / Genentech
    "roche": "Roche",
    "f. hoffmann-la roche": "Roche",
    "hoffmann-la roche": "Roche",
    "genentech": "Roche",
    "genentech, inc.": "Roche",
    # Novartis
    "novartis": "Novartis",
    "novartis pharmaceuticals": "Novartis",
    "novartis ag": "Novartis",
    "novartis pharma ag": "Novartis",
    "novartis pharmaceuticals corporation": "Novartis",
    # Takeda
    "takeda": "Takeda",
    "takeda pharmaceutical": "Takeda",
    "takeda pharmaceuticals": "Takeda",
    # Bayer
    "bayer": "Bayer",
    "bayer ag": "Bayer",
    "bayer pharmaceuticals": "Bayer",
    # GSK
    "glaxosmithkline": "GlaxoSmithKline",
    "gsk": "GlaxoSmithKline",
    "smithkline beecham": "GlaxoSmithKline",
}


# ════════════════════════════════════════════════════════════
#  B2 — Therapeutic-area keyword rules
# ════════════════════════════════════════════════════════════

# Maps condition keywords (lowercased) -> therapeutic area name
# These must match therapeutic_areas.name in the DB
TA_KEYWORD_MAP = {
    # Diabetes
    "diabetes": "Diabetes Mellitus",
    "diabetic": "Diabetes Mellitus",
    "type 2 diabetes": "Diabetes Mellitus, Type 2",
    "type 2 dm": "Diabetes Mellitus, Type 2",
    "t2dm": "Diabetes Mellitus, Type 2",
    "type ii diabetes": "Diabetes Mellitus, Type 2",
    "type 1 diabetes": "Diabetes Mellitus",
    "t1dm": "Diabetes Mellitus",
    "hba1c": "Diabetes Mellitus",
    "glycemic": "Diabetes Mellitus",
    "hyperglycemia": "Diabetes Mellitus",
    "insulin resistance": "Diabetes Mellitus, Type 2",
    # Obesity
    "obesity": "Obesity",
    "obese": "Obesity",
    "overweight": "Obesity",
    "weight loss": "Obesity",
    "weight management": "Obesity",
    "weight reduction": "Obesity",
    "bmi": "Obesity",
    "body mass index": "Obesity",
    "adiposity": "Obesity",
    "metabolic syndrome": "Obesity",
    "nafld": "Obesity",
    "nash": "Obesity",
    "non-alcoholic fatty liver": "Obesity",
    "nonalcoholic steatohepatitis": "Obesity",
    # Heart Failure / Cardiovascular
    "heart failure": "Heart Failure",
    "hfref": "Heart Failure",
    "hfpef": "Heart Failure",
    "reduced ejection fraction": "Heart Failure",
    "preserved ejection fraction": "Heart Failure",
    "cardiac failure": "Heart Failure",
    "congestive heart failure": "Heart Failure",
    "chf": "Heart Failure",
    "left ventricular": "Heart Failure",
    "lvef": "Heart Failure",
    "nyha": "Heart Failure",
    "cardiovascular": "Cardiovascular Diseases",
    "cardio-renal": "Cardiovascular Diseases",
    "cardiometabolic": "Cardiovascular Diseases",
    "atherosclerosis": "Cardiovascular Diseases",
    "myocardial infarction": "Cardiovascular Diseases",
    "stroke": "Cardiovascular Diseases",
    "hypertension": "Hypertension",
    "blood pressure": "Hypertension",
    "hypertensive": "Hypertension",
}


# ════════════════════════════════════════════════════════════
#  B3 — Mechanism-of-action drug class rules
# ════════════════════════════════════════════════════════════

# Maps drug generic names (lowercased) to mechanism-of-action names.
# These must match mechanisms_of_action.name in the DB.
# We'll also load from the DB and try fuzzy matching.

# Drug suffix -> mechanism name
DRUG_CLASS_RULES = [
    # GLP-1 receptor agonists (suffix: -glutide)
    (r"glutide$", "Glucagon-Like Peptide-1 Receptor Agonists"),
    (r"^semaglutide", "Glucagon-Like Peptide-1 Receptor Agonists"),
    (r"^liraglutide", "Glucagon-Like Peptide-1 Receptor Agonists"),
    (r"^dulaglutide", "Glucagon-Like Peptide-1 Receptor Agonists"),
    (r"^tirzepatide", "Glucagon-Like Peptide-1 Receptor Agonists"),  # GLP-1/GIP dual
    (r"^exenatide", "Glucagon-Like Peptide-1 Receptor Agonists"),
    (r"^albiglutide", "Glucagon-Like Peptide-1 Receptor Agonists"),
    (r"^lixisenatide", "Glucagon-Like Peptide-1 Receptor Agonists"),
    # DPP-4 inhibitors (suffix: -gliptin)
    (r"gliptin$", "Dipeptidyl-Peptidase IV Inhibitors"),
    (r"^sitagliptin", "Dipeptidyl-Peptidase IV Inhibitors"),
    (r"^saxagliptin", "Dipeptidyl-Peptidase IV Inhibitors"),
    (r"^linagliptin", "Dipeptidyl-Peptidase IV Inhibitors"),
    (r"^alogliptin", "Dipeptidyl-Peptidase IV Inhibitors"),
    (r"^vildagliptin", "Dipeptidyl-Peptidase IV Inhibitors"),
    # SGLT2 inhibitors (suffix: -gliflozin)
    (r"gliflozin$", "Sodium-Glucose Transporter 2 Inhibitors"),
    (r"^empagliflozin", "Sodium-Glucose Transporter 2 Inhibitors"),
    (r"^dapagliflozin", "Sodium-Glucose Transporter 2 Inhibitors"),
    (r"^canagliflozin", "Sodium-Glucose Transporter 2 Inhibitors"),
    (r"^ertugliflozin", "Sodium-Glucose Transporter 2 Inhibitors"),
    # Insulin
    (r"^insulin", "Insulin"),
    # Metformin / Biguanides
    (r"^metformin", "Metformin"),
    # Thiazolidinediones
    (r"^pioglitazone", "Thiazolidinediones"),
    (r"^rosiglitazone", "Thiazolidinediones"),
    # Appetite suppressants
    (r"^phentermine", "Appetite Depressants"),
    (r"^orlistat", "Appetite Depressants"),
    (r"^naltrexone.*bupropion", "Appetite Depressants"),
    # ── Cardiovascular / Heart Failure mechanisms ──
    # ACE inhibitors (suffix: -pril)
    (r"pril$", "Angiotensin-Converting Enzyme Inhibitors"),
    (r"^enalapril", "Angiotensin-Converting Enzyme Inhibitors"),
    (r"^lisinopril", "Angiotensin-Converting Enzyme Inhibitors"),
    (r"^ramipril", "Angiotensin-Converting Enzyme Inhibitors"),
    (r"^captopril", "Angiotensin-Converting Enzyme Inhibitors"),
    # ARBs (suffix: -sartan)
    (r"sartan$", "Angiotensin II Type 1 Receptor Blockers"),
    (r"^valsartan", "Angiotensin II Type 1 Receptor Blockers"),
    (r"^losartan", "Angiotensin II Type 1 Receptor Blockers"),
    (r"^irbesartan", "Angiotensin II Type 1 Receptor Blockers"),
    (r"^candesartan", "Angiotensin II Type 1 Receptor Blockers"),
    # Beta-blockers (suffix: -olol)
    (r"olol$", "Adrenergic beta-Antagonists"),
    (r"^carvedilol", "Adrenergic beta-Antagonists"),
    (r"^metoprolol", "Adrenergic beta-Antagonists"),
    (r"^bisoprolol", "Adrenergic beta-Antagonists"),
    (r"^atenolol", "Adrenergic beta-Antagonists"),
    (r"^nebivolol", "Adrenergic beta-Antagonists"),
    # ARNI (Neprilysin inhibitor)
    (r"^sacubitril", "Neprilysin Inhibitors"),
    # MRAs
    (r"^spironolactone", "Mineralocorticoid Receptor Antagonists"),
    (r"^eplerenone", "Mineralocorticoid Receptor Antagonists"),
    (r"^finerenone", "Mineralocorticoid Receptor Antagonists"),
    # Other CV
    (r"^vericiguat", "Phosphodiesterase Inhibitors"),
    (r"^ivabradine", "Phosphodiesterase Inhibitors"),
]

# Pharm class text -> mechanism name (from FDA pharm_class_epc / pharm_class_moa)
PHARM_CLASS_MAP = {
    "glucagon-like peptide-1 (glp-1) receptor agonist": "Glucagon-Like Peptide-1 Receptor Agonists",
    "glp-1 receptor agonist": "Glucagon-Like Peptide-1 Receptor Agonists",
    "incretin mimetic": "Incretins",
    "dipeptidyl peptidase 4 inhibitor": "Dipeptidyl-Peptidase IV Inhibitors",
    "dpp-4 inhibitor": "Dipeptidyl-Peptidase IV Inhibitors",
    "sodium-glucose transporter 2 inhibitor": "Sodium-Glucose Transporter 2 Inhibitors",
    "sglt2 inhibitor": "Sodium-Glucose Transporter 2 Inhibitors",
    "insulin": "Insulin",
    "biguanide": "Metformin",
    "thiazolidinedione": "Thiazolidinediones",
    "meglitinide analog": "Hypoglycemic Agents",
    "alpha-glucosidase inhibitor": "Hypoglycemic Agents",
    "amylin analog": "Hypoglycemic Agents",
    "sulfonylurea": "Hypoglycemic Agents",
    # ── Cardiovascular / Heart Failure ──
    "angiotensin-converting enzyme inhibitor": "Angiotensin-Converting Enzyme Inhibitors",
    "ace inhibitor": "Angiotensin-Converting Enzyme Inhibitors",
    "angiotensin 2 receptor blocker": "Angiotensin II Type 1 Receptor Blockers",
    "angiotensin ii receptor blocker": "Angiotensin II Type 1 Receptor Blockers",
    "arb": "Angiotensin II Type 1 Receptor Blockers",
    "beta-adrenergic blocker": "Adrenergic beta-Antagonists",
    "beta blocker": "Adrenergic beta-Antagonists",
    "neprilysin inhibitor": "Neprilysin Inhibitors",
    "angiotensin receptor-neprilysin inhibitor": "Neprilysin Inhibitors",
    "arni": "Neprilysin Inhibitors",
    "aldosterone antagonist": "Mineralocorticoid Receptor Antagonists",
    "mineralocorticoid receptor antagonist": "Mineralocorticoid Receptor Antagonists",
    "non-steroidal mineralocorticoid receptor antagonist": "Mineralocorticoid Receptor Antagonists",
    "loop diuretic": "Diuretics",
    "diuretic": "Diuretics",
    "hcn channel blocker": "Phosphodiesterase Inhibitors",
    "soluble guanylate cyclase stimulator": "Phosphodiesterase Inhibitors",
}


# ════════════════════════════════════════════════════════════
#  Helper: upsert link (copied from backfill_resolution.py)
# ════════════════════════════════════════════════════════════

def _upsert_link(db, source_id, source_type, target_id, target_type,
                 link_type, via, confidence, source, metadata=None) -> bool:
    """Insert a link, return True if created."""
    metadata_json = json.dumps(metadata) if metadata else None
    try:
        row = db.fetch_one(
            """
            INSERT INTO entity_links
                (source_entity_id, source_entity_type,
                 target_entity_id, target_entity_type,
                 link_type, link_via, confidence, metadata, provenance_source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (source_entity_id, target_entity_id, link_type) DO NOTHING
            RETURNING id
            """,
            [str(source_id), source_type, str(target_id), target_type,
             link_type, via, confidence, metadata_json, source],
        )
        return row is not None
    except Exception as e:
        logger.debug("Link upsert error: %s", e)
        return False


def _ensure_company(db, name) -> str | None:
    """Get or create a company, return its UUID."""
    row = db.fetch_one(
        "SELECT id FROM companies WHERE LOWER(name) = LOWER(%s)", [name]
    )
    if row:
        return str(row["id"])
    # Create it
    try:
        row = db.fetch_one(
            """
            INSERT INTO companies (name, source_api, source_url, retrieved_at)
            VALUES (%s, 'backfill_linkage', 'backfill', NOW())
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            [name],
        )
        if row:
            logger.info("Created company: %s", name)
            return str(row["id"])
    except Exception as e:
        logger.debug("Company create error: %s", e)
        # Race condition — try lookup again
        row = db.fetch_one(
            "SELECT id FROM companies WHERE LOWER(name) = LOWER(%s)", [name]
        )
        if row:
            return str(row["id"])
    return None


def _normalise_sponsor(raw_name: str) -> str | None:
    """Normalise a sponsor name to a canonical company name, or None."""
    if not raw_name:
        return None
    key = raw_name.strip().lower()
    # Direct alias lookup
    if key in COMPANY_ALIASES:
        return COMPANY_ALIASES[key]
    # Try prefix matching for long sponsor strings like
    # "Novo Nordisk Investigational Site"
    for alias, canonical in COMPANY_ALIASES.items():
        if key.startswith(alias) or alias.startswith(key):
            return canonical
    return None


# ════════════════════════════════════════════════════════════
#  Phase 1 — B1: Company-Drug OWNS links
# ════════════════════════════════════════════════════════════

def phase1_owns_links(db):
    """
    Create OWNS links by three methods:
      1a. Patent applicant_holder -> company -> drug
      1b. Trial sponsor + INVESTIGATES link -> sponsor owns drug
      1c. Direct drug generic_name pattern matching (known drugs -> known companies)
    """
    print("\n" + "=" * 60)
    print("PHASE 1: Company-Drug OWNS Links (B1 + B4)")
    print("=" * 60)

    company_cache = {}  # canonical_name -> company_id
    drug_company = {}   # drug_id -> company_id  (accumulator)

    # Pre-load all companies
    for row in db.fetch_all("SELECT id, name FROM companies"):
        company_cache[row["name"]] = str(row["id"])

    # ── 1a: From patent applicant_holder ──
    print("\n  --- 1a: Patent applicant_holder -> OWNS ---")
    patents = db.fetch_all("""
        SELECT DISTINCT p.drug_id, p.applicant_holder
        FROM patents p
        WHERE p.applicant_holder IS NOT NULL AND p.drug_id IS NOT NULL
    """)
    matched_patent = 0
    for p in patents:
        canonical = _normalise_sponsor(p["applicant_holder"])
        if not canonical:
            continue
        if canonical not in company_cache:
            cid = _ensure_company(db, canonical)
            if cid:
                company_cache[canonical] = cid
        if canonical in company_cache:
            drug_company[str(p["drug_id"])] = company_cache[canonical]
            matched_patent += 1
    print(f"    Matched via patents: {matched_patent}")

    # ── 1b: From trial sponsor_name (where trial INVESTIGATES drug) ──
    print("\n  --- 1b: Trial sponsor -> OWNS (via INVESTIGATES) ---")
    trial_drugs = db.fetch_all("""
        SELECT ct.sponsor_name, ct.drug_id
        FROM clinical_trials ct
        WHERE ct.drug_id IS NOT NULL AND ct.sponsor_name IS NOT NULL
    """)
    # Group by drug_id: pick the most common sponsor per drug
    from collections import Counter
    drug_sponsors = {}  # drug_id -> Counter of canonical company names
    for td in trial_drugs:
        canonical = _normalise_sponsor(td["sponsor_name"])
        if not canonical:
            continue
        did = str(td["drug_id"])
        if did not in drug_sponsors:
            drug_sponsors[did] = Counter()
        drug_sponsors[did][canonical] += 1

    matched_sponsor = 0
    for did, counter in drug_sponsors.items():
        if did in drug_company:
            continue  # already set by patent
        top_company = counter.most_common(1)[0][0]
        if top_company not in company_cache:
            cid = _ensure_company(db, top_company)
            if cid:
                company_cache[top_company] = cid
        if top_company in company_cache:
            drug_company[did] = company_cache[top_company]
            matched_sponsor += 1
    print(f"    Matched via sponsors: {matched_sponsor}")

    # ── 1c: Known drug->company direct mappings ──
    print("\n  --- 1c: Known drug-company mappings ---")
    KNOWN_DRUG_COMPANIES = {
        "semaglutide": "Novo Nordisk A/S",
        "liraglutide": "Novo Nordisk A/S",
        "insulin aspart": "Novo Nordisk A/S",
        "insulin detemir": "Novo Nordisk A/S",
        "insulin degludec": "Novo Nordisk A/S",
        "tirzepatide": "Eli Lilly and Company",
        "dulaglutide": "Eli Lilly and Company",
        "empagliflozin": "Boehringer Ingelheim",
        "linagliptin": "Boehringer Ingelheim",
        "dapagliflozin": "AstraZeneca PLC",
        "saxagliptin": "AstraZeneca PLC",
        "canagliflozin": "Janssen Pharmaceuticals",
        "sitagliptin": "Merck Sharp & Dohme",
        "ertugliflozin": "Merck Sharp & Dohme",
        "pioglitazone": "Takeda",
        "alogliptin": "Takeda",
        "metformin": "Bristol-Myers Squibb",  # original manufacturer
        "exenatide": "AstraZeneca PLC",  # acquired from Amylin
        "lixisenatide": "Sanofi",
        "insulin glargine": "Sanofi",
        "insulin lispro": "Eli Lilly and Company",
        "insulin glulisine": "Sanofi",
        "phentermine": "Teva Pharmaceuticals",
        "orlistat": "Roche",
    }
    matched_known = 0
    all_drugs = db.fetch_all("SELECT id, generic_name FROM drugs")
    for drug in all_drugs:
        did = str(drug["id"])
        if did in drug_company:
            continue
        gname = (drug["generic_name"] or "").lower().strip()
        if gname in KNOWN_DRUG_COMPANIES:
            canonical = KNOWN_DRUG_COMPANIES[gname]
            if canonical not in company_cache:
                cid = _ensure_company(db, canonical)
                if cid:
                    company_cache[canonical] = cid
            if canonical in company_cache:
                drug_company[did] = company_cache[canonical]
                matched_known += 1
    print(f"    Matched via known mappings: {matched_known}")

    # ── Apply: Update drugs.company_id FK + create OWNS links ──
    print(f"\n  Total drugs with company assignment: {len(drug_company)}")
    fk_updated = 0
    links_created = 0
    for did, cid in drug_company.items():
        # Update FK
        try:
            db.execute(
                "UPDATE drugs SET company_id = %s, updated_at = NOW() WHERE id = %s AND (company_id IS NULL OR company_id != %s)",
                [cid, did, cid],
            )
            fk_updated += 1
        except Exception as e:
            logger.debug("FK update error for drug %s: %s", did, e)

        # Create OWNS link
        created = _upsert_link(
            db,
            source_id=cid, source_type="company",
            target_id=did, target_type="drug",
            link_type="OWNS", via="backfill_linkage",
            confidence=0.9, source="backfill_linkage",
        )
        if created:
            links_created += 1

    print(f"  FK updates: {fk_updated}")
    print(f"  OWNS links created: {links_created}")
    return len(drug_company)


# ════════════════════════════════════════════════════════════
#  Phase 2 — B2: Therapeutic Area classification
# ════════════════════════════════════════════════════════════

def phase2_therapeutic_areas(db):
    """
    Classify drugs into therapeutic areas by:
      2a. Trial conditions[] text matching -> drug's trials mention diabetes/obesity
      2b. Drug generic_name known-class inference (GLP-1s -> diabetes + obesity)
    """
    print("\n" + "=" * 60)
    print("PHASE 2: Drug Therapeutic Area Classification (B2)")
    print("=" * 60)

    # Load TA lookup: name -> id
    ta_lookup = {}
    for row in db.fetch_all("SELECT id, name FROM therapeutic_areas"):
        ta_lookup[row["name"]] = str(row["id"])

    if not ta_lookup:
        print("  WARNING: No therapeutic_areas in DB. Creating base entries.")
        base_tas = [
            ("Diabetes Mellitus", "D003920"),
            ("Diabetes Mellitus, Type 2", "D003924"),
            ("Obesity", "D009765"),
        ]
        for name, mesh_id in base_tas:
            row = db.fetch_one(
                """
                INSERT INTO therapeutic_areas (name, mesh_id, source_api, source_url, retrieved_at)
                VALUES (%s, %s, 'backfill_linkage', 'backfill', NOW())
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                [name, mesh_id],
            )
            if row:
                ta_lookup[name] = str(row["id"])
        print(f"  Created {len(base_tas)} therapeutic areas")

    # Collect drug -> set of TA names
    drug_tas = {}  # drug_id -> set of TA names

    # ── 2a: From trial conditions ──
    print("\n  --- 2a: Trial conditions -> drug TA ---")
    trial_conditions = db.fetch_all("""
        SELECT ct.drug_id, ct.conditions
        FROM clinical_trials ct
        WHERE ct.drug_id IS NOT NULL AND ct.conditions IS NOT NULL
    """)
    matched_condition = 0
    for tc in trial_conditions:
        did = str(tc["drug_id"])
        cond_text = " ".join(tc["conditions"]).lower() if isinstance(tc["conditions"], list) else (tc["conditions"] or "").lower()
        for keyword, ta_name in TA_KEYWORD_MAP.items():
            if keyword in cond_text:
                if did not in drug_tas:
                    drug_tas[did] = set()
                drug_tas[did].add(ta_name)
                matched_condition += 1
                break  # one match per trial is enough
    print(f"    Drugs classified via conditions: {len(drug_tas)}")

    # ── 2b: Known drug classes ──
    print("\n  --- 2b: Drug name -> TA inference ---")
    # GLP-1/DPP-4/SGLT2/Insulin drugs -> diabetes + obesity
    DIABETES_DRUG_PATTERNS = [
        r"glutide$", r"gliptin$", r"gliflozin$",
        r"^insulin", r"^metformin", r"^pioglitazone", r"^rosiglitazone",
        r"^sitagliptin", r"^saxagliptin", r"^linagliptin", r"^alogliptin",
        r"^exenatide", r"^lixisenatide",
    ]
    OBESITY_DRUG_PATTERNS = [
        r"^semaglutide", r"^tirzepatide", r"^liraglutide",
        r"^phentermine", r"^orlistat", r"^naltrexone",
    ]

    all_drugs = db.fetch_all("SELECT id, generic_name FROM drugs")
    for drug in all_drugs:
        did = str(drug["id"])
        gname = (drug["generic_name"] or "").lower().strip()
        for pat in DIABETES_DRUG_PATTERNS:
            if re.search(pat, gname):
                if did not in drug_tas:
                    drug_tas[did] = set()
                drug_tas[did].add("Diabetes Mellitus")
                drug_tas[did].add("Diabetes Mellitus, Type 2")
                break
        for pat in OBESITY_DRUG_PATTERNS:
            if re.search(pat, gname):
                if did not in drug_tas:
                    drug_tas[did] = set()
                drug_tas[did].add("Obesity")
                break
    print(f"    Total drugs with TA: {len(drug_tas)}")

    # ── Apply: Update drugs.therapeutic_area_id FK (pick most specific) + create links ──
    fk_updated = 0
    links_created = 0
    for did, ta_names in drug_tas.items():
        # Pick the most specific TA for the FK (prefer Type 2 over general Diabetes)
        primary_ta = None
        if "Diabetes Mellitus, Type 2" in ta_names:
            primary_ta = "Diabetes Mellitus, Type 2"
        elif "Diabetes Mellitus" in ta_names:
            primary_ta = "Diabetes Mellitus"
        elif "Obesity" in ta_names:
            primary_ta = "Obesity"

        if primary_ta and primary_ta in ta_lookup:
            try:
                db.execute(
                    "UPDATE drugs SET therapeutic_area_id = %s, updated_at = NOW() WHERE id = %s AND therapeutic_area_id IS NULL",
                    [ta_lookup[primary_ta], did],
                )
                fk_updated += 1
            except Exception as e:
                logger.debug("TA FK update error for drug %s: %s", did, e)

        # Create IN_THERAPEUTIC_AREA links for ALL matching TAs
        for ta_name in ta_names:
            if ta_name in ta_lookup:
                created = _upsert_link(
                    db,
                    source_id=did, source_type="drug",
                    target_id=ta_lookup[ta_name], target_type="therapeutic_area",
                    link_type="IN_THERAPEUTIC_AREA", via="backfill_linkage",
                    confidence=0.85, source="backfill_linkage",
                )
                if created:
                    links_created += 1

    print(f"\n  FK updates: {fk_updated}")
    print(f"  IN_THERAPEUTIC_AREA links created: {links_created}")
    return len(drug_tas)


# ════════════════════════════════════════════════════════════
#  Phase 3 — B3: Mechanism of Action classification
# ════════════════════════════════════════════════════════════

def phase3_mechanisms(db):
    """
    Classify drugs by mechanism of action using:
      3a. Drug generic_name regex rules (suffix patterns)
      3b. Fallback: trial intervention text patterns
    """
    print("\n" + "=" * 60)
    print("PHASE 3: Drug Mechanism of Action Classification (B3)")
    print("=" * 60)

    # Load mechanism lookup: name -> id
    mech_lookup = {}
    for row in db.fetch_all("SELECT id, name FROM mechanisms_of_action"):
        mech_lookup[row["name"]] = str(row["id"])

    # Ensure base mechanisms exist
    BASE_MECHANISMS = [
        ("Glucagon-Like Peptide-1 Receptor Agonists", "D000097789"),
        ("Incretins", "D054795"),
        ("Hypoglycemic Agents", "D007004"),
        ("Dipeptidyl-Peptidase IV Inhibitors", "D054873"),
        ("Sodium-Glucose Transporter 2 Inhibitors", "D000077203"),
        ("Insulin", "D007328"),
        ("Thiazolidinediones", "D045162"),
        ("Metformin", "D008687"),
        ("Appetite Depressants", "D001067"),
    ]
    created_count = 0
    for name, mesh_id in BASE_MECHANISMS:
        if name not in mech_lookup:
            row = db.fetch_one(
                """
                INSERT INTO mechanisms_of_action (name, mesh_id, source_api, source_url, retrieved_at)
                VALUES (%s, %s, 'backfill_linkage', 'backfill', NOW())
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                [name, mesh_id],
            )
            if row:
                mech_lookup[name] = str(row["id"])
                created_count += 1
    if created_count:
        print(f"  Created {created_count} mechanism entries")

    # Classify drugs
    drug_mech = {}  # drug_id -> mechanism_name
    all_drugs = db.fetch_all("SELECT id, generic_name FROM drugs")

    for drug in all_drugs:
        did = str(drug["id"])
        gname = (drug["generic_name"] or "").lower().strip()
        for pattern, mech_name in DRUG_CLASS_RULES:
            if re.search(pattern, gname):
                drug_mech[did] = mech_name
                break

    print(f"  Drugs classified by mechanism: {len(drug_mech)}")

    # Apply
    fk_updated = 0
    links_created = 0
    for did, mech_name in drug_mech.items():
        if mech_name not in mech_lookup:
            continue
        mid = mech_lookup[mech_name]

        # Update FK
        try:
            db.execute(
                "UPDATE drugs SET mechanism_id = %s, updated_at = NOW() WHERE id = %s AND mechanism_id IS NULL",
                [mid, did],
            )
            fk_updated += 1
        except Exception as e:
            logger.debug("Mechanism FK update error for drug %s: %s", did, e)

        # Create TARGETS_MECHANISM link
        created = _upsert_link(
            db,
            source_id=did, source_type="drug",
            target_id=mid, target_type="mechanism",
            link_type="TARGETS_MECHANISM", via="backfill_linkage",
            confidence=0.9, source="backfill_linkage",
        )
        if created:
            links_created += 1

    print(f"  FK updates: {fk_updated}")
    print(f"  TARGETS_MECHANISM links created: {links_created}")
    return len(drug_mech)


# ════════════════════════════════════════════════════════════
#  Phase 4 — B4: Backfill SPONSORS links with normalised names
# ════════════════════════════════════════════════════════════

def phase4_sponsors_normalised(db):
    """
    Re-run SPONSORS link creation with normalised company names.
    The original backfill only matched exact LOWER(sponsor_name) = LOWER(companies.name).
    Now we use the alias map.
    """
    print("\n" + "=" * 60)
    print("PHASE 4: Normalised SPONSORS Links (B4)")
    print("=" * 60)

    company_cache = {}
    for row in db.fetch_all("SELECT id, name FROM companies"):
        company_cache[row["name"]] = str(row["id"])

    trials = db.fetch_all("""
        SELECT id, sponsor_name
        FROM clinical_trials
        WHERE sponsor_name IS NOT NULL
    """)

    links_created = 0
    new_matches = 0
    for trial in trials:
        canonical = _normalise_sponsor(trial["sponsor_name"])
        if not canonical:
            continue
        if canonical not in company_cache:
            cid = _ensure_company(db, canonical)
            if cid:
                company_cache[canonical] = cid
        if canonical not in company_cache:
            continue

        cid = company_cache[canonical]
        created = _upsert_link(
            db,
            source_id=cid, source_type="company",
            target_id=trial["id"], target_type="trial",
            link_type="SPONSORS", via="name_normalisation",
            confidence=0.95, source="backfill_linkage",
        )
        if created:
            links_created += 1
            new_matches += 1

    print(f"  New SPONSORS links: {links_created}")
    return links_created


# ════════════════════════════════════════════════════════════
#  Phase 5 — Cross-source entity links (AE, Label, PMC)
# ════════════════════════════════════════════════════════════

def phase5_cross_source_links(db):
    """Create HAS_ADVERSE_EVENT, HAS_LABEL, HAS_FULL_TEXT entity_links
    for records that have drug_id FK but no corresponding graph link."""
    print("\n" + "=" * 60)
    print("PHASE 5: Cross-Source Entity Links (AE / Label / PMC)")
    print("=" * 60)

    total_created = 0

    # 5a: adverse_events -> drug  (HAS_ADVERSE_EVENT)
    ae_rows = db.fetch_all("""
        SELECT ae.id, ae.drug_id
        FROM adverse_events ae
        WHERE ae.drug_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM entity_links el
            WHERE el.source_entity_id = ae.drug_id::text
              AND el.target_entity_id = ae.id::text
              AND el.link_type = 'HAS_ADVERSE_EVENT'
          )
    """)
    ae_created = 0
    for row in ae_rows:
        if _upsert_link(
            db,
            source_id=row["drug_id"], source_type="drug",
            target_id=row["id"], target_type="adverse_event",
            link_type="HAS_ADVERSE_EVENT", via="drug_id_fk",
            confidence=1.0, source="backfill_linkage",
        ):
            ae_created += 1
    print(f"  HAS_ADVERSE_EVENT links created: {ae_created}")
    total_created += ae_created

    # 5b: drug_labels -> drug  (HAS_LABEL)
    dl_rows = db.fetch_all("""
        SELECT dl.id, dl.drug_id
        FROM drug_labels dl
        WHERE dl.drug_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM entity_links el
            WHERE el.source_entity_id = dl.drug_id::text
              AND el.target_entity_id = dl.id::text
              AND el.link_type = 'HAS_LABEL'
          )
    """)
    dl_created = 0
    for row in dl_rows:
        if _upsert_link(
            db,
            source_id=row["drug_id"], source_type="drug",
            target_id=row["id"], target_type="drug_label",
            link_type="HAS_LABEL", via="drug_id_fk",
            confidence=1.0, source="backfill_linkage",
        ):
            dl_created += 1
    print(f"  HAS_LABEL links created: {dl_created}")
    total_created += dl_created

    # 5c: pmc_articles -> drug  (HAS_FULL_TEXT)
    pmc_rows = db.fetch_all("""
        SELECT pa.id, pa.drug_id, pa.pubmed_article_id
        FROM pmc_articles pa
        WHERE pa.drug_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM entity_links el
            WHERE el.source_entity_id = pa.drug_id::text
              AND el.target_entity_id = pa.id::text
              AND el.link_type = 'HAS_FULL_TEXT'
          )
    """)
    pmc_created = 0
    for row in pmc_rows:
        if _upsert_link(
            db,
            source_id=row["drug_id"], source_type="drug",
            target_id=row["id"], target_type="pmc_article",
            link_type="HAS_FULL_TEXT", via="drug_id_fk",
            confidence=1.0, source="backfill_linkage",
        ):
            pmc_created += 1
    print(f"  HAS_FULL_TEXT links created: {pmc_created}")
    total_created += pmc_created

    # 5d: pmc_articles -> pubmed_articles (link full-text to abstract)
    pmc_pub_rows = db.fetch_all("""
        SELECT pa.id, pa.pubmed_article_id
        FROM pmc_articles pa
        WHERE pa.pubmed_article_id IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM entity_links el
            WHERE el.source_entity_id = pa.pubmed_article_id::text
              AND el.target_entity_id = pa.id::text
              AND el.link_type = 'HAS_FULL_TEXT'
          )
    """)
    pmc_pub_created = 0
    for row in pmc_pub_rows:
        if _upsert_link(
            db,
            source_id=row["pubmed_article_id"], source_type="literature",
            target_id=row["id"], target_type="pmc_article",
            link_type="HAS_FULL_TEXT", via="pubmed_article_id_fk",
            confidence=1.0, source="backfill_linkage",
        ):
            pmc_pub_created += 1
    print(f"  HAS_FULL_TEXT (pubmed->pmc) links created: {pmc_pub_created}")
    total_created += pmc_pub_created

    print(f"  Total cross-source links: {total_created}")
    return total_created


# ════════════════════════════════════════════════════════════
#  Phase 6 — Refresh materialized views
# ════════════════════════════════════════════════════════════

def phase6_refresh_views(db):
    """Refresh all materialized views so metrics reflect new links."""
    print("\n" + "=" * 60)
    print("PHASE 6: Refresh Materialized Views")
    print("=" * 60)

    views = [
        "mv_drug_pipeline_strength",
        "mv_trial_success_rate",
        "mv_evidence_density",
        "mv_competitive_landscape",
        "mv_company_portfolio",
    ]
    for view in views:
        try:
            db.execute(f"REFRESH MATERIALIZED VIEW {view}")
            print(f"  Refreshed {view}")
        except Exception as e:
            print(f"  SKIP {view}: {e}")


# ════════════════════════════════════════════════════════════
#  Final report
# ════════════════════════════════════════════════════════════

def show_report(db):
    """Print post-backfill state."""
    print("\n" + "=" * 60)
    print("POST-BACKFILL REPORT")
    print("=" * 60)

    # Entity links by type
    print("\n  Entity Links by Type:")
    rows = db.fetch_all(
        "SELECT link_type, count(*) as c FROM entity_links GROUP BY link_type ORDER BY c DESC"
    )
    for r in rows:
        print(f"    {r['link_type']:30s} {r['c']:>7}")

    # Drug FK coverage
    total_drugs = db.fetch_one("SELECT count(*) as c FROM drugs")["c"]
    with_company = db.fetch_one("SELECT count(*) as c FROM drugs WHERE company_id IS NOT NULL")["c"]
    with_ta = db.fetch_one("SELECT count(*) as c FROM drugs WHERE therapeutic_area_id IS NOT NULL")["c"]
    with_mech = db.fetch_one("SELECT count(*) as c FROM drugs WHERE mechanism_id IS NOT NULL")["c"]

    print(f"\n  Drug FK Coverage ({total_drugs} total):")
    print(f"    company_id:          {with_company:>5}  ({100*with_company//max(total_drugs,1)}%)")
    print(f"    therapeutic_area_id:  {with_ta:>5}  ({100*with_ta//max(total_drugs,1)}%)")
    print(f"    mechanism_id:         {with_mech:>5}  ({100*with_mech//max(total_drugs,1)}%)")

    # Company portfolio
    print("\n  Company Drug Portfolios (top 10):")
    rows = db.fetch_all("""
        SELECT c.name, count(d.id) as drugs
        FROM companies c
        LEFT JOIN drugs d ON d.company_id = c.id
        GROUP BY c.name
        ORDER BY drugs DESC
        LIMIT 10
    """)
    for r in rows:
        print(f"    {r['name']:40s} {r['drugs']:>5} drugs")

    # Competitive landscape preview
    print("\n  Competitive Landscape Preview:")
    rows = db.fetch_all("""
        SELECT ta.name as ta, count(DISTINCT d.id) as drugs, count(DISTINCT d.company_id) as companies
        FROM therapeutic_areas ta
        JOIN drugs d ON d.therapeutic_area_id = ta.id
        GROUP BY ta.name
        ORDER BY drugs DESC
    """)
    if rows:
        for r in rows:
            print(f"    {r['ta']:35s} {r['drugs']:>4} drugs, {r['companies']:>3} companies")
    else:
        print("    (no competitive landscape data yet)")


# ════════════════════════════════════════════════════════════
#  Main
# ════════════════════════════════════════════════════════════

def run():
    db = Database(config.db.dsn)
    db.connect()
    t0 = time.time()

    print("=" * 60)
    print("Market-Zero: Tier-1 Data Linkage Backfill (B1-B4)")
    print("=" * 60)

    # Pre-state
    print("\n  PRE-BACKFILL STATE:")
    for lt in ["OWNS", "IN_THERAPEUTIC_AREA", "TARGETS_MECHANISM", "SPONSORS",
               "HAS_ADVERSE_EVENT", "HAS_LABEL", "HAS_FULL_TEXT"]:
        row = db.fetch_one(
            "SELECT count(*) as c FROM entity_links WHERE link_type = %s", [lt]
        )
        print(f"    {lt:30s} {row['c']:>7}")

    owns = phase1_owns_links(db)
    tas = phase2_therapeutic_areas(db)
    mechs = phase3_mechanisms(db)
    sponsors = phase4_sponsors_normalised(db)
    cross = phase5_cross_source_links(db)
    phase6_refresh_views(db)
    show_report(db)

    elapsed = time.time() - t0
    print(f"\n  Completed in {elapsed:.1f}s")
    db.close()


if __name__ == "__main__":
    run()
