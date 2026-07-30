"""Database layer for the multi-tenant service: connection factory + migrations.

The original CLI store (`scalper.store`) talks to a local SQLite file. The
service talks to **PostgreSQL** in production (a managed Dokploy Postgres service)
and falls back to sqlite for local/CI, keeping one raw-SQL, DB-API style via a
thin dialect adapter. This package owns the connection factory and the
numbered-`.sql` migration runner. See ADR 0008/0012 and
`docs/deployment/postgres-dokploy.md`.
"""

from __future__ import annotations

from scalper.db.connection import connect
from scalper.db.migrate import apply_pending, pending_migrations

__all__ = ["connect", "apply_pending", "pending_migrations"]
