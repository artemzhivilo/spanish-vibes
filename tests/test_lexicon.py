from __future__ import annotations

from unittest.mock import patch

from spanish_vibes.lexicon import lookup_local_translation, translate_spanish_word


def test_lookup_local_translation_basic_word():
    assert lookup_local_translation("hola") == "hello"


def test_lookup_local_translation_conjugated_form():
    translation = lookup_local_translation("hablamos")
    assert translation is not None
    assert "we" in translation.lower()
    assert "hablar" in translation


def test_translate_phrase_uses_ai():
    with patch("spanish_vibes.lexicon._get_cached_translation", return_value=None), \
         patch("spanish_vibes.lexicon._store_translation") as mock_store, \
         patch("spanish_vibes.lexicon._translate_with_ai", return_value="to the museum") as mock_ai:
        result = translate_spanish_word("al museo", "contexto cultural")
        assert result is not None
        assert result["translation"] == "to the museum"
        mock_ai.assert_called_once_with("al museo", "contexto cultural", phrase=True)
        mock_store.assert_called_once()
