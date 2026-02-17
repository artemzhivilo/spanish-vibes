"""Prompt loader — reads AI prompts from data/prompts.yaml with live reload.

Prompts are loaded from the YAML file on first access and cached for 30 seconds.
Dev overrides (stored in the database) take priority over YAML values, so you
can experiment in the dev panel without editing files.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml

# Compute DATA_DIR without importing db (avoids heavy import chain)
_PACKAGE_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _PACKAGE_ROOT.parent.parent
DATA_DIR = _PROJECT_ROOT / "data"

PROMPTS_PATH = DATA_DIR / "prompts.yaml"

_cache: dict[str, Any] | None = None
_cache_time: float = 0.0
_CACHE_TTL = 30.0  # seconds


def _load_prompts() -> dict[str, Any]:
    """Load prompts from YAML file, with a short cache."""
    global _cache, _cache_time
    now = time.monotonic()
    if _cache is not None and (now - _cache_time) < _CACHE_TTL:
        return _cache
    try:
        raw = PROMPTS_PATH.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
    except Exception:
        data = {}
    _cache = data
    _cache_time = now
    return data


def invalidate_cache() -> None:
    """Force the next get() to re-read the YAML file."""
    global _cache, _cache_time
    _cache = None
    _cache_time = 0.0


def _resolve_with_override(key: str) -> str | None:
    """Check dev_overrides for a prompt override, then fall back to YAML."""
    try:
        from .db import get_dev_override
        override = get_dev_override(f"prompt:{key}")
        if override:
            return str(override)
    except Exception:
        pass
    return None


def get(key: str, default: str = "") -> str:
    """Get a prompt string by dotted key, e.g. 'respond_system' or 'scaffolding.1'.

    Resolution order:
    1. Dev override with key 'prompt:<key>'  (live tweaking in dev panel)
    2. YAML file value
    3. default
    """
    # Check dev override first
    override = _resolve_with_override(key)
    if override is not None:
        return override

    data = _load_prompts()

    # Support dotted keys like 'scaffolding.1' or 'conversation_types.general_chat'
    parts = key.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict):
            # Try string key first, then int key for numeric indices
            if part in current:
                current = current[part]
            elif part.isdigit() and int(part) in current:
                current = current[int(part)]
            else:
                return default
        else:
            return default

    if isinstance(current, str):
        return current.strip()
    return default


def get_model(operation: str) -> str:
    """Get the model name for an operation, e.g. 'respond', 'opener', 'mcq'."""
    override = _resolve_with_override(f"model:{operation}")
    if override:
        return override
    data = _load_prompts()
    models = data.get("models", {})
    return str(models.get(operation, "gpt-4o-mini"))


def get_temperature(operation: str) -> float:
    """Get the temperature for an operation."""
    override = _resolve_with_override(f"temp:{operation}")
    if override:
        try:
            return float(override)
        except ValueError:
            pass
    data = _load_prompts()
    temps = data.get("temperatures", {})
    try:
        return float(temps.get(operation, 0.7))
    except (ValueError, TypeError):
        return 0.7


def get_scaffolding(difficulty: int) -> str:
    """Get scaffolding rules for a difficulty level (1, 2, or 3)."""
    return get(f"scaffolding.{difficulty}", default="")


def get_conversation_type_instruction(conv_type: str) -> str | None:
    """Get the instruction template for a conversation type."""
    val = get(f"conversation_types.{conv_type}")
    return val if val else None


def get_all_editable_keys() -> list[dict[str, str]]:
    """Return a list of {key, label, value} dicts for the dev panel editor."""
    data = _load_prompts()
    items: list[dict[str, str]] = []

    # Top-level string prompts
    for key in [
        "default_persona",
        "respond_system",
        "opener_system",
        "english_fallback_system",
        "mcq_system",
        "teach_system",
        "story_system",
    ]:
        val = data.get(key, "")
        if isinstance(val, str):
            items.append({"key": key, "label": key, "value": val.strip()})

    # Scaffolding
    scaffolding = data.get("scaffolding", {})
    for level in [1, 2, 3]:
        val = scaffolding.get(level, "")
        if isinstance(val, str):
            items.append({
                "key": f"scaffolding.{level}",
                "label": f"scaffolding (difficulty {level})",
                "value": val.strip(),
            })

    # Conversation types
    conv_types = data.get("conversation_types", {})
    for ctype in ["general_chat", "role_play", "concept_required", "tutor", "placement"]:
        val = conv_types.get(ctype, "")
        if isinstance(val, str):
            items.append({
                "key": f"conversation_types.{ctype}",
                "label": f"conv type: {ctype}",
                "value": val.strip(),
            })

    return items


def save_to_yaml(key: str, value: str) -> None:
    """Write a prompt value directly to the YAML file (persists across restarts)."""
    data = _load_prompts()

    parts = key.split(".")
    if len(parts) == 1:
        data[parts[0]] = value
    elif len(parts) == 2:
        parent = data.setdefault(parts[0], {})
        if isinstance(parent, dict):
            # Handle integer keys for scaffolding
            k: str | int = int(parts[1]) if parts[1].isdigit() else parts[1]
            parent[k] = value

    try:
        PROMPTS_PATH.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False, width=120),
            encoding="utf-8",
        )
    except Exception:
        pass

    invalidate_cache()


__all__ = [
    "get",
    "get_all_editable_keys",
    "get_conversation_type_instruction",
    "get_model",
    "get_scaffolding",
    "get_temperature",
    "invalidate_cache",
    "save_to_yaml",
]
