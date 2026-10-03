# Conversation runtime coverage

## Coverage summary

- Cases: **81** total (TC-001..TC-081); existing TC-001..TC-041 are preserved unchanged and new IDs are immutable.
- Requirements: **64/64 covered (100%)** (REQ-001..REQ-064; every requirement appears in at least one case).
- Execution status: all cases are intentionally **Not Run**; this documentation task does not create or run implementation tests.
- Automated Test Ref: blank for the new Linux/Compose cases; QA notes remain blank.

## Cases by Test Type

| Test Type/category family | Cases |
|---|---:|
| Happy path / exact flow | 8 |
| macOS permissions/regression | 4 |
| Explicit provisioning / model integrity / config | 12 |
| Linux platform, host/container, and audio validation | 10 |
| FFmpeg capture/cancellation/errors | 6 |
| faster-whisper/STT | 6 |
| Piper/paplay/TTS | 6 |
| Ollama privacy/readiness | 4 |
| Compose CPU/NVIDIA/health/security/volumes/env/build | 12 |
| Lifecycle, signals, restart, stale output, rollback | 9 |
| Performance measurement | 4 |
| Existing runtime context/concurrency/privacy/error coverage | 20 |

Counts are grouped by primary category family for review; a case can exercise more than one requirement or concern, so family totals are not intended to sum as a disjoint partition of all cross-cutting assertions.

## N/A reasons

None for the approved Linux/Compose scope. Payment, accounts/authentication, external hosted-provider contracts, cross-session migration, and UI accessibility remain outside this local single-user runtime; they are not claimed requirements and therefore have no N/A test cases.

## Open questions

None.
