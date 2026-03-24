"""Drug pricing API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional

from api.deps import get_db
from db import Database

router = APIRouter(prefix="/pricing", tags=["pricing"])


@router.get("/latest")
def get_latest_prices(
    limit: int = Query(20, ge=1, le=200),
    country: Optional[str] = Query(None, description="Filter by country code (e.g. US)"),
    price_type: Optional[str] = Query(None, description="Filter by price type (e.g. nadac)"),
    db: Database = Depends(get_db),
):
    """Return latest prices across all drugs, one per drug (most recent effective_date)."""
    conditions = []
    params: list = []

    if country:
        conditions.append("dp.country = %s")
        params.append(country)
    if price_type:
        conditions.append("dp.price_type = %s")
        params.append(price_type)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    rows = db.fetch_all(
        f"""
        SELECT DISTINCT ON (dp.drug_name)
            dp.id, dp.drug_id, dp.drug_name, dp.ndc_code,
            dp.price_type, dp.unit_price, dp.unit,
            dp.currency, dp.country, dp.source_api,
            dp.effective_date, dp.retrieved_at
        FROM drug_pricing dp
        {where}
        ORDER BY dp.drug_name, dp.effective_date DESC NULLS LAST
        LIMIT %s
        """,
        params,
    )

    return {"results": rows, "count": len(rows)}


@router.get("/{drug_id}")
def get_drug_pricing(
    drug_id: str,
    country: Optional[str] = Query(None, description="Filter by country code"),
    price_type: Optional[str] = Query(None, description="Filter by price type"),
    latest_only: bool = Query(False, description="Return only most recent price"),
    limit: int = Query(50, ge=1, le=500),
    db: Database = Depends(get_db),
):
    """Return pricing data for a specific drug."""
    conditions = ["dp.drug_id = %s::uuid"]
    params: list = [drug_id]

    if country:
        conditions.append("dp.country = %s")
        params.append(country)
    if price_type:
        conditions.append("dp.price_type = %s")
        params.append(price_type)

    where = f"WHERE {' AND '.join(conditions)}"

    if latest_only:
        params.append(1)
    else:
        params.append(limit)

    rows = db.fetch_all(
        f"""
        SELECT
            dp.id, dp.drug_id, dp.drug_name, dp.ndc_code,
            dp.price_type, dp.unit_price, dp.unit,
            dp.currency, dp.country, dp.source_api,
            dp.source_url, dp.effective_date, dp.retrieved_at
        FROM drug_pricing dp
        {where}
        ORDER BY dp.effective_date DESC NULLS LAST
        LIMIT %s
        """,
        params,
    )

    return {"drug_id": drug_id, "results": rows, "count": len(rows)}
