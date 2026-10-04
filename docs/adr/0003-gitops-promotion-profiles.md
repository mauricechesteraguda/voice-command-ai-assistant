# ADR 0003: Immutable GitOps promotion uses explicit cloud profiles

## Status
Accepted

## Decision
A cloud profile is a versioned, validated target. Promotion advances immutable references through environments; it does not copy mutable manifests or embed provider credentials. Argo app-of-apps reconciles the selected profile and workload set; rollback selects a prior immutable revision.

## Rationale
Explicit profiles make EKS, GKE, and AKS differences auditable while retaining one promotion model and deterministic rollback.
