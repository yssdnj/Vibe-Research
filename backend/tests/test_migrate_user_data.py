import json

import pytest


def _legacy(root):
    (root / "portfolio.json").write_text('{"holdings": [{"code": "600519"}]}', "utf-8")
    reports = root / "myreports"
    reports.mkdir()
    (reports / "index.json").write_text(json.dumps([{"id": "r1", "ext": ".pdf"}]), "utf-8")
    (reports / "r1.pdf").write_bytes(b"pdf")


def test_migration_rejects_unknown_user(tmp_path):
    from migrate_user_data import migrate

    with pytest.raises(ValueError, match="unknown"):
        migrate("bob", allowed_users={"alice"}, root=tmp_path)


def test_migration_copies_legacy_data_by_default(tmp_path):
    from migrate_user_data import migrate
    from user_storage import UserIdentity, user_dir

    _legacy(tmp_path)
    result = migrate("alice", allowed_users={"alice"}, root=tmp_path)
    target = user_dir(UserIdentity("alice"))

    assert result["files"] == 3
    assert (tmp_path / "portfolio.json").exists()
    assert (target / "portfolio.json").exists()
    assert (target / "reports" / "files" / "r1.pdf").exists()


def test_migration_moves_only_when_explicit(tmp_path):
    from migrate_user_data import migrate

    _legacy(tmp_path)
    migrate("alice", move=True, allowed_users={"alice"}, root=tmp_path)

    assert not (tmp_path / "portfolio.json").exists()
    assert not (tmp_path / "myreports").exists()


def test_migration_refuses_to_overwrite_populated_target(tmp_path):
    from migrate_user_data import migrate
    from user_storage import UserIdentity, user_dir

    _legacy(tmp_path)
    (user_dir(UserIdentity("alice")) / "portfolio.json").write_text("{}", "utf-8")
    with pytest.raises(ValueError, match="populated"):
        migrate("alice", allowed_users={"alice"}, root=tmp_path)
