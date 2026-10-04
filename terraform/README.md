# AWS platform Terraform

The `profiles/eks` root composes private VPC networking, managed EKS, PostgreSQL,
Route53, KMS/Secrets Manager, workload IAM, backups, flow logs, and WAF hooks.
Provider versions are constrained in every module (`hashicorp/aws >= 5.70, < 6`).
Generate and commit `.terraform.lock.hcl` only from a trusted, network-enabled
release environment; CI must use `terraform init -lockfile=readonly`.

No credentials or secret values are represented in configuration or outputs.
Argo owns workload reconciliation after the Terraform-created cluster/bootstrap
boundary.
