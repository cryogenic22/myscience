"""BE-13 — /agent-authority endpoints tests."""

from __future__ import annotations

import pytest


class TestAuthorityRoutes:
    def test_routes_registered(self):
        from api.app import create_app
        app = create_app()
        paths = {r.path for r in app.routes}
        assert "/agent-authority" in paths
        assert "/agent-authority/promotions" in paths
        assert "/agent-authority/{agent}/{scenario_type}" in paths
        # Versioned aliases also mounted
        assert "/api/v1/agent-authority" in paths
