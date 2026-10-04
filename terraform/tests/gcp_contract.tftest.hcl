mock_provider "google" {}

run "plan_has_no_secret_values" {
  command = plan
  variables {
    project_id = "test-project"
  }
  assert {
    condition     = output.argo_bootstrap_boundary != ""
    error_message = "Argo ownership boundary must be explicit"
  }
  assert {
    condition     = output.backup_targets.sql_pitr
    error_message = "SQL PITR must be enabled"
  }
}
