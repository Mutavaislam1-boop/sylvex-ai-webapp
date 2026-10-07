"""Regression tests for remediation item #24: conservative comment cleanup.

Item #24 removed exactly the pure-boilerplate auto-documentation banner
blocks from main.py and webapp/js/cabinet.js - the generic, per-function
"PYTHON-БЛОК: <name>" / "JAVASCRIPT-БЛОК: <name>" templates that merely
restate "this is a backend/frontend function" with no model-specific
content - and nothing else. Banners that had been enriched with real
explanatory text were deliberately left untouched, as were all other
comments (security boundaries, invariants, heartbeat/stale-recovery notes,
billing/provider-quirk explanations, etc.) and all executable code.

This file keeps only lightweight, static, non-duplicative checks: that the
generic banner templates are gone, that a representative sample of the
comments item #24 was required to preserve are still present, and that
both files still parse. The proof that *only* comments changed (and that
executable code is untouched) is a review-time / git-diff verification for
this change, not something persisted here by duplicating ~50,000 lines of
application source as test fixtures.
"""
import pathlib
import shutil
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MAIN_PY = REPO_ROOT / "main.py"
CABINET_JS = REPO_ROOT / "webapp" / "js" / "cabinet.js"

MAIN_PY_SOURCE = MAIN_PY.read_text(encoding="utf-8")
CABINET_JS_SOURCE = CABINET_JS.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The generic auto-documentation banner templates must be gone
# ---------------------------------------------------------------------------

def test_generic_python_banner_template_is_absent():
    # The БЛОК: label itself still legitimately appears on a handful of
    # banners that were enriched with real explanatory content and
    # deliberately preserved - only the generic filler sentences, which
    # existed solely inside the pure boilerplate blocks, must be gone.
    assert "Выполняет отдельный шаг backend-логики SYLVEX." not in MAIN_PY_SOURCE
    assert "Связан с API, базой данных, провайдерами или подготовкой данных для Mini App." not in MAIN_PY_SOURCE


def test_generic_js_banner_template_is_absent():
    # Same rationale as above: the БЛОК: label survives on preserved,
    # enriched banners - only the generic filler sentence must be gone.
    assert "Выполняет часть frontend-логики: читает состояние, меняет интерфейс или связывает UI с backend." not in CABINET_JS_SOURCE


# ---------------------------------------------------------------------------
# Representative preserved comments: security/invariant/heartbeat/billing/
# provider-quirk explanations that item #24 was required to keep
# ---------------------------------------------------------------------------

def test_dup3_telegram_id_helper_rationale_comment_is_preserved():
    # Documents why telegram_id_required_response() exists (DUP-3) - a
    # "why unusual code exists" explanation, not a banner.
    assert "DUP-3" in MAIN_PY_SOURCE
    assert "telegram_id_required_response" in MAIN_PY_SOURCE


def test_classify_openai_creation_error_rationale_comment_is_preserved():
    # Documents the shared billing-limit/safety-policy classification
    # helper (DUP-2) - a provider-quirk / "why unusual code exists" note.
    assert "classify_openai_creation_error" in MAIN_PY_SOURCE


def test_heartbeat_invariant_comments_are_preserved():
    assert "heartbeat" in MAIN_PY_SOURCE


def test_js_poll_creation_job_shared_loop_rationale_comment_is_preserved():
    # Documents why the shared pollCreationJob() loop exists (DUP-2).
    assert "DUP-2" in CABINET_JS_SOURCE
    assert "pollCreationJob" in CABINET_JS_SOURCE


# ---------------------------------------------------------------------------
# Both files must still parse
# ---------------------------------------------------------------------------

def test_main_py_still_parses_as_valid_python():
    import ast

    ast.parse(MAIN_PY_SOURCE)


def test_cabinet_js_still_parses_as_valid_javascript():
    node = shutil.which("node")
    if not node:
        import pytest

        pytest.skip("node not available in this environment")
    result = subprocess.run([node, "--check", str(CABINET_JS)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# No stale references to symbols removed in items #20-23
# ---------------------------------------------------------------------------

def test_no_stale_references_to_symbols_removed_in_items_20_through_23():
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
        assert symbol not in MAIN_PY_SOURCE, f"stale reference to removed symbol {symbol!r} in main.py"
        assert symbol not in CABINET_JS_SOURCE, f"stale reference to removed symbol {symbol!r} in cabinet.js"
