# GKE platform profile

This profile is the provider-native GCP foundation for the platform. Run it from
`terraform/` with a separately managed, encrypted remote state backend. CI must
use OIDC or workforce identity federation; static service-account keys are not
supported.

Terraform owns the VPC, private GKE cluster and autoscaling nodes, Cloud SQL
PostgreSQL, Cloud DNS, KMS/Secret Manager containers, audit logging, Cloud Armor
policy hook, and Workload Identity bindings. Argo owns Kubernetes workloads and
GitOps reconciliation. No database passwords, secret versions, or kubeconfig
credentials are created or returned by this profile.

SQL backups and point-in-time recovery are enabled. Set `rpo_hours` and
`rto_hours` to the approved operational targets and verify restore drills in the
runbook before production use. SQL, KMS, and Secret Manager resources have
destroy protection; removal requires an explicit reviewed change.
