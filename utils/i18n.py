"""Tiny i18n layer over the original next-intl message bundles (messages/*.json).

Supports `{var}` interpolation, ICU-style `{count, plural, =1 {...} other {# ...}}`
and rich tags such as `<b>…</b>` (rendered as Dash components — never as raw
HTML, so translations cannot inject markup).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from dash import html

import constants as C

_DATA = Path(__file__).resolve().parent.parent / "data"
_PLURAL = re.compile(r"\{(\w+), plural, ((?:[^{}]|\{[^{}]*\})*)\}")
_VAR = re.compile(r"\{(\w+)\}")
_TAG = re.compile(r"<(\w+)>(.*?)</\1>|<(\w+)></\3>", re.S)


@lru_cache(maxsize=1)
def _messages() -> dict:
    with open(_DATA / "messages.json", encoding="utf-8") as fh:
        return json.load(fh)


def normalise_locale(value: Any) -> str:
    s = str(value or "").lower()[:5]
    return s if s in C.LOCALES else C.DEFAULT_LOCALE


def _raw(locale: str, ns: str, key: str) -> str:
    msgs = _messages()
    for loc in (locale, C.DEFAULT_LOCALE):
        try:
            return msgs[loc][ns][key]
        except KeyError:
            continue
    return key


def _plural(text: str, values: dict[str, Any]) -> str:
    def repl(m: re.Match) -> str:
        var, body = m.group(1), m.group(2)
        n = values.get(var, 0)
        options = dict(re.findall(r"(=\d+|zero|one|few|many|other)\s*\{([^{}]*)\}", body))
        chosen = options.get(f"={n}") or (options.get("one") if n == 1 else None) or options.get("other", "")
        return chosen.replace("#", str(n))

    return _PLURAL.sub(repl, text)


def t(locale: str, ns: str, key: str, **values: Any) -> str:
    text = _plural(_raw(locale, ns, key), values)
    text = _VAR.sub(lambda m: str(values.get(m.group(1), m.group(0))), text)
    return _TAG.sub(lambda m: m.group(2) or "", text)


def rich(locale: str, ns: str, key: str, tags: dict[str, Callable[[str], Any]] | None = None, **values: Any) -> list:
    """Render a message with <tag> chunks mapped to Dash components."""
    text = _plural(_raw(locale, ns, key), values)
    text = _VAR.sub(lambda m: str(values.get(m.group(1), m.group(0))), text)
    tags = tags or {"b": lambda s: html.Strong(s)}
    out: list = []
    pos = 0
    for m in _TAG.finditer(text):
        if m.start() > pos:
            out.append(text[pos:m.start()])
        name = m.group(1) or m.group(3)
        inner = m.group(2) or ""
        fn = tags.get(name)
        out.append(fn(inner) if fn else inner)
        pos = m.end()
    if pos < len(text):
        out.append(text[pos:])
    return out
