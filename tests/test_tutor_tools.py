from spanish_vibes.tutor_tools import (
    _sanitize_conversation_topic,
    render_conversation_turn,
)


def test_sanitize_conversation_topic_from_instructional_english() -> None:
    raw = "Introductions: name, where you're from, where you live, and what you do day to day"
    cleaned = _sanitize_conversation_topic(raw)
    assert cleaned.startswith("presentarte")
    assert "where you're from" not in cleaned


def test_render_conversation_turn_updates_counter_and_turn_state() -> None:
    html = render_conversation_turn(
        user_message="Me gusta cocinar.",
        ai_reply="¡Qué bien! ¿Qué cocinas normalmente?",
        corrections=[],
        persona_name="Marta",
        turns_done=0,
        max_turns=4,
        session_id="s1",
        conv_state_json='{"messages":[]}',
    )
    assert 'id="turn-counter"' in html
    assert "1 / 4" in html
    assert 'name="turns_done" value="1"' in html
    assert 'id="conv-input-slot" hx-swap-oob="innerHTML"' in html
    assert 'data-chat-role="ai"' in html
    assert 'class="tappable-word' in html


def test_render_conversation_turn_shows_finish_form_at_limit() -> None:
    html = render_conversation_turn(
        user_message="Hoy trabajo mucho.",
        ai_reply="Entiendo, animo!",
        corrections=[],
        persona_name="Marta",
        turns_done=3,
        max_turns=4,
        session_id="s1",
        conv_state_json='{"messages":[]}',
    )
    assert "/tutor/conversation/complete" in html
    assert "Finish conversation" in html
