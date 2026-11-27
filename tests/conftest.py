"""Most API tests exercise traffic features, not login: they run as a signed-in admin
by overriding the auth guard. Tests marked `auth` use the real login flow."""
import pytest


@pytest.fixture(autouse=True)
def _signed_in(request):
    if request.node.get_closest_marker("auth"):
        yield
        return
    try:
        from backend.app.api.auth import require_user
        from backend.app.main import app
    except Exception:  # tests that never import the web app
        yield
        return
    app.dependency_overrides[require_user] = lambda: None
    yield
    app.dependency_overrides.pop(require_user, None)
