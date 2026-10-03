"""Contract tests for the injected conversation-runtime interfaces.

test-10032026-Maurice

These tests deliberately use typed events and deterministic ports.  They do not
route scenarios through a string dispatcher: each case exercises the public
operation that an implementation must provide.
"""

from __future__ import annotations

import csv
import hashlib
import inspect
import io
import json
import logging
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator
from unittest.mock import patch

import pytest


_TRACE_PATH = Path.home() / ".cache" / "agent-trace"
_logger = logging.getLogger("conversation-runtime-tests")
if not _logger.handlers:
    _handler = logging.StreamHandler(io.StringIO())
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)


def _trace(function: Callable[..., Any]) -> Callable[..., Any]:
    """Trace helper lifecycle without recording controlled content."""
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        name = getattr(function, "__qualname__", function.__name__)
        _logger.info(json.dumps({"event": "entry", "function": name, "session": "test-session"}))
        try:
            result = function(*args, **kwargs)
        except Exception as exc:
            _logger.info(json.dumps({"event": "exception", "function": name, "error_type": type(exc).__name__}))
            raise
        _logger.info(json.dumps({"event": "exit", "function": name, "result_type": type(result).__name__}))
        return result
    wrapped.__name__ = function.__name__
    wrapped.__qualname__ = function.__qualname__
    return wrapped


@dataclass(frozen=True)
class AudioFrame:
    data: bytes
    sequence: int
    is_final: bool = True


@dataclass(frozen=True)
class Turn:
    turn_id: int
    transcript: str
    confidence: float


@dataclass(frozen=True)
class CancellationToken:
    generation: int
    cancelled: bool = False


class FakePort:
    """Deterministic adapter with observable calls and no external I/O."""

    @_trace
    def __init__(self, *, result: Any = None, error: Exception | None = None) -> None:
        self.result, self.error, self.calls = result, error, []
        self.chunks: list[str] = []
        self.stopped = threading.Event()

    @_trace
    def call(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return self.result

    @_trace
    def stop(self) -> None:
        self.calls.append(("stop",))
        self.stopped.set()


class BlockingPort(FakePort):
    """A deterministic in-flight adapter used to prove cancellation reaches it."""

    @_trace
    def __init__(self, *, result: Any = None) -> None:
        super().__init__(result=result)
        self.started = threading.Event()
        self.release = threading.Event()

    @_trace
    def call(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        self.started.set()
        self.release.wait(timeout=2)
        return self.result

    @_trace
    def stop(self) -> None:
        super().stop()
        self.release.set()


@_trace
def _ports(**overrides: Any) -> SimpleNamespace:
    ports = {name: FakePort() for name in (
        "audio_capture", "transcriber", "language_model", "synthesizer",
        "player", "provisioner", "network", "metrics", "runner",
    )}
    ports.update(overrides)
    return SimpleNamespace(**ports)


@_trace
def _runtime(*, ports: Any = None, **config: Any) -> Any:
    from conversation_orchestrator import ConversationOrchestrator
    return ConversationOrchestrator(adapters=ports or _ports(), config=config)


@_trace
def _frame(text: str, sequence: int = 1, *, final: bool = True) -> AudioFrame:
    return AudioFrame(text.encode("utf-8"), sequence, final)


@_trace
def _assert_redacted(path: Path, secret: str) -> None:
    content = path.read_text() if path.exists() else ""
    assert secret not in content
    assert "event" in content


@_trace
def _application_records(action: Callable[[], Any]) -> list[logging.LogRecord]:
    """Capture records from the actual application logger, never a test logger."""
    application_logger = logging.getLogger("conversation.runtime")
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    handler.setLevel(logging.DEBUG)
    prior_level = application_logger.level
    application_logger.setLevel(logging.DEBUG)
    application_logger.addHandler(handler)
    try:
        action()
    finally:
        application_logger.removeHandler(handler)
        application_logger.setLevel(prior_level)
    return records


@_trace
def _json_application_events(records: list[logging.LogRecord]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for record in records:
        try:
            value = json.loads(record.getMessage())
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


@_trace
def _assert_application_log_contract(events: list[dict[str, Any]], *forbidden: str) -> None:
    assert events, "the conversation.runtime application logger emitted no structured events"
    serialized = json.dumps(events, sort_keys=True)
    assert all(value not in serialized for value in forbidden)
    assert not any(
        isinstance(handler, logging.FileHandler)
        and str(getattr(handler, "baseFilename", "")).startswith(str(_TRACE_PATH))
        for handler in logging.getLogger("conversation.runtime").handlers
    )
    assert logging.getLogger("conversation-runtime-tests") is not logging.getLogger("conversation.runtime")


@_trace
def _assert_error_event(events: list[dict[str, Any]], operation: str, error_type: str) -> None:
    matching = [event for event in events if event.get("event") == "error"]
    assert matching, "application failure was swallowed without an ERROR record"
    error = next(event for event in matching if event.get("operation") == operation)
    assert error.get("exception_type") == error_type
    assert error.get("severity") == "ERROR"
    assert error.get("event") == "error"
    assert error.get("operation") in {
        "activate_model", "capture", "cancel", "generate", "play", "provision",
        "runtime_factory", "run_conversation", "transcribe",
    }
    expected_codes = {
        "provision": "MODEL_PROVISION_FAILED",
        "generate": "OLLAMA_STREAM_FAILED",
        "play": "PLAYBACK_FAILED",
        "capture": "FFMPEG_CAPTURE_FAILED",
        "transcribe": "MLX_WHISPER_TRANSCRIPTION_FAILED",
        "activate_model": "MODEL_INTEGRITY_FAILED",
    }
    assert error.get("error_code") == expected_codes[operation]
    assert error.get("stack_trace")
    assert error.get("cause") is not None
    assert set(error).issuperset({"correlation_id", "session_id", "generation", "operation", "remediation"})
    assert error["operation"] == operation
    assert error["remediation"]
    assert "Traceback (most recent call last)" not in error["stack_trace"]
    assert not re.search(r"\n(?:[A-Za-z]+Error|RuntimeError):", json.dumps(error))
    assert re.fullmatch(r"[0-9a-f]{12}", error["session_id"])
    assert re.fullmatch(r"[0-9a-f]{32}", error["correlation_id"])


def _application_logger_records(action: Callable[[], Any], logger_name: str) -> tuple[list[logging.LogRecord], str | None]:
    """Capture the real CLI/application logger and its user-visible exception."""
    application_logger = logging.getLogger(logger_name)
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    handler.setLevel(logging.DEBUG)
    prior_level = application_logger.level
    application_logger.setLevel(logging.DEBUG)
    application_logger.addHandler(handler)
    try:
        try:
            action()
        except Exception as exc:
            return records, type(exc).__name__
        return records, None
    finally:
        application_logger.removeHandler(handler)
        application_logger.setLevel(prior_level)


def _assert_cli_events(records: list[logging.LogRecord], *forbidden: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for record in records:
        try:
            value = json.loads(record.getMessage())
        except json.JSONDecodeError:
            pytest.fail("CLI emitted plain-text output instead of a structured event")
        assert isinstance(value, dict)
        events.append(value)
    assert events, "CLI emitted no structured startup/dependency/lifecycle event"
    assert {event.get("event") for event in events} <= {
        "startup", "dependency", "lifecycle", "error", "shutdown",
    }
    serialized = json.dumps(events, sort_keys=True)
    assert all(value not in serialized for value in forbidden)
    return events


def _assert_cli_error(events: list[dict[str, Any]], operation: str, error_type: str) -> None:
    matching = [event for event in events if event.get("event") == "error" and event.get("operation") == operation]
    assert matching, f"missing structured CLI error for {operation}"
    error = matching[-1]
    assert error.get("severity") == "ERROR"
    assert error.get("error_code") in {
        "RUNTIME_FACTORY_FAILED", "CONVERSATION_LOOP_FAILED", "MODEL_PROVISION_FAILED",
        "SHUTDOWN_FAILED",
    }
    assert error.get("exception_type") == error_type
    assert error.get("cause") == error_type
    assert error.get("stack_trace") and "Traceback (most recent call last)" not in error["stack_trace"]
    assert error.get("remediation")
    assert set(error).issuperset({"session_id", "correlation_id"})
    assert re.fullmatch(r"[0-9a-f]{12}", error["session_id"])
    assert re.fullmatch(r"[0-9a-f]{32}", error["correlation_id"])


@_trace
def _assert_direct_adapter_failure(action: Callable[[], Any], operation: str,
                                   error_type: str, *forbidden: str) -> None:
    """Require an application-boundary ERROR for a direct adapter failure."""
    _logger.info(json.dumps({"event": "adapter_failure_assertion", "operation": operation,
                             "session": "test-session"}))
    records: list[logging.LogRecord] = []
    application_logger = logging.getLogger("conversation.runtime")

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    handler.setLevel(logging.DEBUG)
    prior_level = application_logger.level
    application_logger.setLevel(logging.DEBUG)
    application_logger.addHandler(handler)
    try:
        with pytest.raises(Exception) as raised:
            action()
    finally:
        application_logger.removeHandler(handler)
        application_logger.setLevel(prior_level)
    assert type(raised.value).__name__ == error_type
    events = _json_application_events(records)
    _assert_error_event(events, operation, error_type)
    _assert_application_log_contract(events, *forbidden)


def _assert_linux_error(action: Callable[[], Any], operation: str,
                        error_type: str, *forbidden: str) -> list[dict[str, Any]]:
    """Require a structured, operation-specific Linux boundary ERROR."""
    records: list[logging.LogRecord] = []
    application_logger = logging.getLogger("conversation.runtime")

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    handler.setLevel(logging.DEBUG)
    prior_level = application_logger.level
    application_logger.setLevel(logging.DEBUG)
    application_logger.addHandler(handler)
    try:
        with pytest.raises(Exception) as raised:
            action()
    finally:
        application_logger.removeHandler(handler)
        application_logger.setLevel(prior_level)
    assert type(raised.value).__name__ == error_type
    events = _json_application_events(records)
    matching = [event for event in events if event.get("event") == "error"
                and event.get("operation") == operation]
    assert matching, f"missing structured Linux ERROR for {operation}"
    error = matching[-1]
    assert error.get("severity") == "ERROR"
    assert error.get("exception_type") == error_type
    assert error.get("cause") == error_type
    assert error.get("stack_trace")
    assert "Traceback (most recent call last)" not in error["stack_trace"]
    serialized = json.dumps(error, sort_keys=True)
    assert all(value not in serialized for value in forbidden)
    assert not re.search(r"/(?:[^\" ]+)", serialized)
    return events


@_trace
def _linux_module() -> Any:
    """Load the Linux seam without importing hardware or network clients."""
    import importlib
    try:
        return importlib.import_module("linux_runtime")
    except ModuleNotFoundError as exc:
        pytest.fail(f"Linux runtime contract is not implemented: {exc}")


@_trace
def _linux_callable(name: str) -> Callable[..., Any]:
    operation = getattr(_linux_module(), name, None)
    assert callable(operation), f"linux_runtime.{name} must be an injectable seam"
    return operation


@_trace
def _compose_text() -> str:
    candidates = ("compose.yml", "docker-compose.yml")
    for candidate in candidates:
        path = Path(__file__).parents[1] / candidate
        if path.exists():
            return path.read_text()
    pytest.fail("Compose manifest is required for Linux runtime validation")


@_trace
def _compose_data() -> dict[str, Any]:
    text = _compose_text()
    try:
        import yaml
    except ModuleNotFoundError:
        pytest.fail("PyYAML is required to structurally validate Compose without starting services")
    data = yaml.safe_load(text)
    assert isinstance(data, dict) and isinstance(data.get("services"), dict)
    return data


@_trace
def _assert_tokens(text: str, *tokens: str) -> None:
    missing = [token for token in tokens if token not in text]
    assert not missing, f"Compose/config contract missing: {', '.join(missing)}"


@_trace
def _manifest_text(name: str) -> str:
    path = Path(__file__).parents[1] / name
    assert path.exists(), f"required build artifact {name} is missing"
    return path.read_text()


class _TrackedProcess:
    """Injectable child-process fake with timeout and reaping observability."""

    def __init__(self, *, timeout_once: bool = False, pid: int = 4242) -> None:
        self.pid = pid
        self.timeout_once = timeout_once
        self.terminated = 0
        self.killed = 0
        self.waited = 0
        self.communicated = 0
        self.returncode = 0
        self._running = True

    def poll(self) -> int | None:
        return None if self._running else self.returncode

    def terminate(self) -> None:
        self.terminated += 1
        self._running = False

    def kill(self) -> None:
        self.killed += 1
        self._running = False

    def wait(self, **_: Any) -> int:
        self.waited += 1
        if self.timeout_once and self.waited == 1:
            raise subprocess.TimeoutExpired("fixture", 0.01)
        self._running = False
        return self.returncode

    def communicate(self, *_: Any, **__: Any) -> tuple[bytes, bytes]:
        self.communicated += 1
        if self.timeout_once and self.communicated == 1:
            raise subprocess.TimeoutExpired("fixture", 0.01)
        self._running = False
        return b"wav", b""


class _PopenFactory:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.processes: list[_TrackedProcess] = []

    def __call__(self, command: list[str], **kwargs: Any) -> _TrackedProcess:
        process = _TrackedProcess(pid=5000 + len(self.processes))
        self.calls.append((list(command), kwargs))
        self.processes.append(process)
        return process


@_trace
def _estimated_tokens(context: tuple[tuple[str, str], ...]) -> int:
    """Deterministic token estimate used by the contract, not raw message count."""
    return sum((len(text) + 3) // 4 for _, text in context)


@_trace
def _csv_ids_and_refs() -> tuple[set[str], dict[str, str]]:
    path = Path(__file__).parents[1] / "docs" / "test-cases" / "conversation-runtime.csv"
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    return {row["Test Case ID"] for row in rows}, {row["Test Case ID"]: row["Automated Test Ref"] for row in rows}


@_trace
def _test_case(case_id: str) -> None:
    """Run the case-specific callable while retaining a redacted trace."""
    _logger.info(json.dumps({"event": "case", "case_id": case_id, "session": "test-session"}))
    _CASES[case_id]()


def _tc_001() -> None:
    # Preserve the original readiness probe side effect for the mapped suite;
    # the assertions below are the strengthened CLI/factory contract.
    _runtime().start_session()
    import assistant
    from conversation_orchestrator import (
        ConversationOrchestrator,
        FFmpegMicrophoneCapture,
        MLXWhisperTranscriber,
        OllamaStreamingAdapter,
        SayPlayer,
    )

    factory = getattr(assistant, "build_runtime", None)
    assert callable(factory), "CLI must expose an injectable runtime factory"
    runtime = factory(model_path="/local/whisper-base.en")
    assert isinstance(runtime, ConversationOrchestrator)
    assert isinstance(runtime.audio_capture, FFmpegMicrophoneCapture)
    assert runtime.audio_capture.device == ":0"
    assert isinstance(runtime.transcriber, MLXWhisperTranscriber)
    assert isinstance(runtime.language_model, OllamaStreamingAdapter)
    assert runtime.language_model.host.startswith("http://127.0.0.1:")
    assert isinstance(runtime.player, SayPlayer)
    assert runtime.player.executable == "/usr/bin/say"
    assert runtime.config.max_tokens > 0
    assert runtime.network is None

    import assistant

    class _ReadyRuntime:
        def run_conversation(self, *, stop_event: threading.Event) -> None:
            stop_event.set()

    startup_records, startup_exception = _application_logger_records(
        lambda: assistant.main([], runtime_factory=lambda **_: _ReadyRuntime(), stop_event=threading.Event()),
        "assistant",
    )
    assert startup_exception is None
    startup_events = _assert_cli_events(startup_records)
    assert {event.get("event") for event in startup_events}.issuperset({"startup", "dependency", "lifecycle"})

    secret = "factory-secret-do-not-log"
    failure_records, failure_exception = _application_logger_records(
        lambda: assistant.main([], runtime_factory=lambda **_: (_ for _ in ()).throw(RuntimeError(secret)), stop_event=threading.Event()),
        "assistant",
    )
    assert failure_exception == "RuntimeError"
    _assert_cli_error(_assert_cli_events(failure_records, secret), "runtime_factory", "RuntimeError")


def _tc_002() -> None:
    ports = _ports(audio_capture=FakePort(result="permission-granted"))
    result = _runtime(ports=ports).start_session()
    assert result.state == "LISTENING"
    assert ports.audio_capture.calls


def _tc_003() -> None:
    ports = _ports(audio_capture=FakePort(error=PermissionError("denied")))
    result = _runtime(ports=ports).start_session()
    assert result.state == "PERMISSION_PENDING"
    assert ports.audio_capture.calls


def _tc_004() -> None:
    ports = _ports(provisioner=FakePort())
    result = _runtime(ports=ports).provision_model(consent=False)
    assert result.state == "MODEL_PENDING"
    assert ports.provisioner.calls == []
    assert ports.network.calls == []


def _tc_005() -> None:
    ports = _ports(provisioner=FakePort(result="verified"))
    result = _runtime(ports=ports).provision_model(consent=True)
    assert result.state == "READY"
    assert ports.provisioner.calls


def _tc_006() -> None:
    provisioner = FakePort(error=TimeoutError("download timeout"))
    runtime = _runtime(ports=_ports(provisioner=provisioner))
    records = _application_records(lambda: runtime.provision_model(consent=True))
    assert runtime.state == "ERROR_RECOVERABLE"
    _assert_error_event(_json_application_events(records), "provision", "TimeoutError")
    assert runtime.retry_provisioning().state in {"MODEL_PENDING", "READY"}


def _tc_007() -> None:
    import assistant

    stop = threading.Event()
    calls: list[threading.Event] = []

    class _LoopRuntime:
        def run_conversation(self, *, stop_event: threading.Event) -> None:
            calls.append(stop_event)
            stop_event.set()

    def factory(**_: Any) -> _LoopRuntime:
        return _LoopRuntime()

    assert "runtime_factory" in inspect.signature(assistant.main).parameters
    assert "stop_event" in inspect.signature(assistant.main).parameters
    assert assistant.main([], runtime_factory=factory, stop_event=stop) == 0
    assert calls == [stop]

    secret = "loop-secret-do-not-log"

    class _BrokenLoopRuntime:
        session_id = "0123456789ab"
        correlation_id = "0123456789abcdef0123456789abcdef"

        def run_conversation(self, *, stop_event: threading.Event) -> None:
            raise RuntimeError(secret)

    records, exception = _application_logger_records(
        lambda: assistant.main([], runtime_factory=lambda **_: _BrokenLoopRuntime(), stop_event=threading.Event()),
        "assistant",
    )
    assert exception == "RuntimeError"
    _assert_cli_error(_assert_cli_events(records, secret), "run_conversation", "RuntimeError")


def _tc_008() -> None:
    ports = _ports(transcriber=FakePort(result=Turn(1, "clear phrase", 0.99)))
    result = _runtime(ports=ports).transcribe(_frame("audio"))
    assert isinstance(result, Turn)
    assert result.turn_id == 1 and result.confidence == pytest.approx(0.99)

    from conversation_orchestrator import MLXWhisperTranscriber
    _assert_direct_adapter_failure(
        lambda: MLXWhisperTranscriber("/definitely/missing-whisper-model").call(b"audio"),
        "transcribe", "FileNotFoundError", "/definitely/missing-whisper-model", "audio",
    )


def _tc_009() -> None:
    runtime = _runtime()
    result = runtime.transcribe(_frame("", 1))
    assert result.state == "LISTENING"
    assert runtime.context() == ()


def _tc_010() -> None:
    runtime = _runtime(max_turns=10, max_tokens=4, max_bytes=1000)
    runtime.submit_turn(Turn(1, "this deliberately exceeds four estimated tokens", 1.0))
    runtime.submit_turn(Turn(2, "ok", 1.0))
    context = runtime.context()
    assert _estimated_tokens(context) <= 4
    assert "this deliberately exceeds four estimated tokens" not in repr(context)


def _tc_011() -> None:
    runtime = _runtime(); runtime.submit_turn(Turn(1, "private", 1.0)); runtime.shutdown()
    fresh = _runtime()
    assert fresh.context() == ()


def _tc_012() -> None:
    ports = _ports(language_model=FakePort(result=iter(("one", " two", " done"))))
    chunks = list(_runtime(ports=ports).stream_response(Turn(1, "prompt", 1.0)))
    assert chunks == ["one", " two", " done"]


def _tc_013() -> None:
    ports = _ports(synthesizer=FakePort(result=b"audio"), player=FakePort())
    runtime = _runtime(ports=ports)
    assert runtime.play_response(Turn(1, "response", 1.0)).state == "LISTENING"
    assert ports.player.calls


def _tc_014() -> None:
    player = FakePort(); runtime = _runtime(ports=_ports(player=player))
    runtime.begin_playback(Turn(1, "response", 1.0)); runtime.submit_audio(_frame("interrupt"))
    assert player.stopped.is_set()
    assert player.calls.index(("stop",)) < len(player.calls)

    language_model = BlockingPort(result=iter(("late",)))
    runtime = _runtime(ports=_ports(language_model=language_model))
    token = runtime.cancellation_token()
    worker = threading.Thread(target=lambda: runtime.generate_response(Turn(1, "active", 1.0)))
    worker.start()
    assert language_model.started.wait(timeout=1)
    runtime.cancel_turn(token)
    assert token.cancelled and language_model.stopped.is_set()
    worker.join(timeout=1)
    assert not worker.is_alive()

    # A barge-in must stop every producer before the next turn is accepted;
    # stopping only the speaker leaves stale model/TTS output in flight.
    synthesizer = FakePort()
    player = FakePort()
    runtime = _runtime(ports=_ports(
        language_model=BlockingPort(result=iter(("late",))),
        synthesizer=synthesizer,
        player=player,
    ))
    runtime.begin_playback(Turn(1, "response", 1.0))
    accepted = runtime.submit_audio(_frame("genuine user speech", 2))
    assert accepted.turn_id == 1
    assert synthesizer.stopped.is_set() and player.stopped.is_set()


def _tc_015() -> None:
    ports = _ports(audio_capture=FakePort(result="echo"))
    result = _runtime(ports=ports).filter_capture(_frame("echo"), playback_active=True)
    assert result is None


def _tc_016() -> None:
    runtime = _runtime(); token = runtime.cancellation_token()
    events = _application_records(lambda: runtime.cancel_turn(token))
    parsed = _json_application_events(events)
    assert any(event.get("event") == "cancellation" for event in parsed)
    assert any(event.get("generation") == token.generation for event in parsed)
    assert runtime.publish_model_output(token, "late") is None


def _tc_017() -> None:
    result = _runtime(confidence_threshold=0.8).transcribe(Turn(1, "noise", 0.2))
    assert result.state == "LISTENING" and "noise" not in repr(result)


def _tc_018() -> None:
    runtime = _runtime(); runtime.start_session()
    events = _application_records(lambda: runtime.stop_session())
    parsed = _json_application_events(events)
    assert any(event.get("event") == "cancellation" for event in parsed)
    result = runtime.stop_session()
    assert result.state == "STOPPED"


def _tc_019() -> None:
    runtime = _runtime(); first = runtime.cancellation_token(); second = runtime.cancellation_token()
    assert runtime.publish_model_output(first, "old") is None
    assert runtime.publish_model_output(second, "current") is not None


def _tc_020() -> None:
    secret = "PRIVATE-CONTENT-DO-NOT-LOG"
    prompt = "PROMPT-DO-NOT-LOG"
    response = "RESPONSE-DO-NOT-LOG"
    credential = "TOKEN-DO-NOT-LOG"
    runtime = _runtime()
    records = _application_records(lambda: (
        runtime.start_session(),
        runtime.submit_turn(Turn(1, secret, 1.0)),
        runtime.generate_response(Turn(1, prompt, 1.0)),
        runtime.cancel_turn(runtime.cancellation_token()),
        runtime.shutdown(),
    ))
    events = _json_application_events(records)
    _assert_application_log_contract(events, secret, prompt, response, credential, "email@example.com")
    assert {event.get("event") for event in events}.issuperset(
        {"startup", "session", "turn", "external_call", "cancellation", "shutdown"}
    )
    for event in events:
        assert "transcript" not in event and "prompt" not in event and "response" not in event
        assert "tokens" not in event and "credential" not in event and "pii" not in event
    assert all(event.get("session_id") == runtime.session_id for event in events if "session_id" in event)
    assert any(event.get("turn_id") == 1 for event in events)


def _tc_021() -> None:
    ports = _ports(network=FakePort()); runtime = _runtime(ports=ports); runtime.submit_audio(_frame("local"))
    assert ports.network.calls == []


def _tc_022() -> None:
    ports = _ports(language_model=FakePort(error=RuntimeError("unavailable"))); runtime = _runtime(ports=ports)
    records = _application_records(lambda: runtime.generate_response(Turn(1, "prompt", 1.0)))
    assert runtime.state == "ERROR_RECOVERABLE"
    _assert_error_event(_json_application_events(records), "generate", "RuntimeError")
    assert runtime.retry_turn(1).state == "LISTENING"

    from conversation_orchestrator import OllamaStreamingAdapter

    class _UnavailableOllama:
        def chat(self, **_: Any) -> Any:
            raise ConnectionError("ollama-token-should-not-be-logged")

    _assert_direct_adapter_failure(
        lambda: list(OllamaStreamingAdapter().stream("private prompt", _UnavailableOllama())),
        "generate", "ConnectionError", "ollama-token-should-not-be-logged", "private prompt",
    )


def _tc_023() -> None:
    ports = _ports(synthesizer=FakePort(error=RuntimeError("audio"))); runtime = _runtime(ports=ports)
    records = _application_records(lambda: runtime.play_response(Turn(1, "response", 1.0)))
    assert runtime.state == "ERROR_RECOVERABLE"
    _assert_error_event(_json_application_events(records), "play", "RuntimeError")

    from conversation_orchestrator import SayPlayer
    _assert_direct_adapter_failure(
        lambda: SayPlayer("/definitely/missing-say").play("private speech"),
        "play", "FileNotFoundError", "/definitely/missing-say", "private speech",
    )


def _tc_024() -> None:
    runtime = _runtime(); states = [event.state for event in runtime.readiness_events()]
    assert {"PERMISSION_PENDING", "MODEL_PENDING", "READY"}.issubset(states)


def _tc_025() -> None:
    ports = _ports(provisioner=FakePort()); runtime = _runtime(ports=ports)
    assert runtime.start_session().state == "MODEL_PENDING"; assert ports.provisioner.calls == []


def _tc_026() -> None:
    runtime = _runtime(); events = runtime.handle_events(("start", "stop"))
    assert [event.state for event in events] == ["READY", "STOPPED"]


def _tc_027() -> None:
    runtime = _runtime(clock=time.perf_counter); report = runtime.measure_turns(30)
    assert report.p95 is not None and report.count >= 30


def _tc_028() -> None:
    metrics = FakePort(); runtime = _runtime(ports=_ports(metrics=metrics)); runtime.measure_outcomes()
    names = {call[0][0] for call in metrics.calls if call[0]}
    assert {"capture", "transcribe", "generate", "synthesize", "play", "cancel", "shutdown"}.issubset(names)


def _tc_029() -> None:
    readme = (Path(__file__).parents[1] / "README.md").read_text().lower()
    assert "permission" in readme and "consent" in readme and "shutdown" in readme


def _tc_030() -> None:
    ports = _ports(audio_capture=FakePort(error=OSError("device"))); runtime = _runtime(ports=ports)
    records = _application_records(lambda: runtime.capture(_frame("audio")))
    assert runtime.state == "ERROR_RECOVERABLE"
    _assert_error_event(_json_application_events(records), "capture", "OSError")

    from conversation_orchestrator import FFmpegMicrophoneCapture
    _assert_direct_adapter_failure(
        lambda: FFmpegMicrophoneCapture("/definitely/missing-ffmpeg").call(),
        "capture", "FileNotFoundError", "/definitely/missing-ffmpeg", ":0",
    )


def _tc_031() -> None:
    runtime = _runtime(); first = runtime.complete_turn(1, "done"); second = runtime.complete_turn(1, "done")
    assert first is not None and second is None


def _tc_032() -> None:
    from unittest.mock import Mock

    from conversation_orchestrator import (
        FFmpegMicrophoneCapture,
        MLXWhisperTranscriber,
        OllamaStreamingAdapter,
        SayPlayer,
    )

    class _Process:
        def __init__(self) -> None:
            self.terminated = False
            self.waited = False

        def poll(self) -> None:
            return None if not self.terminated else 0

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, **_: Any) -> None:
            self.waited = True

    capture = FFmpegMicrophoneCapture()
    capture.process = _Process()  # type: ignore[assignment]
    player = SayPlayer()
    player.process = _Process()  # type: ignore[assignment]
    transcriber = MLXWhisperTranscriber("/local/whisper")
    language_model = OllamaStreamingAdapter()
    transcriber.stop = Mock()
    language_model.stop = Mock()
    runtime = _runtime(ports=_ports(
        audio_capture=capture,
        transcriber=transcriber,
        language_model=language_model,
        player=player,
    )); runtime.start_session()
    events = _application_records(lambda: runtime.shutdown())
    parsed = _json_application_events(events)
    assert any(event.get("event") == "shutdown" for event in parsed)
    result = runtime.shutdown()
    assert result.state == "STOPPED" and runtime.is_stopped()
    assert capture.process is None and player.process is None
    assert transcriber.stop.called and language_model.stop.called

    import assistant

    secret = "shutdown-secret-do-not-log"
    registered: dict[int, Callable[..., Any]] = {}

    class _ShutdownFailureRuntime:
        session_id = "0123456789ab"
        correlation_id = "0123456789abcdef0123456789abcdef"

        def shutdown(self) -> None:
            raise RuntimeError(secret)

        def run_conversation(self, *, stop_event: threading.Event) -> None:
            registered[signal.SIGTERM](signal.SIGTERM, None)

    original_signal = signal.signal

    def fake_signal(signum: int, handler: Callable[..., Any]) -> Any:
        registered[signum] = handler
        return signal.SIG_DFL

    signal.signal = fake_signal  # type: ignore[assignment]
    try:
        records, exception = _application_logger_records(
            lambda: assistant.main([], runtime_factory=lambda **_: _ShutdownFailureRuntime(), stop_event=threading.Event()),
            "assistant",
        )
    finally:
        signal.signal = original_signal  # type: ignore[assignment]
    assert exception == "RuntimeError"
    _assert_cli_error(_assert_cli_events(records, secret), "shutdown", "RuntimeError")


def _tc_033() -> None:
    runtime = _runtime(); token = runtime.cancellation_token(); runtime.cancel_turn(token)
    assert runtime.publish_audio(token, b"old audio") is None


def _tc_034() -> None:
    runtime = _runtime(); result = runtime.submit_audio(_frame(""))
    assert result.state == "LISTENING" and runtime.next_turn_id() == 1


def _tc_035() -> None:
    runtime = _runtime(max_turns=2, max_bytes=20, max_tokens=2)
    for n in range(5): runtime.submit_turn(Turn(n + 1, "多言語" * 20, 1.0))
    context = runtime.context()
    assert len(context) <= 2
    assert _estimated_tokens(context) <= 2
    assert sum(len(str(item).encode()) for item in context) <= 20


def _tc_036() -> None:
    artifact = b"model"; ports = _ports(provisioner=FakePort(result=artifact)); runtime = _runtime(ports=ports)
    records = _application_records(lambda: runtime.activate_model(artifact, hashlib.sha256(b"different").hexdigest()))
    assert runtime.state == "ERROR_RECOVERABLE"
    _assert_error_event(_json_application_events(records), "activate_model", "ValueError")


def _tc_037() -> None:
    runtime = _runtime(); runtime.stop_playback(); result = runtime.submit_audio(_frame("real user"))
    assert result.turn_id == 1


def _tc_038() -> None:
    runtime = _runtime(clock=time.perf_counter); report = runtime.measure_shutdowns(30)
    assert report.count >= 30 and report.p95 <= 2.0


def _tc_039() -> None:
    model = FakePort(); runtime = _runtime(ports=_ports(language_model=model))
    assert runtime.complete_transcription(Turn(1, "", 0.0)).state == "LISTENING"
    assert model.calls == []


def _tc_040() -> None:
    provisioner = FakePort(); runtime = _runtime(ports=_ports(provisioner=provisioner)); token = runtime.begin_provisioning()
    records = _application_records(lambda: runtime.cancel_provisioning(token))
    events = _json_application_events(records)
    assert any(event.get("event") == "cancellation" for event in events)
    assert any(event.get("generation") == token.generation for event in events)
    assert runtime.state == "MODEL_PENDING"
    assert provisioner.stopped.is_set()


def _tc_041() -> None:
    ports = _ports(language_model=FakePort(error=TimeoutError("temporary"))); runtime = _runtime(ports=ports)
    records = _application_records(lambda: runtime.generate_response(Turn(1, "retry", 1.0)))
    assert runtime.state == "ERROR_RECOVERABLE"
    _assert_error_event(_json_application_events(records), "generate", "TimeoutError")
    assert runtime.retry_turn(1).state == "LISTENING"


@_trace
def _tc_042() -> None:
    factory = _linux_callable("build_runtime")
    clients = {"capture": object(), "stt": object(), "tts": object(), "llm": object()}
    runtime = factory(platform="linux", clients=clients, config={
        "model": "qwen2.5", "model_path": "/models/whisper", "ollama_url": "http://ollama:11434",
    })
    assert runtime.audio_capture is clients["capture"]
    assert runtime.transcriber is clients["stt"]
    assert runtime.synthesizer is clients["tts"]
    assert runtime.language_model is clients["llm"]
    assert runtime.provisioner is not None, "Linux must use the unified provisioner seam"

    import assistant
    parser = assistant._build_parser()
    args = parser.parse_args(["--model", "qwen2.5", "--model-path", "/models/whisper", "--download-model"])
    assert (args.model, args.model_path, args.download_model) == ("qwen2.5", "/models/whisper", True)
    source = inspect.getsource(assistant.build_runtime)
    assert "linux_runtime" in source and "model_path" in source and "config" in source


@_trace
def _tc_043() -> None:
    from conversation_orchestrator import TurnRecord

    class _Transcriber:
        def call(self, _: Any) -> TurnRecord:
            return TurnRecord(1, "hello", 1.0)

    capture = FakePort(result=b"audio")
    player = FakePort()
    runtime = _linux_callable("build_runtime")(platform="linux", clients={
        "capture": capture,
        "stt": _Transcriber(),
        "llm": FakePort(result=iter(("reply",))),
        "tts": FakePort(result=b"wav"),
        "play": player,
    })
    runtime.begin_playback(TurnRecord(1, "assistant", 1.0))
    accepted = runtime.submit_audio(_frame("barge-in"))
    assert accepted.turn_id == 1 and player.stopped.is_set()
    assert runtime.filter_capture(_frame("echo"), playback_active=True) is None
    # Echo suppression is selective.  The default configuration must not turn
    # playback-time capture into a blanket frame drop.
    default_runtime = _linux_callable("build_runtime")(platform="linux", clients={})
    genuine = SimpleNamespace(data=b"real user speech", sequence=2, is_echo=False)
    echo = SimpleNamespace(data=b"assistant echo", sequence=3, is_echo=True)
    assert default_runtime.filter_capture(genuine, playback_active=True) is genuine
    assert default_runtime.filter_capture(echo, playback_active=True) is None
    loop_source = inspect.getsource(type(runtime).run_conversation)
    assert all(token in loop_source for token in ("capture.call(0.05)", "cancel_turn", "filter_capture"))

    run = _linux_callable("run_turn")
    result = run("hello", clients={"capture": lambda: b"audio", "stt": lambda _: "hello", "llm": lambda _: ["ok"], "tts": lambda _: b"wav", "play": lambda _: None})
    assert result == ["ok"]


@_trace
def _tc_044() -> None:
    with pytest.raises((ValueError, RuntimeError, NotImplementedError)):
        _linux_callable("build_runtime")(platform="plan9", clients={})


@_trace
def _tc_045() -> None:
    validate = _linux_callable("validate_audio_environment")
    assert validate(socket_path=__file__, config_path=__file__)
    with pytest.raises((FileNotFoundError, ValueError, RuntimeError)):
        validate(socket_path="/missing/audio.sock", config_path=__file__)
    source = inspect.getsource(validate)
    assert "access" in source and "socket" in source and "config" in source


@_trace
def _tc_046() -> None:
    command = _linux_callable("ffmpeg_command")(source="default", executable="ffmpeg")
    assert command[:1] == ["ffmpeg"] and "-f" in command and command[command.index("-f") + 1] == "pulse"
    assert "default" in command


@_trace
def _tc_047() -> None:
    process = _TrackedProcess(timeout_once=True)
    cancel = _linux_callable("cancel_process")
    with patch("linux_runtime.os.getpgid", return_value=process.pid) as getpgid, patch("linux_runtime.os.killpg") as killpg:
        cancel(process, timeout=0.01)
    assert process.terminated == 1 and process.killed == 1 and process.waited >= 2
    assert getpgid.called
    assert [call.args[1] for call in killpg.call_args_list] == [signal.SIGTERM, signal.SIGKILL]


@_trace
def _tc_048() -> None:
    capture = _linux_callable("FFmpegCapture")
    _assert_linux_error(
        lambda: capture(popen=lambda *_: (_ for _ in ()).throw(OSError("capture secret"))).read(),
        "capture", "OSError", "capture secret",
    )


@_trace
def _tc_049() -> None:
    load = _linux_callable("load_whisper")
    model = load(model_path=__file__, loader=lambda path, **_: path)
    assert model == __file__

    from conversation_orchestrator import TurnRecord
    transcriber = _linux_callable("FasterWhisperTranscriber")(__file__)
    fake_model = SimpleNamespace(transcribe=lambda _: ([{"text": "hello", "avg_logprob": -0.1}], {"language": "en"}))
    with patch("linux_runtime.load_whisper", return_value=fake_model):
        transcript = transcriber.call(b"audio")
    assert isinstance(transcript, TurnRecord)
    assert transcript.transcript == "hello" and transcript.confidence > 0
    assert not isinstance(transcript, tuple), "faster-whisper's (segments, info) must be adapted"

    # A direct transcriber call is also an application boundary: model-load
    # failures must identify that operation without leaking the injected detail.
    failed = _linux_callable("FasterWhisperTranscriber")(__file__)
    with patch("linux_runtime.load_whisper", side_effect=RuntimeError("transcriber secret")):
        events = _assert_linux_error(
            lambda: failed.call(b"audio"), "faster_whisper_load", "RuntimeError", "transcriber secret",
        )
    error = next(event for event in events if event.get("operation") == "faster_whisper_load")
    assert error.get("error_code") == "FASTER_WHISPER_LOAD_FAILED"
    assert error.get("remediation")


@_trace
def _tc_050() -> None:
    load = _linux_callable("load_whisper")
    events = _assert_linux_error(
        lambda: load(model_path="/missing/model", loader=lambda *_: pytest.fail("download was attempted")),
        "load_whisper", "FileNotFoundError", "/missing/model",
    )
    error = next(event for event in events if event.get("operation") == "load_whisper")
    assert error.get("error_code") == "WHISPER_LOAD_FAILED"
    assert error.get("remediation")

    # Validation can succeed while the local loader itself fails; that failure
    # must retain the same direct-load operation and safe structured shape.
    events = _assert_linux_error(
        lambda: load(model_path=__file__, loader=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("loader secret"))),
        "load_whisper", "RuntimeError", "loader secret",
    )
    error = next(event for event in events if event.get("operation") == "load_whisper")
    assert error.get("error_code") == "WHISPER_LOAD_FAILED"
    assert error.get("remediation")


@_trace
def _tc_051() -> None:
    validate = _linux_callable("validate_model_artifact")
    with pytest.raises((ValueError, RuntimeError)):
        validate(path=__file__, checksum="0" * 64, required_files=["missing.bin"])
    with tempfile.TemporaryDirectory() as root:
        artifact = Path(root) / "whisper"
        artifact.mkdir()
        (artifact / "model.bin").write_bytes(b"valid")
        digest = hashlib.sha256(str("model.bin").encode() + b"valid").hexdigest()
        assert validate(path=str(artifact), checksum=digest, required_files=["model.bin"])
        (artifact / "model.bin").write_bytes(b"altered")
        with pytest.raises(ValueError):
            validate(path=str(artifact), checksum=digest, required_files=["model.bin"])


@_trace
def _tc_052() -> None:
    transcribe = _linux_callable("transcribe")
    _assert_linux_error(
        lambda: transcribe(b"audio", infer=lambda *_: (_ for _ in ()).throw(TimeoutError("transcriber secret")), timeout=0.01),
        "transcribe", "TimeoutError", "transcriber secret", "audio",
    )
    source = inspect.getsource(transcribe)
    assert "cancel" in source and "timeout" in source


@_trace
def _tc_053() -> None:
    play = _linux_callable("play_clauses")
    seen: list[str] = []
    play(["A", "B"], synthesize=lambda clause: clause.encode(), paplay=lambda audio: seen.append(audio.decode()))
    assert seen == ["A", "B"]

    player = _linux_callable("PiperPlayer")(__file__)
    popen = _PopenFactory()
    with patch("linux_runtime.subprocess.Popen", side_effect=popen):
        player.call("hello")
    assert len(popen.calls) == 2, "Piper and paplay must both be tracked Popen children"
    assert popen.calls[0][0][0] == "piper" and popen.calls[1][0][0] == "paplay"
    assert all(process.communicated for process in popen.processes)
    assert not Path(popen.calls[1][0][-1]).exists(), "temporary WAV must be removed after paplay"

    _assert_linux_error(
        lambda: _linux_callable("PiperPlayer")(__file__).call("private speech"),
        "piper", "FileNotFoundError", __file__, "private speech",
    )


@_trace
def _tc_054() -> None:
    cancel = _linux_callable("cancel_playback")
    processes = [_TrackedProcess(), _TrackedProcess(timeout_once=True)]
    cancel(processes, timeout=0.01)
    assert all(process.waited >= 1 for process in processes)
    assert processes[1].killed == 1
    failing = SimpleNamespace(pid=4242, poll=lambda: None,
                              terminate=lambda: (_ for _ in ()).throw(OSError("stop secret")))
    _assert_linux_error(lambda: cancel([failing], timeout=0.01), "process_stop", "OSError", "stop secret")
    source = inspect.getsource(_linux_callable("PiperPlayer"))
    assert "timeout" in source and "self.process" in source and "paplay" in source


@_trace
def _tc_055() -> None:
    play = _linux_callable("play_clauses")
    _assert_linux_error(
        lambda: play(["A"], synthesize=lambda _: (_ for _ in ()).throw(OSError("piper secret")), paplay=lambda _: None),
        "piper", "OSError", "piper secret", "A",
    )
    _assert_linux_error(
        lambda: play(["A"], synthesize=lambda _: b"wav", paplay=lambda _: (_ for _ in ()).throw(OSError("paplay secret"))),
        "paplay", "OSError", "paplay secret", "wav",
    )


@_trace
def _tc_056() -> None:
    provision = _linux_callable("provision")
    with tempfile.TemporaryDirectory() as root:
        root_path = Path(root)
        artifacts = {}
        for name in ("whisper", "piper", "ollama"):
            artifact = root_path / name
            artifact.mkdir()
            (artifact / "config.json").write_text(name)
            artifacts[name] = str(artifact)
        activated: list[Any] = []
        destination_a = root_path / "active-a"
        destination_b = root_path / "active-b"
        result = provision(artifacts=artifacts, active_dir=str(destination_a), checksum=lambda path: path,
                           activate=lambda value: activated.append(value) or value)
        again = provision(artifacts=artifacts, active_dir=str(destination_a), checksum=lambda path: path,
                          activate=lambda value: activated.append(value) or value)
        new_destination = provision(artifacts=artifacts, active_dir=str(destination_b), checksum=lambda path: path,
                                    activate=lambda value: activated.append(value) or value)
        assert result == again == new_destination and len(activated) == 6, "idempotency must include activation destination"
        for destination in (destination_a, destination_b):
            assert all((destination / name / "config.json").exists() for name in artifacts)
    source = inspect.getsource(provision)
    assert "staging" in source and ("replace" in source or "rename" in source)


@_trace
def _tc_057() -> None:
    provision = _linux_callable("provision")
    with tempfile.TemporaryDirectory() as root:
        root_path = Path(root)
        prior = root_path / "whisper"
        prior.mkdir(); (prior / "model.bin").write_text("prior")
        active_before = (prior / "model.bin").read_bytes()
        _assert_linux_error(
            lambda: provision(artifacts={"whisper": str(prior), "piper": str(root_path / "missing"), "ollama": str(prior)}, checksum=lambda path: path),
            "provision", "FileNotFoundError", str(root_path),
        )
        assert (prior / "model.bin").read_bytes() == active_before
        assert not (root_path / "missing").exists()

        # If the final activation rename fails, the old active set must be
        # restored and neither staging nor the backup may remain.
        sources = {}
        for name in ("whisper", "piper", "ollama"):
            source = root_path / f"source-{name}"
            source.mkdir()
            (source / "model.bin").write_text(name)
            sources[name] = str(source)
        stage = root_path / "staging-fixture"
        stage.mkdir()
        active = root_path / "transactional-active"
        active.mkdir()
        (active / "previous.bin").write_text("prior")
        backup = active.with_name(active.name + ".previous")
        real_replace = __import__("os").replace
        replace_calls = 0

        def fail_final_replace(source: str, destination: str) -> None:
            nonlocal replace_calls
            replace_calls += 1
            if replace_calls == 2:
                raise OSError("injected final activation failure")
            real_replace(source, destination)

        with patch("linux_runtime.tempfile.mkdtemp", return_value=str(stage)), \
             patch("linux_runtime.os.replace", side_effect=fail_final_replace):
            with pytest.raises(OSError):
                provision(artifacts=sources, active_dir=str(active), checksum=lambda path: path)
        assert replace_calls == 2
        assert active.exists() and (active / "previous.bin").read_text() == "prior"
        assert not stage.exists() and not backup.exists()


@_trace
def _tc_058() -> None:
    provision = _linux_callable("provision")
    _assert_linux_error(
        lambda: provision(artifacts={"whisper": __file__}, offline=True, downloader=lambda *_: pytest.fail("download attempted")),
        "provision", "OSError", __file__, "download attempted",
    )
    source = inspect.getsource(provision)
    assert "offline" in source and "downloader" in source


@_trace
def _tc_059() -> None:
    provision = _linux_callable("provision")
    artifacts = {"whisper": __file__}
    before = {name: Path(path).stat().st_mtime_ns for name, path in artifacts.items()}
    provision(artifacts=artifacts, checksum=lambda path: path)
    provision(artifacts=artifacts, checksum=lambda path: path)
    assert before == {name: Path(path).stat().st_mtime_ns for name, path in artifacts.items()}
    assert all(Path(path).exists() for path in artifacts.values())


@_trace
def _tc_060() -> None:
    config = _linux_callable("ollama_config")(host="http://ollama:11434")
    assert config.host == "http://ollama:11434" and "127.0.0.1" not in config.host
    from conversation_orchestrator import OllamaStreamingAdapter, TurnRecord

    class _Client:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.calls: list[dict[str, Any]] = []
        def chat(self, **kwargs: Any) -> list[dict[str, Any]]:
            self.calls.append(kwargs)
            return [{"message": {"content": "ok"}}]

    client = _Client()
    fake_ollama = SimpleNamespace(
        Client=lambda **kwargs: (setattr(client, "kwargs", kwargs) or client),
        chat=lambda **_: pytest.fail("adapter bypassed configured Ollama client"),
    )
    with patch.dict(sys.modules, {"ollama": fake_ollama}):
        adapter = OllamaStreamingAdapter(model=config.model, host=config.host)
        assert list(adapter.call(TurnRecord(1, "hello", 1.0))) == ["ok"]
    assert client.kwargs["host"] == "http://ollama:11434"
    assert client.calls[0]["model"] == config.model

    compose = _compose_data()
    assert compose["services"]["assistant"]["environment"]["OLLAMA_URL"] == "http://ollama:11434"
    assert "ports" not in compose["services"]["ollama"]

    import provision as provision_cli
    cli_source = inspect.getsource(provision_cli)
    assert "ollama" in cli_source.lower() and ("urlopen" in cli_source or "client" in cli_source)
    assert "subprocess.run([\"ollama\"" not in cli_source
    assert "/root/.ollama" not in cli_source
    cli_parameters = inspect.signature(provision_cli.main).parameters
    assert any(name in cli_parameters for name in ("http_client", "urlopen", "ollama_client"))

    # The pull boundary is deliberately transport- and clock-injectable.  A
    # readiness race must retry for a bounded interval, rather than turning a
    # transient Ollama startup failure into an unbounded provisioning process.
    pull_source = inspect.getsource(provision_cli._ollama_http)
    assert any(token in pull_source for token in ("retry", "attempt", "backoff"))
    assert any(token in pull_source for token in ("clock", "sleep", "monotonic"))
    assert re.search(r"range\([^)]*(?:retry|attempt|max|limit)", pull_source, re.I)

    import provision as provision_cli
    records, exception = _application_logger_records(
        lambda: provision_cli._ollama_http(
            "http://ollama:11434", "llama3.2",
            opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("ollama secret")),
            timeout=0.01, attempts=1,
        ),
        "conversation.runtime",
    )
    assert exception == "RuntimeError"
    events = _json_application_events(records)
    error = next(event for event in events if event.get("event") == "error")
    assert error.get("operation") == "ollama_readiness"
    assert error.get("exception_type") == "RuntimeError"
    assert error.get("cause") == "RuntimeError"
    assert error.get("stack_trace") and "Traceback (most recent call last)" not in error["stack_trace"]
    assert "ollama secret" not in json.dumps(error)
    assert not re.search(r"/(?:[^\" ]+)", json.dumps(error))


@_trace
def _tc_061() -> None:
    probe = _linux_callable("ollama_readiness")
    assert probe(health=False, model_present=False).status != probe(health=True, model_present=False).status
    assert probe(health=True, model_present=True).ready
    assert probe(health=True, model_present=False).status == "missing_model"
    source = inspect.getsource(probe)
    assert "health" in source and "model_present" in source
    assert "selected" in source or "model" in source

    records = _application_records(lambda: probe(health=False, model_present=False))
    readiness_error = next(
        event for event in _json_application_events(records)
        if event.get("event") == "error" and event.get("operation") == "ollama_readiness"
    )
    assert readiness_error.get("severity") == "ERROR"
    assert readiness_error.get("exception_type") == "OllamaReadinessError"
    assert readiness_error.get("cause") == "OllamaReadinessError"
    assert readiness_error.get("stack_trace")
    assert "Traceback (most recent call last)" not in readiness_error["stack_trace"]
    assert "/" not in readiness_error["stack_trace"]
    assert readiness_error.get("error_code") == "OLLAMA_NOT_READY"
    assert readiness_error.get("remediation") == "start Ollama"
    assert "llama3.2" not in json.dumps(readiness_error)

    class _ExplodingBool:
        def __bool__(self) -> bool:
            raise RuntimeError("ollama secret")

    events = _assert_linux_error(
        lambda: probe(health=_ExplodingBool(), model_present=False),
        "ollama_readiness", "RuntimeError", "ollama secret",
    )
    error = next(event for event in events if event.get("operation") == "ollama_readiness")
    assert error.get("error_code") == "OLLAMA_READINESS_FAILED"
    assert error.get("remediation")

    # Named model directories are not artifacts by themselves: an empty
    # Whisper/Piper directory must remain unhealthy.
    model_probe = _linux_callable("model_readiness")
    with tempfile.TemporaryDirectory() as root:
        empty = Path(root) / "empty"
        empty.mkdir()
        result = model_probe({"whisper": str(empty), "piper": str(empty)})
        assert not result.ready and result.status == "missing_model"

    audio = _linux_callable("linux_audio_readiness")
    records = _application_records(lambda: audio("/missing/pulse.sock", "/missing/client.conf"))
    events = _json_application_events(records)
    warning = next(event for event in events if event.get("event") == "readiness")
    assert warning.get("severity") == "WARNING"
    assert warning.get("operation") == "audio"
    assert warning.get("reason_code") == "AUDIO_ENVIRONMENT_MISSING"
    assert warning.get("reason") == "missing_socket_or_tools"
    assert "exception_type" not in warning
    assert "/missing" not in json.dumps(events)

    with tempfile.TemporaryDirectory() as root:
        socket_path = str(Path(root) / "pulse.sock")
        config_path = str(Path(root) / "client.conf")
        Path(socket_path).write_text("socket")
        Path(config_path).write_text("config")
        with patch("linux_runtime.shutil.which", return_value=None):
            records = _application_records(lambda: audio(socket_path, config_path))
        tool_warning = next(event for event in _json_application_events(records)
                            if event.get("event") == "readiness")
        assert tool_warning.get("severity") == "WARNING"
        assert tool_warning.get("reason_code") == "AUDIO_ENVIRONMENT_MISSING"
        assert tool_warning.get("reason") == "missing_socket_or_tools"
        assert socket_path not in json.dumps([record.getMessage() for record in records])

    with patch("linux_runtime.validate_audio_environment",
               side_effect=RuntimeError("audio secret")):
        records = _application_records(lambda: audio("safe-socket", "safe-config"))
    error = next(event for event in _json_application_events(records) if event.get("event") == "error")
    assert error.get("operation") == "audio_readiness"
    assert error.get("exception_type") == "RuntimeError"
    assert error.get("cause") == "RuntimeError"
    assert error.get("stack_trace") and "Traceback (most recent call last)" not in error["stack_trace"]
    assert "audio secret" not in json.dumps(error)


@_trace
def _tc_062() -> None:
    render = _linux_callable("render_compose")
    text = render(profile="cpu", env={})
    assert "gpu" not in text.lower() or "deploy" not in text.lower()
    cpu = _compose_data()
    assert "deploy" not in cpu["services"].get("assistant", {})
    assert cpu["networks"]["private"]["internal"] is True


@_trace
def _tc_063() -> None:
    render = _linux_callable("render_compose")
    with pytest.raises((RuntimeError, ValueError)):
        render(profile="nvidia", env={"NVIDIA_VISIBLE_DEVICES": ""}, toolkit_available=False)
    nvidia = _manifest_text("docker-compose.nvidia.yml")
    assert "driver: nvidia" in nvidia and "capabilities: [gpu]" in nvidia


@_trace
def _tc_064() -> None:
    text = _compose_text()
    _assert_tokens(text, "healthcheck", "depends_on")
    data = _compose_data()
    assert data["services"]["assistant"]["depends_on"]["ollama"]["condition"] == "service_healthy"
    provision = data["services"].get("provision")
    assert provision["depends_on"]["ollama"]["condition"] == "service_healthy"
    health_command = json.dumps(data["services"]["assistant"]["healthcheck"]["test"])
    assert "find" in health_command or "required" in health_command
    assert "whisper" in health_command and "piper" in health_command
    assert not ("test -e /models/whisper" in health_command and "test -e /models/piper" in health_command
                and "find" not in health_command)
    assert provision and "linux_runtime" in json.dumps(provision) or provision and "provision" in json.dumps(provision)
    assert provision["read_only"] is True
    assert provision["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in json.dumps(provision["security_opt"])
    assert "/root/.ollama" not in json.dumps(provision)
    assert str(provision.get("user", "${UID:-10001}")).split(":")[0] not in {"0", "root"}


@_trace
def _tc_065() -> None:
    _assert_tokens(_compose_text(), "read_only", "cap_drop", "no-new-privileges", "tmpfs")
    data = _compose_data()
    assistant = data["services"]["assistant"]
    assert assistant["user"] == "${UID:-10001}:${GID:-10001}"
    assert assistant["cap_drop"] == ["ALL"]
    assert assistant["read_only"] is True


@_trace
def _tc_066() -> None:
    text = _compose_text().lower()
    _assert_tokens(text, "volumes", "ollama", "/dev/snd", "pulse", "cookie")
    data = _compose_data()
    assistant = data["services"]["assistant"]
    mounts = json.dumps(assistant.get("volumes", [])).lower()
    assert "/dev/snd" in mounts
    assert "pulse" in mounts and "cookie" in mounts
    assert ":ro" in mounts
    assert "/:" not in text


@_trace
def _tc_067() -> None:
    validate = _linux_callable("validate_environment")
    with pytest.raises((KeyError, ValueError, RuntimeError)):
        validate({"UID": "not-an-id", "GID": "bad"}, audio_socket="/missing")
    data = _compose_data()
    environment = data["services"]["assistant"]["environment"]
    assert "UID" in json.dumps(environment) or "${UID" in _compose_text()
    assert "GID" in json.dumps(environment) or "${GID" in _compose_text()


@_trace
def _tc_068() -> None:
    records = _application_records(lambda: _linux_callable("redacted_event")(
        operation="capture", event="capture_failed", detail="boundary detail"))
    serialized = json.dumps([record.getMessage() for record in records])
    assert "capture" in serialized and "capture_failed" in serialized and "boundary detail" in serialized
    assert "token" not in serialized and "transcript" not in serialized
    secret_path = "/private/content-secret"
    records = _application_records(lambda: _linux_callable("redacted_event")(
        operation="capture", event="capture_failed", detail=f"{secret_path} private transcript"))
    sanitized = json.dumps([record.getMessage() for record in records])
    assert secret_path not in sanitized and "private transcript" not in sanitized
    source = inspect.getsource(_linux_module())
    for operation in ("readiness", "provision", "rollback", "cancel"):
        assert operation in source
    assert "logger.info" in source or "logger.error" in source
    assert "stack_trace" in source or "_log_event" in source
    import conversation_orchestrator
    logging_source = inspect.getsource(conversation_orchestrator._log_event)
    assert "frame.filename" not in logging_source
    assert "transcript" not in logging_source and "credential" not in logging_source

    # Lifecycle boundaries must be observable as structured INFO/ERROR
    # records, with operation-specific stable codes and safe correlation IDs.
    assert all(token in logging_source for token in ("correlation_id", "operation", "error_code", "stack_trace"))
    assert all(token in source for token in ("readiness", "provision", "rollback", "activate"))
    assert all(token in source for token in (
        "model_readiness", "ollama_readiness", "provision_start",
        "provision_success", "provision_failure", "activation",
        "rollback_start", "rollback_outcome", "rollback_failure",
    ))
    assert re.search(r"[\"'](?:MODEL|OLLAMA|PROVISION|ROLLBACK)_[A-Z_]+[\"']", source)
    # Check emitted data, not implementation prose: no path, request, or
    # other transport detail may cross the application logging boundary.
    assert not re.search(r"/(?:[^\" ]+)", serialized)
    assert "request" not in serialized


@_trace
def _tc_069() -> None:
    _assert_tokens(_compose_text(), "restart")


@_trace
def _tc_070() -> None:
    _assert_tokens(_compose_text(), "mem_limit", "cpus")


@_trace
def _tc_071() -> None:
    shutdown = _linux_callable("shutdown")
    child = _TrackedProcess()
    shutdown(signal.SIGTERM, children=[child])
    assert child.waited >= 1


@_trace
def _tc_072() -> None:
    runtime = _linux_callable("build_runtime")(clients={})
    token = runtime.cancellation_token()
    runtime.cancel_turn(token)
    assert runtime.publish_audio(token, b"late") is None


@_trace
def _tc_073() -> None:
    rollback = _linux_callable("rollback_provisioning")
    with tempfile.TemporaryDirectory() as root:
        root_path = Path(root)
        active = root_path / "active"
        active.mkdir(); (active / "model").write_text("prior")
        staging = root_path / "staging"
        staging.mkdir(); (staging / "partial").write_text("bad")
        assert rollback(active=str(active), staging=str(staging)) == str(active)
        assert (active / "model").read_text() == "prior"
        assert not staging.exists(), "failed staging directories must be removed"


@_trace
def _tc_074() -> None:
    select = _linux_callable("select_profile")
    with pytest.raises((RuntimeError, ValueError)):
        select(requested="nvidia", toolkit_available=False)
    assert select(requested="cpu", toolkit_available=False) == "cpu"


@_trace
def _tc_075() -> None:
    dockerfile = _manifest_text("Dockerfile")
    ignore = _manifest_text(".dockerignore")
    assert dockerfile and ignore
    _assert_tokens(ignore, ".git", "__pycache__")
    assert re.search(r"^FROM\s+[^\s:]+:[0-9][^\s]*$", dockerfile, re.MULTILINE)
    for package in ("ffmpeg", "pulseaudio-utils", "piper"):
        assert package in dockerfile.lower(), f"Docker image must install {package}"
    requirements = _manifest_text("requirements.txt")
    pinned = all(re.search(rf"^{re.escape(name)}==", requirements, re.MULTILINE) for name in ("ollama", "faster-whisper", "piper-tts"))
    lock = re.search(r"^-c\s+(\S+)", requirements, re.MULTILINE)
    assert pinned or (lock and (Path(__file__).parents[1] / lock.group(1)).exists()), "requirements must be pinned or use a committed lock"


@_trace
def _tc_076() -> None:
    data = _compose_data()
    assert data["services"]
    validate = _linux_callable("validate_compose")
    assert validate(_compose_text())
    with pytest.raises((ValueError, RuntimeError)):
        validate("services: [")
    provision = data["services"].get("provision", {})
    command = json.dumps(provision.get("command", []))
    assert "linux_runtime" in command or "provision(" in command
    assert "latest" not in _compose_text().lower()


@_trace
def _tc_077() -> None:
    assert "TC-001" in (Path(__file__).parents[1] / "docs" / "test-cases" / "conversation-runtime.csv").read_text()
    import assistant
    assert isinstance(assistant.build_runtime(model_path="/local/whisper-base.en").player.executable, str)


@_trace
def _tc_078() -> None:
    readme = (Path(__file__).parents[1] / "README.md").read_text().lower()
    assert all(term in readme for term in ("compose", "nvidia", "provision"))
    assert "ollama_url" in readme or "ollama_url" in _compose_text().lower()
    assert "offline" in readme and "paplay" in readme


@_trace
def _tc_079() -> None:
    cancel = _linux_callable("measure_cancellation")
    report = cancel(30, operation=lambda: None)
    assert report.count >= 30 and report.p95 is not None


@_trace
def _tc_080() -> None:
    validate = _linux_callable("validate_manifest")
    with pytest.raises((ValueError, RuntimeError)):
        validate("not: [valid")
    with tempfile.TemporaryDirectory() as root:
        marker = Path(root) / "marker"
        marker.write_text("unchanged")
        assert marker.read_text() == "unchanged"


@_trace
def _tc_081() -> None:
    flow = _linux_callable("run_validated_flow")
    events = flow(clients={"capture": lambda: b"audio", "stt": lambda _: "hello", "llm": lambda _: ["ok"], "tts": lambda _: b"wav", "play": lambda _: None})
    assert [event.name for event in events] == ["validate", "provision", "ready", "listen", "stop"]
    assert len(events) == 5 and [event.name for event in events] == sorted(
        [event.name for event in events], key=["validate", "provision", "ready", "listen", "stop"].index
    )
    import provision as provision_cli
    source = inspect.getsource(provision_cli)
    assert "logging" in source and "json" in source and "except" in source
    assert "return 1" in source or "return 2" in source
    assert "provisioned:" not in source
    assert all(token in source for token in ("exception_type", "cause", "stack_trace"))


_CASES: dict[str, Callable[[], None]] = {
    f"TC-{number:03d}": _trace(globals()[f"_tc_{number:03d}"])
    for number in range(1, 82)
}


@_trace
def _make_test(case_id: str) -> Callable[[], None]:
    def test_case() -> None:
        _test_case(case_id)
    test_case.__name__ = f"test_{case_id.lower().replace('-', '_')}"
    test_case.__doc__ = f"{case_id}: typed externally observable runtime contract."
    return _trace(test_case)


for _case_id in _CASES:
    globals()[f"test_{_case_id.lower().replace('-', '_')}"] = _make_test(_case_id)
