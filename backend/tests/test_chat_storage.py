from test_private_data_isolation import _clients


def test_chat_round_trip_clear_and_isolation(monkeypatch, tmp_path):
    alice, bob = _clients(monkeypatch, tmp_path)
    body = {"messages": [
        {"role": "user", "content": "怎么看今天市场？"},
        {"role": "assistant", "content": "先看客观数据。"},
    ]}

    saved = alice.put("/api/chats/daily-review", json=body)

    assert saved.status_code == 200
    assert saved.json()["data"]["scope"] == "daily-review"
    assert alice.get("/api/chats/daily-review").json()["data"]["messages"] == body["messages"]
    assert bob.get("/api/chats/daily-review").json()["data"]["messages"] == []
    assert alice.delete("/api/chats/daily-review").json() == {"data": {"ok": True}}
    assert alice.get("/api/chats/daily-review").json()["data"]["messages"] == []


def test_chat_rejects_bad_scope_roles_and_limits(monkeypatch, tmp_path):
    alice, _ = _clients(monkeypatch, tmp_path)
    assert alice.put("/api/chats/%20", json={"messages": []}).status_code == 400
    assert alice.put("/api/chats/x", json={
        "messages": [{"role": "system", "content": "no"}],
    }).status_code == 400
    assert alice.put("/api/chats/x", json={
        "messages": [{"role": "user", "content": "x"}] * 41,
    }).status_code == 400
    assert alice.put("/api/chats/x", json={
        "messages": [{"role": "user", "content": "x" * (512 * 1024)}],
    }).status_code == 413
