-- implementation-10042026-Maurice
-- PostgreSQL migration; apply transactionally and reverse with rollback/001.
CREATE TABLE IF NOT EXISTS control_configurations (
    version BIGINT PRIMARY KEY,
    cohort TEXT NOT NULL,
    values_json JSONB NOT NULL,
    signature TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS device_overrides (
    device_id TEXT PRIMARY KEY,
    values_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS admin_audit_events (
    id BIGSERIAL PRIMARY KEY,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL,
    metadata_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS telemetry_events (
    id BIGSERIAL PRIMARY KEY,
    metadata_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
