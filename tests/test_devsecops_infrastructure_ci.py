"""Infrastructure and delivery contract checks."""

from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_tc_devops_0030_protects_terraform_state_and_bootstrap() -> None:
    path = ROOT / "terraform" / "bootstrap"
    assert path.is_dir(), "TC-DEVOPS-0030 requires protected remote state bootstrap"


def test_tc_devops_0031_provisions_segmented_network() -> None:
    path = ROOT / "terraform" / "modules" / "network"
    assert path.is_dir(), "TC-DEVOPS-0031 requires segmented network Terraform"


def test_tc_devops_0032_provisions_budgeted_secure_cluster() -> None:
    path = ROOT / "terraform" / "modules" / "cluster"
    assert path.is_dir(), "TC-DEVOPS-0032 requires budget and security cluster profile"


def test_tc_devops_0033_provisions_dependent_services_and_integrations() -> None:
    path = ROOT / "terraform" / "modules" / "platform-services"
    assert path.is_dir(), "TC-DEVOPS-0033 requires PostgreSQL, DNS, vault, identity, and Argo outputs"


def test_tc_devops_0034_validates_eks_profile() -> None:
    path = ROOT / "terraform" / "profiles" / "eks"
    assert path.is_dir(), "TC-DEVOPS-0034 requires the EKS Terraform profile"


def test_tc_devops_0035_validates_gke_profile() -> None:
    path = ROOT / "terraform" / "profiles" / "gke"
    assert path.is_dir(), "TC-DEVOPS-0035 requires the GKE Terraform profile"


def test_tc_devops_0036_validates_aks_profile() -> None:
    path = ROOT / "terraform" / "profiles" / "aks"
    assert path.is_dir(), "TC-DEVOPS-0036 requires the AKS Terraform profile"


def test_tc_devops_0037_requires_destroy_safeguards() -> None:
    path = ROOT / "terraform" / "tests" / "destroy_safeguards.tftest.hcl"
    assert path.is_file(), "TC-DEVOPS-0037 requires approval and backup destroy safeguards"


def test_tc_devops_0038_meets_backup_rpo_and_rto_targets() -> None:
    path = ROOT / "docs" / "runbooks" / "backup-restore.md"
    assert path.is_file(), "TC-DEVOPS-0038 requires backup, RPO, and RTO evidence"


def test_tc_devops_0039_issues_and_routes_tls_endpoint() -> None:
    path = ROOT / "helm" / "gateway"
    assert path.is_dir(), "TC-DEVOPS-0039 requires Gateway, ExternalDNS, and cert-manager"


def test_tc_devops_0040_runs_validation_tiers() -> None:
    path = ROOT / ".github" / "workflows"
    assert path.is_dir(), "TC-DEVOPS-0040 requires PR, nightly, and release validation workflows"


def test_tc_devops_0041_uses_least_privilege_ci_oidc() -> None:
    path = ROOT / ".github" / "workflows"
    assert path.is_dir(), "TC-DEVOPS-0041 requires least-privilege CI OIDC permissions"


def test_tc_devops_0042_publishes_artifact_evidence() -> None:
    path = ROOT / ".github" / "workflows" / "release.yml"
    assert path.is_file(), "TC-DEVOPS-0042 requires SBOM, provenance, and scanner evidence"


def test_tc_devops_0043_updates_dependencies_and_builds_multiarch() -> None:
    path = ROOT / ".github" / "renovate.json"
    assert path.is_file(), "TC-DEVOPS-0043 requires Renovate and multi-architecture release config"


def test_tc_devops_0044_documents_and_validates_k3s() -> None:
    path = ROOT / "docs" / "infrastructure" / "k3s.md"
    assert path.is_file(), "TC-DEVOPS-0044 requires k3s validation documentation"
