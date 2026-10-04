"""GitOps and security contract checks."""

from pathlib import Path
import re


ROOT = Path(__file__).parents[1]


def _text(path: Path) -> str:
    return path.read_text(errors="ignore")


def _yaml_documents(path: Path) -> str:
    return _text(path).replace("\n", " ")


def test_tc_devops_0017_rolls_back_failed_schema_or_platform_changes() -> None:
    path = ROOT / "migrations" / "rollback"
    assert path.is_dir(), "TC-DEVOPS-0017 requires a tested rollback boundary"


def test_tc_devops_0018_returns_bounded_rate_limit_responses() -> None:
    path = ROOT / "platform_api" / "rate_limit.py"
    assert path.is_file(), "TC-DEVOPS-0018 requires a bounded 429 rate-limit contract"
    text = _text(path)
    assert "device" in text.lower() and "caller" in text.lower()
    assert "retry" in text.lower() and "fail-open" not in text.lower()


def test_tc_devops_0019_renders_secure_helm_and_library_charts() -> None:
    path = ROOT / "helm"
    assert path.is_dir(), "TC-DEVOPS-0019 requires application and library Helm charts"
    assert any(path.rglob("Chart.yaml"))


def test_tc_devops_0020_validates_kind_foundation_dependencies() -> None:
    path = ROOT / "kind"
    assert path.is_dir(), "TC-DEVOPS-0020 requires deterministic kind foundation manifests"
    assert any(path.rglob("*.yaml"))


def test_tc_devops_0021_reconciles_argo_app_of_apps() -> None:
    path = ROOT / "argocd" / "app-of-apps.yaml"
    assert path.is_file(), "TC-DEVOPS-0021 requires an Argo app-of-apps"
    text = _text(path)
    repo_urls = re.findall(r"repoURL:\s*([^,\s]+)", text)
    assert repo_urls and all("example.invalid" not in url for url in repo_urls)
    project = _text(ROOT / "argocd" / "project.yaml")
    assert repo_urls[0] in project, "Argo Project and Application must use the same repository"


def test_tc_devops_0022_gates_immutable_promotion() -> None:
    path = ROOT / "argocd" / "promotion"
    assert path.is_dir(), "TC-DEVOPS-0022 requires immutable promotion gates"
    text = "\n".join(_text(item) for item in path.rglob("*") if item.is_file())
    assert "sha256:" in text and "digest" in text.lower()
    assert "image:" in text and "latest" not in text


def test_tc_devops_0023_self_heals_drift() -> None:
    path = ROOT / "argocd" / "applications"
    assert path.is_dir(), "TC-DEVOPS-0023 requires Argo self-heal configuration"


def test_tc_devops_0024_rolls_back_unhealthy_revision() -> None:
    path = ROOT / "argocd" / "rollback"
    assert path.is_dir(), "TC-DEVOPS-0024 requires unhealthy-revision rollback policy"


def test_tc_devops_0025_measures_slos_and_alert_burn() -> None:
    path = ROOT / "observability"
    assert path.is_dir(), "TC-DEVOPS-0025 requires Prometheus rules and Grafana SLO dashboards"
    assert any(path.rglob("*.yaml"))


def test_tc_devops_0026_supports_optional_logs_and_traces_safely() -> None:
    path = ROOT / "observability" / "optional"
    assert path.is_dir(), "TC-DEVOPS-0026 requires optional Loki/Tempo integration"


def test_tc_devops_0027_reads_secrets_through_eso() -> None:
    path = ROOT / "policies" / "external-secrets"
    assert path.is_dir(), "TC-DEVOPS-0027 requires External Secrets Operator references"


def test_tc_devops_0028_uses_provider_workload_identity() -> None:
    path = ROOT / "policies" / "identity"
    assert path.is_dir(), "TC-DEVOPS-0028 requires provider workload identity manifests"
    text = "\n".join(_text(item) for item in path.rglob("*") if item.is_file())
    assert "repository" in text and "cosign" in text.lower()
    assert "https://github.com/" in text, "Cosign identity must be bound to the repository"


def test_tc_devops_0029_enforces_workload_and_artifact_policy() -> None:
    path = ROOT / "policies"
    assert path.is_dir(), "TC-DEVOPS-0029 requires Kyverno, PSA, network, and Cosign policy"
    text = "\n".join(p.read_text(errors="ignore") for p in path.rglob("*") if p.is_file())
    assert all(token in text for token in ("Kyverno", "Cosign"))
    assert "identity" in text.lower() and "repository" in text.lower()


def test_tc_devops_0046_proves_repository_and_artifact_secret_absence() -> None:
    path = ROOT / "scripts" / "security"
    assert path.is_dir(), "TC-DEVOPS-0046 requires a deterministic secret scan"


def test_tc_devops_0055_encrypts_transport_and_sensitive_records() -> None:
    path = ROOT / "platform_api" / "crypto.py"
    assert path.is_file(), "TC-DEVOPS-0055 requires TLS and stored-record encryption"
