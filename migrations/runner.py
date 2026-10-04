"""Fail-closed, transactional migration runner used by the Argo PreSync hook."""
from __future__ import annotations
import argparse, json, logging, os
from pathlib import Path
from typing import Any
from platform_api.observability import traced
logger = logging.getLogger("control_plane.migrations")
ROOT = Path(__file__).parent

def _log(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, sort_keys=True))

@traced
def run(dsn: str, directory: Path = ROOT) -> int:
    if not dsn.strip(): raise RuntimeError("DATABASE_URL is required")
    import psycopg
    migrations = sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(hashtextextended('voice-command:migrations', 0))")
            try:
                cur.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
                cur.execute("SELECT version FROM schema_migrations")
                applied = {row[0] for row in cur.fetchall()}
                conn.commit()
                for path in migrations:
                    version = path.stem
                    if version in applied: continue
                    _log("migration.start", version=version)
                    with conn.transaction():
                        with conn.cursor() as migration_cur:
                            migration_cur.execute(path.read_text(encoding="utf-8"))
                            migration_cur.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (version,))
                    _log("migration.end", version=version)
            finally:
                cur.execute("SELECT pg_advisory_unlock(hashtextextended('voice-command:migrations', 0))")
    return 0

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--fail", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    try: return run(args.dsn)
    except Exception as exc:
        _log("migration.error", error_type=type(exc).__name__)
        return 1

if __name__ == "__main__": raise SystemExit(main())
