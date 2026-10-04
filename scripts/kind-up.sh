#!/usr/bin/env bash
set -Eeuo pipefail
SESSION_ID="kind-$(date -u +%Y%m%dT%H%M%SZ)-$$"; trace="${RUNNER_TEMP:-/tmp}/$SESSION_ID.jsonl"
log(){ printf '{"session":"%s","event":"%s","detail":"%s"}\n' "$SESSION_ID" "$1" "${*:2}" | tee -a "$trace"; }
finish(){ log inspected-trace; cat "$trace" >/dev/null; rm -f "$trace"; }
trap finish EXIT; log startup; command -v kind >/dev/null; log external-call kind-create
timeout 300 kind create cluster --config kind/cluster.yaml "${@:-}"; log result
