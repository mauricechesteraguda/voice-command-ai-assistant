"""Injectable JWT and OIDC adapters with separate device/admin audiences."""

# implementation-10042026-Maurice
from __future__ import annotations
import base64, hashlib, hmac, json, time
from dataclasses import dataclass
from typing import Any, Callable
from .observability import traced

def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

@dataclass(frozen=True)
class Claims:
    subject: str
    role: str
    audience: str
    expires_at: int
    token_id: str = ""

class JWTAdapter:
    def __init__(self, secret: bytes | str, *, clock: Callable[[], float] = time.time, replay_cache: set[str] | None = None) -> None:
        self.secret = secret.encode() if isinstance(secret, str) else secret
        self.clock, self.replay_cache = clock, replay_cache if replay_cache is not None else set()

    @traced
    def encode(self, *, subject: str, role: str, audience: str, ttl: int = 300, token_id: str = "") -> str:
        now = int(self.clock()); header = {"alg": "HS256", "typ": "JWT"}; payload = {"sub": subject, "role": role, "aud": audience, "iat": now, "exp": now + ttl}
        if token_id: payload["jti"] = token_id
        signing = f"{_b64(json.dumps(header, separators=(',', ':')).encode())}.{_b64(json.dumps(payload, separators=(',', ':')).encode())}"
        return signing + "." + _b64(hmac.new(self.secret, signing.encode(), hashlib.sha256).digest())

    @traced
    def decode(self, token: str, *, audience: str) -> Claims:
        try:
            head, body, signature = token.split(".")
            if json.loads(_unb64(head)).get("alg") != "HS256": raise ValueError("algorithm")
            expected = _b64(hmac.new(self.secret, f"{head}.{body}".encode(), hashlib.sha256).digest())
            if not hmac.compare_digest(signature, expected): raise ValueError("invalid signature")
            payload = json.loads(_unb64(body)); now = int(self.clock())
            if payload.get("aud") != audience: raise ValueError("invalid audience")
            if int(payload.get("exp", 0)) <= now: raise ValueError("expiry")
            jti = str(payload.get("jti", ""))
            if jti and jti in self.replay_cache: raise ValueError("replay")
            if jti: self.replay_cache.add(jti)
            return Claims(str(payload["sub"]), str(payload["role"]), audience, int(payload["exp"]), jti)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeError) as exc:
            raise ValueError("invalid token") from exc

class OIDCAdapter:
    """OIDC discovery/JWKS port; transport is always supplied by the caller."""
    def __init__(self, transport: Callable[[str], dict[str, Any]], issuer: str) -> None:
        self.transport, self.issuer = transport, issuer

    @traced
    def discover(self) -> dict[str, Any]:
        return self.transport(self.issuer.rstrip("/") + "/.well-known/openid-configuration")
