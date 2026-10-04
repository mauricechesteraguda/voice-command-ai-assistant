run "plan_requires_safe_defaults" {
  command = plan
  variables {
    name                    = "test"
    location                = "eastus"
    dns_zone_name           = "example.invalid"
    postgres_admin_login    = "test_admin"
    postgres_admin_password = "not-used-in-tests"
    prevent_destroy         = true
  }
  expect_failures = []
}

# Live destroy is intentionally never part of this suite. The profile marks the
# resource group, PostgreSQL, Key Vault, AKS, and state storage as protected;
# an operator must remove those lifecycle guards in a reviewed change.
