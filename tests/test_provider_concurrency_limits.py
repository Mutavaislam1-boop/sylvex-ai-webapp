"""provider_limit() must not silently collapse every provider to 1 concurrent
slot; each provider gets its own conservative default, still overridable."""
import importlib

import pytest

import provider_concurrency as pc


@pytest.fixture(autouse=True)
def reload_module():
    importlib.reload(pc)
    yield
    importlib.reload(pc)


@pytest.mark.parametrize("provider,expected_default", [
    ("KLING", 3),
    ("RUNWAY", 1),
    ("BYTEPLUS", 2),
    ("OPENAI", 4),
    ("GEMINI", 4),
    ("ELEVENLABS", 2),
    ("GROK", 4),
])
def test_default_limit_is_provider_specific(monkeypatch, provider, expected_default):
    for name in pc.SUPPORTED_PROVIDERS:
        monkeypatch.delenv(f"PROVIDER_CONCURRENCY_{name}", raising=False)
    assert pc.provider_limit(provider) == expected_default


def test_runway_and_openai_defaults_differ():
    # The whole point of this fix: no single flat value for every provider.
    assert pc.provider_limit("RUNWAY") != pc.provider_limit("OPENAI")


def test_explicit_env_override_still_wins(monkeypatch):
    monkeypatch.setenv("PROVIDER_CONCURRENCY_KLING", "9")
    assert pc.provider_limit("KLING") == 9


def test_provider_aliases_share_the_same_default(monkeypatch):
    monkeypatch.delenv("PROVIDER_CONCURRENCY_GEMINI", raising=False)
    assert pc.provider_limit("google") == pc.provider_limit("GEMINI") == 4


def test_unknown_provider_falls_back_to_one(monkeypatch):
    monkeypatch.delenv("PROVIDER_CONCURRENCY_SOME_NEW_PROVIDER", raising=False)
    assert pc.provider_limit("some_new_provider") == 1


def test_bad_env_value_falls_back_to_provider_default(monkeypatch):
    monkeypatch.setenv("PROVIDER_CONCURRENCY_OPENAI", "not-a-number")
    assert pc.provider_limit("OPENAI") == 4
