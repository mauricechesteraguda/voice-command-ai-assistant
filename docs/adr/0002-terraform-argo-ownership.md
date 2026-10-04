# ADR 0002: Terraform provisions infrastructure; Argo reconciles workloads

## Status
Accepted

## Decision
Terraform owns cloud accounts/projects, networks, clusters, managed PostgreSQL, DNS, vault integrations, identities, bootstrap, and Argo installation. Argo owns Kubernetes application and platform workload reconciliation, promotion, self-healing, and rollback. Neither tool edits the other's owned resources.

## Rationale
The boundary gives infrastructure and workload changes independent plans, avoids controller fights, and makes destruction reviewable.
