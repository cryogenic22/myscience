"""BE-27..34 — Phase 1 connector skeletons.

Each connector must:
1. Subclass BaseConnector and pass abstract-method check.
2. Return its declared SourceType.
3. fetch() returns a list (stub mode returns []).
4. health_check() returns a HealthCheckResult; failure surfaces
   as healthy=False rather than raising.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


_CONNECTOR_CLASSES = [
    ("connectors.uspto",        "USPTOConnector",      "uspto"),
    ("connectors.epo",          "EPOPatentsConnector", "epo_patents"),
    ("connectors.biorxiv",      "BioRxivConnector",    "biorxiv"),
    ("connectors.biorxiv",      "MedRxivConnector",    "medrxiv"),
    ("connectors.fda_opdp",     "FDAOPDPConnector",    "fda_opdp"),
    ("connectors.cms_partd",    "CMSPartDConnector",   "cms_partd"),
    ("connectors.cms_pricing",  "CMSPricingConnector", "cms_pricing"),
    ("connectors.who_ictrp",    "WHOICTRPConnector",   "who_ictrp"),
    ("connectors.va_dod",       "VADoDConnector",      "va_dod_formulary"),
]


@pytest.mark.parametrize("module,cls_name,source_str", _CONNECTOR_CLASSES)
def test_connector_skeleton(module, cls_name, source_str):
    import importlib
    from connectors.base import BaseConnector

    mod = importlib.import_module(module)
    cls = getattr(mod, cls_name)
    assert issubclass(cls, BaseConnector), f"{cls_name} must subclass BaseConnector"

    inst = cls()
    assert inst.source_type().value == source_str

    # fetch() returns a list (stub returns [])
    out = inst.fetch()
    assert isinstance(out, list)


@pytest.mark.parametrize("module,cls_name,source_str", _CONNECTOR_CLASSES)
def test_health_check_handles_unreachable(module, cls_name, source_str):
    """If the upstream is unreachable, health_check returns
    healthy=False instead of raising."""
    import importlib
    mod = importlib.import_module(module)
    cls = getattr(mod, cls_name)

    # Patch requests.get on the *module*, not the global, since each
    # connector imported requests at module scope.
    with patch.object(mod, "requests") as mock_requests:
        mock_requests.get.side_effect = RuntimeError("network gone")
        result = cls().health_check()
        assert result.healthy is False
        assert "unreachable" in result.message.lower() or "network" in result.message.lower()


def test_source_type_enum_carries_phase1_values():
    from connectors.base import SourceType
    expected = {"uspto", "epo_patents", "biorxiv", "medrxiv",
                "fda_opdp", "cms_partd", "cms_pricing",
                "who_ictrp", "va_dod_formulary"}
    actual = {st.value for st in SourceType}
    missing = expected - actual
    assert not missing, f"missing SourceType entries: {missing}"
