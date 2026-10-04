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
    """OIDC discovery/JWKS port with asymmetric verification and bounded cache."""
    def __init__(self, transport: Callable[[str], dict[str, Any]], issuer: str, *, clock: Callable[[], float] = time.time, max_age: int = 300, max_keys: int = 32) -> None:
        if not issuer.startswith(("https://", "http://")): raise ValueError("invalid issuer")
        self.transport, self.issuer, self.clock, self.max_age, self.max_keys = transport, issuer.rstrip("/"), clock, max_age, max_keys
        self._discovery: tuple[float, dict[str, Any]] | None = None; self._jwks: tuple[float, dict[str, Any]] | None = None

    @traced
    def discover(self) -> dict[str, Any]:
        if self._discovery and self.clock() - self._discovery[0] < self.max_age: return self._discovery[1]
        result = self.transport(self.issuer + "/.well-known/openid-configuration")
        if result.get("issuer") and result["issuer"].rstrip("/") != self.issuer: raise ValueError("issuer mismatch")
        self._discovery = (self.clock(), result); return result

    @traced
    def jwks(self) -> dict[str, Any]:
        if self._jwks and self.clock() - self._jwks[0] < self.max_age: return self._jwks[1]
        result = self.transport(str(self.discover()["jwks_uri"]))
        self._jwks = (self.clock(), {"keys": list(result.get("keys", []))[:self.max_keys]}); return self._jwks[1]

    @traced
    def verify(self, token: str, *, audience: str, client_id: str | None = None) -> Claims:
        """Verify asymmetric OIDC signatures; stale/outage responses are rejected."""
        try:
            head, body, signature = token.split("."); header = json.loads(_unb64(head)); payload = json.loads(_unb64(body)); now = int(self.clock())
            if header.get("alg") not in {"RS256", "ES256"}: raise ValueError("algorithm")
            key = next((k for k in self.jwks()["keys"] if k.get("kid") == header.get("kid")), None)
            if key is None: raise ValueError("key")
            from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
            from cryptography.hazmat.primitives.hashes import SHA256
            signing, sig = f"{head}.{body}".encode(), _unb64(signature)
            if header["alg"] == "RS256":
                n, e = int.from_bytes(_unb64(key["n"]), "big"), int.from_bytes(_unb64(key["e"]), "big")
                rsa.RSAPublicNumbers(e, n).public_key().verify(sig, signing, padding.PKCS1v15(), SHA256())
            else:
                x, y = int.from_bytes(_unb64(key["x"]), "big"), int.from_bytes(_unb64(key["y"]), "big")
                ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key().verify(sig, signing, ec.ECDSA(SHA256()))
            if not payload.get("iss") or payload["iss"].rstrip("/") != self.issuer or payload.get("aud") != audience or (client_id and payload.get("azp") not in {None, client_id}): raise ValueError("claims")
            if int(payload.get("exp", 0)) <= now: raise ValueError("expiry")
            return Claims(str(payload["sub"]), str(payload.get("role", "device")), audience, int(payload["exp"]), str(payload.get("jti", "")))
        except (ConnectionError, TimeoutError) as exc:
            # Identity-provider outage is fail-closed for new access; cached keys are bounded.
            raise ValueError("OIDC provider unavailable") from exc
        except Exception as exc:
            if isinstance(exc, ValueError): raise ValueError("invalid OIDC token") from exc
            raise ValueError("invalid OIDC token") from exc
