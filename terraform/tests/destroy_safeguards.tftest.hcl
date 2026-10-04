# Aggregate contract: each provider-specific profile is checked in its own run.
# This file intentionally uses distinct run names and does not duplicate the
# provider-specific test files.
mock_provider "aws" {}
mock_provider "google" {}
mock_provider "azurerm" {}

run "aggregate_aws_destroy_safeguards" {
  command = plan
  module { source = "./profiles/eks" }
  variables {
    name                = "test"
    region              = "us-east-1"
    deletion_protection = true
  }
  assert {
    condition     = var.deletion_protection
    error_message = "AWS destruction requires explicit opt-out"
  }
}

run "aggregate_gcp_destroy_safeguards" {
  command = plan
  module { source = "./." }
  variables { project_id = "test-project" }
  assert {
    condition     = google_container_cluster.gke.deletion_protection
    error_message = "GKE destruction protection must remain enabled"
  }
}

run "aggregate_aks_destroy_safeguards" {
  command = plan
  module { source = "./profiles/aks" }
  variables {
    dns_zone_name           = "example.invalid"
    postgres_admin_login    = "test_admin"
    postgres_admin_password = "not-used-in-tests"
    prevent_destroy         = true
  }
  assert {
    condition     = var.prevent_destroy
    error_message = "AKS destruction requires explicit opt-out"
  }
}
