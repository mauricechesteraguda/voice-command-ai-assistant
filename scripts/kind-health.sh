#!/usr/bin/env bash
set -Eeuo pipefail
SESSION_ID="kind-health-$(date -u +%s)-$$"; trace="${RUNNER_TEMP:-/tmp}/$SESSION_ID.jsonl"; trap 'cat "$trace" >/dev/null; rm -f "$trace"' EXIT
log(){ printf '{"session":"%s","event":"%s","detail":"%s"}\n' "$SESSION_ID" "$1" "${*:2}" | tee -a "$trace"; }
log startup; log external-call kubectl; timeout 120 kubectl wait --for=condition=Ready nodes --all --timeout=90s; log result
