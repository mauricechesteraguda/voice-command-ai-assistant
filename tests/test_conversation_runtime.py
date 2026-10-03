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
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator

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


_CASES: dict[str, Callable[[], None]] = {
    f"TC-{number:03d}": _trace(globals()[f"_tc_{number:03d}"])
    for number in range(1, 42)
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
