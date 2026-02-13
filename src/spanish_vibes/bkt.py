"""Bayesian Knowledge Tracing (BKT) engine for concept mastery tracking."""

from __future__ import annotations

P_L0 = 0.0    # prior knowledge (start at zero)
P_T = 0.1     # learn rate per attempt
P_G = 0.25    # guess rate (1/4 for MCQ)
P_S = 0.1     # slip rate

MASTERY_THRESHOLD = 0.90
MIN_ATTEMPTS_FOR_MASTERY = 5


def bkt_update(
    p_mastery: float,
    is_correct: bool,
    *,
    p_transit: float = P_T,
    p_guess: float = P_G,
    p_slip: float = P_S,
) -> float:
    """Standard BKT: posterior update then learning transition.

    Correct: P(L|obs) = P(L)*(1-P(S)) / [P(L)*(1-P(S)) + (1-P(L))*P(G)]
    Wrong:   P(L|obs) = P(L)*P(S) / [P(L)*P(S) + (1-P(L))*(1-P(G))]
    Then:    P(L_new) = P(L|obs) + (1 - P(L|obs)) * P(T)
    """
    if is_correct:
        numerator = p_mastery * (1 - p_slip)
        denominator = p_mastery * (1 - p_slip) + (1 - p_mastery) * p_guess
    else:
        numerator = p_mastery * p_slip
        denominator = p_mastery * p_slip + (1 - p_mastery) * (1 - p_guess)

    if denominator == 0:
        p_posterior = 0.0
    else:
        p_posterior = numerator / denominator

    # Learning transition
    p_new = p_posterior + (1 - p_posterior) * p_transit
    return max(0.0, min(1.0, p_new))


def is_mastered(p_mastery: float, n_attempts: int) -> bool:
    """A concept is mastered when p_mastery >= threshold AND enough attempts."""
    return p_mastery >= MASTERY_THRESHOLD and n_attempts >= MIN_ATTEMPTS_FOR_MASTERY


__all__ = [
    "P_G",
    "P_L0",
    "P_S",
    "P_T",
    "MASTERY_THRESHOLD",
    "MIN_ATTEMPTS_FOR_MASTERY",
    "bkt_update",
    "is_mastered",
]
