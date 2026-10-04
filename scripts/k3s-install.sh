#!/usr/bin/env bash
set -Eeuo pipefail
SESSION_ID="k3s-install-$(date -u +%Y%m%dT%H%M%SZ)-$$"; trace="${RUNNER_TEMP:-/tmp}/${SESSION_ID}.jsonl"
log(){ printf '{"session":"%s","event":"%s"}\n' "$SESSION_ID" "$1" | tee -a "$trace"; }
version="${K3S_VERSION:-v1.30.6+k3s1}"; token_file="${K3S_TOKEN_FILE:-/var/lib/rancher/k3s/server/token}"
command -v curl >/dev/null; command -v timeout >/dev/null; log startup
log install; timeout 180 sh -c "curl --fail --silent --show-error --proto '=https' --tlsv1.2 https://get.k3s.io | INSTALL_K3S_VERSION='$version' sh -s - server --disable=traefik --write-kubeconfig-mode=600"
test -s "$token_file"; log ready
