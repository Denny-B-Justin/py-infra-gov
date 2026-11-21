"""
HTTP-layer security for the Flask server that hosts Dash.

  * Security headers: strict CSP (scripts only from 'self' + hashes of Dash's
    own inline bootstrap), HSTS, nosniff, frame-ancestors, referrer policy,
    permissions policy, COOP/CORP, no-store caching of dynamic responses.
  * CORS: no Access-Control-* headers are ever emitted, so browsers block
    cross-origin reads; cross-origin state-changing requests are rejected by
    an Origin/Referer check (CSRF defence together with SameSite cookies).
  * Exposed files: dotfiles, source, config and backup paths return 404.
  * Errors: generic messages only (no stack traces); details go to the log.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import flask
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

import constants as C

log = logging.getLogger("infragov.security")

_BLOCKED = re.compile(
    r"(^|/)\.(?!well-known)|\.(py|pyc|env|ini|cfg|toml|lock|sqlite3?|db|bak|old|orig|swp|log|sql|pem|key|crt|json\.map)$|"
    r"(^|/)(requirements\.txt|manifest\.json|constants|services|pages|utils|migration|data)(/|$)",
    re.I,
)
_STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}


def _origin_of(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}".lower() if p.scheme and p.netloc else ""


def _allowed_origins() -> set[str]:
    req = flask.request
    allowed = {f"{req.scheme}://{req.host}".lower()}
    if C.APP_BASE_URL:
        allowed.add(_origin_of(C.APP_BASE_URL))
    allowed.update(o.lower() for o in C.ALLOWED_ORIGINS)
    return allowed


def build_csp(script_hashes: list[str]) -> str:
    hashes = " ".join(h if h.startswith("'") else f"'{h}'" for h in script_hashes)
    return "; ".join([
        "default-src 'self'",
        f"script-src 'self' {hashes}".strip(),
        # Dash/Plotly inject <style> elements at runtime; inline *styles* are
        # far lower risk than scripts, which remain strictly locked down.
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self'",
        "media-src 'self'",
        "connect-src 'self'",
        "worker-src 'self' blob:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        # Posit Connect shows content inside its own (same-origin) frame.
        "frame-ancestors 'self'",
        "upgrade-insecure-requests" if C.IS_PRODUCTION else "",
    ]).strip("; ")


def init_security(server: flask.Flask, get_script_hashes) -> None:
    server.wsgi_app = ProxyFix(server.wsgi_app, x_for=1, x_proto=1, x_host=1)  # type: ignore[assignment]
    csp_cache: dict[str, str] = {}

    @server.before_request
    def _guard():
        req = flask.request
        path = req.path or "/"
        if _BLOCKED.search(path.lstrip("/")):
            flask.abort(404)
        if req.method == "OPTIONS":
            # No CORS preflight support: cross-origin callers are refused.
            flask.abort(403)
        if req.method in _STATE_CHANGING:
            origin = req.headers.get("Origin") or _origin_of(req.headers.get("Referer", ""))
            if not origin or origin.lower() not in _allowed_origins():
                log.warning("Blocked cross-origin %s %s", req.method, path)
                flask.abort(403)
            if path.endswith("/_dash-update-component") and not req.is_json:
                flask.abort(415)

    @server.after_request
    def _headers(resp: flask.Response):
        if "csp" not in csp_cache:
            csp_cache["csp"] = build_csp(get_script_hashes())
        h = resp.headers
        h["Content-Security-Policy"] = csp_cache["csp"]
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "SAMEORIGIN"
        h["Referrer-Policy"] = "same-origin"
        h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        h["Cross-Origin-Resource-Policy"] = "same-origin"
        h["X-Permitted-Cross-Domain-Policies"] = "none"
        if C.IS_PRODUCTION:
            h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        for k in ("Access-Control-Allow-Origin", "Access-Control-Allow-Credentials"):
            h.pop(k, None)
        path = flask.request.path or ""
        if "/assets/" in path or "/_dash-component-suites/" in path:
            h.setdefault("Cache-Control", "public, max-age=3600")
        else:
            h["Cache-Control"] = "no-store"
            h["Pragma"] = "no-cache"
        return resp

    @server.errorhandler(Exception)
    def _errors(exc: Exception):
        if isinstance(exc, HTTPException):
            code = exc.code or 500
            return flask.Response(f"{code} {exc.name}", status=code, mimetype="text/plain")
        log.exception("Unhandled server error")
        return flask.Response("500 Internal Server Error", status=500, mimetype="text/plain")
