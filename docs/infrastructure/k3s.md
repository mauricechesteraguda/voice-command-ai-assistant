# k3s / VPS low-cost runbook

**Deployment status:** `Live environment: Not deployed`; no URL is claimed.

Use these commands only on an approved hardened Linux host. No cloud keys are stored on the host.

## Install and validate

```bash
K3S_VERSION=v1.30.6+k3s1 sudo -E scripts/k3s-install.sh
sudo scripts/k3s-validate.sh
```

The installer pins k3s, disables Traefik, uses TLS for its installer download, and writes a mode-600 kubeconfig. Apply NetworkPolicy, OIDC/RBAC, cert-manager, ExternalDNS, and the pinned Argo chart before workloads.

## Backup and recovery

```bash
sudo K3S_BACKUP_DIR=/var/backups/k3s scripts/k3s-backup.sh
sudo tar -xzf /var/backups/k3s/<archive>.tgz -C /
sudo scripts/k3s-validate.sh
```

Backups are encrypted at rest by the approved off-host destination policy. Test restore before production; recovery remains fail-closed until validation succeeds.

## Teardown

Track the chosen cluster name and require exact confirmation:

```bash
sudo K3S_CLUSTER_NAME=my-k3s K3S_CONFIRM_TEARDOWN=my-k3s scripts/k3s-teardown.sh
```

Teardown is destructive and requires a current backup and approval. Terraform owns cloud foundation; Argo owns workloads.
