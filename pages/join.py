"""Accept a dimension invitation — /?page=join&token=… (port of join/[token]/page.tsx).

Security fixes vs. the original: the invitee must be signed in with the SAME
e-mail address the invite was sent to; expired/revoked invites are refused;
the token is looked up by hash only.
"""
from __future__ import annotations

from dash import dcc, html

from services import repository
from services.repository import Forbidden, NotFound
from services.validators import ValidationError, validate_token
from utils.components import href, icon, link
from utils.layout import logo


def _card(icon_name: str, color: str, title: str, body: str, action=None):
    return html.Div([
        html.Div(icon(icon_name, 26), className=f"w-14 h-14 rounded-full flex items-center justify-center mx-auto mb-4 {color}"),
        html.H1(title, className="text-xl font-bold text-gray-900 mb-2"),
        html.P(body, className="text-sm text-gray-500 mb-6"),
        action,
    ], className="bg-white rounded-2xl shadow-md border border-gray-200 max-w-md w-full p-10 text-center")


def layout(ctx):
    token = ctx.params.get("token", "")
    btn = "inline-block bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 px-6 rounded-lg text-sm transition-colors"
    try:
        inv = repository.accept_invitation(ctx.user, validate_token(token))
        content = html.Div([
            _card("check-circle", "bg-green-100 text-green-500", "You're in!", "Redirecting you to your dimension…"),
            dcc.Location(id="join-redirect", href=href("dimension", id=inv["assessmentId"], dim=inv["dimensionId"]), refresh=True),
        ])
    except Forbidden as exc:
        content = _card("alert-triangle", "bg-amber-50 text-amber-500", "Wrong account", str(exc) + " Sign in with the invited address.",
                        link("Go to login", "login", btn))
    except (NotFound, ValidationError) as exc:
        title = "Invite already used" if "already" in str(exc) else "Invite not found"
        content = _card("alert-triangle", "bg-red-50 text-red-500", title,
                        "This invitation link is invalid, has been revoked or has expired." if title == "Invite not found" else str(exc),
                        link("Go to assessments", "assessments", btn))
    return html.Div([
        html.Header(logo(), className="bg-[#111827] text-white h-14 flex items-center px-6 shadow-lg"),
        html.Div(content, className="flex-1 flex items-center justify-center px-4"),
    ], className="min-h-screen bg-gray-100 flex flex-col")
