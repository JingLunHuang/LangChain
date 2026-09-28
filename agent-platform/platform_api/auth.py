"""Explicit bootstrap keys and durable hashed-key issue/list/revoke management."""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Tenant:
    tenant_id: str


def digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def load_tenant_registry() -> dict[str, Tenant]:
    registry = {}
    for entry in os.getenv("PLATFORM_API_KEYS", "").split(","):
        if not entry.strip():
            continue
        key, separator, tenant = entry.strip().partition(":")
        if not key or (separator and not tenant.strip()):
            raise ValueError("Invalid PLATFORM_API_KEYS entry")
        registry[digest(key)] = Tenant(
            tenant.strip() if separator else "tenant-" + digest(key)[:12]
        )
    return registry


class KeyStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS api_keys "
                "(id TEXT PRIMARY KEY, digest TEXT UNIQUE, tenant TEXT, label TEXT, "
                "revoked INTEGER DEFAULT 0)"
            )

    def connection(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.path))

    def issue(self, tenant: str, label: str) -> dict[str, str]:
        key_id, raw = secrets.token_hex(12), "ap_" + secrets.token_urlsafe(32)
        with self.connection() as db:
            db.execute(
                "INSERT INTO api_keys (id,digest,tenant,label) VALUES (?,?,?,?)",
                (key_id, digest(raw), tenant, label),
            )
        return {"id": key_id, "api_key": raw, "tenant_id": tenant, "label": label}

    def authenticate(self, raw: str) -> Tenant | None:
        hashed = digest(raw)
        bootstrap = load_tenant_registry().get(hashed)
        if bootstrap:
            return bootstrap
        with self.connection() as db:
            row = db.execute(
                "SELECT tenant FROM api_keys WHERE digest=? AND revoked=0", (hashed,)
            ).fetchone()
        return Tenant(row[0]) if row else None

    def list_keys(self) -> list[dict[str, str | bool]]:
        with self.connection() as db:
            rows = db.execute("SELECT id,tenant,label,revoked FROM api_keys ORDER BY id").fetchall()
        return [{"id": r[0], "tenant_id": r[1], "label": r[2], "revoked": bool(r[3])} for r in rows]

    def revoke(self, key_id: str) -> bool:
        with self.connection() as db:
            result = db.execute("UPDATE api_keys SET revoked=1 WHERE id=?", (key_id,))
        return result.rowcount > 0
