"""BE-11 — /war-rooms/{id}/cockpit-stream SSE tests."""

from __future__ import annotations

import pytest


class TestCockpitStreamRouteRegistration:
    def test_route_mounted(self):
        from api.app import create_app
        app = create_app()
        paths = {r.path for r in app.routes}
        assert "/war-rooms/{room_id}/cockpit-stream" in paths
        # Versioned alias also mounted
        assert "/api/v1/war-rooms/{room_id}/cockpit-stream" in paths

    def test_constants_are_safe(self):
        from api.routes.war_room import (
            _COCKPIT_HEARTBEAT_S, _COCKPIT_POLL_S, _COCKPIT_MAX_DURATION_S,
        )
        assert 1 <= _COCKPIT_POLL_S <= 30
        assert 5 <= _COCKPIT_HEARTBEAT_S <= 60
        assert _COCKPIT_MAX_DURATION_S <= 3600
