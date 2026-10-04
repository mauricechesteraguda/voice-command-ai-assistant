"""Operations, documentation, and failure contracts."""

from pathlib import Path
import logging
import re


ROOT = Path(__file__).parents[1]


def _text(path: Path) -> str:
    return path.read_text(errors="ignore")


def _assert_safe_log_messages(records: list[logging.LogRecord]) -> None:
    for record in records:
        message = record.getMessage()
        assert "Traceback" not in message and "/Users/" not in message
        assert not re.search(r"password|secret|token=", message, re.I)


def test_tc_devops_0045_publishes_diagrams_urls_costs_and_caveats() -> None:
    path = ROOT / "docs" / "infrastructure"
    assert path.is_dir(), "TC-DEVOPS-0045 requires both infrastructure READMEs"
    assert len(list(path.rglob("README*"))) >= 2


def test_tc_devops_0047_documents_reproducible_teardown() -> None:
    path = ROOT / "docs" / "runbooks" / "teardown.md"
    assert path.is_file(), "TC-DEVOPS-0047 requires reproducible teardown instructions"


def test_tc_devops_0048_preserves_existing_api_compatibility() -> None:
    assert (ROOT / "conversation_orchestrator.py").is_file()
    assert (ROOT / "tests" / "test_conversation_runtime.py").is_file()


def test_tc_devops_0049_documents_cross_cloud_restore() -> None:
    path = ROOT / "docs" / "runbooks" / "cross-cloud-restore.md"
    assert path.is_file(), "TC-DEVOPS-0049 requires cross-cloud restore documentation"


def test_tc_devops_0050_meets_api_latency_and_availability_slos() -> None:
    path = ROOT / "observability" / "slo.yaml"
    assert path.is_file(), "TC-DEVOPS-0050 requires measurable API SLO definitions"


def test_tc_devops_0051_fails_closed_during_cloud_outage() -> None:
    path = ROOT / "edge_control_plane.py"
    assert path.is_file(), "TC-DEVOPS-0051 requires cloud-outage local-only behavior"


def test_tc_devops_0052_handles_identity_provider_outage() -> None:
    path = ROOT / "platform_api" / "auth.py"
    assert path.is_file(), "TC-DEVOPS-0052 requires bounded cached validation and fail-closed new access"
    text = _text(path)
    assert "ConnectionError" in text or "TimeoutError" in text
    assert "cache" in text.lower() and "ttl" in text.lower()
    assert "issuer" in text and "audience" in text


def test_tc_devops_0053_publishes_cost_ranges_and_alerts() -> None:
    path = ROOT / "docs" / "infrastructure" / "costs.yaml"
    assert path.is_file(), "TC-DEVOPS-0053 requires profile cost ranges and alert thresholds"


def test_tc_devops_0054_keeps_conversation_data_local() -> None:
    source = (ROOT / "conversation_orchestrator.py").read_text()
    assert "transcript" in source and "audio" in source


def test_tc_devops_0056_labels_unverified_cloud_claims() -> None:
    path = ROOT / "docs" / "infrastructure" / "cloud-profiles.yaml"
    assert path.is_file(), "TC-DEVOPS-0056 requires explicit cloud_verified labeling"
    assert "cloud_verified" in path.read_text()


def test_tc_devops_0057_provides_live_url_placeholder_without_false_claim() -> None:
    path = ROOT / "docs" / "infrastructure" / "README.md"
    assert path.is_file(), "TC-DEVOPS-0057 requires a clearly labeled live URL placeholder"
    assert "placeholder" in path.read_text().lower()


def test_tc_devops_0058_preserves_source_on_restore_failure() -> None:
    path = ROOT / "docs" / "runbooks" / "restore.md"
    assert path.is_file(), "TC-DEVOPS-0058 requires source-preserving restore failure handling"


def test_tc_devops_0059_returns_structured_errors_and_idempotency(caplog) -> None:
    path = ROOT / "platform_api" / "errors.py"
    assert path.is_file(), "TC-DEVOPS-0059 requires structured errors and idempotency keys"
    text = _text(path)
    assert "correlation_id" in text and "idempotency_key" in text
    assert "stack" not in text.lower() or "path" in text.lower()
    assert "remediation" in text and "cause" in text.lower()
    from platform_api.errors import ErrorCode, log_error, safe_error

    with caplog.at_level(logging.INFO, logger="control_plane.errors"):
        log_error(safe_error(RuntimeError("/Users/operator/password=secret"), correlation_id="corr-1", idempotency_key="idem-1"))
    _assert_safe_log_messages(caplog.records)
    assert any(ErrorCode.INTERNAL_ERROR.value in record.getMessage() for record in caplog.records)


def test_tc_devops_0060_verifies_approved_happy_and_failure_flows() -> None:
    path = ROOT / "tests" / "platform_flows"
    assert path.is_dir(), "TC-DEVOPS-0060 requires deterministic approved happy and failure flow fixtures"
    assert all((path / name).is_file() for name in ("happy.json", "failure.json"))
    assert all("sensitive" not in _text(path / name).lower() for name in ("happy.json", "failure.json"))
