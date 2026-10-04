#!/usr/bin/env bash
set -Eeuo pipefail
SESSION_ID="k3s-validate-$(date -u +%s)-$$"; log(){ printf '{"session":"%s","event":"%s"}\n' "$SESSION_ID" "$1"; }
command -v kubectl >/dev/null; command -v timeout >/dev/null; log startup; timeout 120 kubectl wait --for=condition=Ready nodes --all --timeout=90s; timeout 120 kubectl get --raw=/readyz >/dev/null; log ready
