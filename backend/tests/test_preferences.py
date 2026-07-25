from main import create_app


def test_user_preferences_and_memory_routes_are_registered() -> None:
    app = create_app()
    routes = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }

    assert ("GET", "/api/user/preferences") in routes
    assert ("PATCH", "/api/user/preferences") in routes
    assert ("GET", "/api/auth/me") in routes
    assert ("PATCH", "/api/auth/me") in routes
    assert ("GET", "/api/memories") in routes
    assert ("DELETE", "/api/memories") in routes
    assert ("DELETE", "/api/memories/{memory_id}") in routes
    assert ("GET", "/api/memories/clear-status") in routes
    assert ("GET", "/api/memories/generation-status") in routes
    assert ("POST", "/api/memories/retry-failed") in routes
