from __future__ import annotations

from html import escape

from fastapi.responses import HTMLResponse

from .lexicon import translate_spanish_word
from .words import record_word_tap


def build_translate_tooltip_response(
    *,
    word: str,
    context: str = "",
    conversation_id: int | None = None,
) -> HTMLResponse:
    """Return translation tooltip HTML and record the tapped word."""

    try:
        result = translate_spanish_word(word, context)
    except Exception:
        result = None

    english = result["translation"] if result else None
    spanish_clean = result["word"] if result else word

    try:
        record_word_tap(
            spanish=spanish_clean,
            english=english,
            conversation_id=conversation_id,
            source="conversation" if conversation_id else "general",
        )
    except Exception:
        pass

    if result is None:
        body = '<div class="text-slate-400">(translation unavailable)</div>'
    else:
        word_html = escape(result["word"])
        translation_html = escape(result["translation"])
        body = (
            '<div class="flex flex-col gap-1">'
            f'<div><span class="font-bold text-emerald-300">{word_html}</span>'
            '<span class="text-slate-500 mx-1">→</span>'
            f'<span class="text-slate-100">{translation_html}</span></div>'
            "</div>"
        )

    return HTMLResponse(body)
