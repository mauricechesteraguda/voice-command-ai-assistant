"""macOS local voice assistant CLI.

implementation-10032026-Maurice
"""
from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
import traceback
import uuid
from types import SimpleNamespace
from typing import Any

from conversation_orchestrator import (
    ConversationOrchestrator,
    ExplicitModelProvisioner,
    FFmpegMicrophoneCapture,
    MLXWhisperTranscriber,
    OllamaStreamingAdapter,
    SayPlayer,
    TextSynthesizer,
    traced,
)


logger = logging.getLogger("assistant")

_CLI_ERROR_CODES = {
    "runtime_factory": "RUNTIME_FACTORY_FAILED",
    "run_conversation": "CONVERSATION_LOOP_FAILED",
    "provision": "MODEL_PROVISION_FAILED",
    "shutdown": "SHUTDOWN_FAILED",
}


@traced
def _cli_event(event: str, *, level: int = logging.INFO, operation: str | None = None,
               runtime: Any = None, exc: BaseException | None = None,
               remediation: str | None = None) -> None:
    """Write the CLI's redacted operational events using the runtime schema."""
    payload: dict[str, Any] = {
        "event": event,
        "severity": {logging.DEBUG: "DEBUG", logging.INFO: "INFO",
                     logging.WARNING: "WARNING", logging.ERROR: "ERROR",
                     logging.CRITICAL: "CRITICAL"}.get(level, "ERROR"),
        "session_id": getattr(runtime, "session_id", "") or uuid.uuid4().hex[:12],
        "correlation_id": getattr(runtime, "correlation_id", "") or uuid.uuid4().hex,
    }
    if operation:
        payload["operation"] = operation
    if event == "error":
        payload["error_code"] = _CLI_ERROR_CODES.get(operation or "", "CLI_OPERATION_FAILED")
    if exc is not None:
        payload.update({
            "exception_type": type(exc).__name__,
            "cause": type(exc.__cause__).__name__ if exc.__cause__ else type(exc).__name__,
            # Deliberately omit filenames and source lines: exception messages can
            # contain prompts, paths, credentials, or other user-controlled data.
            "stack_trace": "\n".join(
                f"at {frame.name}:line {frame.lineno}"
                for frame in traceback.extract_tb(exc.__traceback__)
            ) or "at cli boundary",
        })
    if remediation:
        payload["remediation"] = remediation
    logger.log(level, json.dumps(payload, sort_keys=True))


@traced
def _configure_logging(verbose: bool = False) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@traced
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local macOS voice assistant; audio and transcripts stay local by default.")
    parser.add_argument("--download-model", action="store_true", help="explicitly provision a configured model artifact")
    parser.add_argument("--model-path", help="existing local model artifact path")
    parser.add_argument("--model", default="llama3.2")
    parser.add_argument("--verbose", action="store_true")
    return parser


@traced
def _validate_dependencies() -> None:
    if sys.platform != "darwin":
        _cli_event("dependency", level=logging.WARNING, operation="dependency_check",
                   remediation="Run the assistant on macOS with its local adapters installed.")
    else:
        _cli_event("dependency", operation="dependency_check")


@traced
def build_runtime(*, model: str = "llama3.2", model_path: str | None = None,
                  adapters: Any = None, config: dict[str, Any] | None = None) -> ConversationOrchestrator:
    """Compose production ports without opening hardware or downloading models.

    ``adapters`` is an explicit test seam.  Otherwise every port is local and
    lazy: construction does not touch AVFoundation, MLX, Ollama, or ``say``.
    """
    if adapters is None:
        adapters = SimpleNamespace(
            audio_capture=FFmpegMicrophoneCapture(device=":0"),
            transcriber=MLXWhisperTranscriber(model_path or "models/whisper"),
            language_model=OllamaStreamingAdapter(model=model, host="http://127.0.0.1:11434"),
            synthesizer=TextSynthesizer(),
            player=SayPlayer(executable="/usr/bin/say"),
            provisioner=ExplicitModelProvisioner(model_path) if model_path else None,
            network=None,
        )
    values = dict(config or {})
    values.update(model=model, model_path=model_path)
    return ConversationOrchestrator(adapters=adapters, config=values)


@traced
def main(argv: list[str] | None = None, *, runtime_factory: Any = build_runtime,
         stop_event: threading.Event | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    _cli_event("startup", operation="cli_startup")
    _validate_dependencies()
    try:
        runtime = runtime_factory(model=args.model, model_path=args.model_path)
    except Exception as exc:
        _cli_event("error", level=logging.ERROR, operation="runtime_factory", exc=exc,
                   remediation="Check local runtime dependencies and configuration, then retry.")
        raise
    _cli_event("lifecycle", operation="runtime_created", runtime=runtime)
    if args.download_model:
        if not args.model_path:
            parser.error("--download-model requires --model-path; provisioning is explicit and local")
        try:
            result = runtime.provision_model(consent=True)
        except Exception as exc:
            _cli_event("error", level=logging.ERROR, operation="provision", runtime=runtime,
                       exc=exc, remediation="Verify the local model artifact and retry provisioning.")
            raise
        if result.state == "ERROR_RECOVERABLE":
            _cli_event("error", level=logging.ERROR, operation="provision", runtime=runtime,
                       exc=RuntimeError("model provisioning failed"),
                       remediation="Verify the local model artifact and retry provisioning.")
            return 1
    if stop_event is None:
        stop_event = threading.Event()
    shutdown_failed: list[BaseException] = []

    @traced
    def stop(signum: int, frame: Any) -> None:
        if stop_event.is_set():
            return
        _cli_event("shutdown", operation="shutdown", runtime=runtime)
        try:
            runtime.shutdown()
        except Exception as exc:
            shutdown_failed.append(exc)
            _cli_event("error", level=logging.ERROR, operation="shutdown", runtime=runtime,
                       exc=exc, remediation="Inspect adapter shutdown support and retry.")
            raise
        finally:
            stop_event.set()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    _cli_event("lifecycle", operation="conversation_start", runtime=runtime)
    try:
        runtime.run_conversation(stop_event=stop_event)
    except KeyboardInterrupt:
        stop_event.set()
        _cli_event("shutdown", operation="shutdown", runtime=runtime)
        return 0
    except Exception as exc:
        if not shutdown_failed or shutdown_failed[-1] is not exc:
            _cli_event("error", level=logging.ERROR, operation="run_conversation", runtime=runtime,
                       exc=exc, remediation="Inspect the local adapters and retry the conversation.")
        raise
    if shutdown_failed:
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
    except Exception:
        # ``main`` remains an injectable/testable boundary; the executable CLI
        # converts unexpected failures into one deterministic nonzero status.
        raise SystemExit(1)
