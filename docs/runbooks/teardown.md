# Teardown

Confirm owner approval, incident status, and a recent verified backup. Suspend Argo promotion, export state metadata, and run `terraform plan -destroy`; apply only from the protected environment after a second operator approves. Retain audit records and source backups, then revoke OIDC trust and DNS delegation. For kind, run `kind delete cluster --name voice-command` only after collecting diagnostics.
