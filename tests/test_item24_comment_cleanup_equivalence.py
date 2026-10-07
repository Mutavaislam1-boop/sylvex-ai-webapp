"""Regression tests for remediation item #24: conservative comment cleanup.

Item #24 removed exactly the pure-boilerplate auto-documentation banner
blocks from main.py and webapp/js/cabinet.js - the generic, per-function
"PYTHON-БЛОК: <name>" / "JAVASCRIPT-БЛОК: <name>" templates that merely
restate "this is a backend/frontend function" with no model-specific
content - and nothing else. Banners that had been enriched with real
explanatory text (a different second line, or extra lines before the
closing delimiter) were deliberately left untouched, as were all other
comments (security boundaries, invariants, heartbeat/stale-recovery notes,
billing/provider-quirk explanations, etc.) and all executable code.

tests/fixtures/item24_main_py_before.py and
tests/fixtures/item24_cabinet_js_before.js are frozen snapshots of both
files exactly as they were immediately before this cleanup (captured from
git HEAD before the change). This file proves, deterministically, that
applying the exact known banner-removal transform to each "before" snapshot
reproduces the current file byte-for-byte - i.e. the only change made was
removing whole banner-comment blocks matching the fixed template, never a
line that also carries code, and never anything else.
"""
import pathlib
import tokenize
import io

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MAIN_PY = REPO_ROOT / "main.py"
CABINET_JS = REPO_ROOT / "webapp" / "js" / "cabinet.js"
FIXTURE_MAIN_PY_BEFORE = REPO_ROOT / "tests" / "fixtures" / "item24_main_py_before.py"
FIXTURE_CABINET_JS_BEFORE = REPO_ROOT / "tests" / "fixtures" / "item24_cabinet_js_before.js"

PY_DELIM = "# ====================================================="
PY_LINE2 = "# Выполняет отдельный шаг backend-логики SYLVEX."
PY_LINE3 = "# Связан с API, базой данных, провайдерами или подготовкой данных для Mini App."

JS_LINE2_TEXT = "Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend."


def strip_python_banners(text):
    """Remove only whole 5-line blocks matching the exact generic
    PYTHON-БЛОК template (delimiter, name line, the two fixed generic
    sentences, delimiter). Never touches a line it did not fully match."""
    lines = text.split("\n")
    out = []
    removed = 0
    i = 0
    n = len(lines)
    while i < n:
        if (
            lines[i] == PY_DELIM
            and i + 4 < n
            and lines[i + 1].startswith("# PYTHON-БЛОК:")
            and lines[i + 2] == PY_LINE2
            and lines[i + 3] == PY_LINE3
            and lines[i + 4] == PY_DELIM
        ):
            removed += 1
            i += 5
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out), removed


def strip_js_banners(text):
    """Remove only whole 4-line blocks matching the exact generic
    JAVASCRIPT-БЛОК template (delimiter, name line, the one fixed generic
    sentence, delimiter), at any consistent indentation. Never touches a
    line it did not fully match."""
    lines = text.split("\n")
    out = []
    removed = 0
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].strip() == "// =====================================================" and i + 3 < n and "JAVASCRIPT-БЛОК:" in lines[i + 1]:
            indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
            delim_line = indent + "// ====================================================="
            line2_ok = lines[i + 2].strip() == "// " + JS_LINE2_TEXT and lines[i + 2].startswith(indent)
            line3_ok = lines[i + 3] == delim_line
            if lines[i] == delim_line and line2_ok and line3_ok:
                removed += 1
                i += 4
                continue
        out.append(lines[i])
        i += 1
    return "\n".join(out), removed


def test_fixtures_exist_and_are_nonempty():
    assert FIXTURE_MAIN_PY_BEFORE.stat().st_size > 0
    assert FIXTURE_CABINET_JS_BEFORE.stat().st_size > 0


def test_python_banner_strip_of_before_snapshot_reproduces_current_file_exactly():
    before = FIXTURE_MAIN_PY_BEFORE.read_text(encoding="utf-8")
    current = MAIN_PY.read_text(encoding="utf-8")
    stripped, removed = strip_python_banners(before)
    assert removed == 173, f"expected exactly 173 pure PYTHON-БЛОК banners, computed {removed}"
    assert stripped == current, (
        "removing the 173 pure generic PYTHON-БЛОК banner blocks from the "
        "pre-cleanup snapshot must reproduce main.py byte-for-byte; any "
        "mismatch means something beyond those banners changed"
    )


def test_js_banner_strip_of_before_snapshot_reproduces_current_file_exactly():
    before = FIXTURE_CABINET_JS_BEFORE.read_text(encoding="utf-8")
    current = CABINET_JS.read_text(encoding="utf-8")
    stripped, removed = strip_js_banners(before)
    assert removed == 189, f"expected exactly 189 pure JAVASCRIPT-БЛОК banners, computed {removed}"
    assert stripped == current, (
        "removing the 189 pure generic JAVASCRIPT-БЛОК banner blocks from "
        "the pre-cleanup snapshot must reproduce cabinet.js byte-for-byte; "
        "any mismatch means something beyond those banners changed"
    )


def _comment_stripped_token_stream(source):
    """Generic, independent check for Python: the full tokenize stream
    (types + strings) with COMMENT/NL/ENCODING tokens and blank-only lines
    removed, so any change to actual code (not just the banner blocks)
    would show up here too, as a second, banner-pattern-independent proof."""
    tokens = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.ENCODING):
            continue
        tokens.append((tok.type, tok.string))
    return tokens


def test_python_executable_token_stream_is_identical_ignoring_all_comments():
    before = FIXTURE_MAIN_PY_BEFORE.read_text(encoding="utf-8")
    current = MAIN_PY.read_text(encoding="utf-8")
    before_tokens = _comment_stripped_token_stream(before)
    current_tokens = _comment_stripped_token_stream(current)
    assert before_tokens == current_tokens, (
        "the non-comment token stream of main.py must be byte-for-byte "
        "identical before and after item #24's comment cleanup"
    )


def test_main_py_still_parses_as_valid_python():
    import ast

    ast.parse(MAIN_PY.read_text(encoding="utf-8"))


def test_cabinet_js_still_parses_as_valid_javascript():
    import subprocess
    import shutil

    node = shutil.which("node")
    if not node:
        import pytest

        pytest.skip("node not available in this environment")
    result = subprocess.run([node, "--check", str(CABINET_JS)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_no_stale_references_to_symbols_removed_in_items_20_through_23():
    current_main = MAIN_PY.read_text(encoding="utf-8")
    current_js = CABINET_JS.read_text(encoding="utf-8")
    removed_symbols = [
        "lemonsqueezy_configured(",
        "create_lemonsqueezy_checkout(",
        "lemonsqueezy_checkout_url(",
        "_create_heygen_character(",
        "_find_provider_id(",
        "schedule_voice_avatar(",
        "renderBrandGeneratorHeader",
        "filterBrandGeneratorHistory",
        "readableColor",
        "insertVoiceEditorMarkup",
        "getGridDownstreamNodes",
        "waitCharacterCreationJob",
        "waitObjectCreationJob",
        "KLING_VIDEO_DURATIONS",
        "MODEL_ICON_SVG",
        "VIDEO_TEMPLATE_INTRO_KEY",
        "VOICE_STYLE_RU",
        "brandGeneratorObserver",
        "brandGeneratorStartIndex",
        "SYLVEX_CABINET_JS_STARTED",
        "CABINET JS NEW VERSION 11.07.2026",
        "PROSTUDIO IMAGE METADATA DEBUG",
    ]
    for symbol in removed_symbols:
        assert symbol not in current_main, f"stale reference to removed symbol {symbol!r} in main.py"
        assert symbol not in current_js, f"stale reference to removed symbol {symbol!r} in cabinet.js"
