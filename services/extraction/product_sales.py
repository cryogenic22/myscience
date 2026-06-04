"""Pydantic schema for product-level net sales extraction (L7 / Tier 2).

The dossier is asset/drug-level, but every *automated* financial source we have
is company-level (``company_financials`` XBRL, 8-K Item 2.02 disclosures). That
grain mismatch is why a drug-level "Sales & Sentiment" (KBQ-5) view stayed
empty — attributing a parent company's consolidated revenue to one drug would be
fabrication.

Product-level net sales DO exist, but only in narrative documents: earnings
press releases, investor decks, and 10-Q/10-K MD&A tables disclose revenue
*by brand* ("Wegovy net sales $X, +N% YoY"). This schema captures exactly that
product-scoped figure from an uploaded document, so the number is grounded in a
real disclosure with evidence + source — never derived from a company total.

Drives the ``product_sales`` fact (commercial_operational domain, KBQ-5). A
company deck is self-reported, so the emitted fact is ``corporate``-class at
moderate confidence; the corroboration loop can later confirm it against a SEC
filing.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ProductSalesExtraction(BaseModel):
    """Reported net sales for a single product over one fiscal period.

    Product-scoped by construction: ``product_name`` and ``net_sales_usd`` are
    required, so the extractor can never emit a company-level total dressed up
    as a drug figure. Forward-looking guidance (a range, not a point) is out of
    scope for this schema — it routes to the separate ``sales_guidance``
    predicate via a future extractor.
    """

    model_config = ConfigDict(extra="forbid")

    product_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Brand or generic name of the PRODUCT whose sales are "
                    "reported, exactly as stated (\"Wegovy\", \"Ozempic\"). "
                    "Never a company name — this must be a single drug/product.",
    )
    company_name: Optional[str] = Field(
        None, max_length=200,
        description="Reporting company, if stated. Used only for context — the "
                    "fact attaches to the product, not the company.",
    )

    period_label: str = Field(
        ...,
        min_length=1,
        max_length=40,
        description='Fiscal period label as stated: "Q1 2026", "FY2025".',
    )
    period_end: Optional[date] = Field(
        None,
        description="Last day of the reported fiscal period, if derivable.",
    )

    net_sales_usd: float = Field(
        ...,
        description="Product net sales for the period, in FULL US dollars "
                    "(e.g. 2_500_000_000, not 2500). Convert from reported "
                    "currency only if an explicit USD figure or rate is stated; "
                    "otherwise report the stated USD figure.",
    )
    currency: str = Field(
        "USD", max_length=8,
        description="Currency the figure was originally reported in.",
    )
    yoy_change_pct: Optional[float] = Field(
        None,
        description="Year-over-year change as a percent (e.g. 41.0 for +41%, "
                    "-12.0 for a decline), only if stated.",
    )

    headline_summary: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="One-line narrative of the result as stated. Used as the "
                    "fact's evidence text.",
    )
