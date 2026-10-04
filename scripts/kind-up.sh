#!/usr/bin/env bash
set -Eeuo pipefail

SESSION_ID="kind-$(date -u +%Y%m%dT%H%M%SZ)-$$"
trace="${RUNNER_TEMP:-/tmp}/$SESSION_ID.jsonl"
KIND_CLUSTER_NAME="${KIND_CLUSTER_NAME:-voice-platform-${SESSION_ID#kind-}}"
log(){ printf '{"session":"%s","event":"%s","detail":"%s"}\n' "$SESSION_ID" "$1" "${*:2}" | tee -a "$trace"; }
finish(){ log inspected-trace; rm -f "$trace"; }
trap finish EXIT

log startup
command -v kind >/dev/null
command -v kubectl >/dev/null
command -v docker >/dev/null
command -v openssl >/dev/null
log external-call kind-create
timeout 300 kind create cluster --config kind/cluster.yaml --name "$KIND_CLUSTER_NAME" "${@:-}"
kubectl create namespace platform-system --dry-run=client -o yaml | kubectl apply -f -

# Runtime-only values. Values are supplied by the caller or generated immediately before
# Secret creation; none are committed. kubectl's client-side dry-run makes this idempotent.
POSTGRES_PASSWORD="${KIND_POSTGRES_PASSWORD:-$(openssl rand -hex 24)}"
DEX_CLIENT_SECRET="${KIND_DEX_CLIENT_SECRET:-$(openssl rand -hex 24)}"
log external-call secret-bootstrap
kubectl create secret generic postgresql-credentials -n platform-system \
  --from-literal=POSTGRES_PASSWORD="$POSTGRES_PASSWORD" --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic dex-credentials -n platform-system \
  --from-literal=client-secret="$DEX_CLIENT_SECRET" --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic control-plane-credentials -n platform-system \
  --from-literal=CONTROL_PLANE_SIGNING_KEY="${KIND_CONTROL_PLANE_SIGNING_KEY:-$(openssl rand -hex 32)}" \
  --dry-run=client -o yaml | kubectl apply -f -

log external-call image-build
docker build -t voice-command-ai-assistant:local .
log external-call image-load
kind load docker-image voice-command-ai-assistant:local --name "$KIND_CLUSTER_NAME"
log external-call local-services
kubectl apply -f kind/local-services.yaml
log ready
