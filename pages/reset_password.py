"""Set / reset password — /?page=reset-password&token=…

Replaces app/[locale]/auth/update-password/page.tsx. Used both for the
admin "Send invitation" flow (first password) and for "Forgot password".
The token is single-use, stored only as a SHA-256 hash, and expires.
"""
from __future__ import annotations

import constants as C
from dash import Input, Output, State, callback, dcc, html, no_update
from dash.exceptions import PreventUpdate

from services import auth, users
from services.validators import ValidationError, validate_token
from utils.components import alert, href, icon, link
from utils.layout import simple_header

INPUT = ("w-full px-4 py-3 bg-gray-50 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 "
         "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent")


def layout(ctx):
    token = ctx.params.get("token", "")
    row = None
    try:
        row = auth.peek_auth_token(validate_token(token))
    except ValidationError:
        row = None
    if row:
        u = auth.get_user_by_id(row["user_id"]) or {}
        body = [
            html.H1("Set a password", className="text-2xl font-bold text-gray-900 mb-1"),
            html.P(["For ", html.Span(u.get("email", ""), className="font-medium text-gray-700")], className="text-sm text-gray-500 mb-5"),
            html.Div(id="reset-error"),
            dcc.Store(id="reset-token", data=token),
            html.Div([
                html.Div([
                    dcc.Input(id="reset-password", type="password", placeholder="New password", autoComplete="new-password",
                              maxLength=C.PASSWORD_MAX_LENGTH, className=INPUT + " pr-10"),
                    html.Button(icon("eye", 16), id="reset-toggle-pw", n_clicks=0, type="button", **{"aria-label": "Show password"},
                                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"),
                ], className="relative"),
                dcc.Input(id="reset-confirm", type="password", placeholder="Confirm new password", autoComplete="new-password",
                          maxLength=C.PASSWORD_MAX_LENGTH, className=INPUT, n_submit=0),
                html.P(f"At least {C.PASSWORD_MIN_LENGTH} characters, using three of: lower-case, upper-case, digits, symbols.",
                       className="text-xs text-gray-500"),
                html.Button("Save password", id="reset-submit", n_clicks=0,
                            className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-semibold py-3 rounded-lg transition-colors"),
            ], className="space-y-4"),
            html.P("After saving, you'll be taken to the sign-in page.", className="mt-5 text-xs text-gray-400 text-center"),
        ]
    else:
        body = [
            html.H1("This link is invalid or has expired", className="text-xl font-bold text-gray-900 mb-2"),
            html.P("Password links are single-use and expire after a short time. Request a new one and try again.", className="text-sm text-gray-500 mb-6"),
            link("Request a new link", "forgot-password", "text-sm font-semibold text-indigo-600 hover:text-indigo-800"),
            html.Span(" · ", className="text-gray-300"),
            link("← Back to sign in", "login", "text-sm font-semibold text-indigo-600 hover:text-indigo-800"),
        ]
    return html.Div([
        simple_header(),
        html.Div(html.Div([
            html.Div([icon("key-round", 16), html.Span("Set your password", className="text-xs font-bold uppercase tracking-wider")],
                     className="flex items-center gap-2 mb-4 text-indigo-600"),
            html.Div(body, id="reset-body"),
        ], className="bg-white rounded-xl shadow-md w-full max-w-md p-8"), className="flex-1 flex items-center justify-center py-12 px-4"),
    ], className="min-h-screen bg-gray-100 flex flex-col")


@callback(Output("reset-body", "children"), Output("reset-error", "children"),
          Input("reset-submit", "n_clicks"), Input("reset-confirm", "n_submit"),
          State("reset-token", "data"), State("reset-password", "value"), State("reset-confirm", "value"),
          prevent_initial_call=True)
def _save(n, s, token, pw, confirm):
    if not (n or s):
        raise PreventUpdate
    try:
        users.complete_password_reset(validate_token(token), pw or "", confirm or "")
    except ValidationError as exc:
        return no_update, alert(str(exc), "error", "mb-4")
    return html.Div([
        html.Div(icon("check-circle", 22), className="w-12 h-12 rounded-full bg-green-100 text-green-600 flex items-center justify-center mb-4"),
        html.H1("Password updated", className="text-2xl font-bold text-gray-900 mb-2"),
        html.P("You can now sign in with your new password.", className="text-sm text-gray-500 mb-6"),
        html.A("Go to sign in", href=href("login"), className="inline-block bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 px-6 rounded-lg text-sm"),
    ]), None
