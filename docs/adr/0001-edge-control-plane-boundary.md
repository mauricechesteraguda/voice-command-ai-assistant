# ADR 0001: Keep the edge runtime and cloud control plane separate

## Status
Accepted

## Decision
The edge runtime remains functional offline and owns microphone, local inference, playback, and conversation state. The cloud control plane owns deployment intent, platform telemetry, administration, and recovery orchestration. Conversation content and raw audio do not cross the boundary unless a separately consented future capability is approved.

## Rationale
This limits privacy exposure and preserves local operation during WAN or cloud outages. Combining the planes would make availability and data handling dependent on the control plane.
