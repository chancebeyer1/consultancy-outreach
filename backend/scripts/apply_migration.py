"""Apply a single SQL migration file against DATABASE_URL (reads .env).

Migrations use `create table if not exists` / `add column if not exists`, so re-applying
is safe/idempotent.

    cd backend
    uv run python -m scripts.apply_migration db/migrations/0031_comment_queue.sql
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg

from config import BACKEND_DIR, require

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python -m scripts.apply_migration <path-to .sql>")
        raise SystemExit(2)
    path = Path(sys.argv[1])
    if not path.is_absolute():
        path = BACKEND_DIR / sys.argv[1]
    if not path.exists():
        print(f"not found: {path}")
        raise SystemExit(2)
    sql = path.read_text(encoding="utf-8")
    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()
    print(f"[ok] applied {path.name}")


if __name__ == "__main__":
    main()
