"""LLM extraction schemas + protocols.

Each extraction target (exec_change, deal_announced, guidance_change,
crl_event, label_change, etc.) lives in its own module here. Schema is
Pydantic v2; the parser modules in connectors/sec_8k/ etc. consume an
Extractor Protocol that returns these schemas.

Real LLM wiring lives in services/extraction_llm.py (a thin wrapper over
services/llm.py that uses Anthropic tool-use for structured output). Tests
inject stub extractors so the parser logic is unit-testable without
network calls.
"""
