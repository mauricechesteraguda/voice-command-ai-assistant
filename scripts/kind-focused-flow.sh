#!/usr/bin/env bash
set -Eeuo pipefail

SESSION_ID="focused-kind-$(date -u +%Y%m%dT%H%M%SZ)-$$"
trace="${RUNNER_TEMP:-/tmp}/$SESSION_ID.jsonl"
dry_run=0
static=0
port_forward_pid=""
log(){ printf '{"session":"%s","event":"%s"}\n' "$SESSION_ID" "$1" | tee -a "$trace"; }
external(){ log "external:$1"; }
cleanup(){
  if [[ -n "$port_forward_pid" ]]; then kill "$port_forward_pid" 2>/dev/null || true; fi
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
external prerequisites
if (( ! dry_run )); then
  external image-build
  docker build -t voice-command-ai-assistant:local . >/dev/null
  external image-load
  kind load docker-image voice-command-ai-assistant:local
  external local-bootstrap
  scripts/kind-up.sh
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
