"""Plotly charts matching the original Recharts horizontal bar charts."""
from __future__ import annotations

import plotly.graph_objects as go
from dash import dcc

from utils import framework as F

FONT = "Inter, ui-sans-serif, system-ui, sans-serif"
CONFIG = {"displayModeBar": False, "responsive": True}


def _axis(locale: str) -> dict:
    return dict(
        range=[0, 4.05], tickvals=[0, 1, 2, 3, 4],
        ticktext=[""] + [F.score_label(s, locale) for s in (1, 2, 3, 4)],
        gridcolor="#f0f0f0", griddash="dash", zeroline=False, tickfont=dict(size=11, color="#6b7280"),
        fixedrange=True,
    )


def _layout(fig: go.Figure, height: int, left: int, locale: str, legend: bool = False) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=left, r=30, t=5, b=30), plot_bgcolor="white", paper_bgcolor="white",
        font=dict(family=FONT, size=11, color="#4b5563"), bargap=0.35, barmode="group",
        showlegend=legend, legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center", font=dict(size=11)),
        hoverlabel=dict(bgcolor="white", bordercolor="#e5e7eb", font=dict(family=FONT, size=12, color="#1f2937")),
        xaxis=_axis(locale), yaxis=dict(autorange="reversed", tickfont=dict(size=11, color="#4b5563"), fixedrange=True),
    )
    return fig


def _wrap(s: str, width: int = 60) -> str:
    words, lines, cur = (s or "").split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "<br>".join(lines[:8])


def _esc(s: str) -> str:
    # Plotly renders a small HTML subset in hover text — escape data first.
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def indicator_bars(rows: list[dict], locale: str, no_data: str, chart_id: str = "chart") -> dcc.Graph:
    """rows: [{label, question, score}] — one bar per indicator."""
    labels = [r["label"] for r in rows]
    scores = [r["score"] or 0 for r in rows]
    colors = [F.score_color(s) if s else "#e5e7eb" for s in scores]
    hover = [
        f"<b>{_esc(r['label'])}</b><br><span style='color:#6b7280'>{_wrap(_esc(r.get('question', '')))}</span><br>"
        + (f"{r['score']} {F.score_label(r['score'], locale)}" if r["score"] else no_data)
        for r in rows
    ]
    fig = go.Figure(go.Bar(x=scores, y=labels, orientation="h", marker=dict(color=colors, cornerradius=4),
                           hovertext=hover, hoverinfo="text", width=0.6))
    height = max(280, len(rows) * 28 + 60)
    return dcc.Graph(id=chart_id, figure=_layout(fig, height, 70, locale), config=CONFIG)


def comparison_bars(rows: list[dict], locale: str) -> dcc.Graph:
    """Global dashboard: one bar per country for a single indicator."""
    labels = [r["label"] for r in rows]
    scores = [r["score"] for r in rows]
    hover = [f"<b>{_esc(r['country'])}</b><br>Maturity level: <b>{r['score']}</b> ({F.score_label(r['score'], locale)})" for r in rows]
    fig = go.Figure(go.Bar(x=scores, y=labels, orientation="h", marker=dict(color=[F.score_color(s) for s in scores], cornerradius=4),
                           hovertext=hover, hoverinfo="text", width=0.6))
    height = max(160, len(rows) * 38 + 40)
    fig = _layout(fig, height, 140, locale)
    fig.update_xaxes(tickfont=dict(size=10, color="#6b7280"))
    return dcc.Graph(figure=fig, config=CONFIG)


def country_bars(mbis: list[dict], country_label: str, comparison_label: str | None,
                 compare: dict | None, locale: str, no_data: str) -> dcc.Graph:
    labels = [m["code"] for m in mbis]
    traces = []
    primary = [m["score"] or 0 for m in mbis]
    traces.append(go.Bar(
        name=country_label, x=primary, y=labels, orientation="h",
        marker=dict(color=[F.score_color(s) if s else "#e5e7eb" for s in primary], cornerradius=4),
        hovertext=[f"<b>{_esc(m['code'])}</b><br>{_wrap(_esc(m['question']))}<br>{_esc(country_label)}: "
                   + (f"{m['score']} · {F.score_label(m['score'], locale)}" if m["score"] else no_data) for m in mbis],
        hoverinfo="text",
    ))
    if comparison_label:
        comp = [(compare or {}).get(m["code"]) or 0 for m in mbis]
        traces.append(go.Bar(
            name=comparison_label, x=comp, y=labels, orientation="h",
            marker=dict(color=[F.comparison_color(s) if s else "#e5e7eb" for s in comp], cornerradius=4),
            hovertext=[f"<b>{_esc(m['code'])}</b><br>{_esc(comparison_label)}: "
                       + (f"{c} · {F.score_label(c, locale)}" if c else no_data) for m, c in zip(mbis, comp)],
            hoverinfo="text",
        ))
    fig = go.Figure(traces)
    height = max(280, len(mbis) * (38 if comparison_label else 28) + 60)
    return dcc.Graph(figure=_layout(fig, height, 70, locale, legend=bool(comparison_label)), config=CONFIG)
