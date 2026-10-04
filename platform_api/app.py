"""Versioned FastAPI control plane; all external ports are injectable."""

# implementation-10042026-Maurice
from __future__ import annotations
import logging
from typing import Any
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from .audit import AuditLog
from .auth import Claims, JWTAdapter
from .config import ConfigStore
from .observability import Metrics, traced
from .rbac import allows
from .rate_limit import RateLimiter

logger = logging.getLogger("control_plane.api")

class ConfigRequest(BaseModel):
    version: int = Field(gt=0)
    values: dict[str, Any] = Field(default_factory=dict)
    cohort: str = "default"

class OverrideRequest(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)

class ControlPlane:
    def __init__(self, *, jwt: JWTAdapter | None = None, config: ConfigStore | None = None, audit: AuditLog | None = None, limiter: RateLimiter | None = None, metrics: Metrics | None = None, db: Any | None = None) -> None:
        self.jwt = jwt or JWTAdapter("development-only-control-plane-key")
        self.config = config or ConfigStore("development-only-config-key")
        self.audit, self.limiter, self.metrics, self.db = audit or AuditLog(), limiter or RateLimiter(), metrics or Metrics(), db
        self.ready = True

@traced
def create_app(state: ControlPlane | None = None) -> FastAPI:
    control = state or ControlPlane(); app = FastAPI(title="Voice Assistant Control Plane", version="v1")
    bearer = HTTPBearer(auto_error=False)

    @app.middleware("http")
    @traced
    async def lifecycle(request: Request, call_next: Any) -> Response:
        logger.info('{"event":"http.lifecycle","operation":"request.start"}')
        allowed, retry_after = control.limiter.check(request.url.path)
        if not allowed:
            response = Response(content='{"detail":"rate limit exceeded"}', status_code=429, media_type="application/json")
            response.headers["Retry-After"] = str(retry_after)
            return response
        response = await call_next(request)
        logger.info('{"event":"http.lifecycle","operation":"request.end"}')
        return response

    @traced
    def claims(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Claims:
        if credentials is None: raise HTTPException(401, "authentication required")
        try: return control.jwt.decode(credentials.credentials, audience="control-plane-admin")
        except ValueError as exc: raise HTTPException(401, "invalid authentication") from exc

    @traced
    def device_claims(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Claims:
        if credentials is None: raise HTTPException(401, "authentication required")
        try: return control.jwt.decode(credentials.credentials, audience="control-plane-device")
        except ValueError as exc: raise HTTPException(401, "invalid authentication") from exc

    def require(permission: str):
        def dependency(user: Claims = Depends(claims)) -> Claims:
            if not allows(user.role, permission): raise HTTPException(403, "insufficient role")
            return user
        return dependency

    @app.get("/v1/health/live")
    @traced
    def live() -> dict[str, str]: return {"status": "live"}

    @app.get("/v1/health/ready")
    @traced
    def ready() -> dict[str, str]:
        if not control.ready: raise HTTPException(503, "not ready")
        return {"status": "ready"}

    @app.get("/v1/telemetry")
    @traced
    def telemetry(_: Claims = Depends(require("read:telemetry"))) -> dict[str, Any]:
        return {"retention_days": 30, "metrics": control.metrics.snapshot()}

    @app.get("/metrics", response_class=Response)
    @traced
    def metrics() -> Response:
        lines = [f"control_plane_{name} {value}" for name, value in control.metrics.snapshot().items()]
        return Response("\n".join(lines) + ("\n" if lines else ""), media_type="text/plain; version=0.0.4")

    @app.get("/v1/config")
    @traced
    def get_config(_: Claims = Depends(require("read:config"))) -> dict[str, Any]:
        current = control.config.current
        if current is None: return {"version": 0, "values": {}, "signature": ""}
        return {"version": current.version, "values": current.values, "signature": current.signature, "cohort": current.cohort}

    @app.put("/v1/admin/config")
    @traced
    def publish_config(body: ConfigRequest, user: Claims = Depends(require("write:config"))) -> dict[str, Any]:
        try: current = control.config.publish(body.values, version=body.version, cohort=body.cohort)
        except ValueError as exc: raise HTTPException(409, "version must be monotonic") from exc
        control.audit.append(user.subject, "config.publish", "success", {"version": body.version, "operation": "publish"}); return {"version": current.version, "signature": current.signature}

    @app.put("/v1/admin/devices/{device_id}/override")
    @traced
    def set_override(device_id: str, body: OverrideRequest, user: Claims = Depends(require("write:device"))) -> dict[str, str]:
        control.config.set_device_override(device_id, body.values); control.audit.append(user.subject, "device.override", "success", {"operation": "override"}); return {"status": "accepted"}

    @app.get("/v1/devices/{device_id}/config")
    @traced
    def device_config(device_id: str, _: Claims = Depends(device_claims)) -> dict[str, Any]:
        current = control.config.for_device(device_id)
        return {"version": current.version, "values": current.values, "signature": current.signature} if current else {"version": 0, "values": {}}

    @app.get("/v1/admin/audit")
    @traced
    def audit(_: Claims = Depends(require("read:audit"))) -> list[dict[str, Any]]:
        return [{"actor": e.actor, "action": e.action, "outcome": e.outcome, "created_at": e.created_at.isoformat(), "metadata": e.metadata} for e in control.audit.events()]

    app.state.control_plane = control
    return app

app = create_app()
