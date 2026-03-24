"""Backward-compatibility shim — query telemetry merged into services/telemetry.py.

All functions now live in services.telemetry. This module re-exports them
so existing imports (including tests) continue to work without changes.
"""

from services.telemetry import detect_query_gap, log_query_event  # noqa: F401

__all__ = ["detect_query_gap", "log_query_event"]
