"""The built web client served on the API's origin (app/web.py, docs/DEPLOYMENT.md §6)."""

import pytest
from pydantic import ValidationError
from starlette.responses import FileResponse

from app.core.config import Settings, get_settings
from app.web import web_response

STRONG_SECRET = "s" * 40
INDEX = "<!doctype html><title>LEARNABLE</title>"


@pytest.fixture
def dist(tmp_path, monkeypatch):
    """A fake web build, with a secret file next to it that must never be served."""
    build = tmp_path / "dist"
    (build / "assets").mkdir(parents=True)
    (build / "index.html").write_text(INDEX)
    (build / "assets" / "app-3f9a.js").write_text("console.log('app')")
    (build / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("not for the web")
    monkeypatch.setenv("WEB_DIST_DIR", str(build))
    get_settings.cache_clear()
    yield build
    get_settings.cache_clear()


def test_the_page_and_client_side_routes_get_index_html(client, dist):
    for path in ("/", "/courses/abc/chapters/def", "/reset-password?token=xyz"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.text == INDEX
        assert response.headers["content-type"].startswith("text/html")
        assert response.headers["cache-control"] == "no-cache"


def test_files_are_served_with_the_right_caching(client, dist):
    asset = client.get("/assets/app-3f9a.js")
    assert asset.status_code == 200
    assert asset.text == "console.log('app')"
    assert "immutable" in asset.headers["cache-control"]
    assert asset.headers["x-content-type-options"] == "nosniff"
    assert client.get("/favicon.svg").headers["cache-control"] == "no-cache"
    # A fingerprinted asset that isn't there (an old build's file) is a 404, not the page.
    assert client.get("/assets/app-old.js").status_code == 404


def test_nothing_outside_the_build_is_reachable(client, dist):
    response = client.get("/%2E%2E/secret.txt")
    assert "not for the web" not in response.text
    # Directly too, since an HTTP client may normalize ".." before it reaches the server.
    # Either the page (client-side route) or a 404 (under assets/), never the file.
    assert web_response(dist, "/../secret.txt").path == dist.resolve() / "index.html"  # type: ignore[attr-defined]
    outside_assets = web_response(dist, "/assets/../../secret.txt")
    assert not isinstance(outside_assets, FileResponse)
    assert outside_assets.status_code == 404


def test_the_api_keeps_its_own_answers(client, dist):
    assert client.get("/health").json() == {"status": "ok"}
    unknown = client.get("/api/v1/no-such-endpoint")
    assert unknown.status_code == 404
    assert unknown.json()["error_type"] == "not_found"
    # A known path with the wrong method is still a 405, not the web page.
    assert client.get("/api/v1/auth/login").status_code == 405
    # Other methods on page URLs aren't served the page.
    assert client.post("/courses/abc").status_code == 404


def test_without_a_build_nothing_changes(client):
    get_settings.cache_clear()
    response = client.get("/courses/abc")
    assert response.status_code == 404
    assert response.json()["error_type"] == "not_found"


def test_a_build_directory_without_index_html_is_a_config_error(tmp_path):
    with pytest.raises(ValidationError, match=r"has no index\.html"):
        Settings(_env_file=None, auth_secret=STRONG_SECRET, web_dist_dir=tmp_path)


def test_links_in_emails_default_to_the_render_address(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://learnable.onrender.com")
    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)
    assert (
        Settings(_env_file=None, auth_secret=STRONG_SECRET).public_app_url
        == "https://learnable.onrender.com"
    )
    # An explicit PUBLIC_APP_URL (e.g. a custom domain) wins.
    monkeypatch.setenv("PUBLIC_APP_URL", "https://learnable.example.com")
    assert (
        Settings(_env_file=None, auth_secret=STRONG_SECRET).public_app_url
        == "https://learnable.example.com"
    )
