import os

from fastapi.testclient import TestClient

import app as app_module


def _configure_auth(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "_LOGIN_USERS",
        {"alice": {"password": "secret", "role": "admin"}},
        raising=False,
    )
    monkeypatch.setattr(app_module, "_LOGIN_SECRET", "test-signing-secret", raising=False)
    monkeypatch.setattr(app_module, "_API_KEY", "", raising=False)


def test_login_sets_cookie_and_unlocks_protected_api(monkeypatch):
    _configure_auth(monkeypatch)
    client = TestClient(app_module.app)

    assert client.get("/api/auth/status").json() == {
        "enabled": True,
        "authenticated": False,
        "user": None,
    }
    assert client.get("/api/indices").status_code == 401

    response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "secret", "remember": True},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "user": {"username": "alice", "role": "admin"}}
    assert "vr_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Max-Age=2592000" in response.headers["set-cookie"]
    assert client.get("/api/indices").status_code != 401


def test_login_rejects_bad_credentials_without_revealing_account(monkeypatch):
    _configure_auth(monkeypatch)
    client = TestClient(app_module.app)

    response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong", "remember": False},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "账号或密码错误"}
    assert "vr_session=" not in response.headers.get("set-cookie", "")


def test_logout_clears_cookie_and_locks_api_again(monkeypatch):
    _configure_auth(monkeypatch)
    client = TestClient(app_module.app)
    client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "secret", "remember": False},
    )

    response = client.post("/api/auth/logout")

    assert response.status_code == 200
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert client.get("/api/indices").status_code == 401


def test_auth_is_optional_when_no_users_are_configured(monkeypatch):
    monkeypatch.setattr(app_module, "_LOGIN_USERS", {}, raising=False)
    monkeypatch.setattr(app_module, "_API_KEY", "", raising=False)
    client = TestClient(app_module.app)

    assert client.get("/api/auth/status").json() == {
        "enabled": False,
        "authenticated": True,
        "user": None,
    }
    assert client.get("/api/indices").status_code != 401


def test_bearer_key_remains_valid_for_api_clients(monkeypatch):
    _configure_auth(monkeypatch)
    monkeypatch.setattr(app_module, "_API_KEY", "api-secret", raising=False)
    client = TestClient(app_module.app)

    response = client.get("/api/indices", headers={"Authorization": "Bearer api-secret"})

    assert response.status_code != 401

