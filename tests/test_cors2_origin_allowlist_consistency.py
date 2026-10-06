# Regression tests for the security audit's CORS-2 finding:
#
# main.py's CORSMiddleware was registered with its own, separately-parsed
# copy of WEBSITE_ORIGINS (only .strip(), no trailing-slash normalization),
# while services/security.py's origin_allowed() (the CSRF guard) parsed the
# same env var independently (.strip().rstrip('/')) - two normalizations
# of one allowlist that could silently drift apart. Worse: neither layer
# ever rejected a literal '*' entry. Starlette's CORSMiddleware treats "*"
# in allow_origins as a sentinel that reflects ANY request's Origin back
# with Access-Control-Allow-Credentials: true when allow_credentials=True
# (confirmed directly against this installed Starlette version's
# CORSMiddleware.is_allowed_origin/__init__ - allow_all_origins short-
# circuits to True regardless of allow_credentials), i.e. exactly the
# "allow_origins=['*'] + allow_credentials=True would silently work if
# ever misconfigured" footgun the audit named.
#
# Fix (services/runtime_checks.py):
# - parse_website_origins() is now the SINGLE shared parser: normalizes
#   whitespace/trailing-slash/dedup, and unconditionally drops any entry
#   that is or contains '*'. services/security.py's website_origins()
#   (origin_allowed's source of truth) and main.py's CORSMiddleware
#   registration both read this exact same function's output now, so they
#   cannot drift onto two different trusted-origin sets again.
# - website_origins_configuration_error() flags a wildcard entry as a hard
#   configuration error; validate_runtime() raises it in production, so a
#   misconfigured WEBSITE_ORIGINS=* deploy refuses to even start, rather
#   than silently running with CORS disabled or (pre-fix) wide open.
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_runtime_checks(monkeypatch=None):
    path = ROOT / 'services/runtime_checks.py'
    spec = importlib.util.spec_from_file_location('cors2_runtime_checks_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# parse_website_origins(): the single shared parser.
# ---------------------------------------------------------------------------

def test_parse_website_origins_normalizes_a_valid_configured_list():
    rc = _load_runtime_checks()
    origins = rc.parse_website_origins('https://sylvex.ai/, https://www.sylvex.ai , https://sylvex.ai')
    assert origins == ['https://sylvex.ai', 'https://www.sylvex.ai']


def test_parse_website_origins_drops_a_bare_wildcard_entry():
    rc = _load_runtime_checks()
    assert rc.parse_website_origins('*') == []


def test_parse_website_origins_drops_a_wildcard_mixed_with_valid_origins():
    # Never widen the allowlist: the one bad entry is dropped, the good
    # ones are kept - this must never degrade into trusting everything.
    rc = _load_runtime_checks()
    origins = rc.parse_website_origins('https://sylvex.ai, *, https://app.example.com/*')
    assert origins == ['https://sylvex.ai']


def test_parse_website_origins_drops_wildcard_subdomain_patterns_too():
    # Starlette's allow_origins does exact-string matching, not globbing -
    # a value like 'https://*.sylvex.ai' would never match a real Origin
    # header anyway, but it's still dropped defensively since any '*' is
    # exactly the dangerous-sentinel shape CORS-2 is about.
    rc = _load_runtime_checks()
    assert rc.parse_website_origins('https://*.sylvex.ai') == []


def test_parse_website_origins_empty_input_returns_empty_list():
    rc = _load_runtime_checks()
    assert rc.parse_website_origins('') == []
    assert rc.parse_website_origins(None if False else '') == []


# ---------------------------------------------------------------------------
# services.security.website_origins() must be the exact same shared parser -
# proving CORS and the CSRF guard cannot drift onto two different lists.
# ---------------------------------------------------------------------------

def test_security_website_origins_delegates_to_the_shared_parser(monkeypatch):
    from services import security as security_module
    from services import runtime_checks as runtime_checks_module

    monkeypatch.setenv('WEBSITE_ORIGINS', 'https://sylvex.ai/, https://www.sylvex.ai')
    assert security_module.website_origins() == runtime_checks_module.parse_website_origins()
    assert security_module.website_origins() == ['https://sylvex.ai', 'https://www.sylvex.ai']


def test_security_website_origins_never_returns_a_wildcard(monkeypatch):
    from services import security as security_module

    monkeypatch.setenv('WEBSITE_ORIGINS', '*')
    assert security_module.website_origins() == []


def test_origin_allowed_rejects_an_arbitrary_origin_even_with_a_valid_origin_configured(monkeypatch):
    from services import security as security_module

    monkeypatch.setenv('WEBSITE_ORIGINS', 'https://sylvex.ai')
    assert security_module.origin_allowed({b'origin': b'https://attacker.example'}) is False
    assert security_module.origin_allowed({b'origin': b'https://sylvex.ai'}) is True


def test_origin_allowed_treats_a_configured_wildcard_as_no_trusted_origins(monkeypatch):
    # Outside production this still no-ops permissively by design (see
    # origin_allowed's own docstring on unset-vs-production) - the point
    # proven here is narrower: a wildcard never becomes a literal '*'
    # match target, so an attacker's Origin can never match the string '*'.
    from services import security as security_module

    monkeypatch.setenv('WEBSITE_ORIGINS', '*')
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.delenv('RAILWAY_ENVIRONMENT_ID', raising=False)
    assert security_module.origin_allowed({b'origin': b'https://attacker.example'}) is False
    assert security_module.origin_allowed({b'origin': b'*'}) is False


# ---------------------------------------------------------------------------
# website_origins_configuration_error() / validate_runtime(): fail closed
# in production on a wildcard WEBSITE_ORIGINS.
# ---------------------------------------------------------------------------

def test_configuration_error_flags_a_wildcard_origin():
    rc = _load_runtime_checks()
    error = rc.website_origins_configuration_error('*')
    assert error
    assert 'wildcard' in error.lower()


def test_configuration_error_flags_a_wildcard_mixed_with_valid_origins():
    rc = _load_runtime_checks()
    error = rc.website_origins_configuration_error('https://sylvex.ai, *')
    assert error


def test_configuration_error_is_empty_for_a_valid_configured_list():
    rc = _load_runtime_checks()
    assert rc.website_origins_configuration_error('https://sylvex.ai, https://www.sylvex.ai') == ''


@pytest.fixture
def production_runtime(monkeypatch):
    rc = _load_runtime_checks()
    values = {
        'APP_ENV': 'production', 'R2_BUCKET': 'test', 'R2_ENDPOINT': 'https://storage.example.com',
        'R2_ACCESS_KEY_ID': 'test', 'R2_SECRET_ACCESS_KEY': 'test', 'DATABASE_URL': 'postgresql://test',
        'BOT_TOKEN': 'test', 'WEBAPP_URL': 'https://app.example.com', 'ENABLE_DEV_PAYMENTS': '0',
        'PROSTUDIO_MOCK_GENERATION': '0', 'WEBSITE_ORIGINS': 'https://sylvex.ai',
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv('TELEGRAM_PAYMENT_WEBHOOK_SECRET', raising=False)
    return rc


# validate_runtime()'s own first check refuses to run at all on a Python
# older than the project's required 3.12 (see services/runtime_checks.py);
# this sandbox's pytest runs on 3.11 (the same reason
# tests/test_runtime_checks.py's non-webhook tests are a pre-existing,
# documented failure here) - these 4 integration tests exercise genuinely
# new behavior (the wildcard fail-closed check), so they're skipped here
# rather than left permanently red like that pre-existing file, to avoid
# inflating the suite's known-failure count with new, non-pre-existing
# failures.
_requires_py312 = pytest.mark.skipif(sys.version_info < (3, 12), reason='validate_runtime() requires Python 3.12+ (its own first check); run this on the project runtime to exercise it')


@_requires_py312
def test_validate_runtime_passes_with_a_single_valid_website_origin(production_runtime):
    production_runtime.validate_runtime()  # must not raise


@_requires_py312
def test_validate_runtime_fails_closed_on_a_wildcard_website_origin(production_runtime, monkeypatch):
    monkeypatch.setenv('WEBSITE_ORIGINS', '*')
    with pytest.raises(RuntimeError, match='wildcard'):
        production_runtime.validate_runtime()


@_requires_py312
def test_validate_runtime_fails_closed_on_a_wildcard_mixed_with_a_valid_origin(production_runtime, monkeypatch):
    monkeypatch.setenv('WEBSITE_ORIGINS', 'https://sylvex.ai, *')
    with pytest.raises(RuntimeError, match='wildcard'):
        production_runtime.validate_runtime()


@_requires_py312
def test_validate_runtime_still_fails_closed_when_website_origins_unset(production_runtime, monkeypatch):
    # Pre-existing check, unchanged by this fix - still enforced after it.
    monkeypatch.delenv('WEBSITE_ORIGINS', raising=False)
    with pytest.raises(RuntimeError, match='WEBSITE_ORIGINS must be set'):
        production_runtime.validate_runtime()


# ---------------------------------------------------------------------------
# Integration: the real app's CORS behavior with WEBSITE_ORIGINS configured.
# Fresh subprocess per case since main.py reads WEBSITE_ORIGINS once, at
# import time, to decide whether/how to register CORSMiddleware (same
# pattern as test_edit_sessions.py's test_website_can_preflight_authenticated_edit_history_save).
# ---------------------------------------------------------------------------

def _run_cors_check(website_origins_env, origin_header):
    code = f'''
import os, asyncio
os.environ['WEBSITE_ORIGINS'] = {website_origins_env!r}
import httpx, main
async def check():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='https://api.sylvex.ai') as client:
        response = await client.options('/api/public/prostudio/edit-sessions/edit-example', headers={{
            'Origin': {origin_header!r}, 'Access-Control-Request-Method': 'PUT',
            'Access-Control-Request-Headers': 'Content-Type'}})
        print('STATUS', response.status_code)
        print('ACAO', response.headers.get('access-control-allow-origin', ''))
        print('WEBSITE_ORIGINS_PARSED', main._website_origins)
asyncio.run(check())
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    lines = dict(line.split(' ', 1) for line in result.stdout.strip().splitlines())
    return lines


def test_cors_allows_the_valid_configured_website_origin():
    lines = _run_cors_check('https://sylvex.ai', 'https://sylvex.ai')
    assert lines['STATUS'] == '200'
    assert lines['ACAO'] == 'https://sylvex.ai'


def test_cors_rejects_an_arbitrary_origin_not_in_the_configured_allowlist():
    lines = _run_cors_check('https://sylvex.ai', 'https://attacker.example')
    assert lines['STATUS'] == '400'
    assert lines['ACAO'] == ''


def test_cors_never_registers_a_wildcard_allowlist_even_if_configured():
    # With WEBSITE_ORIGINS='*', main._website_origins must come out empty
    # (the shared parser drops the wildcard) - so CORSMiddleware is never
    # even added (see main.py's `if _website_origins:` guard), and an
    # arbitrary origin's preflight gets no CORS treatment at all rather
    # than being silently allowed through with credentials.
    lines = _run_cors_check('*', 'https://attacker.example')
    assert lines['WEBSITE_ORIGINS_PARSED'] == '[]'
    assert lines['ACAO'] == ''
