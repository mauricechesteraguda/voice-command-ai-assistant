#!/usr/bin/env bash
set -Eeuo pipefail
SESSION_ID="kind-rollback-$(date -u +%s)-$$"; trace="${RUNNER_TEMP:-/tmp}/$SESSION_ID.jsonl"; trap 'cat "$trace" >/dev/null; rm -f "$trace"' EXIT
log(){ printf '{"session":"%s","event":"%s","detail":"%s"}\n' "$SESSION_ID" "$1" "${*:2}" | tee -a "$trace"; }
revision="${1:?immutable revision required}"; [[ "$revision" != latest ]] || { log error mutable-revision; exit 2; }; log startup; log external-call "kubectl rollout undo revision=$revision"; timeout 120 kubectl rollout undo deployment/platform-api --to-revision="$revision"; log result
