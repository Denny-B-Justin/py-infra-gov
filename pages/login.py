"""Sign in — /?page=login (port of app/[locale]/login/page.tsx).

One login form for every account; what a user can do afterwards is decided
by their role (Admin vs Owner/Contributor/Reviewer/Viewer) on the server.
"""
from __future__ import annotations

from urllib.parse import parse_qs

import flask
from dash import Input, Output, State, callback, dcc, html, no_update
from dash.exceptions import PreventUpdate

from services import auth, repository
from services.validators import ValidationError, validate_token
from utils.components import alert, href, icon, link
from utils.i18n import t
from utils.layout import logo


def layout(ctx):
    loc = ctx.locale
    token = ctx.params.get("token")
    invite = None
    if token:
        try:
            invite = repository.peek_invitation(validate_token(token))
        except ValidationError:
            invite = None
    invite_box = None
    if invite and invite["status"] == "Pending":
        invite_box = html.Div([icon("mail", 16, "mt-0.5"), html.Div([
            html.P("You've been invited", className="font-semibold"),
            html.P(f"Sign in to join dimension D{invite['dimensionId']} as a {invite['role']}.", className="text-xs text-indigo-700 mt-0.5"),
        ])], className="mb-5 px-4 py-3 bg-indigo-50 border border-indigo-200 rounded-lg text-indigo-800 text-sm flex items-start gap-2")
    inp = ("w-full px-4 py-3 bg-gray-50 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 "
           "appearance-none focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition")
    return html.Div([
        html.Header([
            link(logo(), "home", "flex items-center hover:opacity-90 transition-opacity"),
            html.Nav([link("About", "about", "text-gray-300 hover:text-white text-sm transition-colors"),
                      link("Release Notes", "release-notes", "text-gray-300 hover:text-white text-sm transition-colors")], className="ml-8 flex gap-6"),
            html.Div(html.Div(html.Span("?", className="text-white text-xs"), className="w-8 h-8 rounded-full bg-gray-600 flex items-center justify-center"), className="ml-auto"),
        ], className="bg-[#111827] text-white h-14 flex items-center px-6 shadow-lg"),
        html.Div(html.Div([
            html.H1("InfraGov Country", className="text-2xl font-bold text-gray-900 mb-1"),
            html.H1("Assessment Tool", className="text-2xl font-bold text-gray-900 mb-6"),
            invite_box,
            html.Div(id="login-error"),
            html.Div([
                dcc.Input(id="login-email", type="email", placeholder=t(loc, "Login", "emailPlaceholder"), autoComplete="username",
                          maxLength=254, required=True, debounce=False, className=inp, n_submit=0),
                html.Div([
                    dcc.Input(id="login-password", type="password", placeholder=t(loc, "Login", "passwordPlaceholder"),
                              autoComplete="current-password", maxLength=128, required=True, className=inp + " pr-10", n_submit=0),
                    html.Button(icon("eye", 16), id="login-toggle-pw", n_clicks=0, type="button", **{"aria-label": "Show password"},
                                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"),
                ], className="relative"),
                html.Button(t(loc, "Login", "signIn"), id="login-submit", n_clicks=0,
                            className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-semibold py-3 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"),
                html.Div(link(t(loc, "Login", "forgotPassword"), "forgot-password",
                              "text-sm text-indigo-600 hover:text-indigo-800 font-medium transition-colors"), className="text-center"),
            ], className="space-y-4"),
            html.P("Please contact your administrator for access.", className="mt-6 text-xs text-gray-400 text-center"),
        ], className="bg-white rounded-xl shadow-md w-full max-w-md p-8"), className="flex-1 flex items-center justify-center py-12 px-4"),
    ], className="min-h-screen bg-gray-100 flex flex-col")


@callback(
    Output("login-error", "children"),
    Output("url", "href", allow_duplicate=True),
    Output("login-password", "value"),
    Input("login-submit", "n_clicks"),
    Input("login-email", "n_submit"),
    Input("login-password", "n_submit"),
    State("login-email", "value"),
    State("login-password", "value"),
    State("url", "search"),
    prevent_initial_call=True,
)
def _login(n, s1, s2, email, password, search):
    if not (n or s1 or s2):
        raise PreventUpdate  # Dash 4 fires on dynamic insertion
    user, error = auth.authenticate(email or "", password or "")
    if not user:
        return alert(error, "error", "mb-4"), no_update, ""
    auth.start_session(user["id"])
    flask.session["tutorial_seen"] = False
    dest = href("assessments")
    token = (parse_qs((search or "").lstrip("?")).get("token") or [""])[0]
    if token:
        try:
            inv = repository.accept_invitation(user, validate_token(token))
            dest = href("dimension", id=inv["assessmentId"], dim=inv["dimensionId"])
        except Exception:  # noqa: BLE001 - invalid invite never blocks sign-in
            dest = href("join", token=token)
    return None, dest, ""
