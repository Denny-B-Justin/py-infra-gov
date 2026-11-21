"""Account — /?page=account&tab=profile|security|notifications (port of app/[locale]/account/page.tsx).

Fixes vs. original: profile and preferences are actually persisted; password
change verifies the current password, enforces policy and revokes other
sessions; e-mail (the login identifier) is read-only.
"""
from __future__ import annotations

import flask
from dash import ALL, Input, Output, State, callback, ctx as dctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

import constants as C
from pages import pages_constants as PC
from services import users
from utils.components import alert, icon, initials, link
from utils.context import require_user, user_message
from utils.countries import profile_countries
from utils.layout import app_shell

L = "block text-xs font-semibold text-gray-600 mb-1.5"
IN = ("w-full px-3 py-2.5 bg-gray-50 border border-gray-300 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 "
      "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:bg-gray-100 disabled:text-gray-500")
TABS = [("profile", "Profile", "user"), ("security", "Security", "lock"), ("notifications", "Notifications", "bell")]


def _profile(u):
    opt = lambda s: html.Span(s, className="text-gray-400 font-normal")  # noqa: E731
    return html.Div([
        html.H2("Profile Information", className="text-lg font-semibold text-gray-900 mb-1"),
        html.P("Update your personal details and organisation affiliation.", className="text-gray-500 text-sm mb-6"),
        html.Div([
            html.Div([html.Label("Full Name *", className=L), dcc.Input(id="ac-name", value=u["name"], maxLength=120, className=IN)], className="col-span-2"),
            html.Div([html.Label("Email *", className=L), dcc.Input(id="ac-email", value=u["email"], disabled=True, className=IN),
                      html.P("Your sign-in e-mail can only be changed by an Admin.", className="text-[11px] text-gray-400 mt-1")]),
            html.Div([html.Label(["Phone ", opt("(optional)")], className=L), dcc.Input(id="ac-phone", type="tel", value=u.get("phone", ""), maxLength=40, placeholder="+381 11 123 4567", className=IN)]),
            html.Div([html.Label(["Job Title ", opt("(optional)")], className=L), dcc.Input(id="ac-job", value=u.get("jobTitle", ""), maxLength=120, placeholder="Senior PIM Analyst", className=IN)]),
            html.Div([html.Label("Country", className=L), dcc.Dropdown(id="ac-country", options=[{"label": c, "value": c} for c in profile_countries()],
                                                                    value=u.get("country") or None, placeholder="Select country...", className="ig-select")]),
            html.Div([html.Label("Organisation", className=L), dcc.Input(id="ac-org", value=u.get("organisation", ""), maxLength=120, className=IN)], className="col-span-2"),
        ], className="grid grid-cols-2 gap-4"),
        html.Div([html.Button([icon("save", 14), "Save Changes"], id="ac-save", n_clicks=0,
                              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors"),
                  html.Span(id="ac-save-msg")], className="flex items-center gap-3 pt-5 mt-5 border-t border-gray-100"),
    ], className="bg-white rounded-xl border border-gray-200 shadow-sm p-6")


def _security():
    return html.Div([
        html.Div([
            html.H2("Change Password", className="text-lg font-semibold text-gray-900 mb-1"),
            html.P(f"Use at least {C.PASSWORD_MIN_LENGTH} characters with a mix of letters, numbers, and symbols. Other signed-in sessions are signed out when you change it.",
                   className="text-gray-500 text-sm mb-5"),
            html.Div(id="pw-msg"),
            html.Div([
                html.Div([html.Label("Current password", className=L), dcc.Input(id="pw-current", type="password", autoComplete="current-password", maxLength=128, className=IN)]),
                html.Div([html.Label("New password", className=L), dcc.Input(id="pw-new", type="password", autoComplete="new-password", maxLength=128, className=IN)]),
                html.Div([html.Label("Confirm new password", className=L), dcc.Input(id="pw-confirm", type="password", autoComplete="new-password", maxLength=128, className=IN)]),
                html.Button([icon("lock", 14), "Update Password"], id="pw-submit", n_clicks=0,
                            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors"),
            ], className="space-y-4 max-w-md"),
        ], className="bg-white rounded-xl border border-gray-200 shadow-sm p-6"),
        html.Div([html.H3("Two-Factor Authentication", className="text-base font-semibold text-gray-900 mb-1"),
                  html.P("Add an extra layer of security to your account. Recommended for Owner accounts.", className="text-gray-500 text-sm mb-4"),
                  html.Button("Set up MFA (coming soon)", disabled=True, className="text-sm font-semibold px-4 py-2 rounded-lg border border-gray-200 text-gray-400 cursor-not-allowed")],
                 className="bg-white rounded-xl border border-gray-200 shadow-sm p-6"),
        html.Div([html.H3("Active Sessions", className="text-base font-semibold text-gray-900 mb-1"),
                  html.P(f"Sessions expire after {C.SESSION_IDLE_TIMEOUT_MIN} minutes idle, or {C.SESSION_ABSOLUTE_TIMEOUT_HOURS} hours after sign-in.", className="text-gray-500 text-sm mb-4"),
                  html.Div([html.Div([html.P("This browser", className="text-sm font-medium text-gray-800"), html.P("Active now", className="text-xs text-gray-500")]),
                            html.Span("Current", className="text-xs font-semibold px-2 py-0.5 rounded-full bg-green-100 text-green-700")],
                           className="flex items-center justify-between bg-gray-50 border border-gray-200 rounded-lg px-4 py-3")],
                 className="bg-white rounded-xl border border-gray-200 shadow-sm p-6"),
    ], className="space-y-5")


def _notifications(u):
    prefs = u["preferences"]
    return html.Div([
        html.H2("Notification Preferences", className="text-lg font-semibold text-gray-900 mb-1"),
        html.P("Choose what to be notified about by email.", className="text-gray-500 text-sm mb-5"),
        dcc.Checklist(id="nt-prefs", options=[{"label": html.Div([html.P(title, className="text-sm font-medium text-gray-800"), html.P(desc, className="text-xs text-gray-500 mt-0.5")]),
                                               "value": key} for key, title, desc in PC.ACCOUNT_NOTIFICATION_ITEMS],
                      value=[k for k, _, _ in PC.ACCOUNT_NOTIFICATION_ITEMS if prefs.get(k)], className="space-y-3 ig-toggles",
                      labelClassName="flex items-center justify-between gap-4 p-4 bg-gray-50 border border-gray-200 rounded-lg cursor-pointer flex-row-reverse"),
        html.Div([html.Button([icon("save", 14), "Save Preferences"], id="nt-save", n_clicks=0,
                              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors"),
                  html.Span(id="nt-msg")], className="flex items-center gap-3 pt-5 mt-5 border-t border-gray-100"),
    ], className="bg-white rounded-xl border border-gray-200 shadow-sm p-6")


def _tab_body(u, tab):
    return _security() if tab == "security" else _notifications(u) if tab == "notifications" else _profile(u)


def _nav(tab):
    return [html.Button([icon(ic, 15, "text-indigo-600" if tab == key else "text-gray-400"), label], id={"type": "ac-tab", "index": key}, n_clicks=0,
                        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors "
                        + ("bg-indigo-50 text-indigo-700" if tab == key else "text-gray-600 hover:bg-gray-50")) for key, label, ic in TABS]


def layout(ctx):
    u = ctx.user
    tab = ctx.params.get("tab") if ctx.params.get("tab") in dict((k, 1) for k, _, _ in TABS) else "profile"
    main = html.Main([
        link([icon("arrow-left", 14), "Back to assessments"], "assessments", "inline-flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 mb-6"),
        html.Div([html.Div(initials(u["name"]) or "U", className="w-16 h-16 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xl font-bold"),
                  html.Div([html.H1(u["name"], className="text-2xl font-bold text-gray-900"),
                            html.P(f"{u['email']} · {u['organisation']}", className="text-gray-500 text-sm")])], className="flex items-center gap-4 mb-8"),
        html.Div([
            html.Nav(html.Div(_nav(tab), id="ac-nav", className="bg-white rounded-xl border border-gray-200 shadow-sm p-2 space-y-1"), className="w-56 shrink-0"),
            html.Div(_tab_body(u, tab), id="ac-body", className="flex-1"),
        ], className="flex gap-6"),
    ], className="pt-28 px-8 py-8 max-w-5xl mx-auto w-full")
    return app_shell(ctx, main)


@callback(Output("ac-nav", "children"), Output("ac-body", "children"), Input({"type": "ac-tab", "index": ALL}, "n_clicks"), prevent_initial_call=True)
def _switch(clicks):
    if not dctx.triggered_id or not any(clicks):
        raise PreventUpdate
    u = require_user()
    tab = dctx.triggered_id["index"]
    return _nav(tab), _tab_body(u, tab)


@callback(Output("ac-save-msg", "children"), Input("ac-save", "n_clicks"),
          State("ac-name", "value"), State("ac-phone", "value"), State("ac-job", "value"), State("ac-country", "value"), State("ac-org", "value"),
          prevent_initial_call=True)
def _save_profile(n, name, phone, job, country, org):
    if not n:
        raise PreventUpdate
    u = require_user()
    try:
        users.update_profile(u, {"name": name, "phone": phone, "jobTitle": job, "country": country, "organisation": org})
    except Exception as exc:  # noqa: BLE001
        return alert(user_message(exc), "error", "text-xs")
    return html.Span([icon("check-circle", 14), "Profile updated"], className="flex items-center gap-1.5 text-sm text-green-700 font-medium")


@callback(Output("pw-msg", "children"), Output("pw-current", "value"), Output("pw-new", "value"), Output("pw-confirm", "value"),
          Input("pw-submit", "n_clicks"), State("pw-current", "value"), State("pw-new", "value"), State("pw-confirm", "value"), prevent_initial_call=True)
def _change_pw(n, cur, new, confirm):
    if not n:
        raise PreventUpdate
    u = require_user()
    try:
        users.change_password(u, cur or "", new or "", confirm or "", flask.session.get("sid"))
    except Exception as exc:  # noqa: BLE001
        return alert(user_message(exc), "error", "mb-4"), "", no_update, no_update
    return alert("Password changed successfully.", "success", "mb-4"), "", "", ""


@callback(Output("nt-msg", "children"), Input("nt-save", "n_clicks"), State("nt-prefs", "value"), prevent_initial_call=True)
def _save_prefs(n, values):
    if not n:
        raise PreventUpdate
    u = require_user()
    users.update_preferences(u, {k: (k in (values or [])) for k, _, _ in PC.ACCOUNT_NOTIFICATION_ITEMS})
    return html.Span([icon("check-circle", 14), "Preferences saved"], className="flex items-center gap-1.5 text-sm text-green-700 font-medium")
