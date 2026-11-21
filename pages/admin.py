"""Admin → Users — /?page=admin (port of app/[locale]/admin/invites/page.tsx + /api/admin/invites).

Protected twice: the router refuses non-Admins, and every callback re-checks
the Admin role server-side before doing anything.
"""
from __future__ import annotations

from dash import ALL, Input, Output, State, callback, ctx as dctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

import constants as C
from pages import pages_constants as PC
from services import permissions as P
from services import users
from utils.components import alert, icon
from utils.context import base_url, require_user, user_message
from utils.countries import country_names
from utils.layout import app_shell

L = "block text-xs font-semibold text-gray-600 mb-1"
IN = "w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"


def _require_admin() -> dict:
    user = require_user()
    if not P.is_admin(user):
        raise PreventUpdate
    return user


def users_list(admin):
    rows = users.list_users(admin)
    return html.Div([
        html.Header(html.Div([html.H2("Users on the platform", className="text-sm font-semibold text-gray-800"),
                              html.P(f"{len(rows)} {'user' if len(rows) == 1 else 'users'}", className="text-xs text-gray-500 mt-0.5")]),
                    className="px-5 py-4 border-b border-gray-100"),
        html.P("No users yet.", className="px-5 py-8 text-center text-sm text-gray-400") if not rows else html.Ul([html.Li([
            html.Div("".join(s[0] for s in (r["name"] or r["email"]).split() if s)[:2].upper(),
                     className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-xs font-bold shrink-0"),
            html.Div([html.P(r["name"] or html.Span("No name set", className="text-gray-400 italic"), className="text-sm font-medium text-gray-800 truncate"),
                      html.P(" · ".join(x for x in (r["email"], r.get("organisation"), r.get("country")) if x), className="text-xs text-gray-500 truncate")], className="flex-1 min-w-0"),
            html.Button([icon("key-round", 12), "Reset link"], id={"type": "adm-reset", "index": r["id"]}, n_clicks=0,
                        className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800 flex items-center gap-1 shrink-0"),
            html.Span(r["role"], className="text-[10px] font-semibold px-2 py-0.5 rounded-full shrink-0 " + PC.ROLE_BADGE_BORDERED.get(r["role"], "")),
        ], className="flex items-center gap-3 px-5 py-3") for r in rows], className="divide-y divide-gray-100"),
    ], className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden")


def _mode_buttons(mode):
    seg = "flex-1 px-3 py-1.5 rounded text-xs font-semibold transition-colors "
    return [html.Button("Send invitation", id={"type": "adm-mode", "index": "invite"}, n_clicks=0,
                        className=seg + ("bg-white text-gray-800 shadow-sm" if mode == "invite" else "text-gray-500 hover:text-gray-700")),
            html.Button("Set password", id={"type": "adm-mode", "index": "password"}, n_clicks=0,
                        className=seg + ("bg-white text-gray-800 shadow-sm" if mode == "password" else "text-gray-500 hover:text-gray-700"))]


def layout(ctx):
    main = html.Main([
        dcc.Store(id="adm-mode", data="invite"),
        html.Div([icon("shield-check", 16), html.Span("Admin", className="text-xs font-bold uppercase tracking-wider")], className="flex items-center gap-2 mb-1 text-indigo-600"),
        html.H1("Users", className="text-3xl font-bold text-gray-900 mb-2"),
        html.P("Add users to InfraGov. Most of the time you'll send an email invitation, but for shared accounts or cases where the inbox isn't reachable, you can also create a user directly with a password.",
               className="text-gray-500 max-w-2xl mb-8"),
        html.Div([
            html.Section([
                html.Div([icon("user-plus", 16, "text-indigo-600"), html.H2("Add a user", className="text-base font-semibold text-gray-900")], className="flex items-center gap-2 mb-4"),
                html.Div(_mode_buttons("invite"), id="adm-mode-btns", className="flex items-center bg-gray-100 rounded-lg p-1 mb-4"),
                html.Div(id="adm-msg"),
                html.Div([
                    html.Div([html.Label(["Email ", html.Span("*", className="text-red-500")], className=L),
                              dcc.Input(id="adm-email", type="email", placeholder="user@example.org", maxLength=254, className=IN)]),
                    html.Div([html.Label("Name", className=L), dcc.Input(id="adm-name", placeholder="Full name", maxLength=120, className=IN)]),
                    html.Div([html.Label("Organisation", className=L), dcc.Input(id="adm-org", placeholder="Ministry of Finance", maxLength=120, className=IN)]),
                    html.Div([html.Label("Country", className=L), dcc.Dropdown(id="adm-country", options=[{"label": c, "value": c} for c in country_names()],
                                                                            placeholder="— Select country —", className="ig-select")]),
                    html.Div([html.Label("Role", className=L), dcc.Dropdown(id="adm-role", options=[{"label": "Owner — can create assessments", "value": "Owner"},
                                                                                                 {"label": "Admin — full platform access", "value": "Admin"}],
                                                                         value="Owner", clearable=False, searchable=False, className="ig-select")]),
                    html.Div([html.Label(["Password ", html.Span("*", className="text-red-500")], className=L),
                              dcc.Input(id="adm-password", type="password", autoComplete="new-password", maxLength=128, placeholder=f"Min. {C.PASSWORD_MIN_LENGTH} characters", className=IN),
                              html.P("The user's email is auto-confirmed and no invitation email is sent. Share these credentials over a secure channel.", className="text-[11px] text-gray-500 mt-1")],
                             id="adm-pw-block", className="hidden"),
                    html.Button([icon("mail", 14), "Send invitation"], id="adm-submit", n_clicks=0,
                                className="w-full flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-4 py-2.5 rounded-lg transition-colors"),
                ], className="space-y-3"),
            ], className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 self-start"),
            html.Div(users_list(ctx.user), id="adm-users"),
        ], className="grid grid-cols-1 lg:grid-cols-[400px_1fr] gap-6"),
    ], className="pt-28 px-8 py-8 max-w-6xl mx-auto w-full")
    return app_shell(ctx, main)


@callback(Output("adm-mode", "data"), Output("adm-mode-btns", "children"), Output("adm-pw-block", "className"), Output("adm-submit", "children"),
          Input({"type": "adm-mode", "index": ALL}, "n_clicks"), prevent_initial_call=True)
def _mode(clicks):
    if not dctx.triggered_id or not any(clicks):
        raise PreventUpdate
    _require_admin()
    mode = dctx.triggered_id["index"]
    label = [icon("key-round", 14), "Create user"] if mode == "password" else [icon("mail", 14), "Send invitation"]
    return mode, _mode_buttons(mode), "" if mode == "password" else "hidden", label


@callback(Output("adm-msg", "children"), Output("adm-users", "children"),
          Output("adm-email", "value"), Output("adm-name", "value"), Output("adm-org", "value"), Output("adm-password", "value"),
          Input("adm-submit", "n_clicks"), State("adm-mode", "data"), State("adm-email", "value"), State("adm-name", "value"), State("adm-org", "value"),
          State("adm-country", "value"), State("adm-role", "value"), State("adm-password", "value"), prevent_initial_call=True)
def _create(n, mode, email, name, org, country, role, password):
    if not n:
        raise PreventUpdate
    admin = _require_admin()
    try:
        if mode == "password" and not password:
            raise users.ValidationError("Password is required.")
        res = users.create_user(admin, email=email or "", name=name or "", organisation=org or "", country=country or "",
                                role=role or "Owner", password=password if mode == "password" else None, base_url=base_url())
    except Exception as exc:  # noqa: BLE001
        return alert(user_message(exc), "error", "mb-4"), no_update, no_update, no_update, no_update, ""
    if res["mode"] == "password":
        msg = alert(["User ", html.Span(res["email"], className="font-semibold"), " created. They can sign in immediately with the password you set — no confirmation email was sent."], "success", "mb-4")
    elif res.get("emailSent"):
        msg = alert(["Invitation sent to ", html.Span(res["email"], className="font-semibold"), ". They'll receive an email shortly."], "success", "mb-4")
    else:
        msg = alert([html.P(["User ", html.Span(res["email"], className="font-semibold"), " created. E-mail is not configured, so share this one-time set-password link securely "
                             f"(valid {C.INVITE_SET_PASSWORD_TTL_HOURS} h):"]),
                     html.Div([html.Code(res["link"], className="text-[11px] break-all"), dcc.Clipboard(content=res["link"], className="cursor-pointer ml-2")], className="mt-2 flex items-start")],
                    "success", "mb-4")
    return msg, users_list(admin), "", "", "", ""


@callback(Output("adm-msg", "children", allow_duplicate=True), Input({"type": "adm-reset", "index": ALL}, "n_clicks"), prevent_initial_call=True)
def _reset(clicks):
    if not dctx.triggered_id or not any(clicks):
        raise PreventUpdate
    admin = _require_admin()
    try:
        link_ = users.admin_reset_link(admin, dctx.triggered_id["index"], base_url())
    except Exception as exc:  # noqa: BLE001
        return alert(user_message(exc), "error", "mb-4")
    return alert([html.P(f"One-time password reset link (valid {C.RESET_TOKEN_TTL_MIN} minutes). Share it only with the account owner:"),
                  html.Div([html.Code(link_, className="text-[11px] break-all"), dcc.Clipboard(content=link_, className="cursor-pointer ml-2")], className="mt-2 flex items-start")],
                 "info", "mb-4")
