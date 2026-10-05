# Changelog — 2026-10-03

- Documented the macOS local-first architecture, runtime state and
  cancellation behavior, bounded context, model configuration, and continuous
  conversation happy flow.
- Documented AVFoundation/FFmpeg capture, MLX Whisper, localhost Ollama
  streaming, clause buffering, and `/usr/bin/say` playback.
- Added current prerequisites, virtual-environment installation, explicit
  model provisioning, privacy/logging guidance, acoustic limitations,
  troubleshooting, and the 151-test command (`python3 -m pytest -q`).
- Replaced the outdated platform and hosted speech-service guidance.
- Added Linux Pulse/PipeWire, faster-whisper, Piper/paplay, private Ollama,
  explicit multi-artifact provisioning, hardened CPU Compose, and optional
  NVIDIA deployment validation.
- Pinned the Linux image and Ollama image, locked Python dependencies, added
  non-root audio-aware provisioning/readiness checks, and documented offline
  recovery, rollback, and NVIDIA commands.
- Added the standard MIT license with 2026 Maurice Aguda copyright notice and
  linked it from the README.

- Added deterministic security wrappers, pinned CI validation/release/OIDC workflows,
  Renovate configuration, kind health/rollback helpers, and multicloud operations
  documentation with explicit unverified cloud pricing assumptions.
- Added the edge/control-plane boundary, signed API, Terraform profiles for AWS/GCP/Azure,
  Helm/Argo/Kubernetes delivery, observability, policy, backup/restore, and security
  contracts covered by 151 tests (81 existing runtime tests plus 64 platform cases).
- Final validation includes Python 3.10 `pytest -x -q`, Terraform format/validate checks,
  and native Terraform tests where provider tooling is available. Local kind image pulls
   remain externally blocked; no cloud environment was deployed and no live URL is claimed.
- Fixed Terraform workflow matrix expressions so manual runs execute only the selected
  provider while retaining protected, checksum-verified apply behavior.

Author Name: Aguda, Maurice
