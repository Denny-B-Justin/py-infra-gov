"""
Static framework metadata (InfraGov 2.0 dimensions + PAG-FA pillars and all
indicator questions / maturity descriptions, in 4 languages).

`data/frameworks.json` is extracted verbatim from the original
lib/data*.ts and lib/pagfa*.ts so wording is identical to the Next.js app.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import constants as C

_DATA = Path(__file__).resolve().parent.parent / "data"

SCORE_COLORS = {1: "#64CBD6", 2: "#599EC7", 3: "#4E71B8", 4: "#4345AA"}
COMPARISON_COLORS = {1: "#F6CC55", 2: "#F5AC44", 3: "#F38B34", 4: "#F26B23"}
NO_DATA_COLOR = "#9CA3AF"
MATURITY_COLORS = {"Incipient": "#64CBD6", "Nascent": "#599EC7", "Emerging": "#4E71B8", "Advanced": "#4345AA"}
MATURITY_TEXT_COLORS = {"Incipient": "#1F2937", "Nascent": "#1F2937", "Emerging": "#FFFFFF", "Advanced": "#FFFFFF"}
MATURITY_LABELS = {
    "en": ["Incipient", "Nascent", "Emerging", "Advanced"],
    "es": ["Incipiente", "Naciente", "Emergente", "Avanzado"],
    "fr": ["Initial", "Naissant", "Émergent", "Avancé"],
    "pt": ["Incipiente", "Nascente", "Emergente", "Avançado"],
}
PRIMARY_COLOR = "#4345AA"
COMPARE_COLOR = "#F26B23"
PAGFA_COLOR = "#37b37f"


@lru_cache(maxsize=1)
def _frameworks() -> dict:
    with open(_DATA / "frameworks.json", encoding="utf-8") as fh:
        return json.load(fh)


def dimensions_for(kind: str, locale: str = "en") -> list[dict]:
    kind = kind if kind in C.FRAMEWORKS else "infragov"
    by_locale = _frameworks()[kind]
    return by_locale.get(locale) or by_locale["en"]


def dimension_meta(kind: str, dim_id: int, locale: str = "en") -> dict | None:
    for d in dimensions_for(kind, locale):
        if d["id"] == dim_id:
            return d
    return None


def indicator(kind: str, dim_id: int, index0: int, locale: str = "en") -> dict:
    meta = dimension_meta(kind, dim_id, locale)
    if meta and 0 <= index0 < len(meta["indicators"]):
        return meta["indicators"][index0]
    return {"question": "", "incipient": "", "nascent": "", "emerging": "", "advanced": ""}


def mbi_code(dim_id: int, mbi_id: int) -> str:
    # The original stores codes as "D<dim>.<n>" for both frameworks.
    return f"D{dim_id}.{mbi_id}"


def display_prefix(kind: str) -> str:
    return "P" if kind == "pagfa" else "D"


def score_color(score: int | float | None) -> str:
    if not score:
        return NO_DATA_COLOR
    return SCORE_COLORS.get(int(score), SCORE_COLORS[4])


def comparison_color(score: int | float | None) -> str:
    if not score:
        return NO_DATA_COLOR
    return COMPARISON_COLORS.get(int(score), COMPARISON_COLORS[4])


def score_label(score: int | float | None, locale: str = "en") -> str:
    if not score:
        return "N/A"
    labels = MATURITY_LABELS.get(locale, MATURITY_LABELS["en"])
    idx = int(score) - 1
    return labels[idx] if 0 <= idx < 4 else ""


def maturity_to_score(level: str | None) -> int:
    return {"Incipient": 1, "Nascent": 2, "Emerging": 3, "Advanced": 4}.get(level or "", 0)


def framework_label(kind: str) -> str:
    return "PAG-FA" if kind == "pagfa" else "InfraGov"
