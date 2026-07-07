import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

API_DIR = Path(__file__).resolve().parent.parent / "api"


def load_api_module(relative_path: str, modname: str):
    path = API_DIR / relative_path
    spec = importlib.util.spec_from_file_location(modname, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    return module


from webauth import check_admin_password, is_allowed_photo_host  # noqa: E402


class TestCheckAdminPassword:
    def test_correct_password(self, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
        assert check_admin_password("hunter2") is True

    def test_wrong_password(self, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
        assert check_admin_password("wrong") is False

    def test_missing_provided(self, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
        assert check_admin_password(None) is False

    def test_admin_password_not_configured(self, monkeypatch):
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        assert check_admin_password("anything") is False


class TestIsAllowedPhotoHost:
    @pytest.mark.parametrize("hostname", [
        "en.wikipedia.org",
        "upload.wikimedia.org",
        "www.inaturalist.org",
        "inaturalist-open-data.s3.amazonaws.com",
        "www.birds.cornell.edu",
        "macaulaylibrary.org",
    ])
    def test_allowed_hosts(self, hostname):
        assert is_allowed_photo_host(hostname) is True

    @pytest.mark.parametrize("hostname", ["evil.com", "wikipedia.org.evil.com", "", None])
    def test_disallowed_hosts(self, hostname):
        assert is_allowed_photo_host(hostname) is False


@pytest.fixture(scope="module")
def login_module():
    return load_api_module("login.py", "site_api_login")


class TestLoginEndpoint:
    def test_correct_password(self, login_module, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
        client = login_module.app.test_client()
        resp = client.post("/api/login", json={"password": "hunter2"})
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True}

    def test_wrong_password(self, login_module, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
        client = login_module.app.test_client()
        resp = client.post("/api/login", json={"password": "nope"})
        assert resp.status_code == 401
        assert resp.get_json() == {"ok": False}

    def test_no_body(self, login_module, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
        client = login_module.app.test_client()
        resp = client.post("/api/login")
        assert resp.status_code == 401


@pytest.fixture(scope="module")
def photo_proxy_module():
    return load_api_module("photo-proxy.py", "site_api_photo_proxy")


class TestPhotoProxy:
    def test_missing_src(self, photo_proxy_module):
        client = photo_proxy_module.app.test_client()
        resp = client.get("/api/photo-proxy")
        assert resp.status_code == 400

    def test_disallowed_host(self, photo_proxy_module):
        client = photo_proxy_module.app.test_client()
        resp = client.get("/api/photo-proxy?src=https://evil.com/x.jpg")
        assert resp.status_code == 400

    def test_allowed_host_success(self, photo_proxy_module, monkeypatch):
        fake_resp = MagicMock()
        fake_resp.raise_for_status = MagicMock()
        fake_resp.content = b"fake-bytes"
        fake_resp.headers = {"content-type": "image/png"}
        monkeypatch.setattr(photo_proxy_module.requests, "get", MagicMock(return_value=fake_resp))
        client = photo_proxy_module.app.test_client()
        resp = client.get("/api/photo-proxy?src=https://en.wikipedia.org/x.jpg")
        assert resp.status_code == 200
        assert resp.data == b"fake-bytes"
        assert resp.headers["Content-Type"] == "image/png"

    def test_upstream_failure(self, photo_proxy_module, monkeypatch):
        real_requests = photo_proxy_module.requests

        def raise_err(*a, **kw):
            raise real_requests.RequestException("boom")

        monkeypatch.setattr(photo_proxy_module.requests, "get", raise_err)
        client = photo_proxy_module.app.test_client()
        resp = client.get("/api/photo-proxy?src=https://en.wikipedia.org/x.jpg")
        assert resp.status_code == 502


@pytest.fixture(scope="module")
def post_module():
    return load_api_module("post.py", "site_api_post")


class TestPostEndpoint:
    def test_unauthorized(self, post_module, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
        client = post_module.app.test_client()
        resp = client.post("/api/post", json={}, headers={"X-Admin-Password": "wrong"})
        assert resp.status_code == 401

    def test_no_tiktok_session(self, post_module, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
        client = post_module.app.test_client()
        resp = client.post(
            "/api/post",
            json={"photo_url": "x", "caption": "y"},
            headers={"X-Admin-Password": "hunter2"},
        )
        assert resp.status_code == 401
        assert "Connect" in resp.get_json()["error"]

    def test_missing_fields(self, post_module, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
        client = post_module.app.test_client()
        client.set_cookie("tt_access_token", "faketoken")
        resp = client.post("/api/post", json={}, headers={"X-Admin-Password": "hunter2"})
        assert resp.status_code == 400

    def test_success(self, post_module, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
        fake_resp = MagicMock()
        fake_resp.json.return_value = {"data": {"publish_id": "pub123"}, "error": {"code": "ok"}}
        monkeypatch.setattr(post_module.requests, "post", MagicMock(return_value=fake_resp))
        client = post_module.app.test_client()
        client.set_cookie("tt_access_token", "faketoken")
        resp = client.post(
            "/api/post",
            json={"photo_url": "https://en.wikipedia.org/x.jpg", "caption": "Hello"},
            headers={"X-Admin-Password": "hunter2"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "sent_to_tiktok"
        assert body["publish_id"] == "pub123"

    def test_tiktok_api_error(self, post_module, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
        fake_resp = MagicMock()
        fake_resp.json.return_value = {"error": {"code": "invalid_param", "message": "bad"}}
        monkeypatch.setattr(post_module.requests, "post", MagicMock(return_value=fake_resp))
        client = post_module.app.test_client()
        client.set_cookie("tt_access_token", "faketoken")
        resp = client.post(
            "/api/post",
            json={"photo_url": "https://en.wikipedia.org/x.jpg", "caption": "Hello"},
            headers={"X-Admin-Password": "hunter2"},
        )
        assert resp.status_code == 502


@pytest.fixture(scope="module")
def generate_module():
    return load_api_module("generate.py", "site_api_generate")


class TestGenerateEndpoint:
    def test_unauthorized(self, generate_module, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
        client = generate_module.app.test_client()
        resp = client.post(
            "/api/generate",
            json={"species": "Robin", "category": "bird"},
            headers={"X-Admin-Password": "wrong"},
        )
        assert resp.status_code == 401

    def test_missing_species(self, generate_module, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
        client = generate_module.app.test_client()
        resp = client.post(
            "/api/generate", json={"category": "bird"}, headers={"X-Admin-Password": "hunter2"}
        )
        assert resp.status_code == 400

    def test_invalid_category(self, generate_module, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
        client = generate_module.app.test_client()
        resp = client.post(
            "/api/generate",
            json={"species": "Robin", "category": "fish"},
            headers={"X-Admin-Password": "hunter2"},
        )
        assert resp.status_code == 400

    def test_research_not_found(self, generate_module, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
        monkeypatch.setattr(generate_module.research_mod, "research", MagicMock(return_value=None))
        client = generate_module.app.test_client()
        resp = client.post(
            "/api/generate",
            json={"species": "Not A Species", "category": "bird"},
            headers={"X-Admin-Password": "hunter2"},
        )
        assert resp.status_code == 422

    def test_no_photo_found(self, generate_module, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
        fake_result = MagicMock(
            common_name="Robin",
            scientific_name="Turdus migratorius",
            category="bird",
            wikipedia_url="https://en.wikipedia.org/wiki/Robin",
            conservation_status="Least Concern",
        )
        monkeypatch.setattr(generate_module.research_mod, "research", MagicMock(return_value=fake_result))
        fake_selection = MagicMock(photo=None, approved=False)
        monkeypatch.setattr(
            generate_module.image_reviewer, "select_best_photo", MagicMock(return_value=fake_selection)
        )
        client = generate_module.app.test_client()
        resp = client.post(
            "/api/generate",
            json={"species": "Robin", "category": "bird"},
            headers={"X-Admin-Password": "hunter2"},
        )
        assert resp.status_code == 422

    def test_success(self, generate_module, monkeypatch):
        monkeypatch.setenv("ADMIN_PASSWORD", "hunter2")
        fake_result = MagicMock(
            common_name="Robin",
            scientific_name="Turdus migratorius",
            category="bird",
            wikipedia_url="https://en.wikipedia.org/wiki/Robin",
            conservation_status="Least Concern",
        )
        monkeypatch.setattr(generate_module.research_mod, "research", MagicMock(return_value=fake_result))

        fake_photo = MagicMock(
            url="https://en.wikipedia.org/x.jpg", source="wikipedia", attribution="CC BY-SA"
        )
        fake_selection = MagicMock(photo=fake_photo, approved=True)
        monkeypatch.setattr(
            generate_module.image_reviewer, "select_best_photo", MagicMock(return_value=fake_selection)
        )

        fake_content = MagicMock(
            instagram_caption="caption ig", tiktok_caption="caption tt", alt_text="alt text"
        )
        monkeypatch.setattr(
            generate_module.content_generator, "generate_content", MagicMock(return_value=fake_content)
        )

        client = generate_module.app.test_client()
        resp = client.post(
            "/api/generate",
            json={"species": "Robin", "category": "bird"},
            headers={"X-Admin-Password": "hunter2"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["common_name"] == "Robin"
        assert body["photo"]["url"] == "https://en.wikipedia.org/x.jpg"
        assert body["photo"]["reviewer_approved"] is True
        assert body["instagram_caption"] == "caption ig"


@pytest.fixture(scope="module")
def tiktok_login_module():
    return load_api_module("auth/tiktok/login.py", "site_api_tiktok_login")


class TestTikTokLogin:
    def test_missing_client_key(self, tiktok_login_module, monkeypatch):
        monkeypatch.delenv("TIKTOK_CLIENT_KEY", raising=False)
        client = tiktok_login_module.app.test_client()
        resp = client.get("/api/auth/tiktok/login")
        assert resp.status_code == 500

    def test_redirects_with_pkce_cookies(self, tiktok_login_module, monkeypatch):
        monkeypatch.setenv("TIKTOK_CLIENT_KEY", "ck123")
        client = tiktok_login_module.app.test_client()
        resp = client.get("/api/auth/tiktok/login")
        assert resp.status_code == 302
        assert "client_key=ck123" in resp.headers["Location"]
        cookies = resp.headers.getlist("Set-Cookie")
        assert any("tt_state=" in c for c in cookies)
        assert any("tt_verifier=" in c for c in cookies)


@pytest.fixture(scope="module")
def tiktok_callback_module():
    return load_api_module("auth/tiktok/callback.py", "site_api_tiktok_callback")


class TestTikTokCallback:
    def test_error_param(self, tiktok_callback_module):
        client = tiktok_callback_module.app.test_client()
        resp = client.get("/api/auth/tiktok/callback?error=access_denied")
        assert resp.status_code == 302
        assert "tiktok_error=access_denied" in resp.headers["Location"]

    def test_state_mismatch(self, tiktok_callback_module):
        client = tiktok_callback_module.app.test_client()
        client.set_cookie("tt_state", "expected", path="/api/auth/tiktok")
        client.set_cookie("tt_verifier", "verifier", path="/api/auth/tiktok")
        resp = client.get("/api/auth/tiktok/callback?state=wrong&code=abc")
        assert resp.status_code == 302
        assert "state_mismatch" in resp.headers["Location"]

    def test_token_exchange_failure(self, tiktok_callback_module, monkeypatch):
        real_requests = tiktok_callback_module.requests

        def raise_err(*a, **kw):
            raise real_requests.RequestException("boom")

        monkeypatch.setattr(tiktok_callback_module.requests, "post", raise_err)
        client = tiktok_callback_module.app.test_client()
        client.set_cookie("tt_state", "s1", path="/api/auth/tiktok")
        resp = client.get("/api/auth/tiktok/callback?state=s1&code=abc")
        assert resp.status_code == 302
        assert "token_exchange_failed" in resp.headers["Location"]

    def test_no_access_token(self, tiktok_callback_module, monkeypatch):
        fake_resp = MagicMock()
        fake_resp.json.return_value = {}
        monkeypatch.setattr(tiktok_callback_module.requests, "post", MagicMock(return_value=fake_resp))
        client = tiktok_callback_module.app.test_client()
        client.set_cookie("tt_state", "s1", path="/api/auth/tiktok")
        resp = client.get("/api/auth/tiktok/callback?state=s1&code=abc")
        assert resp.status_code == 302
        assert "no_access_token" in resp.headers["Location"]

    def test_success(self, tiktok_callback_module, monkeypatch):
        fake_resp = MagicMock()
        fake_resp.json.return_value = {"access_token": "tok123", "expires_in": 3600}
        monkeypatch.setattr(tiktok_callback_module.requests, "post", MagicMock(return_value=fake_resp))
        client = tiktok_callback_module.app.test_client()
        client.set_cookie("tt_state", "s1", path="/api/auth/tiktok")
        resp = client.get("/api/auth/tiktok/callback?state=s1&code=abc")
        assert resp.status_code == 302
        assert "tiktok_connected=1" in resp.headers["Location"]
