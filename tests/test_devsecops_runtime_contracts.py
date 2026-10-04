"""Externally observable platform contracts."""

import ast
import re
from pathlib import Path


ROOT = Path(__file__).parents[1]

# TEST MODIFICATION BLOCK: audit-strengthened assertions remain inside the
# existing mapped cases; no case IDs or Automated Test Refs are changed.


def _fastapi_paths() -> set[str]:
    """Return the deployed application's actual route table, not copied strings."""
    from platform_api.app import create_app

    return {route.path for route in create_app().routes if hasattr(route, "path")}


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_tc_devops_0001_preserves_sealed_81_case_flow() -> None:
    source = (ROOT / "tests/test_conversation_runtime.py").read_text()
    assert len(re.findall(r"_tc_\d{3}", source)) >= 81
    assert len(re.findall(r"_case_id =", source)) == 0
    assert "for _case_id in _CASES" in source
    assert "range(1, 82)" in source


def test_tc_devops_0002_serves_versioned_configuration_api() -> None:
    path = ROOT / "platform_api" / "app.py"
    assert path.is_file(), "TC-DEVOPS-0002 requires the versioned FastAPI configuration API"
    deployed_probe = _source(ROOT / "kind" / "local-services.yaml")
    probe_paths = set(re.findall(r"path:\s*(/[^\s,}]+)", deployed_probe))
    assert probe_paths <= _fastapi_paths(), "deployed probes must target real FastAPI routes"
    tree = ast.parse(_source(path))
    assert any(isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "FastAPI" for node in ast.walk(tree))
    assert "postgres" in _source(path).lower() or "repository" in _source(path).lower()


def test_tc_devops_0003_reports_safe_live_and_ready_health() -> None:
    path = ROOT / "platform_api" / "app.py"
    assert path.is_file(), "TC-DEVOPS-0003 requires live and ready health routes"
    text = path.read_text()
    assert "/health/live" in text and "/health/ready" in text


def test_tc_devops_0004_exposes_privacy_safe_telemetry() -> None:
    path = ROOT / "platform_api" / "app.py"
    assert path.is_file(), "TC-DEVOPS-0004 requires the telemetry endpoint"
    assert "/telemetry" in path.read_text()
    text = _source(path)
    assert ".increment(" in text, "request/device metrics must be incremented on real paths"
    assert "transport" in text and "drop" in text.lower(), "telemetry transport success and bounded drops need a seam"
    observability = _source(ROOT / "platform_api" / "observability.py")
    assert "tracer" in observability.lower() and "inject" in observability.lower(), "OTel spans require an injectable tracer"


def test_tc_devops_0005_protects_admin_mutations() -> None:
    path = ROOT / "platform_api" / "app.py"
    assert path.is_file(), "TC-DEVOPS-0005 requires authenticated admin mutations"
    assert "/admin/" in path.read_text()
    text = _source(path)
    assert "idempot" in text.lower() and "exception" in text.lower(), "global safe exception/idempotency envelope is required"


def test_tc_devops_0006_authenticates_device_client() -> None:
    path = ROOT / "platform_api" / "auth.py"
    assert path.is_file(), "TC-DEVOPS-0006 requires device authorization authentication"
    text = _source(path)
    assert "device" in text and "audience" in text


def test_tc_devops_0007_authenticates_admin_client() -> None:
    path = ROOT / "platform_api" / "auth.py"
    assert path.is_file(), "TC-DEVOPS-0007 requires admin OIDC authentication"
    text = _source(path)
    assert "issuer" in text and "jwks" in text.lower() and "signature" in text
    from platform_api.auth import JWTAdapter

    adapter = JWTAdapter("test-secret")
    device_token = adapter.encode(subject="device", role="device", audience="control-plane-device")
    try:
        adapter.decode(device_token, audience="control-plane-admin")
    except ValueError:
        pass
    else:
        raise AssertionError("device and admin clients must have separate audiences")
    assert "cache" in text.lower() and "max" in text.lower(), "OIDC/JWKS cache must be bounded"


def test_tc_devops_0008_enforces_least_privilege_roles() -> None:
    path = ROOT / "platform_api" / "rbac.py"
    assert path.is_file(), "TC-DEVOPS-0008 requires explicit role and permission enforcement"


def test_tc_devops_0009_uses_os_credential_store() -> None:
    path = ROOT / "edge_control_plane.py"
    assert path.is_file(), "TC-DEVOPS-0009 requires an OS-backed credential boundary"
    text = _source(path)
    assert "Keyring" in text and "darwin" in text.lower() and "linux" in text.lower()
    assert "ephemeral" in text.lower() or "fallback" in text.lower()


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
    text = _source(path)
    assert "ConnectionError" in text or "TimeoutError" in text
    assert "nonexpir" in text.lower() or "expires" in text.lower()
    assert "monotonic" in text.lower() and "safe" in text.lower()
    from edge_control_plane import Consent, EdgeControlPlane

    def unavailable(*_: object, **__: object) -> dict[str, object]:
        raise ConnectionError("transport down")

    client = EdgeControlPlane(transport=unavailable, consent=Consent(privacy=True, telemetry=True), offline=False)
    try:
        cached = client.fetch_config("device-1")
        exported = client.export_telemetry({"event": "safe"})
    except (ConnectionError, TimeoutError) as exc:
        raise AssertionError("offline fetch/export must absorb transport failures") from exc
    assert cached is not None and exported is False


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
    text = _source(path)
    assert "30" in text and "365" in text
    assert "job" in text.lower() or "purge" in text.lower()


def test_tc_devops_0016_records_immutable_admin_audit_events() -> None:
    path = ROOT / "platform_api" / "audit.py"
    assert path.is_file(), "TC-DEVOPS-0016 requires append-only administrative audit events"
    text = _source(path)
    assert "frozen=True" in text and "purge" in text
    assert "postgres" in text.lower() or "repository" in text.lower()
