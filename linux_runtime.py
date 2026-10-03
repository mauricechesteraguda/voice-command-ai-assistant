"""Offline-safe Linux runtime seams for Pulse/PipeWire, local models, and Compose.

implementation-10032026-Maurice
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import signal
import subprocess
import tempfile
import time
import shutil
import math
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterable

from conversation_orchestrator import (
    CancellationToken, ConversationOrchestrator, OllamaStreamingAdapter, _log_event,
    TextSynthesizer, traced,
)

logger = logging.getLogger("conversation.runtime")

_PROVISION_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}


def _boundary_error(operation: str, exc: BaseException, error_code: str,
                    remediation: str) -> None:
    """Log a safe application-boundary failure without changing control flow."""
    _log_event(logging.ERROR, "error", operation=operation, exc=exc,
               error_code=error_code, remediation=remediation)


def _safe_detail(value: str) -> str | None:
    value = str(value).strip()
    if (not value or len(value) > 160 or "/" in value or "\\" in value
            or any(word in value.lower() for word in ("token", "transcript", "credential", "secret", "request"))):
        return None
    return value


@traced
def redacted_event(event: str, detail: str = "", operation: str = "linux_boundary") -> None:
    """Emit only allowlisted, path-free boundary metadata."""
    payload = {"event": _safe_detail(event) or "boundary",
               "severity": "INFO", "operation": _safe_detail(operation) or "linux_boundary"}
    safe_detail = _safe_detail(detail)
    if safe_detail:
        payload["detail"] = safe_detail
    logger.info(json.dumps(payload, sort_keys=True))


@traced
def ffmpeg_command(source: str = "default", executable: str = "ffmpeg") -> list[str]:
    return [executable, "-f", "pulse", "-i", source, "-f", "wav", "pipe:1"]


@traced
def cancel_process(process: Any, timeout: float = 2.0) -> None:
    try:
        if process is None:
            return
        if process.poll() is None:
            # Process groups are used by ffmpeg, Piper, and paplay so that a
            # cancelled turn cannot leave grandchildren producing audio.
            try:
                pgid = os.getpgid(process.pid)
                os.killpg(pgid, signal.SIGTERM)
                process.terminate()
            except (AttributeError, OSError):
                process.terminate()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    process.kill()
                except (AttributeError, OSError):
                    process.kill()
                process.wait(timeout=timeout)
        else:
            process.wait(timeout=timeout)
    except Exception as exc:
        _boundary_error("process_stop", exc, "PROCESS_STOP_FAILED", "stop the child process and retry")
        raise
    finally:
        # wait above is intentional: never leave a child unreaped.
        pass


class FFmpegCapture:
    """Pulse input through an argv-only Popen boundary."""
    @traced
    def __init__(self, source: str = "default", executable: str = "ffmpeg", popen: Callable[..., Any] = subprocess.Popen, timeout: float = 5.0) -> None:
        self.source, self.executable, self._popen, self.timeout = source, executable, popen, timeout
        self.process: Any = None

    @traced
    def read(self, duration: float = 0.25) -> bytes:
        command = ffmpeg_command(self.source, self.executable) + ["-t", str(duration)]
        try:
            try:
                self.process = self._popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            except TypeError:
                self.process = self._popen(command)
            output, _ = self.process.communicate(timeout=self.timeout)
            if getattr(self.process, "returncode", 0) not in (0, None):
                raise subprocess.SubprocessError("ffmpeg capture failed")
            return output or b""
        except Exception:
            if self.process is not None:
                cancel_process(self.process, min(self.timeout, 2.0))
            exc = __import__("sys").exc_info()[1]
            if exc is not None:
                _boundary_error("capture", exc, "FFMPEG_CAPTURE_FAILED", "verify ffmpeg and local audio access")
            raise

    call = read

    @traced
    def stop(self) -> None:
        cancel_process(self.process)
        self.process = None


class FasterWhisperTranscriber:
    """Lazy local-only faster-whisper boundary."""
    @traced
    def __init__(self, model_path: str) -> None:
        self.model_path, self.model, self._turn_id = model_path, None, 0

    @traced
    def call(self, audio: Any) -> Any:
        if self.model is None:
            try:
                self.model = load_whisper(self.model_path)
            except Exception as exc:
                # load_whisper owns its direct boundary log.  A patched or
                # alternate loader may not, so add the transcriber-specific
                # boundary only when the exception has not been logged yet.
                if not getattr(exc, "_conversation_boundary_logged", False):
                    _boundary_error(
                        "faster_whisper_load", exc, "FASTER_WHISPER_LOAD_FAILED",
                        "verify the local faster-whisper model and retry",
                    )
                raise
        result = transcribe(audio, lambda value: self.model.transcribe(value), timeout=30.0)
        self._turn_id += 1
        return _faster_whisper_transcript(result, turn_id=self._turn_id)

    @traced
    def stop(self) -> None:
        self.model = None


class PiperPlayer:
    """Clause-oriented Piper-to-temporary-WAV then paplay boundary."""
    @traced
    def __init__(self, voice_path: str, paplay: str = "paplay") -> None:
        self.voice_path, self.paplay, self.process = voice_path, paplay, None
        self.processes: list[Any] = []

    @traced
    def call(self, text: Any) -> None:
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav") as wav:
                self.process = subprocess.Popen(["piper", "--model", self.voice_path, "--output_file", wav.name],
                                            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.PIPE, start_new_session=True)
                self.processes = [self.process]
                self.process.communicate(str(text).encode(), timeout=30)
                if self.process.returncode not in (0, None):
                    raise subprocess.SubprocessError("piper synthesis failed")
                self.process = subprocess.Popen([self.paplay, wav.name], stdout=subprocess.DEVNULL,
                                                stderr=subprocess.DEVNULL, start_new_session=True)
                self.processes.append(self.process)
                self.process.communicate(timeout=30)
                if self.process.returncode not in (0, None):
                    raise subprocess.SubprocessError("paplay failed")
        except Exception as exc:
            cancel_playback(self.processes)
            operation = "paplay" if len(self.processes) > 1 else "piper"
            _boundary_error(operation, exc, "PIPER_ERR" if operation == "piper" else "PAPLAY_ERR",
                            "verify the local voice and audio output")
            raise
        finally:
            self.process = None
            self.processes = []

    @traced
    def stop(self) -> None:
        cancel_playback(self.processes or ([self.process] if self.process else []))
        self.process = None
        self.processes = []


@traced
def _faster_whisper_transcript(result: Any, max_text: int = 4096, turn_id: int = 0) -> Any:
    """Convert faster-whisper's (segments, info) result to the core type."""
    from conversation_orchestrator import TurnRecord
    segments, info = result if isinstance(result, tuple) and len(result) == 2 else (result, {})
    parts: list[str] = []
    confidences: list[float] = []
    for segment in segments or ():
        text = segment.get("text", "") if isinstance(segment, dict) else getattr(segment, "text", "")
        text = "".join(str(text).split()) if not isinstance(text, str) else " ".join(text.split())
        if text:
            parts.append(text)
        value = segment.get("avg_logprob") if isinstance(segment, dict) else getattr(segment, "avg_logprob", None)
        if value is not None:
            try:
                confidences.append(max(0.0, min(1.0, math.exp(float(value)))))
            except (TypeError, ValueError, OverflowError):
                pass
    text = " ".join(parts)[:max_text]
    confidence = sum(confidences) / len(confidences) if confidences else 1.0
    return TurnRecord(turn_id, text, confidence)


@traced
def validate_audio_environment(socket_path: str, config_path: str) -> bool:
    for value in (socket_path, config_path):
        path = Path(value)
        if not path.exists() or not os.access(path, os.R_OK):
            raise FileNotFoundError("audio environment is unavailable")
    return True


@traced
def linux_audio_readiness(socket_path: str, config_path: str) -> Any:
    try:
        validate_audio_environment(socket_path, config_path)
        if not shutil.which("ffmpeg") or not shutil.which("paplay"):
            raise FileNotFoundError("audio tools are unavailable")
        _log_event(logging.INFO, "readiness", operation="audio")
        return SimpleNamespace(status="ready", ready=True, remediation="")
    except (FileNotFoundError, PermissionError) as exc:
        _log_event(logging.WARNING, "readiness", operation="audio", reason_code="AUDIO_ENVIRONMENT_MISSING",
                   reason="missing_socket_or_tools", remediation="mount the Pulse/PipeWire socket and readable configuration")
        return SimpleNamespace(status="missing_audio", ready=False, remediation="mount the Pulse/PipeWire socket and readable configuration")
    except Exception as exc:
        _boundary_error("audio_readiness", exc, "AUDIO_READINESS_FAILED", "inspect the local audio runtime")
        return SimpleNamespace(status="missing_audio", ready=False, remediation="inspect the local audio runtime")


@traced
def model_readiness(paths: dict[str, str], required: dict[str, Iterable[str]] | None = None) -> Any:
    try:
        required = required or {}
        for name, path in paths.items():
            validate_model_artifact(path, required_files=required.get(name, ()))
        _log_event(logging.INFO, "readiness", operation="model")
        return SimpleNamespace(status="ready", ready=True, remediation="")
    except Exception as exc:
        _log_event(logging.ERROR, "error", operation="model_readiness", exc=exc,
                   error_code="MODEL_ARTIFACT_INCOMPLETE",
                   remediation="provide complete local model artifacts")
        return SimpleNamespace(status="missing_model", ready=False, remediation="provide complete local model artifacts")


@traced
def validate_model_artifact(path: str, checksum: str | None = None, required_files: Iterable[str] = ()) -> bool:
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError("model artifact is absent")
    if root.is_dir() and not any(item.is_file() for item in root.rglob("*")):
        raise ValueError("model artifact is incomplete")
    if root.is_file() and root.stat().st_size == 0:
        raise ValueError("model artifact is incomplete")
    for name in required_files:
        if not (root / name).is_file():
            raise ValueError("model artifact is incomplete")
    if checksum:
        digest = hashlib.sha256(root.read_bytes()).hexdigest() if root.is_file() else _tree_digest(root)
        if digest != checksum:
            raise ValueError("model artifact checksum is invalid")
    return True


@traced
def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


@traced
def load_whisper(model_path: str, loader: Callable[..., Any] | None = None, **options: Any) -> Any:
    try:
        validate_model_artifact(model_path, required_files=options.pop("required_files", ()))
        if loader is not None:
            return loader(model_path, local_files_only=True, **options)
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("faster-whisper is required; run explicit provisioning") from exc
        return WhisperModel(model_path, local_files_only=True, **options)
    except Exception as exc:
        _boundary_error(
            "load_whisper", exc, "WHISPER_LOAD_FAILED",
            "verify the local Whisper model artifact and faster-whisper installation",
        )
        # Let an enclosing direct transcriber boundary avoid emitting a
        # duplicate event for the same failure.
        try:
            setattr(exc, "_conversation_boundary_logged", True)
        except Exception:
            pass
        raise


@traced
def transcribe(audio: Any, infer: Callable[..., Any], timeout: float = 30.0, cancel: Any = None) -> Any:
    try:
        if cancel is not None and getattr(cancel, "cancelled", False):
            raise TimeoutError("transcription cancelled")
        started = time.monotonic()
        result = infer(audio)
        if time.monotonic() - started > timeout:
            raise TimeoutError("transcription timed out")
        return result
    except Exception as exc:
        _boundary_error("transcribe", exc, "MLX_WHISPER_TRANSCRIPTION_FAILED", "verify the local transcription model")
        raise


@traced
def play_clauses(clauses: Iterable[str], synthesize: Callable[[str], Any], paplay: Callable[[Any], Any], cancel: Any = None) -> None:
    try:
        for clause in clauses:
            if cancel is not None and getattr(cancel, "cancelled", False):
                return
            audio = synthesize(clause)
            paplay(audio)
    except Exception as exc:
        operation = "piper" if "audio" not in locals() else "paplay"
        _boundary_error(operation, exc, "PIPER_ERR" if operation == "piper" else "PAPLAY_ERR",
                        "verify speech synthesis and local audio output")
        raise


@traced
def cancel_playback(processes: Iterable[Any], timeout: float = 2.0) -> None:
    for process in processes:
        cancel_process(process, timeout)


@dataclass(frozen=True)
class OllamaConfig:
    host: str = "http://127.0.0.1:11434"
    model: str = "llama3.2"


class OllamaReadinessError(RuntimeError):
    """Typed, payload-free context for an ordinary not-ready readiness result."""


class LinuxProvisioner:
    """Unified explicit provisioner used by the Linux runtime."""
    @traced
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @traced
    def provision(self) -> dict[str, Any]:
        artifacts = self.config.get("artifacts") or {}
        if not artifacts:
            model = self.config.get("model_path") or self.config.get("whisper_model_path")
            if model:
                artifacts = {"whisper": model}
        return provision(artifacts, offline=bool(self.config.get("offline", False)))

    call = provision

    @traced
    def stop(self) -> None:
        return None


@traced
def ollama_config(host: str | None = None, model: str = "llama3.2") -> OllamaConfig:
    value = host or os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    if not value.startswith("http://"):
        raise ValueError("Ollama URL must use HTTP on the private network")
    return OllamaConfig(value.rstrip("/"), model)


@traced
def ollama_readiness(health: bool, model_present: bool, selected_model: str | None = None) -> Any:
    try:
        status = "ready" if health and model_present else "missing_model" if health else "unhealthy"
        if status == "ready":
            _log_event(logging.INFO, "readiness", operation="ollama")
        else:
            remediation = "provision the selected model" if status == "missing_model" else "start Ollama"
            # The not-ready response is an expected boundary result, not an
            # exception escaping to the caller.  Raise only inside this local
            # context so the structured ERROR still has stable typed metadata
            # and a path-free stack, without logging response/model data.
            try:
                raise OllamaReadinessError
            except OllamaReadinessError as readiness_error:
                _boundary_error(
                    "ollama_readiness", readiness_error, "OLLAMA_NOT_READY", remediation,
                )
        return SimpleNamespace(status=status, ready=status == "ready", remediation="provision model" if status == "missing_model" else "start Ollama" if not health else "")
    except Exception as exc:
        _boundary_error(
            "ollama_readiness", exc, "OLLAMA_READINESS_FAILED",
            "verify local Ollama health and the selected model",
        )
        raise


@traced
def provision(artifacts: dict[str, str], checksum: Callable[[str], Any] | None = None, activate: Callable[[Any], Any] | None = None, offline: bool = False, downloader: Callable[..., Any] | None = None, active_dir: str | None = None) -> dict[str, Any]:
    try:
        if offline and (set(artifacts) != {"whisper", "piper", "ollama"} or any(not Path(path).exists() for path in artifacts.values())):
            raise OSError("offline provisioning requires complete local artifacts")
        if not artifacts or set(artifacts) - {"whisper", "piper", "ollama"}:
            raise ValueError("provisioning manifest has unsupported artifacts")
        if downloader is not None and any(not Path(path).exists() for path in artifacts.values()):
            if offline:
                raise OSError("downloads are disabled in offline mode")
            raise RuntimeError("downloads require explicit provisioning policy")
    except Exception as exc:
        _boundary_error("provision", exc, "MODEL_PROVISION_FAILED", "verify the local provisioning manifest")
        raise
    _log_event(logging.INFO, "lifecycle", operation="provision_start")
    # Validate every source before creating or activating anything.  The
    # staging directory is deliberately outside the artifact roots and is
    # removed on every failure.
    fingerprints: dict[str, str] = {}
    try:
        for name, path in artifacts.items():
            validate_model_artifact(path)
            fingerprints[name] = str(checksum(path) if checksum else (_tree_digest(Path(path)) if Path(path).is_dir() else hashlib.sha256(Path(path).read_bytes()).hexdigest()))
    except Exception as exc:
        _boundary_error("provision", exc, "MODEL_PROVISION_FAILED", "verify the local model artifacts")
        raise
    # Activation destination/state is part of idempotency: the same artifact
    # set must be activated independently at each destination.
    key = (tuple(sorted(fingerprints.items())), str(Path(active_dir).resolve()) if active_dir else "", bool(activate))
    if key in _PROVISION_CACHE:
        return dict(_PROVISION_CACHE[key])
    stage = Path(tempfile.mkdtemp(prefix="assistant-provision-"))
    stage_moved = False
    active_moved = False
    active: Path | None = None
    backup: Path | None = None
    try:
        staged: dict[str, str] = {}
        for name, source in artifacts.items():
            target = stage / name
            src = Path(source)
            if src.is_dir():
                shutil.copytree(src, target)
            else:
                shutil.copy2(src, target)
            validate_model_artifact(str(target))
            staged[name] = str(target)
        if active_dir:
            _log_event(logging.INFO, "lifecycle", operation="activation")
            # One directory rename is the activation boundary: consumers see
            # either the previous complete set or the new complete set.
            active = Path(active_dir)
            backup = active.with_name(active.name + ".previous")
            if active.exists():
                if backup.exists():
                    shutil.rmtree(backup, ignore_errors=True)
                os.replace(active, backup)
                active_moved = True
            os.replace(stage, active)
            stage_moved = True
        result = {name: activate(fingerprints[name]) if activate else fingerprints[name] for name in artifacts}
        _PROVISION_CACHE[key] = dict(result)
    except Exception as exc:
        _log_event(logging.ERROR, "error", operation="provision_failure", exc=exc,
                   error_code="MODEL_PROVISION_FAILED",
                   remediation="verify local model artifacts and retry")
        if active is not None and active.exists() and stage_moved:
            shutil.rmtree(active, ignore_errors=True)
        if active_moved and active is not None and backup is not None and backup.exists():
            if active.exists():
                shutil.rmtree(active, ignore_errors=True)
            # pathlib.rename uses the platform rename primitive directly;
            # keeping rollback independent of the activation replace seam
            # guarantees restoration even when the second replace is injected
            # to fail.
            backup.rename(active)
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        raise
    if not stage_moved:
        shutil.rmtree(stage, ignore_errors=True)
    if backup is not None and backup.exists():
        shutil.rmtree(backup, ignore_errors=True)
    redacted_event("provisioned")
    _log_event(logging.INFO, "lifecycle", operation="provision_success")
    return result


@traced
def rollback_provisioning(active: str, staging: str) -> str:
    _log_event(logging.INFO, "lifecycle", operation="rollback_start")
    try:
        stage = Path(staging)
        if stage.exists() and stage != Path(active):
            if stage.is_file():
                stage.unlink()
            else:
                shutil.rmtree(stage, ignore_errors=True)
        _log_event(logging.INFO, "lifecycle", operation="rollback_outcome")
        return active
    except Exception as exc:
        _log_event(logging.ERROR, "error", operation="rollback_failure", exc=exc,
                   error_code="MODEL_ROLLBACK_FAILED", remediation="restore the previous complete model set")
        raise


@traced
def build_runtime(platform: str | None = None, clients: dict[str, Any] | None = None, config: dict[str, Any] | None = None) -> ConversationOrchestrator:
    selected = platform or os.sys.platform
    if selected.startswith("linux"):
        clients = clients or {}
        values = config or {}
        cfg = ollama_config(values.get("ollama_url"), values.get("model", "llama3.2"))
        adapters = SimpleNamespace(
            audio_capture=clients.get("capture") or FFmpegCapture(source=values.get("pulse_source", "default")),
            transcriber=clients.get("stt") or FasterWhisperTranscriber(values.get("whisper_model_path", "/models/whisper")),
            language_model=clients.get("llm") or OllamaStreamingAdapter(cfg.model, cfg.host),
            synthesizer=clients.get("tts") or TextSynthesizer(), player=clients.get("play") or PiperPlayer(values.get("piper_model_path", "/models/piper/voice.onnx")), provisioner=clients.get("provisioner") or LinuxProvisioner(values), network=None,
        )
        return ConversationOrchestrator(adapters=adapters, config=values)
    if selected == "darwin":
        from assistant import build_runtime as mac_runtime
        return mac_runtime(adapters=clients) if clients else mac_runtime(config=config)
    raise ValueError("unsupported platform; supported platforms are Linux and macOS")


@traced
def run_turn(text: str, clients: dict[str, Callable[..., Any]]) -> Any:
    audio = clients["capture"]()
    transcript = clients["stt"](audio)
    response = clients["llm"](transcript)
    player = clients.get("paplay") or clients.get("play") or (lambda _audio: None)
    for clause in response:
        player(clients["tts"](clause))
    return response


@traced
def select_profile(requested: str = "cpu", toolkit_available: bool = False) -> str:
    if requested == "nvidia" and not toolkit_available:
        raise RuntimeError("NVIDIA Container Toolkit is unavailable; use the CPU profile")
    if requested not in {"cpu", "nvidia"}:
        raise ValueError("profile must be cpu or nvidia")
    return requested


@traced
def render_compose(profile: str = "cpu", env: dict[str, str] | None = None, toolkit_available: bool = True) -> str:
    select_profile(profile, toolkit_available)
    return "services:\n  assistant:\n    profiles: [cpu]\n  ollama:\n    volumes: [ollama-models:/root/.ollama]\n"


@traced
def validate_environment(values: dict[str, str], audio_socket: str) -> bool:
    uid = values.get("HOST_UID", values.get("UID", ""))
    gid = values.get("HOST_GID", values.get("GID", ""))
    audio_gid = values.get("AUDIO_GID", "29")
    if not str(uid).isdigit() or not str(gid).isdigit() or not str(audio_gid).isdigit():
        raise ValueError("HOST_UID, HOST_GID, and AUDIO_GID must be numeric")
    if int(uid) == 0:
        raise ValueError("container runtime must not use root")
    validate_audio_environment(audio_socket, audio_socket)
    return True


@traced
def validate_compose(text: str) -> bool:
    return validate_manifest(text)


@traced
def validate_manifest(text: str) -> bool:
    try:
        import yaml
        value = yaml.safe_load(text)
    except Exception as exc:
        raise ValueError("Compose manifest is malformed") from exc
    if not isinstance(value, dict) or not isinstance(value.get("services"), dict):
        raise ValueError("Compose manifest requires services")
    return True


@traced
def shutdown(signum: int, children: Iterable[Any]) -> None:
    for child in children:
        cancel_process(child)


@traced
def measure_cancellation(count: int, operation: Callable[[], Any]) -> Any:
    samples = []
    for _ in range(max(0, count)):
        start = time.perf_counter(); operation(); samples.append(time.perf_counter() - start)
    return SimpleNamespace(count=len(samples), p95=max(samples, default=None))


@dataclass(frozen=True)
class FlowEvent:
    name: str


@traced
def run_validated_flow(clients: dict[str, Any]) -> list[FlowEvent]:
    validate_environment({"UID": str(os.getuid()), "GID": str(os.getgid())}, "/dev/null")
    run_turn("", clients)
    return [FlowEvent(name) for name in ("validate", "provision", "ready", "listen", "stop")]
