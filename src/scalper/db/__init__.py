"""Database layer for the multi-tenant service: libsql connection + migrations.

The original CLI store (`scalper.store`) talks to a local SQLite file. The
service talks to a self-hosted libsql (`sqld`) instance via the libsql client,
but keeps the same raw-SQL, DB-API style. This package owns the connection
factory and the numbered-`.sql` migration runner. See ADR 0008 and
`docs/deployment/sqld-dokploy.md`.
"""

from __future__ import annotations

from scalper.db.connection import connect
from scalper.db.migrate import apply_pending, pending_migrations

__all__ = ["connect", "apply_pending", "pending_migrations"]
