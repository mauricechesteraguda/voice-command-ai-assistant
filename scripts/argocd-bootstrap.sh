#!/usr/bin/env bash
set -Eeuo pipefail
SESSION_ID="argocd-bootstrap-$(date -u +%Y%m%dT%H%M%SZ)-$$"
trace="${RUNNER_TEMP:-/tmp}/${SESSION_ID}.jsonl"
chart_version="${ARGOCD_CHART_VERSION:-7.7.16}"
repo_url="${ARGO_REPO_URL:-https://github.com/mauricechesteraguda/voice-command-ai-assistant.git}"
log(){ printf '{"session":"%s","event":"%s"}\n' "$SESSION_ID" "$1" | tee -a "$trace"; }
external(){ log "external:$1"; }
trap 'rm -f "$trace"' EXIT
command -v kubectl >/dev/null; command -v helm >/dev/null
log startup
external namespace
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
external helm-install
helm repo add argo https://argoproj.github.io/argo-helm >/dev/null
helm repo update >/dev/null
timeout 180 helm upgrade --install argocd argo/argo-cd --namespace argocd --version "$chart_version" --wait --timeout 150s
external controller-ready
timeout 180 kubectl -n argocd rollout status deployment/argocd-server --timeout=150s
log app-of-apps
kubectl apply -f <(sed "s#https://github.com/mauricechesteraguda/voice-command-ai-assistant.git#$repo_url#g" argocd/app-of-apps.yaml)
timeout 180 kubectl -n argocd wait --for=jsonpath='{.status.sync.status}'=Synced application/platform-root --timeout=150s
log ready
