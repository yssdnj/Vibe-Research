"""Small atomic JSON repositories keyed by resolved private file path."""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path

_LOCKS: dict[str, threading.Lock] = {}
_GUARD = threading.Lock()


def _lock(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


def load(path: Path, default):
    with _lock(path):
        try:
            return json.loads(path.read_text("utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return default


def save(path: Path, value) -> None:
    with _lock(path):
        _save_unlocked(path, value)


def _save_unlocked(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), "utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def mutate(path: Path, default, callback):
    with _lock(path):
        try:
            value = json.loads(path.read_text("utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            value = default
        result, next_value = callback(value)
        _save_unlocked(path, next_value)
        return result
