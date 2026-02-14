from __future__ import annotations

from spanish_vibes.template_helpers import make_words_tappable


def test_make_words_tappable_wraps_spanish_words():
    html = make_words_tappable("¡Hola amigo!")
    assert 'data-word="Hola"' in html
    assert 'tappable-word' in html
    assert '¡' in html and '!' in html


def test_make_words_tappable_preserves_spacing():
    html = make_words_tappable("hola, mundo feliz")
    assert html.count('tappable-word') == 3
    assert html.count(' ') >= 2
