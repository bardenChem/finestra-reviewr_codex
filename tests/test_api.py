from __future__ import annotations

from scireview.api.app import create_app


def test_health_endpoint_is_registered() -> None:
    app = create_app()
    route = next(route for route in app.routes if getattr(route, "path", None) == "/health")

    assert route.endpoint() == {"status": "ok"}
