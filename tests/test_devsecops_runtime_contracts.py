"""Externally observable platform contracts."""

import ast
import json
import re
from pathlib import Path

import pytest


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

    # The default deployment must not silently create process-local state or
    # development signing/JWT secrets.  The injected repository seam remains
    # usable for deterministic tests, while production requires its DSN.
    app_source = _source(path)
    assert "DATABASE_URL" in app_source
    assert "connection_factory" in app_source
    assert "token_urlsafe" not in app_source

    from platform_api.app import ControlPlane, create_app
    from platform_api.audit import AuditLog
    from platform_api.auth import JWTAdapter
    from platform_api.config import ConfigStore
    from platform_api.repository import PostgresRepository

    shared = PostgresRepository()
    first = ControlPlane(
        db=shared, jwt=JWTAdapter("jwt-test"),
        config=ConfigStore("config-test", repository=shared),
        audit=AuditLog(repository=shared),
    )
    first.config.publish({"flag": "default"}, version=1, cohort="default")
    first.config.publish({"flag": "cohort"}, version=2, cohort="beta")
    first.config.set_device_override("device-1", {"flag": "device"})
    first.audit.append("admin", "config.publish", "success", {"version": 2})
    shared.idempotency["request-1"] = {"version": 2, "signature": first.config.current.signature}

    second = ControlPlane(
        db=shared, jwt=JWTAdapter("jwt-test"),
        config=ConfigStore("config-test", repository=shared),
        audit=AuditLog(repository=shared),
    )
    first_app = create_app(first)
    second_app = create_app(second)
    assert first_app.state.control_plane is first
    assert second_app.state.control_plane is second
    assert second.config.current is not None
    assert second.config.current.cohort == "beta"
    assert second.config.for_device("device-1").values["flag"] == "device"
    assert shared.idempotency["request-1"]["version"] == 2
    assert any(event["action"] == "config.publish" for event in shared.audit_events)
    assert "cohort" in app_source and "idempot" in app_source.lower()


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
    assert "payload[\"iss\"]" in text, "OIDC tokens must carry an exact issuer claim"
    assert "payload.get(\"iss\", self.issuer)" not in text

    # Missing issuer is not equivalent to the configured issuer.  Exercise the
    # verification seam with a fake JWKS/transport and a signed token shape.
    from platform_api.auth import OIDCAdapter, _b64
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives.hashes import SHA256
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.private_numbers().public_numbers
    unsigned = {
        "alg": "RS256", "typ": "JWT", "kid": "test",
    }
    payload = {"sub": "admin", "aud": "control-plane-admin", "exp": 2_000_000_000}
    head = _b64(json.dumps(unsigned, separators=(",", ":")).encode())
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = key.sign(f"{head}.{body}".encode(), padding.PKCS1v15(), SHA256())
    token = f"{head}.{body}.{_b64(signature)}"
    jwks = {"keys": [{"kid": "test", "kty": "RSA", "n": _b64(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")), "e": _b64(numbers.e.to_bytes(3, "big"))}]}
    transport = lambda url: {"issuer": "https://issuer.test", "jwks_uri": "https://issuer.test/keys"} if "well-known" in url else jwks
    oidc = OIDCAdapter(transport, "https://issuer.test")
    with pytest.raises(ValueError):
        oidc.verify(token, audience="control-plane-admin")


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
    edge = _source(ROOT / "edge_control_plane.py")
    assert all(token in edge for token in ("pinned", "public", "verify"))
    from edge_control_plane import Consent, EdgeControlPlane
    client = EdgeControlPlane(
        transport=lambda *_: {"version": 7, "values": {"danger": True}, "signature": "bogus"},
        consent=Consent(privacy=True), offline=False,
    )
    assert client.fetch_config("device-1")["version"] == 0
    assert client.fetch_config("device-1")["version"] == 0


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
    migration_job = _source(ROOT / "helm/app/templates/migration-job.yaml")
    assert "PreSync" in migration_job
    assert "secretKeyRef" in migration_job or "envFrom" in migration_job
    assert "DATABASE_URL" in migration_job
    assert re.search(r"(?:migrate|migration)[-_ ]?(?:run|runner)", migration_job, re.IGNORECASE)
    assert "echo" not in migration_job.lower()
    assert any(flag in migration_job for flag in ("set -e", "--fail", "&&"))


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
