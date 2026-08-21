from pathlib import Path
import re

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app as app_module
import user_storage


def test_user_directories_are_distinct_and_cannot_escape_root(monkeypatch, tmp_path):
    monkeypatch.setenv("VR_DATA_DIR", str(tmp_path))

    alice = user_storage.user_dir(user_storage.UserIdentity("alice", "user"))
    bob = user_storage.user_dir(user_storage.UserIdentity("bob", "user"))
    hostile = user_storage.user_dir(user_storage.UserIdentity("../alice", "user"))

    assert alice != bob != hostile
    assert alice.parent == tmp_path / "users"
    assert hostile.parent == tmp_path / "users"
    assert re.fullmatch(r"[0-9a-f]{16}", hostile.name)
    assert "alice" not in hostile.name


def test_private_identity_rejects_request_without_session_identity():
    class State:
        user = None

    class Request:
        state = State()

    with pytest.raises(HTTPException) as exc:
        user_storage.private_identity(Request())
    assert exc.value.status_code == 401


def test_api_key_alone_cannot_read_private_portfolio(monkeypatch):
    monkeypatch.setattr(app_module, "_LOGIN_USERS", {"alice": {"password": "x", "role": "user"}})
    monkeypatch.setattr(app_module, "_API_KEY", "api-secret")
    client = TestClient(app_module.app)

    response = client.get("/api/portfolio", headers={"Authorization": "Bearer api-secret"})

    assert response.status_code == 401
