# Static contract: destructive operations require reviewed changes. The profile
# uses deletion_protection/prevent_destroy on SQL, KMS, and Secret Manager.
mock_provider "google" {}

run "destroy_safeguards_are_declared" {
  command = plan
  variables {
    project_id = "test-project"
  }
}
