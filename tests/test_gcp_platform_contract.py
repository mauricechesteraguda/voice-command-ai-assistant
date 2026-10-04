"""Offline, provider-native GCP platform contract checks."""

from pathlib import Path


ROOT = Path(__file__).parents[1]
TF = ROOT / "terraform"


def test_gcp_profile_is_pinned_and_secret_free() -> None:
    versions = (TF / "versions.tf").read_text()
    main = (TF / "main.tf").read_text()
    assert 'source  = "hashicorp/google"' in versions
    assert 'version = "~> 6.0"' in versions
    assert "google_secret_manager_secret" in main
    assert "google_secret_manager_secret_version" not in main
    assert "google_service_account_key" not in main


def test_gke_contract_covers_private_autoscaling_and_identity() -> None:
    main = (TF / "main.tf").read_text()
    assert "google_compute_network" in main
    assert "google_container_cluster" in main
    assert "enable_private_nodes" in main
    assert "google_container_node_pool" in main
    assert "google_service_account_iam_member" in main
    for identity in ("argo", "eso", "externaldns", "cert_manager"):
        assert identity in main


def test_managed_data_and_edge_safety_contract() -> None:
    main = (TF / "main.tf").read_text()
    assert "google_sql_database_instance" in main
    assert "point_in_time_recovery_enabled = true" in main
    assert "google_dns_managed_zone" in main
    assert "google_compute_security_policy" in main
    assert "google_project_iam_audit_config" in main
    assert "google_billing_budget" in main
    assert "deletion_protection = true" in main
    assert "prevent_destroy = true" in main
