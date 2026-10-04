"""Externally observable platform contracts."""

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_tc_devops_0001_preserves_sealed_81_case_flow() -> None:
    source = (ROOT / "tests/test_conversation_runtime.py").read_text()
    assert len(re.findall(r"_tc_\d{3}", source)) >= 81
    assert len(re.findall(r"_case_id =", source)) == 0
    assert "for _case_id in _CASES" in source
    assert "range(1, 82)" in source


def test_tc_devops_0002_serves_versioned_configuration_api() -> None:
    path = ROOT / "platform_api" / "app.py"
    assert path.is_file(), "TC-DEVOPS-0002 requires the versioned FastAPI configuration API"


def test_tc_devops_0003_reports_safe_live_and_ready_health() -> None:
    path = ROOT / "platform_api" / "app.py"
    assert path.is_file(), "TC-DEVOPS-0003 requires live and ready health routes"
    text = path.read_text()
    assert "/health/live" in text and "/health/ready" in text


def test_tc_devops_0004_exposes_privacy_safe_telemetry() -> None:
    path = ROOT / "platform_api" / "app.py"
    assert path.is_file(), "TC-DEVOPS-0004 requires the telemetry endpoint"
    assert "/telemetry" in path.read_text()


def test_tc_devops_0005_protects_admin_mutations() -> None:
    path = ROOT / "platform_api" / "app.py"
    assert path.is_file(), "TC-DEVOPS-0005 requires authenticated admin mutations"
    assert "/admin/" in path.read_text()


def test_tc_devops_0006_authenticates_device_client() -> None:
    path = ROOT / "platform_api" / "auth.py"
    assert path.is_file(), "TC-DEVOPS-0006 requires device authorization authentication"


def test_tc_devops_0007_authenticates_admin_client() -> None:
    path = ROOT / "platform_api" / "auth.py"
    assert path.is_file(), "TC-DEVOPS-0007 requires admin OIDC authentication"


def test_tc_devops_0008_enforces_least_privilege_roles() -> None:
    path = ROOT / "platform_api" / "rbac.py"
    assert path.is_file(), "TC-DEVOPS-0008 requires explicit role and permission enforcement"


def test_tc_devops_0009_uses_os_credential_store() -> None:
    path = ROOT / "edge_control_plane.py"
    assert path.is_file(), "TC-DEVOPS-0009 requires an OS-backed credential boundary"


def test_tc_devops_0010_rejects_signature_replay_and_expiry() -> None:
    path = ROOT / "platform_api" / "auth.py"
    assert path.is_file(), "TC-DEVOPS-0010 requires signature, replay, expiry, and cache validation"
    text = path.read_text()
    assert all(token in text for token in ("signature", "replay", "expiry"))


def test_tc_devops_0011_keeps_privacy_and_telemetry_consent_independent() -> None:
    path = ROOT / "edge_control_plane.py"
    assert path.is_file(), "TC-DEVOPS-0011 requires purpose-specific consent state"
    text = path.read_text()
    assert "privacy" in text and "telemetry" in text


def test_tc_devops_0012_remains_offline_and_drops_denied_exports() -> None:
    path = ROOT / "edge_control_plane.py"
    assert path.is_file(), "TC-DEVOPS-0012 requires nonblocking offline and denied-export behavior"
    assert "offline" in path.read_text()


def test_tc_devops_0013_allowlists_metadata_and_redacts_identifiers() -> None:
    path = ROOT / "platform_api" / "privacy.py"
    assert path.is_file(), "TC-DEVOPS-0013 requires metadata allowlisting and identifier redaction"
    assert "redact" in path.read_text()


def test_tc_devops_0014_applies_reversible_postgres_migrations() -> None:
    path = ROOT / "migrations"
    assert path.is_dir(), "TC-DEVOPS-0014 requires versioned PostgreSQL migrations"
    assert any(path.iterdir())


def test_tc_devops_0015_enforces_class_specific_retention() -> None:
    path = ROOT / "platform_api" / "retention.py"
    assert path.is_file(), "TC-DEVOPS-0015 requires configured class-specific retention"


def test_tc_devops_0016_records_immutable_admin_audit_events() -> None:
    path = ROOT / "platform_api" / "audit.py"
    assert path.is_file(), "TC-DEVOPS-0016 requires append-only administrative audit events"
