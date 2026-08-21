from fastapi.testclient import TestClient

import app as app_module
from test_private_data_isolation import _clients


def test_watchlist_normalizes_deduplicates_and_isolates(monkeypatch, tmp_path):
    alice, bob = _clients(monkeypatch, tmp_path)

    response = alice.put("/api/watchlist", json={
        "codes": [" 600519 ", "600519", "000001"],
    })

    assert response.status_code == 200
    assert response.json()["data"] == ["600519", "000001"]
    assert alice.get("/api/watchlist").json()["data"] == ["600519", "000001"]
    assert bob.get("/api/watchlist").json()["data"] == []


def test_watchlist_rejects_invalid_or_too_many_codes(monkeypatch, tmp_path):
    alice, _ = _clients(monkeypatch, tmp_path)
    assert alice.put("/api/watchlist", json={"codes": ["abc"]}).status_code == 400
    codes = [f"{i:06d}" for i in range(201)]
    assert alice.put("/api/watchlist", json={"codes": codes}).status_code == 400


def test_notes_crud_and_user_isolation(monkeypatch, tmp_path):
    alice, bob = _clients(monkeypatch, tmp_path)

    created = alice.post("/api/notes", json={
        "kind": "复盘", "title": "今日复盘", "content": "只属于 Alice",
    })

    assert created.status_code == 200
    note = created.json()["data"]
    assert note["id"] and note["title"] == "今日复盘"
    assert [item["id"] for item in alice.get("/api/notes").json()["data"]] == [note["id"]]
    assert bob.get("/api/notes").json()["data"] == []
    assert bob.delete(f"/api/notes/{note['id']}").status_code == 404
    assert alice.delete(f"/api/notes/{note['id']}").json() == {"data": {"ok": True}}


def test_note_fields_are_bounded(monkeypatch, tmp_path):
    alice, _ = _clients(monkeypatch, tmp_path)
    assert alice.post("/api/notes", json={
        "kind": "复盘", "title": "x" * 201, "content": "body",
    }).status_code == 400
    assert alice.post("/api/notes", json={
        "kind": "复盘", "title": "ok", "content": "x" * 100_001,
    }).status_code == 400
