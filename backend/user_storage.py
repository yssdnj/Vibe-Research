"""Safe per-user storage paths derived only from verified server identity."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, Request

_IDENTITY_LOCK = threading.Lock()


@dataclass(frozen=True)
class UserIdentity:
    username: str
    role: str = "user"


def data_root() -> Path:
    return Path(os.environ.get("VR_DATA_DIR") or Path.home() / ".vibe-research")


def user_key(username: str) -> str:
    return hashlib.sha256(username.encode("utf-8")).hexdigest()[:16]


def user_dir(identity: UserIdentity) -> Path:
    path = data_root() / "users" / user_key(identity.username)
    with _IDENTITY_LOCK:
        path.mkdir(parents=True, exist_ok=True)
        identity_file = path / "identity.json"
        created_at = datetime.now(timezone.utc).isoformat()
        if identity_file.exists():
            try:
                created_at = json.loads(identity_file.read_text(encoding="utf-8")).get("createdAt") or created_at
            except (OSError, ValueError, TypeError):
                pass
        payload = {"username": identity.username, "role": identity.role, "createdAt": created_at}
        fd, tmp_name = tempfile.mkstemp(prefix=".identity-", suffix=".tmp", dir=path)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            os.replace(tmp_name, identity_file)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
    return path


def identity_from_request(request: Request) -> UserIdentity | None:
    value = getattr(request.state, "user", None)
    if isinstance(value, UserIdentity):
        return value
    if isinstance(value, dict) and value.get("username"):
        return UserIdentity(str(value["username"]), str(value.get("role") or "user"))
    return None


def private_identity(request: Request) -> UserIdentity:
    identity = identity_from_request(request)
    if not identity:
        raise HTTPException(401, "请先登录后再访问个人数据")
    return identity

