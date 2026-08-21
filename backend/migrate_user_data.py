"""Explicitly migrate legacy unscoped data into one authenticated user."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

import user_storage as us


def _configured_users() -> set[str]:
    load_dotenv(Path(__file__).with_name(".env"), override=False)
    users = set()
    for entry in os.environ.get("LOGIN_USERS", "").split(","):
        parts = entry.strip().split(":")
        if len(parts) == 3 and parts[0].strip():
            users.add(parts[0].strip())
    return users


def migrate(to_user: str, *, move: bool = False, allowed_users=None, root=None) -> dict:
    allowed = set(allowed_users) if allowed_users is not None else _configured_users()
    if to_user not in allowed:
        raise ValueError(f"unknown configured user: {to_user}")

    legacy_root = Path(root) if root is not None else us.data_root()
    target = us.user_dir(us.UserIdentity(to_user))
    target_portfolio = target / "portfolio.json"
    target_reports = target / "reports"
    if target_portfolio.exists() or (target_reports.exists() and any(target_reports.rglob("*"))):
        raise ValueError("target user storage is already populated")

    sources: list[tuple[Path, Path]] = []
    legacy_portfolio = legacy_root / "portfolio.json"
    if legacy_portfolio.is_file():
        sources.append((legacy_portfolio, target_portfolio))

    legacy_reports = legacy_root / "myreports"
    if legacy_reports.is_dir():
        index = legacy_reports / "index.json"
        if index.is_file():
            sources.append((index, target_reports / "index.json"))
        for source in legacy_reports.iterdir():
            if source.is_file() and source.name != "index.json":
                sources.append((source, target_reports / "files" / source.name))

    for source, destination in sources:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if move:
            shutil.move(str(source), str(destination))
        else:
            shutil.copy2(source, destination)
    if move and legacy_reports.exists():
        try:
            legacy_reports.rmdir()
        except OSError:
            pass
    return {"user": to_user, "files": len(sources), "mode": "move" if move else "copy"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy private data to one user")
    parser.add_argument("--to-user", required=True)
    parser.add_argument("--move", action="store_true", help="remove legacy files after migration")
    args = parser.parse_args()
    try:
        result = migrate(args.to_user, move=args.move)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"{result['mode']} complete: {result['files']} files -> user {result['user']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
