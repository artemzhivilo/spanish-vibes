"""Tests for bkt.py: BKT update equations and mastery detection."""

from __future__ import annotations

import pytest

from spanish_vibes.bkt import (
    MASTERY_THRESHOLD,
    MIN_ATTEMPTS_FOR_MASTERY,
    P_G,
    P_L0,
    P_S,
    P_T,
    bkt_update,
    is_mastered,
)


class TestBKTUpdate:
    def test_correct_answer_increases_mastery(self):
        p = bkt_update(0.0, True)
        assert p > 0.0

    def test_wrong_answer_stays_low(self):
        p = bkt_update(0.0, False)
        # After one wrong answer from zero, should still be very low
        assert p < 0.15

    def test_repeated_correct_approaches_one(self):
        p = P_L0
        for _ in range(20):
            p = bkt_update(p, True)
        assert p > 0.95

    def test_repeated_wrong_stays_low(self):
        p = P_L0
        for _ in range(5):
            p = bkt_update(p, False)
        assert p < 0.5

    def test_correct_then_wrong_decreases(self):
        p = P_L0
        for _ in range(5):
            p = bkt_update(p, True)
        p_after_correct = p
        p = bkt_update(p, False)
        assert p < p_after_correct

    def test_guess_rate_prevents_instant_mastery(self):
        # Even with correct answer, can't go too high too fast because P(G)=0.25
        p = bkt_update(0.0, True)
        assert p < 0.5

    def test_output_always_between_0_and_1(self):
        for p_init in [0.0, 0.1, 0.5, 0.9, 1.0]:
            for correct in [True, False]:
                result = bkt_update(p_init, correct)
                assert 0.0 <= result <= 1.0

    def test_custom_parameters(self):
        # Higher transit rate = faster learning
        p_fast = bkt_update(0.0, True, p_transit=0.3)
        p_slow = bkt_update(0.0, True, p_transit=0.05)
        assert p_fast > p_slow

    def test_high_mastery_wrong_answer(self):
        # Even at high mastery, a wrong answer should reduce but not crash
        p = bkt_update(0.95, False)
        assert 0.5 < p < 0.95

    def test_zero_denominator_handled(self):
        # Edge case: p_mastery=0, p_guess=0 could cause div by zero
        p = bkt_update(0.0, True, p_guess=0.0, p_slip=0.0)
        # Should handle gracefully
        assert 0.0 <= p <= 1.0


class TestIsMastered:
    def test_mastered(self):
        assert is_mastered(0.95, 10) is True

    def test_not_mastered_low_p(self):
        assert is_mastered(0.5, 10) is False

    def test_not_mastered_few_attempts(self):
        assert is_mastered(0.95, 3) is False

    def test_exactly_at_threshold(self):
        assert is_mastered(MASTERY_THRESHOLD, MIN_ATTEMPTS_FOR_MASTERY) is True

    def test_just_below_threshold(self):
        assert is_mastered(MASTERY_THRESHOLD - 0.01, MIN_ATTEMPTS_FOR_MASTERY) is False
