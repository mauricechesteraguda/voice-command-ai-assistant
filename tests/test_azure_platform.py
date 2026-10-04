"""Offline structural checks for the Azure platform contract."""

from pathlib import Path
import re

ROOT = Path(__file__).parents[1]


def test_azure_profile_is_pinned_and_composed() -> None:
    profile = ROOT / "terraform/azure/profiles/aks"
    text = (profile / "main.tf").read_text()
    assert 'version = "4.44.0"' in text
    for module in ("network", "cluster", "platform-services"):
        assert re.search(rf'source\s*=\s*"../../../modules/{module}"', text)


def test_aks_has_budgeted_autoscaling_and_workload_identity() -> None:
    text = (ROOT / "terraform/azure/modules/cluster/main.tf").read_text()
    for marker in ("auto_scaling_enabled", "min_count", "max_count", "oidc_issuer_enabled", "azurerm_federated_identity_credential", "azurerm_role_assignment"):
        assert marker in text


def test_no_secret_outputs_and_recovery_hooks_exist() -> None:
    outputs = "\n".join(p.read_text() for p in (ROOT / "terraform").rglob("outputs.tf"))
    assert "password" not in outputs.lower()
    assert (ROOT / "terraform/azure/tests/destroy_safeguards.tftest.hcl").is_file()
    assert (ROOT / "docs/runbooks/backup-restore.md").is_file()
    assert (ROOT / "helm/gateway/values.yaml").is_file()
