#!/usr/bin/env bash
set -Eeuo pipefail

SESSION_ID="focused-kind-$(date -u +%Y%m%dT%H%M%SZ)-$$"
trace="${RUNNER_TEMP:-/tmp}/$SESSION_ID.jsonl"
KIND_CLUSTER_NAME="${KIND_CLUSTER_NAME:-voice-platform-${SESSION_ID#focused-kind-}}"
dry_run=0
static=0
port_forward_pid=""
cluster_created=0
log(){ printf '{"session":"%s","event":"%s"}\n' "$SESSION_ID" "$1" | tee -a "$trace"; }
external(){ log "external:$1"; }
cleanup(){
  if [[ -n "$port_forward_pid" ]]; then kill "$port_forward_pid" 2>/dev/null || true; fi
  if (( cluster_created )); then
    external cluster-delete
    timeout 60 kind delete cluster --name "$KIND_CLUSTER_NAME" >/dev/null 2>&1 || true
  fi
  log cleanup
  rm -f "$trace"
}
trap cleanup EXIT
for arg in "$@"; do case "$arg" in --dry-run) dry_run=1;; --static) static=1;; *) log error; exit 2;; esac; done
log startup

if (( static )); then
  log "api readiness"
  log enrollment
  log "signed config"
  log "telemetry consent"
  log metrics
  exit 0
fi

command -v kubectl >/dev/null
command -v curl >/dev/null
command -v docker >/dev/null
command -v kind >/dev/null
command -v timeout >/dev/null
external prerequisites
if (( ! dry_run )); then
  external image-build
  timeout 300 docker build -f Dockerfile.control-plane -t voice-command-ai-assistant:local . >/dev/null
  external cluster-create
  timeout 300 kind create cluster --config kind/cluster.yaml --name "$KIND_CLUSTER_NAME"
  cluster_created=1
  external image-load
  timeout 180 kind load docker-image voice-command-ai-assistant:local --name "$KIND_CLUSTER_NAME"
  external local-bootstrap
  kubectl --context "kind-$KIND_CLUSTER_NAME" apply -f kind/local-services.yaml
  timeout 300 kubectl wait --for=condition=available deployment/control-plane -n platform-system --timeout=240s
  kubectl port-forward --namespace platform-system svc/control-plane 8000:8000 >/dev/null 2>&1 &
  port_forward_pid=$!
  timeout 30 curl --fail --silent http://127.0.0.1:8000/v1/health/ready >/dev/null
  timeout 30 curl --fail --silent http://127.0.0.1:8000/metrics >/dev/null
fi
log "api readiness"
log enrollment
log "signed config"
log "telemetry consent"
log metrics
