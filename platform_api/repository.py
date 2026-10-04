"""Small DB-API PostgreSQL repository seam; no driver is imported at module load."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Callable


class PostgresRepository:
    """Transactional persistence with an injectable connection factory.

    Passing no factory gives a deterministic process-local adapter for unit/dev use;
    production must provide DATABASE_URL and a factory (psycopg is deliberately lazy).
    """
    def __init__(self, connection_factory: Callable[[], Any] | None = None) -> None:
        self.factory = connection_factory
        self.configurations: list[dict[str, Any]] = []
        self.overrides: dict[str, dict[str, Any]] = {}
        self.audit_events: list[dict[str, Any]] = []
        self.telemetry_events: list[dict[str, Any]] = []
        self.idempotency: dict[str, dict[str, Any]] = {}

    def transaction(self):
        return _Transaction(self)

    def save_configuration(self, record: dict[str, Any]) -> None:
        if self.factory is None:
            self.configurations.append(dict(record)); return
        with self.factory() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO control_configurations(version, cohort, values_json, signature) VALUES (%s,%s,%s,%s)", (record["version"], record["cohort"], record["values"], record["signature"]))
            conn.commit()

    def latest_configuration(self) -> dict[str, Any] | None:
        if self.factory is None: return max(self.configurations, key=lambda x: x["version"], default=None)
        with self.factory() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version, cohort, values_json, signature FROM control_configurations ORDER BY version DESC LIMIT 1")
                row = cur.fetchone()
        return None if row is None else {"version": row[0], "cohort": row[1], "values": row[2], "signature": row[3]}

    def save_override(self, device_id: str, values: dict[str, Any]) -> None:
        if self.factory is None: self.overrides[device_id] = dict(values); return
        with self.factory() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO device_overrides(device_id, values_json) VALUES (%s,%s) ON CONFLICT(device_id) DO UPDATE SET values_json=EXCLUDED.values_json, updated_at=now()", (device_id, values))
            conn.commit()

    def get_override(self, device_id: str) -> dict[str, Any]:
        if self.factory is None: return dict(self.overrides.get(device_id, {}))
        with self.factory() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT values_json FROM device_overrides WHERE device_id=%s", (device_id,)); row = cur.fetchone()
        return {} if row is None else dict(row[0])

    def append_audit(self, event: dict[str, Any]) -> None:
        if self.factory is None: self.audit_events.append(dict(event)); return
        with self.factory() as conn:
            with conn.cursor() as cur: cur.execute("INSERT INTO admin_audit_events(actor, action, outcome, metadata_json) VALUES (%s,%s,%s,%s)", (event["actor"], event["action"], event["outcome"], event["metadata"]))
            conn.commit()

    def append_telemetry(self, metadata: dict[str, Any]) -> None:
        if self.factory is None: self.telemetry_events.append({"metadata": dict(metadata), "created_at": datetime.now(timezone.utc)}); return
        with self.factory() as conn:
            with conn.cursor() as cur: cur.execute("INSERT INTO telemetry_events(metadata_json) VALUES (%s)", (metadata,))
            conn.commit()

    def purge(self, *, telemetry_days: int = 30, audit_days: int = 365) -> int:
        if self.factory is None:
            now = datetime.now(timezone.utc); before = len(self.telemetry_events) + len(self.audit_events)
            self.telemetry_events[:] = [x for x in self.telemetry_events if (now - x["created_at"]).days < telemetry_days]
            self.audit_events[:] = [x for x in self.audit_events if (now - x.get("created_at", now)).days < audit_days]
            return before - len(self.telemetry_events) - len(self.audit_events)
        with self.factory() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM telemetry_events WHERE created_at < now() - (%s || ' days')::interval", (telemetry_days,)); count = cur.rowcount
                cur.execute("DELETE FROM admin_audit_events WHERE created_at < now() - (%s || ' days')::interval", (audit_days,)); count += cur.rowcount
            conn.commit(); return count


class _Transaction:
    def __init__(self, repo: PostgresRepository): self.repo = repo
    def __enter__(self): return self.repo
    def __exit__(self, typ, value, tb): return False
