#!/usr/bin/env bash
set -Eeuo pipefail
exec "$(dirname "$0")/run-scan.sh" checkov "$@"
