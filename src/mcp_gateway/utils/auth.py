# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
import time
from contextvars import ContextVar

import httpx

# PyJWT ships as a pinned dependency of the mcp SDK (pyjwt[crypto] in uv.lock), so it is
# present in the image without widening this service's own dependency set.
import jwt

from starlette.types import ASGIApp, Receive, Scope, Send
from comps.cores.mega.logger import get_erag_logger

logger = get_erag_logger("mcp_gateway")

# ContextVar holding a mutable handle for the SSE connection being served. It is set once
# on connect and carries the session id, which is only known after FastMCP emits its
# endpoint event. A mutable handle is required because tool handlers do not run in the task
# that received the tool-call POST - the MCP SSE transport feeds requests into the
# long-lived stream task, which copied its context at connect time. Mutating the handle is
# visible there; rebinding a ContextVar would not be.
_current_session: ContextVar[dict | None] = ContextVar("_current_session", default=None)

# session_id -> {"caller": str, "azp": str, "token": str, "last_activity": float}
# The caller's own access token is held for the life of the session because that is what
# tool handlers forward to EDP. It is replaced by the fresher token on every tool call and
# dropped when the stream closes.
_session_state: dict[str, dict] = {}


class TokenError(Exception):
    """Raised when a bearer token is missing, malformed, expired or not issued for us."""


async def cleanup_inactive_sessions(timeout: int) -> None:
    """Background task - drop sessions idle beyond timeout."""
    while True:
        await asyncio.sleep(60)
        now = time.monotonic()
        to_remove = []
        for sid, state in list(_session_state.items()):
            if sid.startswith("__pending__"):
                continue
            if now - state.get("last_activity", now) > timeout:
                to_remove.append(sid)
        for sid in to_remove:
            _session_state.pop(sid, None)
            logger.info(f"Session {sid[:8]} closed due to inactivity")


def caller_identity(claims: dict) -> str:
    """Stable identity for a caller: the client the token was issued to plus its subject."""
    azp = claims.get("azp") or claims.get("client_id") or ""
    sub = claims.get("sub") or ""
    if not azp and not sub:
        raise TokenError("token carries neither azp/client_id nor sub")
    return f"{azp}:{sub}"


def get_caller_token() -> str:
    """Return the access token of the caller whose session is being served.

    The gateway never mints tokens of its own - it forwards the caller's token to EDP, so a
    tool call can never exceed the privileges of the agent that made it. The token is read
    from the session the handle points at, not from the calling task's context, because tool
    handlers run on the SSE stream task.
    """
    handle = _current_session.get()
    session_id = handle.get("session_id") if handle else None
    state = _session_state.get(session_id) if session_id else None
    token = state.get("token") if state else None
    if not token:
        raise RuntimeError("No caller token for this session - request was not authenticated")
    return token


class JwksVerifier:
    """Verifies caller tokens against the authorization server's published keys.

    The Envoy Gateway SecurityPolicy already validates tokens at the edge. Verifying again
    here means a request that reaches the pod by any other route (in-mesh caller, port
    forward) is held to the same standard, so the service does not depend on being behind
    the gateway for its authorization decisions.
    """

    def __init__(
        self,
        jwks_uri: str,
        issuer: str,
        audience: str,
        algorithms: list[str],
        cache_ttl: int = 300,
        min_refetch_interval: int = 30,
    ) -> None:
        self.jwks_uri = jwks_uri
        self.issuer = issuer
        self.audience = audience
        self.algorithms = algorithms
        self.cache_ttl = cache_ttl
        self.min_refetch_interval = min_refetch_interval
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def _refresh(self) -> None:
        async with self._lock:
            # Another coroutine may have refreshed while this one waited for the lock.
            if time.monotonic() - self._fetched_at < self.min_refetch_interval:
                return
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(self.jwks_uri)
            r.raise_for_status()
            key_set = jwt.PyJWKSet.from_dict(r.json())
            self._keys = {key.key_id: key for key in key_set.keys if key.key_id}
            self._fetched_at = time.monotonic()
            logger.info(f"Loaded {len(self._keys)} signing key(s) from {self.jwks_uri}")

    async def _key_for(self, kid: str | None) -> jwt.PyJWK:
        stale = time.monotonic() - self._fetched_at > self.cache_ttl
        if not self._keys or stale:
            await self._refresh()
        if kid and kid not in self._keys:
            # Unknown kid means either key rotation or a forged header. Refetching is
            # rate-limited so an attacker cannot turn bogus kids into a fetch amplifier.
            await self._refresh()
        if kid:
            key = self._keys.get(kid)
            if key is None:
                raise TokenError("token is signed by an unknown key")
            return key
        if len(self._keys) != 1:
            raise TokenError("token has no kid and the key set is ambiguous")
        return next(iter(self._keys.values()))

    async def verify(self, token: str) -> dict:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise TokenError("malformed token header") from exc

        try:
            key = await self._key_for(header.get("kid"))
        except httpx.HTTPError as exc:
            logger.error(f"Could not reach the JWKS endpoint {self.jwks_uri}: {exc}")
            raise TokenError("signing keys are temporarily unavailable") from exc

        try:
            return jwt.decode(
                token,
                key=key.key,
                algorithms=self.algorithms,
                audience=self.audience or None,
                issuer=self.issuer or None,
                leeway=30,
                options={"verify_aud": bool(self.audience), "require": ["exp"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenError("token has expired") from exc
        except jwt.InvalidAudienceError as exc:
            raise TokenError("token audience does not include this gateway") from exc
        except jwt.InvalidIssuerError as exc:
            raise TokenError("token issuer is not accepted by this gateway") from exc
        except jwt.PyJWTError as exc:
            raise TokenError("token signature or claims are not valid") from exc


async def _send_json_response(send: Send, status: int, body: str, extra_headers: list | None = None) -> None:
    encoded = body.encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(encoded)).encode()),
    ]
    headers.extend(extra_headers or [])
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": encoded, "more_body": False})


class BearerAuthMiddleware:
    """Bearer-token enforcement and per-session caller binding for MCP connections.

    Pure ASGI middleware (no BaseHTTPMiddleware) so that SSE streaming works correctly -
    BaseHTTPMiddleware buffers the response body, which breaks long-lived SSE streams.

    Agents obtain their own Keycloak token (client_credentials against their own client)
    and present it as `Authorization: Bearer`. The gateway is an OAuth 2.0 resource
    server: it never sees a client secret and never mints a token.

      On SSE connect (GET .../sse):
        - Verifies the token, enforces session caps per caller.
        - Intercepts the first SSE 'endpoint' event to learn FastMCP's session UUID and
          binds that UUID to the caller's identity.

      On tool call (POST .../messages/?session_id=<uuid>):
        - Verifies the token and requires its identity to match the one the session was
          opened with, so a leaked session UUID on its own grants nothing.
        - Stores the freshest verified token on the session, which is where tool handlers
          read it from; they run on the SSE stream task, not the POST task.

    Unauthenticated paths: the health endpoint and the protected-resource metadata
    document. Every 401 carries WWW-Authenticate with a resource_metadata pointer, which
    is how a spec-compliant MCP client discovers the authorization server and knows to
    refresh an expired token.
    """

    def __init__(
        self,
        app: ASGIApp,
        verifier,
        resource_metadata_url: str,
        public_paths: set[str],
        max_concurrent_sessions: int,
        max_sessions_per_client: int,
    ) -> None:
        self.app = app
        self.verifier = verifier
        self.resource_metadata_url = resource_metadata_url
        self.public_paths = public_paths
        self.max_concurrent_sessions = max_concurrent_sessions
        self.max_sessions_per_client = max_sessions_per_client

    def _challenge_header(self, error: str) -> list:
        value = f'Bearer realm="mcp", error="{error}"'
        if self.resource_metadata_url:
            value += f', resource_metadata="{self.resource_metadata_url}"'
        return [(b"www-authenticate", value.encode())]

    async def _unauthorized(self, send: Send, detail: str, error: str = "invalid_token") -> None:
        await _send_json_response(
            send,
            status=401,
            body=json.dumps({"error": error, "detail": detail}),
            extra_headers=self._challenge_header(error),
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "").rstrip("/")
        if path in self.public_paths:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"").decode().strip()
        scheme, _, token = authorization.partition(" ")
        token = token.strip()
        if scheme.lower() != "bearer" or not token:
            await self._unauthorized(send, "Provide an Authorization: Bearer <access_token> header")
            return

        try:
            claims = await self.verifier.verify(token)
            caller = caller_identity(claims)
        except TokenError as exc:
            await self._unauthorized(send, str(exc))
            return

        azp = claims.get("azp") or claims.get("client_id") or ""
        if path.endswith("/sse"):
            await self._handle_sse(scope, receive, send, caller, azp, token)
        else:
            await self._handle_message(scope, receive, send, caller, token)

    async def _handle_sse(
        self, scope: Scope, receive: Receive, send: Send, caller: str, azp: str, token: str
    ) -> None:
        if len(_session_state) >= self.max_concurrent_sessions:
            await _send_json_response(
                send,
                status=503,
                body='{"error":"too_many_sessions","detail":"Maximum concurrent sessions reached"}',
            )
            return

        if sum(1 for s in _session_state.values() if s.get("caller") == caller) >= self.max_sessions_per_client:
            await _send_json_response(
                send,
                status=503,
                body='{"error":"too_many_sessions_per_client","detail":"Maximum sessions per client reached"}',
            )
            return

        # Temporary key until FastMCP's endpoint event reveals the real session UUID.
        placeholder = f"__pending__{id(scope)}"
        _session_state[placeholder] = {
            "caller": caller,
            "azp": azp,
            "token": token,
            "last_activity": time.monotonic(),
        }
        # Set before the app runs so the stream task and everything it spawns inherit it.
        handle: dict = {"session_id": placeholder}
        ctx_token = _current_session.set(handle)

        # Wrap `send` to intercept the SSE endpoint event and re-key the session under the
        # UUID that subsequent POSTs will carry.
        real_uuid: list[str] = []

        async def _send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.body" and not real_uuid:
                body = message.get("body", b"")
                text = body.decode(errors="replace") if isinstance(body, bytes) else body
                if "event: endpoint" in text and "session_id=" in text:
                    for line in text.splitlines():
                        line = line.strip()
                        if line.startswith("data:") and "session_id=" in line:
                            uuid_hex = line.split("session_id=")[-1].strip()
                            if uuid_hex and not uuid_hex.startswith("__pending__"):
                                state = _session_state.pop(placeholder, None)
                                if state is not None:
                                    _session_state[uuid_hex] = state
                                    handle["session_id"] = uuid_hex
                                    real_uuid.append(uuid_hex)
                                    logger.info(f"Session {uuid_hex[:8]} bound to client {azp}")
                            break
            await send(message)

        try:
            await self.app(scope, receive, _send_wrapper)
        finally:
            _current_session.reset(ctx_token)
            _session_state.pop(real_uuid[0] if real_uuid else placeholder, None)

    async def _handle_message(self, scope: Scope, receive: Receive, send: Send, caller: str, token: str) -> None:
        query = scope.get("query_string", b"").decode()
        session_id: str | None = None
        for part in query.split("&"):
            if part.startswith("session_id="):
                session_id = part[len("session_id="):]
                break

        state = _session_state.get(session_id) if session_id else None
        if state is None:
            await _send_json_response(
                send,
                status=404,
                body='{"error":"unknown_session","detail":"No active session for the given session_id"}',
            )
            return

        # The session UUID travels in the URL and therefore through access logs. Binding it
        # to the caller identity means possession of the UUID alone grants nothing.
        if state.get("caller") != caller:
            logger.warning(f"Rejected session {session_id[:8]} - caller does not own this session")
            await _send_json_response(
                send,
                status=403,
                body='{"error":"session_mismatch","detail":"Token does not belong to this session"}',
            )
            return

        # Hand the freshest verified token to the session so tool handlers running on the
        # stream task forward a token that is still valid.
        state["token"] = token
        state["last_activity"] = time.monotonic()
        await self.app(scope, receive, send)
