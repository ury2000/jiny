"""OAuth 2.0 (PKCE S256) authentication and atomic token persistence for Jiny Companion."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import time
from typing import Any, Callable, Optional, Sequence
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

DEFAULT_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
DEFAULT_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
DEFAULT_OAUTH_SCOPES: tuple[str, ...] = ("https://www.googleapis.com/auth/cloud-platform",)
DEFAULT_TOKEN_PATH = Path(__file__).resolve().parent / "oauth_token.json"

HttpTransport = Callable[[str, dict[str, str], Optional[bytes], float], tuple[int, bytes]]


class OAuthError(RuntimeError):
    """Raised when OAuth authorization, token exchange, or persistence fails."""


def default_http_transport(
    url: str,
    headers: dict[str, str],
    body: Optional[bytes],
    timeout: float,
) -> tuple[int, bytes]:
    """Perform an HTTP GET/POST request via stdlib urllib without leaking secrets."""
    method = "POST" if body is not None else "GET"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            return int(status), response.read()
    except urllib.error.HTTPError as exc:
        payload = exc.read() if hasattr(exc, "read") else b""
        return int(exc.code), payload
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OAuthError(f"OAuth HTTP transport error: {exc.__class__.__name__}: {exc}") from exc


def generate_code_verifier() -> str:
    """Generate an RFC 7636 compliant PKCE code verifier (64 URL-safe chars)."""
    return base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode("ascii")


def compute_code_challenge(verifier: str) -> str:
    """Compute an S256 PKCE code challenge from a verifier."""
    if not verifier:
        raise OAuthError("PKCE code_verifier must not be empty.")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def generate_state() -> str:
    """Generate a high-entropy OAuth state parameter."""
    return secrets.token_urlsafe(32)


def load_client_secrets_file(path: Path) -> dict[str, str]:
    """Load Google OAuth client secrets ('installed', 'web', or flat JSON)."""
    if not path.exists():
        raise OAuthError(f"Client secrets file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OAuthError(f"Failed to read client secrets JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise OAuthError("Client secrets JSON must be an object.")

    section: dict[str, Any]
    if isinstance(raw.get("installed"), dict):
        section = raw["installed"]
    elif isinstance(raw.get("web"), dict):
        section = raw["web"]
    else:
        section = raw

    client_id = str(section.get("client_id", "")).strip()
    if not client_id:
        raise OAuthError("Client secrets JSON is missing 'client_id'.")

    return {
        "client_id": client_id,
        "client_secret": str(section.get("client_secret", "")).strip(),
        "auth_uri": str(section.get("auth_uri", DEFAULT_AUTH_ENDPOINT)).strip() or DEFAULT_AUTH_ENDPOINT,
        "token_uri": str(section.get("token_uri", DEFAULT_TOKEN_ENDPOINT)).strip() or DEFAULT_TOKEN_ENDPOINT,
    }


def _parse_finite_float(raw: Any, field_name: str) -> float:
    """Parse a finite float, rejecting booleans, NaN, and +/-inf with OAuthError."""
    if isinstance(raw, bool):
        raise OAuthError(f"Invalid '{field_name}' in OAuth payload.")
    try:
        val = float(raw)
    except (TypeError, ValueError) as exc:
        raise OAuthError(f"Invalid '{field_name}' in OAuth payload.") from exc
    if not math.isfinite(val):
        raise OAuthError(f"Invalid '{field_name}' in OAuth payload.")
    return val


@dataclass
class OAuthToken:
    """Stored OAuth 2.0 token bundle (sensitive fields hidden from repr)."""

    access_token: str = field(repr=False)
    token_type: str = "Bearer"
    refresh_token: Optional[str] = field(default=None, repr=False)
    expires_at: Optional[float] = None
    scope: Optional[str] = None
    id_token: Optional[str] = field(default=None, repr=False)

    def is_expired(self, leeway_seconds: float = 60.0, now: Optional[float] = None) -> bool:
        if self.expires_at is None:
            return False
        current = time.time() if now is None else now
        return current >= (self.expires_at - max(0.0, leeway_seconds))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "access_token": self.access_token,
            "token_type": self.token_type,
        }
        if self.refresh_token:
            payload["refresh_token"] = self.refresh_token
        if self.expires_at is not None:
            payload["expires_at"] = self.expires_at
        if self.scope:
            payload["scope"] = self.scope
        if self.id_token:
            payload["id_token"] = self.id_token
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OAuthToken":
        if not isinstance(data, dict):
            raise OAuthError("OAuth token payload must be a JSON object.")
        access_token = str(data.get("access_token", "")).strip()
        if not access_token:
            raise OAuthError("OAuth token payload missing 'access_token'.")
        expires_raw = data.get("expires_at")
        expires_at: Optional[float] = None
        if expires_raw is not None:
            expires_at = _parse_finite_float(expires_raw, "expires_at")
        refresh_token = data.get("refresh_token")
        scope = data.get("scope")
        id_token = data.get("id_token")
        return cls(
            access_token=access_token,
            token_type=str(data.get("token_type", "Bearer") or "Bearer").strip(),
            refresh_token=str(refresh_token).strip() if refresh_token else None,
            expires_at=expires_at,
            scope=str(scope).strip() if scope else None,
            id_token=str(id_token).strip() if id_token else None,
        )


class OAuthTokenStore:
    """Atomic UTF-8 JSON file store for OAuth tokens."""

    def __init__(self, token_path: Path = DEFAULT_TOKEN_PATH) -> None:
        self.token_path = Path(token_path)

    def load(self) -> Optional[OAuthToken]:
        if not self.token_path.exists():
            return None
        try:
            raw = json.loads(self.token_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OAuthError(f"Failed to read OAuth token store '{self.token_path}': {exc}") from exc
        return OAuthToken.from_dict(raw)

    def save(self, token: OAuthToken) -> Path:
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.token_path.with_suffix(self.token_path.suffix + ".tmp")
        try:
            serialized = json.dumps(token.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n"
        except (TypeError, ValueError) as exc:
            raise OAuthError(f"Cannot serialize OAuth token to JSON: {exc}") from exc
        tmp_path.write_text(serialized, encoding="utf-8")
        os.replace(tmp_path, self.token_path)
        try:
            os.chmod(self.token_path, 0o600)
        except OSError:
            pass
        return self.token_path

    def clear(self) -> None:
        if self.token_path.exists():
            self.token_path.unlink()


class OAuthManager:
    """Manages OAuth 2.0 PKCE authorization, token exchange, refresh, and status."""

    def __init__(
        self,
        client_id: str,
        client_secret: str = "",
        token_path: Path = DEFAULT_TOKEN_PATH,
        scopes: Sequence[str] = DEFAULT_OAUTH_SCOPES,
        auth_endpoint: str = DEFAULT_AUTH_ENDPOINT,
        token_endpoint: str = DEFAULT_TOKEN_ENDPOINT,
        http_transport: Optional[HttpTransport] = None,
        timeout: float = 30.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.client_id = (client_id or "").strip()
        self.client_secret = (client_secret or "").strip()
        self.store = OAuthTokenStore(token_path)
        self.scopes = tuple(s.strip() for s in scopes if str(s).strip()) or DEFAULT_OAUTH_SCOPES
        self.auth_endpoint = (auth_endpoint or DEFAULT_AUTH_ENDPOINT).strip()
        self.token_endpoint = (token_endpoint or DEFAULT_TOKEN_ENDPOINT).strip()
        self._http_transport: HttpTransport = http_transport or default_http_transport
        self.timeout = max(1.0, float(timeout))
        self._clock = clock

    def build_authorization_url(self, redirect_uri: str, state: str, code_challenge: str) -> str:
        if not self.client_id:
            raise OAuthError("Missing OAuth client_id.")
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(self.scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{self.auth_endpoint}?{urllib.parse.urlencode(params)}"

    def _post_token_form(self, form_fields: dict[str, str]) -> dict[str, Any]:
        encoded = urllib.parse.urlencode(form_fields).encode("utf-8")
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        status, raw_body = self._http_transport(self.token_endpoint, headers, encoded, self.timeout)
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OAuthError(f"OAuth token endpoint returned invalid JSON (HTTP {status}).") from exc

        if not isinstance(payload, dict):
            raise OAuthError(f"OAuth token endpoint returned unexpected payload (HTTP {status}).")

        if status >= 400 or "error" in payload:
            err_code = str(payload.get("error", f"http_{status}"))
            err_desc = str(payload.get("error_description", "")).strip()
            detail = f"{err_code}: {err_desc}" if err_desc else err_code
            raise OAuthError(f"OAuth token request failed ({detail}).")

        return payload

    def _token_from_response(
        self,
        payload: dict[str, Any],
        fallback_refresh_token: Optional[str] = None,
    ) -> OAuthToken:
        access_token = str(payload.get("access_token", "")).strip()
        if not access_token:
            raise OAuthError("OAuth token response did not include 'access_token'.")

        expires_at: Optional[float] = None
        if payload.get("expires_in") is not None:
            expires_in = _parse_finite_float(payload["expires_in"], "expires_in")
            expires_at = self._clock() + expires_in
            if not math.isfinite(expires_at):
                raise OAuthError("Invalid 'expires_in' in OAuth payload.")
        elif payload.get("expires_at") is not None:
            expires_at = _parse_finite_float(payload["expires_at"], "expires_at")

        refresh_raw = payload.get("refresh_token")
        refresh_token = str(refresh_raw).strip() if refresh_raw else fallback_refresh_token

        return OAuthToken(
            access_token=access_token,
            token_type=str(payload.get("token_type", "Bearer") or "Bearer").strip(),
            refresh_token=refresh_token,
            expires_at=expires_at,
            scope=str(payload.get("scope")).strip() if payload.get("scope") else None,
            id_token=str(payload.get("id_token")).strip() if payload.get("id_token") else None,
        )

    def exchange_code(self, code: str, redirect_uri: str, code_verifier: str) -> OAuthToken:
        if not self.client_id:
            raise OAuthError("Missing OAuth client_id.")
        clean_code = (code or "").strip()
        if not clean_code:
            raise OAuthError("Authorization code must not be empty.")

        form: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": clean_code,
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "code_verifier": code_verifier,
        }
        if self.client_secret:
            form["client_secret"] = self.client_secret

        payload = self._post_token_form(form)
        token = self._token_from_response(payload)
        self.store.save(token)
        return token

    def refresh_access_token(self, token: Optional[OAuthToken] = None) -> OAuthToken:
        if not self.client_id:
            raise OAuthError("Missing OAuth client_id for token refresh.")
        current = token if token is not None else self.store.load()
        if current is None:
            raise OAuthError("No stored OAuth token found. Run --oauth-login first.")
        if not current.refresh_token:
            raise OAuthError("Stored OAuth token has no refresh_token. Re-run --oauth-login.")

        form: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": current.refresh_token,
            "client_id": self.client_id,
        }
        if self.client_secret:
            form["client_secret"] = self.client_secret

        payload = self._post_token_form(form)
        refreshed = self._token_from_response(payload, fallback_refresh_token=current.refresh_token)
        self.store.save(refreshed)
        return refreshed

    def get_access_token(self, force_refresh: bool = False, leeway_seconds: float = 60.0) -> str:
        token = self.store.load()
        if token is None:
            raise OAuthError("OAuth token not found. Run --oauth-login to authenticate.")
        if force_refresh or token.is_expired(leeway_seconds=leeway_seconds, now=self._clock()):
            token = self.refresh_access_token(token)
        return token.access_token

    def get_token_status(self) -> dict[str, Any]:
        """Return safe, non-secret status metadata about the stored token."""
        try:
            token = self.store.load()
        except OAuthError as exc:
            return {
                "token_path": str(self.store.token_path),
                "has_token": False,
                "has_refresh_token": False,
                "expired": True,
                "expires_at": None,
                "error": str(exc),
            }

        if token is None:
            return {
                "token_path": str(self.store.token_path),
                "has_token": False,
                "has_refresh_token": False,
                "expired": True,
                "expires_at": None,
            }

        return {
            "token_path": str(self.store.token_path),
            "has_token": True,
            "has_refresh_token": bool(token.refresh_token),
            "expired": token.is_expired(now=self._clock()),
            "expires_at": token.expires_at,
            "scope": token.scope,
        }

    def authorize_interactive(
        self,
        port: int = 0,
        timeout_seconds: float = 180.0,
        open_browser: bool = True,
        manual_fallback: bool = True,
        input_fn: Callable[[str], str] = input,
    ) -> OAuthToken:
        """Run PKCE loopback OAuth authorization flow with manual redirect/code fallback."""
        if not self.client_id:
            raise OAuthError("Missing OAuth client_id. Configure oauth_client_id first.")

        verifier = generate_code_verifier()
        challenge = compute_code_challenge(verifier)
        expected_state = generate_state()

        if port < 0:
            redirect_uri = "http://127.0.0.1/callback"
            auth_url = self.build_authorization_url(redirect_uri, expected_state, challenge)
            if open_browser:
                webbrowser.open(auth_url)
            if not manual_fallback:
                raise OAuthError("Loopback server disabled and manual_fallback=False.")
            return self._complete_manual_flow(auth_url, redirect_uri, expected_state, verifier, input_fn)

        result: dict[str, Any] = {"code": None, "error": None}

        class _CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self_req) -> None:
                parsed = urllib.parse.urlparse(self_req.path)
                if parsed.path not in ("/callback", "/"):
                    body = b"Not Found"
                    self_req.send_response(404)
                    self_req.send_header("Content-Type", "text/plain; charset=utf-8")
                    self_req.send_header("Content-Length", str(len(body)))
                    self_req.end_headers()
                    self_req.wfile.write(body)
                    return

                params = urllib.parse.parse_qs(parsed.query)
                if "error" in params:
                    result["error"] = OAuthError(f"Authorization denied: {params['error'][0]}")
                    body = b"<html><body><h3>Jiny OAuth failed. You may close this tab.</h3></body></html>"
                    self_req.send_response(400)
                else:
                    recv_state = params.get("state", [""])[0]
                    recv_code = params.get("code", [""])[0]
                    if recv_state != expected_state:
                        result["error"] = OAuthError("OAuth state mismatch in callback.")
                        body = b"<html><body><h3>Invalid OAuth state.</h3></body></html>"
                        self_req.send_response(400)
                    elif not recv_code:
                        result["error"] = OAuthError("OAuth callback did not contain a code.")
                        body = b"<html><body><h3>Missing authorization code.</h3></body></html>"
                        self_req.send_response(400)
                    else:
                        result["code"] = recv_code
                        body = b"<html><body><h3>Jiny OAuth complete. You may close this tab.</h3></body></html>"
                        self_req.send_response(200)

                self_req.send_header("Content-Type", "text/html; charset=utf-8")
                self_req.send_header("Content-Length", str(len(body)))
                self_req.end_headers()
                self_req.wfile.write(body)

            def log_message(self_req, format: str, *args: Any) -> None:
                return

        server: Optional[HTTPServer] = None
        try:
            server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
        except OSError as exc:
            if not manual_fallback:
                raise OAuthError(f"Failed to start loopback OAuth server: {exc}") from exc
            redirect_uri = "http://127.0.0.1/callback"
            auth_url = self.build_authorization_url(redirect_uri, expected_state, challenge)
            if open_browser:
                webbrowser.open(auth_url)
            return self._complete_manual_flow(auth_url, redirect_uri, expected_state, verifier, input_fn)

        try:
            actual_port = server.server_address[1]
            redirect_uri = f"http://127.0.0.1:{actual_port}/callback"
            auth_url = self.build_authorization_url(redirect_uri, expected_state, challenge)
            print(f"Open this URL to authorize Jiny:\n{auth_url}")
            if open_browser:
                webbrowser.open(auth_url)

            server.timeout = 0.5
            deadline = self._clock() + max(0.5, timeout_seconds)
            while result["code"] is None and result["error"] is None and self._clock() < deadline:
                server.handle_request()
        finally:
            server.server_close()

        if result["error"] is not None:
            raise result["error"]
        if result["code"]:
            return self.exchange_code(result["code"], redirect_uri, verifier)

        if manual_fallback:
            return self._complete_manual_flow(auth_url, redirect_uri, expected_state, verifier, input_fn)
        raise OAuthError("Timed out waiting for OAuth callback.")

    def _complete_manual_flow(
        self,
        auth_url: str,
        redirect_uri: str,
        expected_state: str,
        verifier: str,
        input_fn: Callable[[str], str],
    ) -> OAuthToken:
        print(f"Manual OAuth fallback. Authorize at:\n{auth_url}")
        raw_entry = input_fn("Paste the full redirect URL or authorization code: ").strip()
        if not raw_entry:
            raise OAuthError("No authorization code or redirect URL provided.")

        code = raw_entry
        if "://" in raw_entry or "?" in raw_entry:
            parsed = urllib.parse.urlparse(raw_entry)
            params = urllib.parse.parse_qs(parsed.query)
            if "error" in params:
                raise OAuthError(f"Authorization denied: {params['error'][0]}")
            if "state" in params and params["state"][0] != expected_state:
                raise OAuthError("OAuth state mismatch in pasted redirect URL.")
            code = params.get("code", [""])[0].strip()

        if not code:
            raise OAuthError("Could not extract authorization code.")
        return self.exchange_code(code, redirect_uri, verifier)


def run_oauth_login(
    cfg: Any,
    open_browser: bool = True,
    port: int = 0,
    timeout_seconds: float = 180.0,
    manual_fallback: bool = True,
    input_fn: Callable[[str], str] = input,
    manager: Optional[OAuthManager] = None,
) -> Path:
    """Execute interactive OAuth login using CompanionConfig and persist oauth_token.json."""
    if manager is None:
        client_id = str(getattr(cfg, "oauth_client_id", "") or "").strip()
        if not client_id:
            raise OAuthError(
                "Missing OAuth client_id. Set JINY_OAUTH_CLIENT_ID or 'oauth_client_id' in config.json."
            )
        manager = OAuthManager(
            client_id=client_id,
            client_secret=str(getattr(cfg, "oauth_client_secret", "") or "").strip(),
            token_path=Path(getattr(cfg, "oauth_token_path", DEFAULT_TOKEN_PATH)),
            scopes=tuple(getattr(cfg, "oauth_scopes", DEFAULT_OAUTH_SCOPES) or DEFAULT_OAUTH_SCOPES),
            auth_endpoint=str(getattr(cfg, "oauth_auth_endpoint", DEFAULT_AUTH_ENDPOINT) or DEFAULT_AUTH_ENDPOINT),
            token_endpoint=str(getattr(cfg, "oauth_token_endpoint", DEFAULT_TOKEN_ENDPOINT) or DEFAULT_TOKEN_ENDPOINT),
        )
    manager.authorize_interactive(
        port=port,
        timeout_seconds=timeout_seconds,
        open_browser=open_browser,
        manual_fallback=manual_fallback,
        input_fn=input_fn,
    )
    return manager.store.token_path
