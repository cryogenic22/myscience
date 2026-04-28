"""SEC 8-K item-code parsers.

Each Item is parsed independently because they have different shapes:

  Item 1.01 — Material Definitive Agreement → deal_announced events  (A2.2)
  Item 2.02 — Results of Operations         → financial_disclosure +
                                                guidance_change events (A2.3)
  Item 5.02 — Departure/Election of Officers → exec_change events    (A2.1)
  Item 8.01 — Other Events                  → CRL detection          (A2.4)

Common pattern: rule-based header detection (no LLM) → narrative block
extraction → LLM-locked structured extraction → event-row build with
deterministic event_hash for idempotency.

The parsers expose Protocol-typed functions so unit tests can inject
stub extractors. Real LLM wiring lives in services/extraction_llm.py.
"""
