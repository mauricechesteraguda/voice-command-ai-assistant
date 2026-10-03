"""Explicit Linux provisioning CLI using the private Ollama HTTP API."""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen as _urlopen

from linux_runtime import provision, validate_model_artifact
from conversation_orchestrator import _log_event, traced

logger = logging.getLogger("conversation.runtime")


@traced
def _event(event: str, operation: str, **fields: Any) -> None:
    allowed = {"event": event, "operation": operation, "severity": "INFO" if event != "error" else "ERROR"}
    allowed.update({key: value for key, value in fields.items() if key in {"error_code", "remediation", "model"}})
    exc = fields.get("exc")
    if exc is not None:
        allowed.update({
            "exception_type": type(exc).__name__,
            "cause": type(exc.__cause__).__name__ if exc.__cause__ else type(exc).__name__,
            "stack_trace": "".join(f"  in {frame.name}\n" for frame in __import__("traceback").extract_tb(exc.__traceback__)),
        })
    (logger.error if allowed["severity"] == "ERROR" else logger.info)(json.dumps(allowed, sort_keys=True))


@traced
def _ollama_http(url: str, model: str, *, opener: Callable[..., Any], timeout: float,
                 attempts: int = 3, backoff: float = 1.0) -> None:
    """Pull and verify a model, retrying only transient readiness failures."""
    base = url.rstrip("/")
    attempts = max(1, min(int(attempts), 10))
    for attempt in range(attempts):
        try:
            request = Request(base + "/api/pull", data=json.dumps({"name": model, "stream": True}).encode(),
                              headers={"Content-Type": "application/json"}, method="POST")
            with opener(request, timeout=timeout) as response:
                for line in response:
                    if line:
                        try:
                            json.loads(line)
                        except (TypeError, ValueError) as exc:
                            raise RuntimeError("invalid Ollama pull response") from exc
            tags_request = Request(base + "/api/tags", method="GET")
            with opener(tags_request, timeout=timeout) as response:
                data = json.loads(response.read())
            names = {str(item.get("name", "")).split(":", 1)[0] for item in data.get("models", [])}
            if model.split(":", 1)[0] not in names:
                raise RuntimeError("selected Ollama model is not ready")
            _event("success", "ollama_readiness")
            return
        except (HTTPError, URLError, TimeoutError, ConnectionError, RuntimeError) as exc:
            status = getattr(exc, "code", None)
            transient = isinstance(exc, (URLError, TimeoutError, ConnectionError, RuntimeError)) or status in {408, 425, 429, 500, 502, 503, 504}
            if not transient or attempt + 1 >= attempts:
                _event("error", "ollama_readiness", error_code="OLLAMA_NOT_READY",
                       remediation="start private Ollama and verify model readiness", exc=exc)
                raise
            _event("retry", "ollama_readiness", error_code="OLLAMA_NOT_READY",
                   remediation="waiting for private Ollama readiness")
            time.sleep(max(0.0, backoff) * (2 ** attempt))


@traced
def main(argv: list[str] | None = None, urlopen: Callable[..., Any] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provision local Whisper, Piper, and Ollama artifacts")
    parser.add_argument("--consent", action="store_true", help="explicitly authorize provisioning")
    parser.add_argument("--offline", action="store_true", help="never pull from Ollama")
    parser.add_argument("--whisper", required=True)
    parser.add_argument("--piper", required=True)
    parser.add_argument("--ollama-model", default="llama3.2")
    parser.add_argument("--ollama-url", default=os.getenv("OLLAMA_URL", "http://ollama:11434"))
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retry-attempts", type=int, default=int(os.getenv("OLLAMA_RETRY_ATTEMPTS", "3")))
    parser.add_argument("--retry-backoff", type=float, default=float(os.getenv("OLLAMA_RETRY_BACKOFF", "1.0")))
    parser.add_argument("--runtime", default="linux_runtime.provision", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if not args.consent:
            raise ValueError("consent is required")
        if not args.ollama_model.replace("-", "").replace(".", "").replace(":", "").isalnum():
            raise ValueError("invalid Ollama model name")
        validate_model_artifact(args.whisper)
        validate_model_artifact(args.piper)
        if not args.offline:
            _event("external_call", "ollama_provision")
            _ollama_http(args.ollama_url, args.ollama_model, opener=urlopen or _urlopen,
                         timeout=args.timeout, attempts=args.retry_attempts, backoff=args.retry_backoff)
        else:
            _event("lifecycle", "ollama_provision_offline")
        # Offline controls Ollama network access; local activation remains a
        # filesystem-only operation for the two local artifact sets.
        provision({"whisper": args.whisper, "piper": args.piper}, offline=False)
        _event("success", "provision")
        print("completed: Whisper, Piper, and Ollama " + args.ollama_model)
        return 0
    except Exception as exc:
        _event("error", "provision", error_code="MODEL_PROVISION_FAILED",
               remediation="verify private Ollama readiness and local artifacts", exc=exc)
        print(json.dumps({"event": "error", "operation": "provision", "error_code": "MODEL_PROVISION_FAILED",
                          "remediation": "verify private Ollama readiness and local artifacts"}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
