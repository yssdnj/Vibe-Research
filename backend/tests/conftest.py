import pytest


@pytest.fixture(autouse=True)
def isolated_local_app(monkeypatch, tmp_path):
    """Keep tests independent of a developer's real .env and private data."""
    import app as app_module

    monkeypatch.setattr(app_module, "_LOGIN_USERS", {})
    monkeypatch.setattr(app_module, "_API_KEY", "")
    monkeypatch.setenv("VR_DATA_DIR", str(tmp_path / "user-data"))
