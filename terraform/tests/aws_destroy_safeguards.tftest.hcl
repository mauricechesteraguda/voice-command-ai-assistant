mock_provider "aws" {
}
run "plan_requires_safe_defaults" {
  command = plan
  variables {
    name                = "test"
    region              = "us-east-1"
    deletion_protection = true
  }
  module {
    source = "../profiles/eks"
  }
  assert {
    condition     = var.deletion_protection == true
    error_message = "destruction requires explicit opt-out"
  }
}
