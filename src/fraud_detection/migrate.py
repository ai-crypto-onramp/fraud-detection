"""Apply SQL migrations against the configured PostgreSQL instance.

Usage::

    python -m fraud_detection.migrate

Reads ``DB_URL`` from the environment (via :mod:`fraud_detection.config`) and
applies every ``migrations/*.sql`` file in lexical order inside a single
transaction. The migrations directory is shipped with the package source so
the path resolves whether the service is run from the repo root or an
installed wheel.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from fraud_detection.config import settings


def migration_dir() -> Path:
    """Return the on-disk ``migrations/`` directory.

    Resolves to ``<repo>/migrations`` when running from a source checkout
    and falls back to a sibling of the installed package for wheel installs.
    """

    here = Path(__file__).resolve().parent
    repo_migrations = here.parent.parent.parent / "migrations"
    if repo_migrations.is_dir():
        return repo_migrations
    return here.parent.parent / "migrations"


def ordered_sql_files(directory: Path) -> Iterable[Path]:
    return sorted(directory.glob("*.sql"))


def apply_migrations(db_url: str | None = None) -> list[str]:
    """Apply all migrations and return the list of applied file names.

    Raises if ``DB_URL`` is not configured or if a migration fails.
    """

    url = db_url or settings.db_url
    if not url:
        raise RuntimeError("DB_URL is not configured")

    try:
        import psycopg  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised in integration envs
        raise RuntimeError("psycopg is required to run migrations") from exc

    directory = migration_dir()
    files = list(ordered_sql_files(directory))
    if not files:
        return []

    applied: list[str] = []
    with psycopg.connect(url) as conn:  # type: ignore[attr-defined]
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
            for path in files:
                cur.execute(
                    "SELECT 1 FROM schema_migrations WHERE filename = %s",
                    (path.name,),
                )
                if cur.fetchone():
                    continue
                cur.execute(path.read_text())
                cur.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (%s)",
                    (path.name,),
                )
                applied.append(path.name)
        conn.commit()
    return applied


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI shim
    applied = apply_migrations()
    if applied:
        print(f"Applied {len(applied)} migration(s): {', '.join(applied)}")
    else:
        print("No new migrations to apply")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())