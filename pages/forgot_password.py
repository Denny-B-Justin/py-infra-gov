"""Forgot password — /?page=forgot-password (port of app/[locale]/forgot-password/page.tsx)."""
from __future__ import annotations

import constants as C
from dash import Input, Output, State, callback, dcc, html, no_update
from dash.exceptions import PreventUpdate

from services import auth, ratelimit, users
from services.validators import ValidationError
from utils.components import alert, icon, link
from utils.context import base_url
from utils.layout import simple_header

INPUT = ("w-full px-4 py-2.5 bg-gray-50 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 "
         "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent")


def _request_form():
    return html.Div([
        html.Div(icon("key-round", 20), className="w-11 h-11 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center mb-4"),
        html.H1("Forgot your password?", className="text-2xl font-bold text-gray-900 mb-1"),
        html.P("Enter your email and we'll send you a link to reset your password.", className="text-sm text-gray-500 mb-6"),
        html.Div(id="forgot-error"),
        html.Div([
            html.Label("Email address", htmlFor="forgot-email", className="block text-xs font-semibold text-gray-600 mb-1.5"),
            dcc.Input(id="forgot-email", type="email", placeholder="you@gov.org", autoComplete="email", maxLength=254, autoFocus=True,
                      className=INPUT, n_submit=0),
        ], className="mb-4"),
        html.Button("Send reset link", id="forgot-submit", n_clicks=0,
                    className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2 text-sm"),
    ])


def layout(ctx):
    return html.Div([
        simple_header(),
        html.Div(html.Div([
            link([icon("arrow-left", 14), "Back to login"], "login", "inline-flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 mb-6"),
            html.Div(_request_form(), id="forgot-body"),
        ], className="bg-white rounded-xl shadow-md w-full max-w-md p-8"), className="flex-1 flex items-center justify-center py-12 px-4"),
    ], className="min-h-screen bg-gray-100 flex flex-col")


@callback(Output("forgot-body", "children"), Output("forgot-error", "children"),
          Input("forgot-submit", "n_clicks"), Input("forgot-email", "n_submit"), State("forgot-email", "value"),
          prevent_initial_call=True)
def _send(n, s, email):
    if not (n or s):
        raise PreventUpdate
    limit, window = C.RESET_RATE_PER_IP
    if not ratelimit.allow("reset-ip", auth.client_ip(), limit, window):
        return no_update, alert("Too many requests. Please wait a minute and try again.", "error", "mb-4")
    try:
        users.request_password_reset(email or "", base_url())
    except ValidationError:
        return no_update, alert("Please enter a valid email address.", "error", "mb-4")
    note = None if C.SMTP_ENABLED else html.P(
        "E-mail delivery is not configured on this server — ask your administrator for a reset link.",
        className="text-xs text-amber-700 mt-3")
    return html.Div([
        html.Div(icon("mail", 20), className="w-11 h-11 rounded-full bg-green-50 text-green-600 flex items-center justify-center mb-4"),
        html.H1("Check your email", className="text-2xl font-bold text-gray-900 mb-2"),
        html.P("If an account exists for:", className="text-sm text-gray-500"),
        html.P((email or "").strip().lower()[:254], className="text-sm font-semibold text-gray-800 my-1"),
        html.P("…you'll receive an email with a reset link in the next few minutes. The link is valid for one hour. "
               "If you don't see anything, check your spam folder.", className="text-sm text-gray-500"),
        note,
        link("Try a different email", "forgot-password", "mt-6 inline-block text-sm text-indigo-600 hover:text-indigo-800 font-medium"),
    ]), None
