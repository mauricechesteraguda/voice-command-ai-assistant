# Infrastructure operations

**Deployment status:** `Live environment: Not deployed`  
**Live URL placeholder:** `https://<environment>.<domain.example>` (placeholder only; no live URL exists).

```mermaid
flowchart LR
  PR[PR checks] --> Image[Signed GHCR digest]
  Image --> Argo[Argo app-of-apps]
  TF[Terraform via OIDC] --> K8s[(EKS / GKE / AKS)]
  Argo --> K8s
  K8s --> Monitor[Prometheus / Grafana]
```

Scope: local kind bootstrap, Terraform cloud profiles, Argo reconciliation, security evidence, observability, backups, and operator recovery. Raw audio, transcripts, prompts, and responses remain local. Start with `infrastructure/README.md`; operational runbooks are in `docs/runbooks/`.
