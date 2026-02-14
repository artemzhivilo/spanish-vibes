"""Common Jinja helpers and filters for Spanish Vibes templates."""

from __future__ import annotations

import html
import re
from typing import Any

_WORD_SPLIT = re.compile(r"(\s+|[¡¿.,!?;:()\[\]{}<>\-–—\"'«»…])", re.UNICODE)
_WORD_CHARS = re.compile(r"^[A-Za-zÁÉÍÓÚÜáéíóúñÑ]+$", re.UNICODE)


def make_words_tappable(text: str | None) -> str:
    """Wrap each Spanish-like word in a tappable span for translations."""
    if not text:
        return ""
    parts = _WORD_SPLIT.split(text)
    wrapped: list[str] = []
    for part in parts:
        if not part:
            continue
        if _WORD_CHARS.match(part):
            display = html.escape(part)
            data_attr = html.escape(part, quote=True)
            wrapped.append(
                "<span class=\"tappable-word cursor-pointer hover:bg-violet-500/20 "
                "hover:rounded px-0.5 transition-colors\" "
                f"data-word=\"{data_attr}\">{display}</span>"
            )
        else:
            wrapped.append(html.escape(part))
    return "".join(wrapped)


def register_template_filters(env: Any) -> None:
    """Attach shared filters to a Jinja environment exactly once."""
    env.filters.setdefault("tappable", make_words_tappable)
