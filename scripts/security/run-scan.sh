#!/usr/bin/env bash
set -Eeuo pipefail

# implementation-10042026-Maurice
SESSION_ID="security-$(date -u +%Y%m%dT%H%M%SZ)-$$"
TRACE_DIR="${TRACE_DIR:-${RUNNER_TEMP:-/tmp}/voice-command-security}"
TRACE_FILE="$TRACE_DIR/$SESSION_ID.jsonl"
mkdir -p "$TRACE_DIR"
log() { local event="$1"; shift; printf '{"session":"%s","event":"%s","tool":"%s","ts":"%s","detail":"%s"}\n' "$SESSION_ID" "$event" "${1:-security}" "$(date -u +%FT%TZ)" "${*:2}" >> "$TRACE_FILE"; }
cleanup() { log inspected trace; cat "$TRACE_FILE"; rm -f "$TRACE_FILE"; rmdir "$TRACE_DIR" 2>/dev/null || true; }
trap cleanup EXIT
tool="${1:?tool required: trivy|checkov|gitleaks|native}"; shift
case "$tool" in
  trivy) cmd=(trivy fs --scanners vuln,secret,misconfig --exit-code 1 --no-progress . "$@");;
  checkov) cmd=(checkov -d . --quiet --compact "$@");;
  gitleaks) cmd=(gitleaks detect --source . --no-banner --redact "$@");;
  native) cmd=(python3 scripts/security/native-validators.py "$@");;
  *) log error "unknown tool"; exit 2;;
esac
log startup "$tool"; log external-call "${cmd[*]}"
if [[ "${SECURITY_DRY_RUN:-0}" == 1 ]]; then log dry-run "$tool"; exit 0; fi
timeout "${SECURITY_TIMEOUT_SECONDS:-300}" "${cmd[@]}"; status=$?
log result "exit=$status"; exit "$status"
