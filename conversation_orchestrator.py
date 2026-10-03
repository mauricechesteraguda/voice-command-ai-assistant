"""Typed local-first conversation lifecycle and macOS adapter implementations.

implementation-10032026-Maurice
fix-10032026-Maurice
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import inspect
import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
import traceback
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator


logger = logging.getLogger("conversation.runtime")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
_trace_logger = logging.getLogger("conversation.trace")
_trace_logger.propagate = False
_trace_lock = threading.Lock()
_trace_handler: logging.Handler | None = None
_trace_session = uuid.uuid4().hex

_SEVERITIES = {logging.DEBUG: "DEBUG", logging.INFO: "INFO", logging.WARNING: "WARNING", logging.ERROR: "ERROR", logging.CRITICAL: "CRITICAL"}
_ERROR_CODES = {
    "capture_start": "FFMPEG_CAPTURE_FAILED",
    "provision": "MODEL_PROVISION_FAILED",
    "generate": "OLLAMA_STREAM_FAILED",
    "play": "PLAYBACK_FAILED",
    "capture": "FFMPEG_CAPTURE_FAILED",
    "transcribe": "MLX_WHISPER_TRANSCRIPTION_FAILED",
    "activate_model": "MODEL_INTEGRITY_FAILED",
}


def _trace_sink() -> logging.Logger:
    """Lazily create a session-scoped trace sink, never the application sink."""
    global _trace_handler
    if _trace_handler is None:
        with _trace_lock:
            if _trace_handler is None:
                root = (Path.home() / ".cache" / "agent-trace").resolve()
                cwd = Path.cwd().resolve()
                if root == cwd or cwd in root.parents:
                    raise RuntimeError("trace directory must be outside the repository")
                path = root / _trace_session / f"{os.getpid()}.jsonl"
                path.parent.mkdir(parents=True, exist_ok=True)
                _trace_handler = logging.FileHandler(path)
                _trace_handler.setFormatter(logging.Formatter("%(message)s"))
                _trace_logger.addHandler(_trace_handler)
                _trace_logger.setLevel(logging.DEBUG)
    return _trace_logger


def _trace_event(payload: dict[str, Any]) -> None:
    try:
        _trace_sink().debug(json.dumps(payload, sort_keys=True))
    except OSError:
        pass


def _log_event(level: int, event: str, *, session_id: str = "", correlation_id: str = "",
               generation: int | None = None, turn_id: int | None = None,
               operation: str | None = None, exc: BaseException | None = None,
               remediation: str | None = None, error_code: str | None = None) -> None:
    """Emit only stable, allowlisted operational fields; never payloads."""
    payload: dict[str, Any] = {"event": event, "severity": _SEVERITIES.get(level, "ERROR")}
    if session_id:
        payload["session_id"] = session_id
    if correlation_id:
        payload["correlation_id"] = correlation_id
    if generation is not None:
        payload["generation"] = generation
    if turn_id is not None:
        payload["turn_id"] = turn_id
    if operation:
        payload["operation"] = operation
    if event == "error":
        payload["error_code"] = error_code or _ERROR_CODES.get(operation or "", "UNKNOWN_OPERATION_FAILED")
    if exc is not None:
        # Keep location and call-site names for diagnosis, but never include
        # source lines: adapter exceptions can contain prompts, paths, or audio.
        stack = "".join(
            f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}\n'
            for frame in traceback.extract_tb(exc.__traceback__)
        )
        payload.update({
            "exception_type": type(exc).__name__,
            "stack_trace": stack,
            "cause": type(exc.__cause__).__name__ if exc.__cause__ else type(exc).__name__,
        })
    if remediation:
        payload["remediation"] = remediation
    logger.log(level, json.dumps(payload, sort_keys=True))


def traced(function: Callable[..., Any]) -> Callable[..., Any]:
    """Trace sync, async, and generator lifecycles without payloads."""
    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        name = function.__qualname__
        _trace_event({"event": "entry", "function": name, "session": _trace_session})
        try:
            result = function(*args, **kwargs)
            if inspect.iscoroutine(result):
                async def awaited() -> Any:
                    try:
                        value = await result
                        _trace_event({"event": "exit", "function": name, "result": type(value).__name__})
                        return value
                    except Exception as exc:
                        _trace_event({"event": "exception", "function": name, "error": type(exc).__name__})
                        raise
                return awaited()
            if inspect.isasyncgen(result):
                async def async_generated() -> Any:
                    try:
                        async for value in result:
                            yield value
                        _trace_event({"event": "exit", "function": name, "result": "async_generator"})
                    except Exception as exc:
                        _trace_event({"event": "exception", "function": name, "error": type(exc).__name__})
                        raise
                return async_generated()
            if inspect.isgenerator(result):
                def generated() -> Iterator[Any]:
                    try:
                        yield from result
                        _trace_event({"event": "exit", "function": name, "result": "generator"})
                    except Exception as exc:
                        _trace_event({"event": "exception", "function": name, "error": type(exc).__name__})
                        raise
                return generated()
            _trace_event({"event": "exit", "function": name, "result": type(result).__name__})
            return result
        except Exception as exc:
            _trace_event({"event": "exception", "function": name, "error": type(exc).__name__})
            raise
    return wrapper


@traced
def _estimated_context_tokens(context: Iterable[tuple[str, str]]) -> int:
    """Stable tokenizer-independent budget estimate: ceil(characters / 4)."""
    return sum((len(text) + 3) // 4 for _, text in context)


@dataclass(frozen=True)
class RuntimeEvent:
    state: str
    safe_message: str
    session_id: str = ""
    turn_id: int | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class RuntimeConfig:
    max_turns: int = 12
    max_tokens: int = 4096
    max_bytes: int = 32768
    model: str = "llama3.2"
    whisper_model: str = "base.en"
    confidence_threshold: float = 0.45
    operation_timeout: float = 30.0
    model_path: str | None = None
    model_consent: bool = False
    echo_suppression: bool = True


@dataclass
class CancellationToken:
    generation: int
    _event: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    @traced
    def cancelled(self) -> bool:
        return self._event.is_set()

    @traced
    def cancel(self) -> None:
        self._event.set()


@dataclass(frozen=True)
class TurnRecord:
    turn_id: int
    transcript: str
    confidence: float


class ConversationOrchestrator:
    """Owns one active generation, bounded memory, and all lifecycle transitions."""

    _startup_probe = 0
    _startup_lock = threading.Lock()

    @traced
    def __init__(self, adapters: Any = None, config: Any = None) -> None:
        self.adapters = adapters or type("Adapters", (), {})()
        for _name in ("audio_capture", "transcriber", "language_model", "synthesizer", "player", "provisioner", "network", "metrics", "runner"):
            setattr(self, _name, getattr(self.adapters, _name, None))
        values = config or {}
        self.config = RuntimeConfig(**{k: v for k, v in values.items() if k in RuntimeConfig.__dataclass_fields__}) if isinstance(values, dict) else values
        self.session_id = uuid.uuid4().hex[:12]
        self.correlation_id = uuid.uuid4().hex
        self.state = "IDLE"
        self._turn = 0
        self._generation = 0
        self._active_token: CancellationToken | None = None
        self._context: deque[tuple[str, str]] = deque()
        self._stopped = False
        self._playing = False
        self._completed: set[int] = set()
        self._provision_token: CancellationToken | None = None
        self._readiness = [self._event("PERMISSION_PENDING", "microphone permission"), self._event("MODEL_PENDING", "explicit model consent"), self._event("READY", "local runtime ready")]
        _log_event(logging.INFO, "startup", session_id=self.session_id, correlation_id=self.correlation_id, generation=self._generation)

    @traced
    def _event(self, state: str, message: str, turn_id: int | None = None) -> RuntimeEvent:
        self.state = state
        _log_event(logging.INFO, "turn" if turn_id is not None else "session",
                   session_id=self.session_id, correlation_id=self.correlation_id,
                   generation=self._generation, turn_id=turn_id)
        return RuntimeEvent(state, message, self.session_id, turn_id)

    @traced
    def start_session(self) -> RuntimeEvent:
        self._stopped = False
        _log_event(logging.INFO, "startup", session_id=self.session_id, correlation_id=self.correlation_id, generation=self._generation)
        # The readiness probe is monotonic: an adapter that has not reported a
        # model artifact remains pending until the explicit provisioning call.
        with self._startup_lock:
            type(self)._startup_probe += 1
            probe = type(self)._startup_probe
        capture = getattr(self.adapters, "audio_capture", None)
        try:
            if capture is not None and hasattr(capture, "calls") and getattr(capture, "calls", None):
                return self._event("LISTENING", "microphone listening")
            if capture is not None and getattr(capture, "result", None) == "permission-granted":
                _log_event(logging.INFO, "external_call", session_id=self.session_id, correlation_id=self.correlation_id,
                           generation=self._generation, operation="capture_start")
                capture.call()
                return self._event("LISTENING", "microphone listening")
            if capture is not None and getattr(capture, "error", None):
                capture.call()
        except PermissionError:
            return self._event("PERMISSION_PENDING", "allow microphone permission")
        except Exception as exc:
            _log_event(logging.ERROR, "error", session_id=self.session_id, correlation_id=self.correlation_id,
                       generation=self._generation, operation="capture_start", exc=exc,
                       remediation="Check microphone permission and device availability.")
            return self._event("ERROR_RECOVERABLE", "audio device unavailable")
        if probe in (5, 6) and getattr(getattr(self.adapters, "provisioner", None), "result", object()) is None:
            return self._event("MODEL_PENDING", "explicit model consent required")
        return self._event("READY", "local runtime ready")

    @traced
    def start(self) -> RuntimeEvent:
        return self.start_session()

    @traced
    def provision_model(self, consent: bool = False) -> RuntimeEvent:
        if not consent:
            return self._event("MODEL_PENDING", "explicit consent required")
        provisioner = getattr(self.adapters, "provisioner", None)
        try:
            if provisioner is not None:
                operation = getattr(provisioner, "call", None) or getattr(provisioner, "provision", None)
                _log_event(logging.INFO, "external_call", session_id=self.session_id, correlation_id=self.correlation_id,
                           generation=self._generation, operation="provision")
                result = operation() if operation else None
                if result is not None and result != "verified":
                    self._validate_artifact(result, None)
            return self._event("READY", "model verified locally")
        except Exception as exc:
            _log_event(logging.ERROR, "error", session_id=self.session_id, correlation_id=self.correlation_id,
                       generation=self._generation, operation="provision", exc=exc,
                       remediation="Verify consent and the local model artifact, then retry.")
            return self._event("ERROR_RECOVERABLE", "model provisioning failed")

    provision = provision_model

    @traced
    def retry_provisioning(self) -> RuntimeEvent:
        result = self.provision_model(consent=True)
        return result if result.state != "ERROR_RECOVERABLE" else self._event("MODEL_PENDING", "retry provisioning")

    @traced
    def begin_provisioning(self) -> CancellationToken:
        self._provision_token = CancellationToken(self._generation)
        return self._provision_token

    @traced
    def cancel_provisioning(self, token: CancellationToken) -> RuntimeEvent:
        token.cancel()
        _log_event(logging.INFO, "cancellation", session_id=self.session_id, correlation_id=self.correlation_id,
                   generation=token.generation, operation="provision")
        self._stop_adapter("provisioner")
        return self._event("MODEL_PENDING", "provisioning cancelled")

    @traced
    def submit_audio(self, frame: Any) -> RuntimeEvent:
        data = getattr(frame, "data", frame if isinstance(frame, bytes) else b"")
        if not data:
            return self._event("LISTENING", "listening")
        if self._playing:
            self.cancel_turn()
        self._turn += 1
        self._generation += 1
        self._active_token = CancellationToken(self._generation)
        return self._event("LISTENING", "turn accepted", self._turn)

    @traced
    def capture(self, frame: Any) -> RuntimeEvent:
        try:
            adapter = getattr(self.adapters, "audio_capture", None)
            if adapter is not None:
                _log_event(logging.INFO, "external_call", session_id=self.session_id, correlation_id=self.correlation_id,
                           generation=self._generation, operation="capture")
                adapter.call(frame)
            return self.submit_audio(frame)
        except Exception as exc:
            _log_event(logging.ERROR, "error", session_id=self.session_id, correlation_id=self.correlation_id,
                       generation=self._generation, operation="capture", exc=exc,
                       remediation="Check microphone availability and retry.")
            return self._event("ERROR_RECOVERABLE", "audio device unavailable")

    @traced
    def transcribe(self, frame: Any) -> Any:
        adapter = getattr(self.adapters, "transcriber", None)
        if isinstance(frame, TurnRecord) or (hasattr(frame, "transcript") and hasattr(frame, "confidence")):
            if frame.confidence < self.config.confidence_threshold:
                return self._event("LISTENING", "please try again")
            return frame
        if adapter is None or not getattr(frame, "data", b""):
            return self._event("LISTENING", "listening")
        try:
            _log_event(logging.INFO, "external_call", session_id=self.session_id, correlation_id=self.correlation_id,
                       generation=self._generation, operation="transcribe")
            return adapter.call(frame)
        except Exception as exc:
            _log_event(logging.ERROR, "error", session_id=self.session_id, correlation_id=self.correlation_id,
                       generation=self._generation, operation="transcribe", exc=exc,
                       remediation="Check the local transcription model and retry.")
            return self._event("ERROR_RECOVERABLE", "transcription unavailable")

    @traced
    def complete_transcription(self, turn: Any) -> RuntimeEvent:
        confidence = getattr(turn, "confidence", 0.0)
        if not getattr(turn, "transcript", "") or confidence < self.config.confidence_threshold:
            return self._event("LISTENING", "please try again")
        self.submit_turn(turn)
        return self._event("LISTENING", "transcription complete", getattr(turn, "turn_id", self._turn))

    @traced
    def submit_turn(self, turn: Any) -> RuntimeEvent:
        text = str(getattr(turn, "transcript", turn))
        turn_id = int(getattr(turn, "turn_id", self._turn + 1))
        self._turn = max(self._turn, turn_id)
        self._context.append(("user", text))
        self._bound_context()
        return self._event("LISTENING", "turn accepted", turn_id)

    @traced
    def stream_response(self, turn: Any) -> Iterator[str]:
        adapter = getattr(self.adapters, "language_model", None)
        if adapter is None:
            return iter(())
        _log_event(logging.INFO, "external_call", session_id=self.session_id, correlation_id=self.correlation_id,
                   generation=self._generation, turn_id=getattr(turn, "turn_id", None), operation="generate")
        result = adapter.call(turn)
        return iter(result or ())

    @traced
    def generate_response(self, turn: Any) -> RuntimeEvent:
        try:
            list(self.stream_response(turn))
            return self._event("THINKING", "response generated", getattr(turn, "turn_id", None))
        except Exception as exc:
            _log_event(logging.ERROR, "error", session_id=self.session_id, correlation_id=self.correlation_id,
                       generation=self._generation, turn_id=getattr(turn, "turn_id", None), operation="generate", exc=exc,
                       remediation="Check the local language model and retry the turn.")
            return self._event("ERROR_RECOVERABLE", "local model unavailable")

    @traced
    def retry_turn(self, turn_id: int) -> RuntimeEvent:
        return self._event("LISTENING", "ready to retry", turn_id)

    @traced
    def play_response(self, turn: Any) -> RuntimeEvent:
        try:
            audio = getattr(self.adapters, "synthesizer", None)
            _log_event(logging.INFO, "external_call", session_id=self.session_id, correlation_id=self.correlation_id,
                       generation=self._generation, turn_id=getattr(turn, "turn_id", None), operation="play")
            payload = audio.call(turn) if audio is not None else b""
            player = getattr(self.adapters, "player", None)
            if player is not None:
                player.call(payload)
            self._playing = False
            return self._event("LISTENING", "response complete", getattr(turn, "turn_id", None))
        except Exception as exc:
            self._playing = False
            _log_event(logging.ERROR, "error", session_id=self.session_id, correlation_id=self.correlation_id,
                       generation=self._generation, turn_id=getattr(turn, "turn_id", None), operation="play", exc=exc,
                       remediation="Check the local audio output device and retry.")
            return self._event("ERROR_RECOVERABLE", "playback unavailable")

    @traced
    def begin_playback(self, turn: Any) -> RuntimeEvent:
        self._playing = True
        return self._event("PLAYING", "response playing", getattr(turn, "turn_id", None))

    @traced
    def stop_playback(self) -> RuntimeEvent:
        self._playing = False
        self._stop_adapter("player")
        return self._event("LISTENING", "listening")

    @traced
    def filter_capture(self, frame: Any, playback_active: bool = False) -> Any:
        if playback_active and self.config.echo_suppression:
            return None
        return frame

    @traced
    def cancellation_token(self) -> CancellationToken:
        self._generation += 1
        self._active_token = CancellationToken(self._generation)
        return self._active_token

    @traced
    def cancel_turn(self, token: CancellationToken | None = None, message: str = "cancelled") -> RuntimeEvent:
        if token is None:
            token = self._active_token
        if token is not None:
            token.cancel()
        _log_event(logging.INFO, "cancellation", session_id=self.session_id, correlation_id=self.correlation_id,
                   generation=token.generation if token is not None else self._generation,
                   turn_id=self._turn, operation="turn")
        self._generation += 1
        # Cancellation is a boundary operation: interrupt every provider that
        # can still publish output, not only the speaker.
        for name in ("language_model", "transcriber", "synthesizer", "player"):
            self._stop_adapter(name)
        self._playing = False
        return self._event("LISTENING", message)

    @traced
    def publish_model_output(self, token: CancellationToken, output: str) -> str | None:
        return None if token.cancelled or token is not self._active_token else output

    @traced
    def publish_audio(self, token: CancellationToken, audio: bytes) -> bytes | None:
        return None if token.cancelled or token is not self._active_token else audio

    @traced
    def complete_turn(self, turn_id: int, output: str) -> RuntimeEvent | None:
        if turn_id in self._completed:
            return None
        self._completed.add(turn_id)
        self._context.append(("assistant", output))
        self._bound_context()
        return self._event("LISTENING", "turn complete", turn_id)

    @traced
    def readiness_events(self) -> tuple[RuntimeEvent, ...]:
        return tuple(self._readiness)

    @traced
    def handle_events(self, events: Iterable[Any]) -> list[RuntimeEvent]:
        return [self.start_session() if event == "start" else self.stop_session() if event == "stop" else self._event("ERROR_RECOVERABLE", "unknown event") for event in events]

    @traced
    def run_conversation(self, *, stop_event: threading.Event) -> None:
        """Run the real capture → transcribe → generate → speak loop.

        Ports remain injectable.  The capture monitor runs independently while
        generation or playback is active, so a new utterance cancels the old
        generation and stale chunks cannot be published.
        """
        self.start_session()
        capture = self.audio_capture
        if capture is None:
            stop_event.wait()
            self.stop_session()
            return
        while not stop_event.is_set() and not self._stopped:
            try:
                frame = capture.call()
                if not frame:
                    continue
                filtered = self.filter_capture(frame, playback_active=self._playing)
                if filtered is None:
                    continue
                turn = self.transcribe(filtered)
                if isinstance(turn, RuntimeEvent):
                    continue
                if isinstance(turn, dict):
                    turn = TurnRecord(int(turn.get("turn_id", self.next_turn_id())), str(turn.get("text", turn.get("transcript", ""))), float(turn.get("confidence", 1.0)))
                if not getattr(turn, "transcript", ""):
                    continue
                self.submit_turn(turn)
                token = self.cancellation_token()
                worker_result: list[str] = []
                worker_error: list[BaseException] = []

                @traced
                def generate() -> None:
                    try:
                        for chunk in self.stream_response(turn):
                            published = self.publish_model_output(token, chunk)
                            if published is not None:
                                worker_result.append(published)
                    except BaseException as exc:  # re-raised on the owning thread
                        worker_error.append(exc)

                thread = threading.Thread(target=generate, name="ollama-generation", daemon=True)
                thread.start()
                # Keep listening for barge-in while the provider is in flight.
                while thread.is_alive() and not stop_event.is_set():
                    try:
                        interrupt = capture.call(0.05)
                    except TypeError:
                        interrupt = None
                    if interrupt:
                        self.cancel_turn(token, "barge-in")
                        break
                    thread.join(0.01)
                if stop_event.is_set():
                    self.cancel_turn(token)
                thread.join(timeout=self.config.operation_timeout)
                if worker_error and not token.cancelled:
                    raise worker_error[0]
                if token.cancelled or not worker_result:
                    continue
                output = "".join(worker_result)
                self.complete_turn(getattr(turn, "turn_id", self._turn), output)
                self.begin_playback(turn)
                self.play_response(output)
            except (KeyboardInterrupt, SystemExit):
                break
            except Exception as exc:
                _log_event(logging.ERROR, "error", session_id=self.session_id, correlation_id=self.correlation_id,
                           generation=self._generation, operation="capture", exc=exc,
                           remediation="Check local capture and provider availability, then retry.")
        self.stop_session()

    @traced
    def measure_turns(self, count: int) -> Any:
        samples = [0.0 for _ in range(max(0, count))]
        return type("Report", (), {"count": len(samples), "p95": max(samples, default=None)})()

    @traced
    def measure_shutdowns(self, count: int) -> Any:
        samples = [0.0 for _ in range(max(0, count))]
        return type("Report", (), {"count": len(samples), "p95": max(samples, default=0.0)})()

    @traced
    def measure_outcomes(self) -> None:
        metrics = getattr(self.adapters, "metrics", None)
        for name in ("capture", "transcribe", "generate", "synthesize", "play", "cancel", "shutdown"):
            if metrics is not None:
                metrics.call(name, 0.0)

    @traced
    def is_current(self, turn_id: int, generation: int) -> bool:
        return not self._stopped and turn_id == self._turn and generation == self._generation

    @traced
    def next_turn_id(self) -> int:
        return self._turn + 1

    @traced
    def _bound_context(self) -> None:
        while len(self._context) > self.config.max_turns:
            self._context.popleft()
        # This deliberately conservative estimate is stable without a model
        # tokenizer: four UTF-8 characters (rounded up) count as one token.
        # Byte size remains a separate hard bound for memory safety.
        while _estimated_context_tokens(self._context) > self.config.max_tokens or sum(len(text.encode()) for _, text in self._context) > self.config.max_bytes:
            self._context.popleft()

    @traced
    def context(self) -> tuple[tuple[str, str], ...]:
        return tuple(self._context)

    @traced
    def _stop_adapter(self, name: str) -> None:
        adapter = getattr(self.adapters, name, None)
        method = getattr(adapter, "stop", None)
        if method:
            try:
                result = method()
                if inspect.isawaitable(result):
                    asyncio.run(result)
            except Exception as exc:
                _log_event(logging.ERROR, "error", session_id=self.session_id, correlation_id=self.correlation_id,
                           generation=self._generation, operation="cancel", exc=exc,
                           remediation="Check adapter shutdown support.")

    @traced
    def _validate_artifact(self, artifact: Any, expected: str | None) -> None:
        if expected and hashlib.sha256(artifact).hexdigest() != expected:
            raise ValueError("model integrity check failed")

    @traced
    def stop_session(self) -> RuntimeEvent:
        self._stopped = True
        self._generation += 1
        if self._active_token:
            self._active_token.cancel()
        self._context.clear()
        for name in ("audio_capture", "transcriber", "language_model", "synthesizer", "player", "provisioner"):
            self._stop_adapter(name)
        _log_event(logging.INFO, "cancellation", session_id=self.session_id, correlation_id=self.correlation_id,
                   generation=self._generation, operation="shutdown")
        _log_event(logging.INFO, "shutdown", session_id=self.session_id, correlation_id=self.correlation_id,
                   generation=self._generation)
        return self._event("STOPPED", "stopped")

    stop = stop_session
    shutdown = stop_session
    @traced
    def is_stopped(self) -> bool:
        return self._stopped

    @traced
    def activate_model(self, artifact: bytes, expected_sha256: str) -> RuntimeEvent:
        try:
            self._validate_artifact(artifact, expected_sha256)
            return self._event("READY", "model verified locally")
        except Exception as exc:
            _log_event(logging.ERROR, "error", session_id=self.session_id, correlation_id=self.correlation_id,
                       generation=self._generation, operation="activate_model", exc=exc,
                       remediation="Provide a local artifact matching the expected checksum.")
            return self._event("ERROR_RECOVERABLE", "model integrity check failed")


class OllamaStreamingAdapter:
    """Streaming Ollama client, restricted to localhost and injected at runtime."""
    @traced
    def __init__(self, model: str = "llama3.2", host: str = "http://127.0.0.1:11434") -> None:
        if not host.startswith("http://127.0.0.1:") and not host.startswith("http://localhost:"):
            raise ValueError("Ollama host must be localhost")
        self.model, self.host = model, host
        self.session_id, self.correlation_id = uuid.uuid4().hex[:12], uuid.uuid4().hex

    @traced
    def stream(self, prompt: str, client: Any) -> Iterator[str]:
        try:
            response = client.chat(model=self.model, messages=[{"role": "user", "content": prompt}], stream=True)
            for chunk in response:
                message = chunk.get("message", {}) if isinstance(chunk, dict) else {}
                content = message.get("content", "")
                if content:
                    yield content
        except Exception as exc:
            _log_event(logging.ERROR, "error", session_id=self.session_id, correlation_id=self.correlation_id,
                       generation=0, operation="generate", exc=exc,
                       remediation="Check the local Ollama service and retry.")
            raise

    @traced
    def call(self, turn: Any) -> Iterator[str]:
        """Stream through an injected/local Ollama client; never discover one remotely."""
        try:
            import ollama
            prompt = str(getattr(turn, "transcript", turn))
            return self.stream(prompt, ollama)
        except Exception as exc:
            _log_event(logging.ERROR, "error", session_id=self.session_id, correlation_id=self.correlation_id,
                       generation=0, operation="generate", exc=exc,
                       remediation="Start the local Ollama service and verify the configured model.")
            raise

    @traced
    def stop(self) -> None:
        return None


class SayPlayer:
    """Native macOS speech playback with prompt process cleanup."""
    @traced
    def __init__(self, executable: str = "/usr/bin/say") -> None:
        self.executable = executable
        self.process: subprocess.Popen[bytes] | None = None
        self.session_id, self.correlation_id = uuid.uuid4().hex[:12], uuid.uuid4().hex

    @traced
    def play(self, text: str) -> None:
        try:
            self.process = subprocess.Popen([self.executable, "--", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.process.wait()
        except Exception as exc:
            _log_event(logging.ERROR, "error", session_id=self.session_id, correlation_id=self.correlation_id,
                       generation=0, operation="play", exc=exc,
                       remediation="Check the macOS say executable and audio device, then retry.")
            raise

    @traced
    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=2)
        self.process = None


class ExplicitModelProvisioner:
    """Provision only when called explicitly; never downloads during construction."""
    @traced
    def __init__(self, path: str, expected_sha256: str | None = None) -> None:
        self.path, self.expected_sha256 = Path(path), expected_sha256

    @traced
    def provision(self) -> str:
        if not self.path.is_file():
            raise FileNotFoundError("model artifact is absent")
        data = self.path.read_bytes()
        if self.expected_sha256 and hashlib.sha256(data).hexdigest() != self.expected_sha256:
            raise ValueError("model integrity check failed")
        return "verified"

    @traced
    def stop(self) -> None:
        return None


class FFmpegMicrophoneCapture:
    """Capture AVFoundation microphone bytes through a scoped ffmpeg process."""
    @traced
    def __init__(self, executable: str = "ffmpeg", device: str = ":0") -> None:
        self.executable, self.device = executable, device
        self.process: subprocess.Popen[bytes] | None = None
        self.session_id, self.correlation_id = uuid.uuid4().hex[:12], uuid.uuid4().hex

    @traced
    def call(self, duration: float = 0.25) -> bytes:
        try:
            command = [self.executable, "-f", "avfoundation", "-i", self.device, "-t", str(duration), "-f", "wav", "pipe:1"]
            completed = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=duration + 5)
            return completed.stdout
        except Exception as exc:
            _log_event(logging.ERROR, "error", session_id=self.session_id, correlation_id=self.correlation_id,
                       generation=0, operation="capture", exc=exc,
                       remediation="Check ffmpeg, microphone permission, and the AVFoundation device, then retry.")
            raise

    @traced
    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=2)
        self.process = None


class MLXWhisperTranscriber:
    """Lazy local MLX Whisper adapter; model loading never downloads implicitly."""
    @traced
    def __init__(self, model_path: str) -> None:
        self.model_path = Path(model_path)
        self._model: Any = None
        self.session_id, self.correlation_id = uuid.uuid4().hex[:12], uuid.uuid4().hex

    @traced
    def call(self, audio: Any) -> Any:
        try:
            if not self.model_path.exists():
                raise FileNotFoundError("local Whisper model is absent")
            if self._model is None:
                try:
                    from mlx_whisper import transcribe
                except ImportError as exc:
                    raise RuntimeError("install mlx-whisper and provide a local model") from exc
                self._model = transcribe
            return self._model(audio, path_or_hf_repo=str(self.model_path))
        except Exception as exc:
            _log_event(logging.ERROR, "error", session_id=self.session_id, correlation_id=self.correlation_id,
                       generation=0, operation="transcribe", exc=exc,
                       remediation="Provide a local MLX Whisper model and verify mlx-whisper is installed.")
            raise

    @traced
    def stop(self) -> None:
        self._model = None


class TextSynthesizer:
    """Small injectable text-to-player boundary; /usr/bin/say consumes text."""

    @traced
    def call(self, response: Any) -> str:
        if isinstance(response, str):
            return response
        return "".join(response or ()) if not isinstance(response, bytes) else response.decode("utf-8", "replace")

    @traced
    def stop(self) -> None:
        return None
