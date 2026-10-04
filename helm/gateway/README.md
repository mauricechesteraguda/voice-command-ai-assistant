# Gateway and WAF hook

This directory is the Argo-owned handoff boundary for Gateway API, Azure WAF,
ExternalDNS, and cert-manager. Terraform creates the Azure DNS zone and workload
identities; Argo installs controllers and reconciles routes/certificates. No
static Azure credentials are stored in these values.
