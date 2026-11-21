"""Not found / forbidden pages."""
from __future__ import annotations

from dash import html

from utils.components import icon, link


def not_found(ctx, message: str = "The page you're looking for doesn't exist."):
    return _box("Page not found", message, "search", ctx)


def forbidden(ctx, message: str = "You don't have access to this page."):
    return _box("Access denied", message, "lock", ctx)


def _box(title: str, message: str, icon_name: str, ctx):
    target = "assessments" if ctx.user else "home"
    return html.Div(html.Div([
        html.Div(icon(icon_name, 22, "text-gray-500"), className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-gray-100 mb-4"),
        html.H1(title, className="text-xl font-bold text-gray-900 mb-2"),
        html.P(message, className="text-sm text-gray-500 mb-6"),
        link([icon("arrow-left", 14), "Back"], target, "inline-flex items-center gap-1.5 text-sm font-semibold text-indigo-600 hover:text-indigo-800"),
    ], className="bg-white rounded-xl border border-gray-200 shadow-sm p-10 text-center max-w-md"),
        className="min-h-screen bg-gray-100 flex items-center justify-center px-4")
