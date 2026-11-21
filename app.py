"""
InfraGov Assessment Tool — Dash application entry point (Posit Connect).

Pages are addressed with a query parameter:  /?page=<name>[&key=value…]
e.g. /?page=home, /?page=assessments, /?page=dimension&id=<uuid>&dim=3

Run locally:   python app.py            (APP_ENV=development, DB_BACKEND=sqlite)
Posit Connect: entrypoint "app:app" (see manifest.json)
"""
from __future__ import annotations

import io
import logging
import os
import sys
from datetime import timedelta
from urllib.parse import parse_qs

import dash
import flask
from dash import Dash, Input, Output, State, dcc, html

import constants as C

logging.basicConfig(level=logging.INFO if C.IS_PRODUCTION else logging.DEBUG,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("infragov")

_problems = C.validate_runtime_config()
if _problems:
    for p in _problems:
        log.critical("Configuration error: %s", p)
    if C.IS_PRODUCTION:
        sys.exit("Refusing to start with an insecure/incomplete configuration. See .env.sample.")

# ---------------------------------------------------------------- Flask / Dash
server = flask.Flask(__name__)
server.config.update(
    SECRET_KEY=C.SECRET_KEY or os.urandom(32),
    SESSION_COOKIE_NAME=C.SESSION_COOKIE_NAME,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=C.IS_PRODUCTION,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_PATH=os.environ.get("DASH_REQUESTS_PATHNAME_PREFIX", "/") or "/",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=C.SESSION_ABSOLUTE_TIMEOUT_HOURS),
    MAX_CONTENT_LENGTH=C.MAX_CONTENT_LENGTH,
    PROPAGATE_EXCEPTIONS=False,
    DEBUG=False,
)

app = Dash(
    __name__,
    server=server,
    title=C.APP_TITLE,
    update_title=None,
    suppress_callback_exceptions=True,
    serve_locally=True,             # never pull JS/CSS from a CDN
    compress=False,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"},
               {"name": "description", "content": C.APP_DESCRIPTION},
               {"name": "referrer", "content": "same-origin"}],
)
app.config.include_assets_files = True

# Import page modules (registers their callbacks).
from pages import (  # noqa: E402
    about, account, admin, assessments, country, dashboard, details, dimension_entry, dimensions, errors, forgot_password,
    home, join, login, new_assessment, publish, release_notes, report, reset_password, shared_panels, shell, suggest_responses,
    visualization,
)
from pages import pages_constants as PC  # noqa: E402
from services import auth, repository  # noqa: E402
from services import documents as D  # noqa: E402
from services import permissions as P  # noqa: E402
from services.security import init_security  # noqa: E402
from utils.components import href  # noqa: E402
from utils.context import Ctx, current_locale  # noqa: E402
from utils.layout import assessment_shell, tutorial_modal  # noqa: E402

init_security(server, lambda: app.csp_hashes())

app.layout = html.Div([
    dcc.Location(id="url", refresh="callback-nav"),
    dcc.Store(id="refresh", data=0),
    dcc.Download(id="download"),
    html.Div(id="tutorial-host"),
    html.Div(id="modal-host"),
    dcc.Loading(html.Div(id="page-content"), type="circle", color="#4345AA", delay_show=400, overlay_style={"visibility": "visible", "opacity": 0.6}),
])

ASSESSMENT_PAGES = {"dimensions", "dimension", "publish", "visualization", "details", "report"}


def _params(search: str | None) -> tuple[str, dict[str, str]]:
    raw = parse_qs((search or "").lstrip("?"), keep_blank_values=False)
    page = (raw.get("page") or [PC.PAGE_HOME])[0][:40]
    allowed = PC.PAGES.get(page, (False, False, ()))[2]
    params = {k: v[0][:200] for k, v in raw.items() if k in allowed and v}
    return page, params


def render_page(search: str | None):
    page, params = _params(search)
    user = auth.current_user()
    locale = current_locale()
    ctx = Ctx(user=user, locale=locale, page=page, params=params)
    if page not in PC.PAGES:
        return errors.not_found(ctx), None
    needs_login, admin_only, _ = PC.PAGES[page]
    if needs_login and not user:
        nxt = {"token": params["token"]} if page == "join" and params.get("token") else {}
        return None, href("login", **nxt)
    if page in PC.PUBLIC_ONLY_PAGES and user:
        return None, href("assessments")
    if admin_only and not P.is_admin(user):
        auth.log_security_event("authz.admin_denied", user["id"] if user else None, page)
        return None, href("assessments")
    if user:
        ctx.nav_countries = repository.countries_by_framework(user)
        if P.is_admin(user):
            ctx.pending = repository.pending_unpublish_requests(user, locale)
        ctx.bell = shell.bell(ctx.pending, P.is_admin(user))
    simple = {"home": home, "about": about, "release-notes": release_notes, "login": login, "forgot-password": forgot_password,
              "reset-password": reset_password, "join": join, "assessments": assessments, "new-assessment": new_assessment,
              "dashboard": dashboard, "country": country, "account": account, "admin": admin}
    try:
        if page in simple:
            return simple[page].layout(ctx), None
        aid = params.get("id", "")
        from services.validators import is_uuid

        if not is_uuid(aid):
            return errors.not_found(ctx, "Assessment not found."), None
        a = repository.get_assessment(user, aid, locale, entries=True, comments=page == "dimension", team=page == "details",
                                      unpublish=page == "dimension")
        ctx.assessment_kind = a["kind"]
        if page == "report":
            return html.Div([shell_nav(ctx), html.Div(report.layout(ctx, a), className="pt-14 print:pt-0")],
                            className="min-h-screen bg-gray-100", **{"data-framework": a["kind"]}), None
        dim = None
        if page in ("dimension", "publish"):
            try:
                dim = int(params.get("dim", "1"))
            except ValueError:
                dim = 1
        body = {
            "dimensions": lambda: dimensions.content(ctx, a),
            "dimension": lambda: dimension_entry.content(ctx, a, dim),
            "publish": lambda: publish.content(ctx, a, dim),
            "visualization": lambda: visualization.content(ctx, a),
            "details": lambda: details.content(ctx, a),
        }[page]()
        return assessment_shell(ctx, a, body, P.can_manage(user, a)), None
    except repository.Forbidden as exc:
        return errors.forbidden(ctx, str(exc)), None
    except repository.NotFound as exc:
        return errors.not_found(ctx, str(exc)), None


def shell_nav(ctx):
    from utils.layout import navbar

    return navbar(ctx)


@app.callback(Output("page-content", "children"), Output("url", "href"), Output("tutorial-host", "children"),
              Input("url", "search"), Input("refresh", "data"), State("url", "href"))
def route(search, _refresh, current_href):
    try:
        content, redirect = render_page(search)
    except Exception:  # noqa: BLE001
        log.exception("Page render failed")
        return errors.not_found(Ctx(None, "en", "error", {}), "Something went wrong loading this page."), dash.no_update, None
    tutorial = None
    page, _ = _params(search)
    if page == "assessments" and content is not None and auth.current_user() and not flask.session.get("tutorial_seen", True):
        tutorial = tutorial_modal(True)
    if redirect:
        return dash.no_update, redirect, None
    return content, dash.no_update, tutorial


# ---------------------------------------------------------------- authorised file download
@server.route("/files/document/<doc_id>")
def download_document(doc_id: str):
    from services.validators import is_uuid

    user = auth.current_user()
    if not user:
        flask.abort(401)
    if not is_uuid(doc_id):
        flask.abort(404)
    try:
        name, mime, data = D.download(user, doc_id)
    except repository.Forbidden:
        auth.log_security_event("authz.document_denied", user["id"], doc_id)
        flask.abort(403)
    except repository.NotFound:
        flask.abort(404)
    resp = flask.send_file(io.BytesIO(data), mimetype=mime, as_attachment=True, download_name=name)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return resp


@server.route("/healthz")
def healthz():
    return flask.Response("ok", mimetype="text/plain")


# ---------------------------------------------------------------- local development server
if __name__ == "__main__":
    # Debug stays OFF even locally unless APP_ENV=development AND DASH_DEBUG=true.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8050")), debug=C.DEBUG,
            dev_tools_ui=C.DEBUG, dev_tools_props_check=C.DEBUG, dev_tools_hot_reload=False)
