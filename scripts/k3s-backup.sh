#!/usr/bin/env bash
set -Eeuo pipefail
SESSION_ID="k3s-backup-$(date -u +%s)-$$"; destination="${K3S_BACKUP_DIR:-/var/backups/k3s}"; log(){ printf '{"session":"%s","event":"%s"}\n' "$SESSION_ID" "$1"; }
command -v tar >/dev/null; command -v timeout >/dev/null; mkdir -p "$destination"; log start; timeout 120 tar --xattrs --acls -czf "$destination/k3s-$(date -u +%Y%m%dT%H%M%SZ).tgz" /var/lib/rancher/k3s/server/db /var/lib/rancher/k3s/server/token; log complete
