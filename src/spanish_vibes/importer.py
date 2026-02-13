from __future__ import annotations

import argparse
import hashlib
import html as html_mod
import re
from glob import glob
from pathlib import Path
from typing import Any, Sequence

import markdown

from . import lessons
from .db import get_lesson_by_slug, upsert_lesson_with_content


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the limited YAML subset used in concept/exercise blocks."""
    result: dict[str, Any] = {}
    top_key: str | None = None
    list_item: dict[str, str] | None = None

    for line in text.split("\n"):
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        trimmed = line.strip()

        if indent == 0:
            m = re.match(r"^([\w-]+):\s*(.*)", trimmed)
            if not m:
                continue
            top_key = m.group(1)
            val = m.group(2).strip().strip("\"'")
            if val:
                result[top_key] = val
            else:
                result[top_key] = []
            list_item = None
        elif top_key and indent >= 2:
            if trimmed.startswith("- "):
                content = trimmed[2:].strip()
                kv = re.match(r"^([\w-]+):\s*(.*)", content)
                if kv:
                    list_item = {kv.group(1): kv.group(2).strip().strip("\"'")}
                    if not isinstance(result[top_key], list):
                        result[top_key] = []
                    result[top_key].append(list_item)
                else:
                    v = content.strip("\"'")
                    if not isinstance(result[top_key], list):
                        result[top_key] = []
                    result[top_key].append(v)
                    list_item = None
            else:
                kv2 = re.match(r"^([\w-]+):\s*(.*)", trimmed)
                if kv2:
                    v2 = kv2.group(2).strip().strip("\"'")
                    if list_item is not None:
                        list_item[kv2.group(1)] = v2
                    else:
                        if isinstance(result[top_key], list) and len(result[top_key]) == 0:
                            result[top_key] = {}
                        if isinstance(result[top_key], dict):
                            result[top_key][kv2.group(1)] = v2
    return result


def _esc(s: str) -> str:
    return html_mod.escape(s, quote=True)


def _render_concept_html(data: dict[str, Any]) -> str:
    parts = ['<div class="concept-widget">']
    parts.append('<div class="cw-header"><span class="cw-icon">\U0001f4a1</span> Key Concept</div>')
    kind = data.get("kind", "")
    if kind:
        parts.append(f'<p class="cw-kind">{_esc(kind.replace("_", " "))}</p>')
    examples = data.get("examples", [])
    if isinstance(examples, list) and examples:
        parts.append('<div class="cw-examples">')
        for ex in examples:
            if isinstance(ex, dict):
                text = ex.get("text", "")
                eng = ex.get("english", "")
                parts.append(
                    f'<div class="cw-example">'
                    f'<span class="cw-es">{_esc(text)}</span>'
                    f'<span class="cw-arrow">\u2192</span>'
                    f'<span class="cw-en">{_esc(eng)}</span>'
                    f'</div>'
                )
        parts.append('</div>')
    parts.append('</div>')
    return "".join(parts)


def _render_mcq_html(data: dict[str, Any], idx: int) -> str:
    prompt = data.get("prompt", "")
    answer = data.get("answer", "")
    options = data.get("options", [])
    fb = data.get("feedback", {})
    fb_correct = fb.get("correct", "Correct!") if isinstance(fb, dict) else "Correct!"
    fb_incorrect = fb.get("incorrect", "Not quite.") if isinstance(fb, dict) else "Not quite."

    parts = [f'<div class="exercise-widget" id="ex-mcq-{idx}">']
    parts.append('<div class="ew-header"><span class="ew-icon">\u270f\ufe0f</span> Quick Check</div>')
    parts.append(f'<p class="ew-prompt">{_esc(prompt)}</p>')
    parts.append('<div class="ew-options">')
    for opt in options if isinstance(options, list) else []:
        parts.append(
            f'<button class="ew-opt" '
            f'data-answer="{_esc(answer)}" '
            f'data-correct="{_esc(fb_correct)}" '
            f'data-incorrect="{_esc(fb_incorrect)}" '
            f'data-value="{_esc(opt)}">'
            f'{_esc(opt)}</button>'
        )
    parts.append('</div>')
    parts.append('<div class="ew-feedback" hidden></div>')
    parts.append('</div>')
    return "".join(parts)


def _render_fill_html(data: dict[str, Any], idx: int) -> str:
    prompt = data.get("prompt", "")
    answer = data.get("answer", "")
    fb = data.get("feedback", {})
    fb_correct = fb.get("correct", "Correct!") if isinstance(fb, dict) else "Correct!"
    fb_incorrect = fb.get("incorrect", "Not quite.") if isinstance(fb, dict) else "Not quite."

    parts = [f'<div class="exercise-widget" id="ex-fill-{idx}">']
    parts.append('<div class="ew-header"><span class="ew-icon">\U0001f4dd</span> Fill in the Blank</div>')
    parts.append(f'<p class="ew-prompt">{_esc(prompt)}</p>')
    parts.append('<div class="ew-input-row">')
    parts.append('<input type="text" class="ew-input" placeholder="Type your answer\u2026" autocomplete="off" />')
    parts.append(
        f'<button class="ew-check" '
        f'data-answer="{_esc(answer)}" '
        f'data-correct="{_esc(fb_correct)}" '
        f'data-incorrect="{_esc(fb_incorrect)}">'
        f'Check</button>'
    )
    parts.append('</div>')
    parts.append('<div class="ew-feedback" hidden></div>')
    parts.append('</div>')
    return "".join(parts)


def _strip_lesson_text_heading(html_content: str) -> str:
    """Remove the generic '<h1>Lesson Text</h1>' that every lesson markdown starts with."""
    return re.sub(r"<h1>\s*Lesson Text\s*</h1>\s*", "", html_content, count=1)


def _post_process_code_blocks(html_content: str) -> str:
    """Replace concept/exercise code blocks with interactive widget HTML."""
    exercise_idx = 0

    def _replace_block(match: re.Match[str]) -> str:
        nonlocal exercise_idx
        lang = match.group(1)
        raw = html_mod.unescape(match.group(2))
        data = _parse_simple_yaml(raw)

        if lang == "concept":
            return _render_concept_html(data)
        if lang == "exercise":
            ex_type = data.get("type", "")
            if ex_type == "mcq":
                result = _render_mcq_html(data, exercise_idx)
                exercise_idx += 1
                return result
            if ex_type in ("fill_in_blank", "fill-in-blank"):
                result = _render_fill_html(data, exercise_idx)
                exercise_idx += 1
                return result
        # Unknown type — keep original
        return match.group(0)

    return re.sub(
        r'<pre><code class="language-(concept|exercise)">(.*?)</code></pre>',
        _replace_block,
        html_content,
        flags=re.DOTALL,
    )


def render_markdown_to_html(markdown_text: str) -> str:
    """Render lesson markdown content to HTML."""

    raw_html = markdown.markdown(
        markdown_text,
        extensions=[
            "tables",
            "fenced_code",
            "attr_list",
            "md_in_html",
        ],
        output_format="html5",
    )
    processed = _strip_lesson_text_heading(raw_html)
    return _post_process_code_blocks(processed)


def parse_lesson_markdown(path: Path) -> tuple[lessons.LessonParseResult, str, str]:
    """Parse a lesson markdown file returning the parse result, sha, and rendered HTML."""

    parsed = lessons.load_lesson(path)
    raw_text = parsed.raw_text
    content_sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    rendered_html = render_markdown_to_html(parsed.body_markdown)
    return parsed, content_sha, rendered_html


def process_lesson_file(path: Path, *, store_html: bool = True) -> tuple[str, int]:
    parsed, content_sha, rendered_html = parse_lesson_markdown(path)
    if not store_html:
        existing = get_lesson_by_slug(parsed.doc.slug)
        content_sha_to_store = existing.get("content_sha", "") if existing else ""
        content_html_to_store = existing.get("content_html", "") if existing else ""
    else:
        content_sha_to_store = content_sha
        content_html_to_store = rendered_html
    status, lesson_id = upsert_lesson_with_content(
        slug=parsed.doc.slug,
        title=parsed.doc.title,
        level_score=parsed.doc.level_score,
        difficulty=parsed.doc.difficulty,
        path=path.as_posix(),
        content_sha=content_sha_to_store,
        content_html=content_html_to_store,
    )
    lessons.sync_lesson(parsed, lesson_id=lesson_id)
    return status, lesson_id


def process_paths(paths: Sequence[Path], *, store_html: bool = True) -> dict[str, int]:
    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    for path in paths:
        status, _ = process_lesson_file(path, store_html=store_html)
        counts.setdefault(status, 0)
        counts[status] += 1
    return counts


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import lesson markdown into the database")
    parser.add_argument(
        "--glob",
        default="content/lessons/*.md",
        help="Glob pattern for lesson markdown files",
    )
    parser.add_argument(
        "--store-html",
        dest="store_html",
        action="store_true",
        help="Store rendered HTML in the lessons cache",
    )
    parser.add_argument(
        "--no-store-html",
        dest="store_html",
        action="store_false",
        help="Skip storing rendered HTML",
    )
    parser.set_defaults(store_html=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    pattern = args.glob
    store_html: bool = args.store_html

    path_strings = glob(pattern, recursive=True)
    paths = sorted(Path(p) for p in path_strings)
    if not paths:
        print(f"No lessons found for pattern: {pattern}")
        return

    counts = process_paths(paths, store_html=store_html)
    print(
        "Processed {total} lessons (inserted: {ins}, updated: {upd}, unchanged: {unch})".format(
            total=sum(counts.values()),
            ins=counts.get("inserted", 0),
            upd=counts.get("updated", 0),
            unch=counts.get("unchanged", 0),
        )
    )


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
