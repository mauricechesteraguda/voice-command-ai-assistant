#!/usr/bin/env bash
set -Eeuo pipefail
SESSION_ID="k3s-teardown-$(date -u +%s)-$$"; log(){ printf '{"session":"%s","event":"%s"}\n' "$SESSION_ID" "$1"; }
command -v k3s-uninstall.sh >/dev/null; [[ "${K3S_CONFIRM_TEARDOWN:-}" == "${K3S_CLUSTER_NAME:-k3s}" ]] || { log refusal; exit 2; }; log teardown; timeout 120 k3s-uninstall.sh; log complete
