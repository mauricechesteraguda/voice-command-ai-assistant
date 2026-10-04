# Azure AKS platform profile

This is a plan-ready example. It deliberately does not contain credentials or
secret outputs. Provide the PostgreSQL password with `TF_VAR_postgres_admin_password`
from an approved secret manager, then run `terraform init` and `terraform plan`.

Terraform owns Azure infrastructure and the Argo installation boundary. Argo
owns Kubernetes workloads, promotions, and rollback; this profile does not
apply application manifests.
