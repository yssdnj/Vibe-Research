import base64

from fastapi.testclient import TestClient

import app as app_module
import portfolio as pf


def _clients(monkeypatch, tmp_path):
    monkeypatch.setenv("VR_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        app_module,
        "_LOGIN_USERS",
        {
            "alice": {"password": "alice-pass", "role": "admin"},
            "bob": {"password": "bob-pass", "role": "user"},
        },
    )
    monkeypatch.setattr(app_module, "_LOGIN_SECRET", "test-secret")
    monkeypatch.setattr(app_module, "_API_KEY", "")
    alice = TestClient(app_module.app)
    bob = TestClient(app_module.app)
    assert alice.post("/api/auth/login", json={
        "username": "alice", "password": "alice-pass", "remember": False,
    }).status_code == 200
    assert bob.post("/api/auth/login", json={
        "username": "bob", "password": "bob-pass", "remember": False,
    }).status_code == 200
    return alice, bob


def test_portfolio_is_isolated_by_authenticated_user(monkeypatch, tmp_path):
    alice, bob = _clients(monkeypatch, tmp_path)
    monkeypatch.setattr(app_module.pf.astock, "tencent_quote", lambda codes: {
        code: {"name": code, "price": 10.0} for code in codes
    })

    added = alice.post("/api/portfolio/holding", json={
        "code": "600519", "shares": 10, "cost": 8,
    })

    assert added.status_code == 200
    assert [item["code"] for item in added.json()["data"]["holdings"]] == ["600519"]
    assert bob.get("/api/portfolio").json()["data"]["holdings"] == []


def test_reports_are_isolated_and_ids_do_not_cross_users(monkeypatch, tmp_path):
    alice, bob = _clients(monkeypatch, tmp_path)
    uploaded = alice.post("/api/myreports", json={
        "name": "alice-private.pdf",
        "content_b64": base64.b64encode(b"%PDF-1.4 private").decode("ascii"),
    })

    assert uploaded.status_code == 200
    report_id = uploaded.json()["data"]["id"]
    assert len(alice.get("/api/myreports").json()["data"]) == 1
    assert bob.get("/api/myreports").json()["data"] == []
    assert bob.get(f"/api/myreports/file/{report_id}").status_code == 404
    assert bob.delete(f"/api/myreports/{report_id}").json() == {"data": {"ok": False}}
    assert alice.get(f"/api/myreports/file/{report_id}").status_code == 200


def test_scheduler_enumerates_each_existing_user_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("VR_DATA_DIR", str(tmp_path))
    first = tmp_path / "users" / "aaa"
    second = tmp_path / "users" / "bbb"
    first.mkdir(parents=True)
    second.mkdir()

    assert pf._scheduled_data_dirs() == [first, second]
