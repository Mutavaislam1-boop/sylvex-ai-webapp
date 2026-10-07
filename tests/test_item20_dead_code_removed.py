"""Regression test for remediation item #20: removal of audit-confirmed
dead Python code from main.py.

Each symbol below was verified (git grep across the whole repo, not just
main.py) to have zero live callers/references before being deleted:
  - lemonsqueezy_configured() / create_lemonsqueezy_checkout() /
    lemonsqueezy_checkout_url(): LemonSqueezy checkout was discontinued -
    public_lemonsqueezy_checkout() now returns 410 directly and never
    calls any of these. The webhook path (verify_lemonsqueezy_webhook,
    public_lemonsqueezy_webhook, lemonsqueezy_pack_for_variant,
    lemonsqueezy_variant_for_pack, lemonsqueezy_headers) stays live so
    already-subscribed LemonSqueezy customers keep working.
  - _create_heygen_character() / _find_provider_id(): HeyGen was removed
    from the Character creation pipeline (GPT Image -> SYLVEX Storage ->
    SYLVEX Character only); _find_provider_id's only caller was
    _create_heygen_character itself, so both are dead together.
  - schedule_voice_avatar() (singular): superseded by
    schedule_voice_avatars_batch(), which is the only one any caller in
    the codebase actually uses.

This file asserts the dead symbols are gone AND that every protected/live
symbol named in the remediation boundaries is still present, so a future
accidental re-introduction or over-deletion is caught either way.
"""
import main


REMOVED_PYTHON_SYMBOLS = [
    "lemonsqueezy_configured",
    "create_lemonsqueezy_checkout",
    "lemonsqueezy_checkout_url",
    "_create_heygen_character",
    "_find_provider_id",
    "schedule_voice_avatar",
]


def test_dead_python_symbols_no_longer_exist():
    for name in REMOVED_PYTHON_SYMBOLS:
        assert not hasattr(main, name), f"{name} was supposed to be removed as dead code"


def test_lemonsqueezy_webhook_handling_is_untouched():
    # The explicit "do not touch" boundary: webhook verification and the
    # pack/variant mapping it depends on for already-subscribed customers.
    assert hasattr(main, "verify_lemonsqueezy_webhook")
    assert hasattr(main, "public_lemonsqueezy_webhook")
    assert hasattr(main, "lemonsqueezy_pack_for_variant")
    assert hasattr(main, "lemonsqueezy_variant_for_pack")
    assert hasattr(main, "lemonsqueezy_headers")
    assert hasattr(main, "public_lemonsqueezy_checkout")


def test_live_voice_avatar_batch_scheduler_is_untouched():
    assert hasattr(main, "schedule_voice_avatars_batch")


def test_live_heygen_headers_helper_is_untouched():
    # heygen_headers() has other live callers unrelated to Character
    # creation (e.g. the Video mode HeyGen avatar lookalike feature) and
    # must not be affected by removing _create_heygen_character.
    assert hasattr(main, "heygen_headers")


def test_unrelated_temp_marked_functions_are_untouched():
    # TEMP-1 and TEMP-5 boundaries explicitly called out as out of scope
    # for this item.
    assert hasattr(main, "cleanup_orphaned_text_prostudio_jobs")
    assert hasattr(main, "fallback_public_user")
