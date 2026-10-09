"""Request authentication and limits. Business handlers remain responsible for resource ownership."""
from __future__ import annotations
import asyncio
import contextvars
import hashlib
import hmac
import json
import os
import re
import threading
import time
from collections import OrderedDict
from http.cookies import SimpleCookie
from urllib.parse import parse_qsl, urlencode, urlsplit
from starlette.responses import JSONResponse
from services.runtime_checks import is_production, parse_website_origins

actor_id = contextvars.ContextVar('sylvex_actor_id', default=0)
actor_init_data = contextvars.ContextVar('sylvex_init_data', default='')
PUBLIC_GETS = frozenset({
 '/health/live', '/health/ready', '/api/public/config', '/api/payment-links',
 '/api/public/prostudio/preset-catalog', '/api/public/prostudio/voice-avatars',
 '/api/public/prostudio/image-capabilities', '/api/public/prostudio/model-capabilities', '/api/public/prostudio/video-templates',
 '/api/public/prostudio/photo-catalog', '/api/public/prostudio/photo-tool-demos',
 '/api/public/prostudio/quick-image-catalog', '/api/public/prostudio/kling/effects',
 '/api/public/prostudio/pricing-catalog',
 '/api/public/video/templates', '/api/public/prostudio/references',
 # Website web-session read: has no Telegram initData to present, so it
 # authenticates itself off its own cookie (see verify_web_session_token)
 # instead of going through this middleware's Telegram check.
 '/api/web/session/me',
 # Public, non-secret OAuth client id - fetched before any session exists.
 '/api/web/auth/config',
 # Emailed link, opened directly in a browser - no cookie or initData
 # exists yet at click time either; the route validates its own token.
 '/api/web/auth/verify-email',
 # SYLVEX Assistant Guide Mode must work for a genuine guest (no SYLVEX
 # account at all) - same self-authenticating-off-its-own-cookie pattern as
 # /api/web/session/me above; every other Assistant endpoint (conversation
 # CRUD, files, realtime voice) requires a real signed-in account and goes
 # through this middleware's normal website-session resolution instead.
 '/api/web/assistant/state',
})
# POST routes under /api/web/... all authenticate with the website's own
# session cookie or a mailed/one-time token (see services/account_identity.py
# and verify_web_session_token) rather than Telegram initData, so every one
# of them - whether it's a public sign-in/sign-up step or an
# already-authenticated account action that reads the session cookie itself
# inside its handler - must bypass this middleware's Telegram-only check.
# Every other /api/ POST still requires Telegram initData, exactly as before.
PUBLIC_POSTS = frozenset({
 '/api/web/auth/telegram', '/api/web/auth/google', '/api/web/auth/apple', '/api/web/auth/logout',
 '/api/web/auth/register', '/api/web/auth/login',
 '/api/web/auth/forgot-password', '/api/web/auth/reset-password',
 '/api/web/auth/resend-verification',
 '/api/web/account/password/change', '/api/web/account/email/set', '/api/web/account/delete',
 '/api/web/account/telegram/preview', '/api/web/account/telegram/confirm',
 # Guide Mode must work for a guest with no SYLVEX account - see
 # PUBLIC_GETS's /api/web/assistant/state comment above. Identity is
 # resolved from the website session cookie inside the handler itself
 # (falls back to telegram_id=0 for a real guest, never persists for one);
 # never calls OpenAI regardless of what a tampered client claims, since
 # the guide-vs-AI choice is re-derived server-side from get_user_state().
 '/api/web/assistant/message',
})
MULTIPART_ROUTES = frozenset({'/api/public/prostudio/upload-media','/api/public/prostudio/transcribe','/api/public/prostudio/elevenlabs/voice-clone','/api/web/assistant/files'})
WEBHOOKS = frozenset({'/api/public/payments/stars/webhook','/api/public/payments/paypal/webhook','/api/public/payments/lemonsqueezy/webhook'})
# Routes whose own handler resolves the real authenticated user id itself
# (after subscription state is known, for /assistant/message) and calls
# check_request_quota exactly once with it. The generic per-request
# middleware quota_check below must never ALSO fire for these:
# - /api/web/assistant/message is a PUBLIC_POST (a guest with no account
#   must still reach Guide Mode) and this middleware skips uid resolution
#   entirely for public routes, so a middleware-level quota_check here would
#   run with uid=0 and let every guest/free-website caller share one global
#   quota bucket - the handler resolves the caller's real id itself instead.
# - /api/web/assistant/realtime/session IS resolved normally by this
#   middleware (it's a protected route), so without this exemption its
#   already-real uid would be quota-checked twice: once here, once again by
#   the handler - double-decrementing a subscriber's quota per request.
ASSISTANT_SELF_QUOTA_ROUTES = frozenset({'/api/web/assistant/message', '/api/web/assistant/realtime/session'})
# application/sdp bodies (WebRTC offer/answer exchange) must be replayed to
# the route byte-for-byte, never parsed as JSON - see the `sdp` flag below.
SDP_ROUTES = frozenset({'/api/public/home-idea/realtime', '/api/web/assistant/realtime/session'})
PUBLIC_PATTERNS = [re.compile(x) for x in (
 r'/api/public/prostudio/voice-avatar/[A-Za-z0-9_-]+',
 r'/api/public/video/templates/[^/]+',
 r'/api/public/prostudio/share/[A-Za-z0-9_-]+(?:/(?:download|media))?',
)]

class SecurityError(ValueError):
 def __init__(self, code, status=401): self.code, self.status = code, status; super().__init__(code)

def bot_tokens():
 return tuple(dict.fromkeys(x.strip() for x in (os.getenv('BOT_TOKEN',''),os.getenv('TELEGRAM_BOT_TOKEN','')) if x.strip()))

def validated_user(init_data, tokens=None, now=None):
 if not isinstance(init_data,str) or len(init_data)>16384: raise SecurityError('invalid_init_data')
 pairs=parse_qsl(init_data,keep_blank_values=True)
 data=dict(pairs)
 if len(data)!=len(pairs): raise SecurityError('duplicate_init_data_fields')
 received=data.pop('hash','')
 if not re.fullmatch(r'[a-fA-F0-9]{64}',received): raise SecurityError('invalid_init_data')
 message='\n'.join(f'{k}={data[k]}' for k in sorted(data)).encode()
 tokens=bot_tokens() if tokens is None else tokens
 if not tokens: raise SecurityError('telegram_auth_not_configured',503)
 valid=any(hmac.compare_digest(hmac.new(hmac.new(b'WebAppData',t.encode(),hashlib.sha256).digest(),message,hashlib.sha256).hexdigest(),received.lower()) for t in tokens)
 if not valid: raise SecurityError('invalid_init_data')
 try:
  age=(time.time() if now is None else now)-int(data['auth_date'])
  if age < -30 or age > int(os.getenv('TELEGRAM_AUTH_MAX_AGE_SECONDS','3600')): raise ValueError()
  user=json.loads(data['user'])
  if not isinstance(user,dict) or isinstance(user.get('id'),bool) or not isinstance(user.get('id'),int) or user['id']<=0: raise ValueError()
 except (KeyError,ValueError,TypeError): raise SecurityError('expired_or_invalid_telegram_user')
 return user

def signing_key():
 # Domain separation keeps media/session tokens independent from Telegram HMAC.
 key=os.getenv('MEDIA_SIGNING_SECRET','').strip() or next(iter(bot_tokens()),'')
 if not key: raise SecurityError('media_signing_not_configured',503)
 return hmac.new(key.encode(),b'SYLVEX media v1',hashlib.sha256).digest()

def website_origins():
 # CORS-2: delegates to runtime_checks.parse_website_origins() - the single
 # shared parser main.py's CORSMiddleware registration also calls (via this
 # same function), so CORS and this module's own origin_allowed() (CSRF
 # guard) can never drift onto two differently-normalized trusted-origin
 # lists. That parser also unconditionally drops any wildcard ('*') entry -
 # see its docstring for why.
 return parse_website_origins()

def security_response_headers():
 """Content-Security-Policy + (in production) Strict-Transport-Security,
 applied to EVERY response - not just the /api/* ones secured_send already
 adds x-content-type-options/referrer-policy to (see __call__ below:
 the real Pro Studio UI page itself, the one actually at risk of being
 framed or of serving injected script, is served from the /webapp/ static
 mount, which is NOT "protected" and bypasses secured_send entirely - a
 CSP/HSTS that only reached /api/* JSON responses would never reach the
 one response that matters for either header).
 Security audit HDR-1/HDR-2/HDR-3:
 - frame-ancestors is this app's only clickjacking defense (no
 X-Frame-Options is sent - it can't express an allow-list the way
 frame-ancestors can, and every current browser enforces frame-ancestors
 anyway). Scoped to exactly the two real embedding flows, confirmed
 against this codebase rather than guessed:
 'self' (defensive default) + WEBSITE_ORIGINS (the operator-configured
 website origin(s) that iframe Pro Studio via sylvex-website/pro-studio.html
 ?embed=web - see main.py's CORSMiddleware and services/security.py's
 origin_allowed() above, which already treat this exact env var as the
 trusted-website allowlist; webapp/js/cabinet.js's hostOrigin() falls back
 to the same 'https://sylvex.ai' default used here when WEBSITE_ORIGINS
 is unset) + the real Telegram WebView origins the official
 telegram-web-app.js integration (loaded throughout webapp/*.html) is
 embedded under when opened in Telegram Web: https://web.telegram.org and
 https://*.telegram.org (covers webk./webz. and any other Telegram-run
 web-client subdomain). Native Telegram desktop/mobile apps render this
 same page in their own WebView, outside any browser frame-ancestors
 enforcement, so they are unaffected either way.
 - object-src 'none' and base-uri 'self' are added as safe, broadly
 compatible XSS-hardening (object-src blocks legacy plugin content
 nobody here uses; base-uri stops a <base> tag injection from redirecting
 every relative URL on the page) without touching script-src/style-src/
 img-src/connect-src, which would need a full inventory of every external
 host this app's pages legitimately load (Telegram's own script, R2/CDN
 media, OAuth SDKs, payment providers, etc.) to restrict without risking
 exactly the kind of breakage this fix is scoped to avoid.
 - HSTS only when is_production(): this app is served behind a
 TLS-terminating proxy that talks plain HTTP to the container
 (Dockerfile runs uvicorn with --no-proxy-headers), so scope['scheme']
 here is never a reliable signal for "this connection is really HTTPS" -
 is_production() is the same signal runtime_checks.validate_runtime()
 already uses to enforce HTTPS-only config, and never sending it outside
 production means it can never pin a developer's plain-http localhost
 into forced HTTPS."""
 origins=website_origins() or ['https://sylvex.ai']
 frame_ancestors=' '.join(["'self'",'https://web.telegram.org','https://*.telegram.org',*origins])
 csp=f"frame-ancestors {frame_ancestors}; object-src 'none'; base-uri 'self'"
 result=[(b'content-security-policy',csp.encode())]
 if is_production():
  result.append((b'strict-transport-security',b'max-age=63072000; includeSubDomains'))
 return result

def origin_allowed(headers):
 """CSRF guard for the cookie-authenticated website-session surface: the
 sylvex_web_session cookie is necessarily SameSite=None (the Pro Studio
 iframe embed is cross-origin), so without this, any page the victim's
 browser loads could ride that cookie into a state-changing request. Requires
 the request's Origin (or, failing that, Referer) to be one of
 WEBSITE_ORIGINS - a real browser fetch()/form POST always sends one of
 these for a cross-origin request, and the legitimate website always sends
 Origin on same-origin POSTs too.
 WEBSITE_ORIGINS unset is NOT treated as "nothing to protect": CORS being
 unconfigured only stops an attacker's JS from reading the response, it
 never stops the browser from sending the request or the server from
 executing it - a pure CSRF attack (state-changing, fire-and-forget) never
 needed to read the response anyway. So this fails CLOSED (rejects) in
 production when WEBSITE_ORIGINS is unset, rather than silently going
 permissive. runtime_checks.validate_runtime() already refuses to even
 start the app in that state (see its own WEBSITE_ORIGINS check) - this is
 a second, independent backstop for any caller that reaches
 SecurityMiddleware without going through normal startup (a test, or a
 future entry point). Outside production (local dev, the test suite, which
 never sets WEBSITE_ORIGINS - see tests/conftest.py's APP_ENV='test') an
 unset WEBSITE_ORIGINS still no-ops, since there the real website origin
 is unknowable to configure in the first place."""
 allowed=website_origins()
 if not allowed: return not is_production()
 origin=headers.get(b'origin',b'').decode().strip().rstrip('/')
 if origin: return origin in allowed
 referer=headers.get(b'referer',b'').decode().strip()
 if referer:
  parsed=urlsplit(referer)
  if parsed.scheme and parsed.netloc: return f'{parsed.scheme}://{parsed.netloc}' in allowed
 # Neither header present on a state-changing request - never the shape of
 # a real browser fetch()/form submission; reject rather than guess.
 return False

# ---------------------------------------------------------------------------
# Web session (SYLVEX website sign-in via the Telegram Login Widget).
#
# This is a second, independent credential type - a signed cookie - that
# proves the browser is a specific telegram_id without ever presenting
# Telegram WebApp initData. It never creates a second user: the telegram_id
# it carries is the same primary key the Mini App already uses, so
# get_user_state(telegram_id) returns the exact same account either way.
# ---------------------------------------------------------------------------
WEB_SESSION_COOKIE='sylvex_web_session'
WEB_SESSION_MAX_AGE=int(os.getenv('WEB_SESSION_MAX_AGE_SECONDS',str(60*60*24*30)))

def web_session_secret():
 # Own secret so a leaked BOT_TOKEN alone can't forge a web session, and vice versa.
 key=os.getenv('WEB_SESSION_SECRET','').strip() or next(iter(bot_tokens()),'')
 if not key: raise SecurityError('web_session_not_configured',503)
 return hmac.new(key.encode(),b'SYLVEX web session v1',hashlib.sha256).digest()

def create_web_session_token(telegram_id,generation=0):
 exp=int(time.time())+WEB_SESSION_MAX_AGE
 payload=f'{int(telegram_id)}.{int(generation)}.{exp}'
 sig=hmac.new(web_session_secret(),payload.encode(),hashlib.sha256).hexdigest()
 return f'{payload}.{sig}'

def verify_web_session_token(token):
 # Carries a sylvex_accounts.account_id (see services/account_identity.py),
 # always positive under the current model; the optional leading '-' is
 # kept accepted only for compatibility with any already-issued cookie.
 # Returns (account_id, generation) - generation is this account's
 # session-generation counter at the moment the token was minted (see
 # current_web_session_generation()/revoke_web_sessions() below; COOKIE-2
 # in the security audit: this token used to be pure stateless HMAC with
 # no way to invalidate a copy captured elsewhere once the real user logs
 # out/changes password/deletes their account).
 #
 # An earlier version of this fix carried a wall-clock issued_at instead
 # and compared it against a revocation timestamp - an old token minted
 # in the same second as a revocation could then survive the check, and
 # simply switching < to <= didn't help, since a fresh token reissued
 # immediately after that revocation (e.g. right after a password change)
 # can be minted in that very same second too, making the ordering
 # genuinely ambiguous at second resolution and still racy at any finite
 # clock resolution. A monotonic integer generation counter has no such
 # ambiguity: revoke_web_sessions() always returns the freshly
 # incremented value, which is used to mint the reissued cookie directly
 # (see main.py's _set_web_session_cookie) - no clock read, no race, by
 # construction rather than by narrowing a timing window.
 #
 # A legacy 3-field token (the original pre-COOKIE-2 shape, or the
 # issued_at-based shape from the first version of this fix) is rejected
 # the same way a tampered one is - a clean 401 that forces an ordinary
 # re-login, never a crash.
 try:
  telegram_id_s,generation_s,exp_s,sig=str(token).split('.',3)
  if not re.fullmatch(r'-?[0-9]+',telegram_id_s) or not re.fullmatch(r'[0-9]+',generation_s) or not re.fullmatch(r'[0-9]+',exp_s): raise ValueError()
  expected=hmac.new(web_session_secret(),f'{telegram_id_s}.{generation_s}.{exp_s}'.encode(),hashlib.sha256).hexdigest()
  if not hmac.compare_digest(expected,sig): raise ValueError()
  if int(exp_s)<time.time(): raise ValueError()
  telegram_id=int(telegram_id_s)
  if telegram_id==0: raise ValueError()
 except (ValueError,AttributeError,TypeError): raise SecurityError('invalid_web_session')
 return telegram_id,int(generation_s)

# ---------------------------------------------------------------------------
# Mini App session continuity (seamless reauth).
#
# Telegram WebApp initData carries an auth_date stamped once when the Mini
# App instance was launched and never re-signed in place - the Telegram
# WebApp JS SDK has no method to reissue it, so once
# TELEGRAM_AUTH_MAX_AGE_SECONDS has passed every request's initData is
# permanently stale until the user closes and reopens the app. This cookie
# is minted (and slid forward) on every request whose initData DID validate,
# and is then accepted as a fallback identity proof whenever initData fails
# to validate on a later request from the same browser - same-origin
# `credentials: 'same-origin'` (webapp/js/api-auth.js) already sends it on
# every /api/ call automatically, so this requires no frontend change and no
# reload: a request that would have 401'd instead keeps working. Own secret/
# domain-separation string, independent of both BOT_TOKEN and the website
# session's own signing, so a leak of any one credential type can't forge
# another. Never accepted for /api/admin/ routes - those must always present
# real, fresh Telegram initData or the admin service token.
# ---------------------------------------------------------------------------
TG_SESSION_COOKIE='sylvex_tg_session'
TG_SESSION_MAX_AGE=int(os.getenv('TG_SESSION_MAX_AGE_SECONDS',str(60*60*24*30)))

def tg_session_secret():
 key=os.getenv('WEB_SESSION_SECRET','').strip() or next(iter(bot_tokens()),'')
 if not key: raise SecurityError('web_session_not_configured',503)
 return hmac.new(key.encode(),b'SYLVEX tg session v1',hashlib.sha256).digest()

def create_tg_session_token(telegram_id,generation=0):
 exp=int(time.time())+TG_SESSION_MAX_AGE
 payload=f'{int(telegram_id)}.{int(generation)}.{exp}'
 sig=hmac.new(tg_session_secret(),payload.encode(),hashlib.sha256).hexdigest()
 return f'{payload}.{sig}'

def verify_tg_session_token(token):
 # Returns (telegram_id, generation) - see verify_web_session_token's
 # docstring above for why a generation counter travels with it instead
 # of a wall-clock issued_at (COOKIE-2).
 try:
  telegram_id_s,generation_s,exp_s,sig=str(token).split('.',3)
  if not re.fullmatch(r'[0-9]+',telegram_id_s) or not re.fullmatch(r'[0-9]+',generation_s) or not re.fullmatch(r'[0-9]+',exp_s): raise ValueError()
  expected=hmac.new(tg_session_secret(),f'{telegram_id_s}.{generation_s}.{exp_s}'.encode(),hashlib.sha256).hexdigest()
  if not hmac.compare_digest(expected,sig): raise ValueError()
  if int(exp_s)<time.time(): raise ValueError()
  telegram_id=int(telegram_id_s)
  if telegram_id<=0: raise ValueError()
 except (ValueError,AttributeError,TypeError): raise SecurityError('invalid_tg_session')
 return telegram_id,int(generation_s)

def tg_session_uid_from_cookie_header(cookie_header):
 """Returns (telegram_id, generation), or (0, 0) if absent/invalid. Token
 parsing only - no DB access, so this stays safe to call synchronously on
 the hot Mini App request path; the caller is responsible for checking
 the returned generation against current_tg_session_generation() itself
 (via asyncio.to_thread) wherever that matters."""
 if not cookie_header: return 0,0
 jar=SimpleCookie()
 try: jar.load(cookie_header)
 except Exception: return 0,0
 morsel=jar.get(TG_SESSION_COOKIE)
 if not morsel: return 0,0
 try: return verify_tg_session_token(morsel.value)
 except SecurityError: return 0,0

def tg_session_set_cookie_bytes(telegram_id,generation=0):
 """Raw `set-cookie` header value (bytes) for the ASGI response - this
 middleware operates below Starlette's Response object, so it can't call
 response.set_cookie() the way main.py's website-session routes do.
 Minted with generation=0 on this - the hot, every-successful-request -
 path, since nothing in this codebase calls revoke_tg_sessions() yet (see
 its docstring below); the day it does, whatever calls it is also
 responsible for passing the live generation through to any reissue it
 triggers, exactly as main.py's password-change route does for
 revoke_web_sessions()."""
 token=create_tg_session_token(telegram_id,generation)
 jar=SimpleCookie()
 jar[TG_SESSION_COOKIE]=token
 morsel=jar[TG_SESSION_COOKIE]
 morsel['path']='/'
 morsel['max-age']=TG_SESSION_MAX_AGE
 morsel['secure']=True
 morsel['httponly']=True
 morsel['samesite']='Lax'
 return morsel.OutputString().encode()

# ---------------------------------------------------------------------------
# Bridge: website session -> the same telegram_id-keyed business data.
#
# Every protected /api/ route below still requires Telegram initData except
# the narrow /api/web/* auth surface (PUBLIC_POSTS/PUBLIC_GETS above) - so a
# website-embedded Pro Studio session (sylvex-website/pro-studio.html's
# iframe, ?embed=web; see webapp/js/cabinet.js's usesWebSessionAuth()) has
# no Telegram initData to present for the actual generation/jobs/
# characters/objects/history surface, only the sylvex_web_session cookie.
# verify_web_session_token() above already turns that cookie into a
# sylvex_accounts.account_id; this resolves it one step further to that
# account's active_telegram_id, the exact storage key every existing
# telegram_id-keyed table and handler already reads (see
# services/account_identity.py's _new_web_account). Once that id is `uid`
# below, in place of a Telegram-validated one, nothing downstream - not the
# generation endpoints, not the query/body telegram_id rewrite a few lines
# down - needs to know the difference. Small TTL cache since this runs on
# every protected website-embedded request and the mapping only changes on
# the rare Telegram-merge event.
# ---------------------------------------------------------------------------
_WEB_UID_CACHE_TTL=30.0
_web_uid_cache={}

def _database_url():
 return os.getenv('DATABASE_PUBLIC_URL','').strip() or os.getenv('DATABASE_URL','').strip()

def web_session_account_id_from_cookie_header(cookie_header):
 """Returns (account_id, generation), or (0, 0) if absent/invalid. Token
 parsing only - no DB access; see tg_session_uid_from_cookie_header's
 docstring above - same reasoning applies here."""
 # Raw ASGI header parsing - no Starlette Request object at this layer.
 if not cookie_header: return 0,0
 jar=SimpleCookie()
 try: jar.load(cookie_header)
 except Exception: return 0,0
 morsel=jar.get(WEB_SESSION_COOKIE)
 if not morsel: return 0,0
 try: return verify_web_session_token(morsel.value)
 except SecurityError: return 0,0

def resolve_web_session_uid(account_id):
 """Blocking DB lookup - call via asyncio.to_thread from async code."""
 now=time.monotonic()
 cached=_web_uid_cache.get(account_id)
 if cached and cached[1]>now:
  print("SESSION_ME_TIMING:", {"stage": "resolve_web_session_uid.cache_hit", "ms": 0, "account_id": account_id})
  return cached[0]
 database_url=_database_url()
 if not database_url: return 0
 from db_pool import db_connect
 lookup_started=time.monotonic()
 checkout_started=time.monotonic()
 conn=db_connect(database_url)
 print("SESSION_ME_TIMING:", {"stage": "resolve_web_session_uid.checkout", "ms": round((time.monotonic()-checkout_started)*1000), "account_id": account_id})
 try:
  cur=conn.cursor()
  q_start=time.monotonic()
  cur.execute('SELECT active_telegram_id FROM sylvex_accounts WHERE account_id = %s',(account_id,))
  row=cur.fetchone()
  print("SESSION_ME_TIMING:", {"stage": "resolve_web_session_uid.select_sylvex_accounts", "ms": round((time.monotonic()-q_start)*1000), "account_id": account_id})
  cur.close()
 finally:
  release_started=time.monotonic()
  conn.close()
  print("SESSION_ME_TIMING:", {"stage": "resolve_web_session_uid.release", "ms": round((time.monotonic()-release_started)*1000), "account_id": account_id})
 print("SESSION_ME_TIMING:", {"stage": "resolve_web_session_uid.total", "ms": round((time.monotonic()-lookup_started)*1000), "account_id": account_id})
 telegram_id=int(row[0]) if row and row[0] else 0
 if len(_web_uid_cache)>5000: _web_uid_cache.clear()
 _web_uid_cache[account_id]=(telegram_id,now+_WEB_UID_CACHE_TTL)
 return telegram_id

# ---------------------------------------------------------------------------
# Server-side session revocation (security audit COOKIE-2).
#
# Both sylvex_web_session and sylvex_tg_session above are otherwise pure
# stateless HMAC: a copy of either token captured elsewhere (network
# capture, a synced device, a misconfigured proxy log) keeps working for
# its full max-age even after the legitimate user logs out, changes their
# password, or deletes their account - there was no server-side state to
# check against.
#
# This adds a per-subject monotonic session-generation counter, bumped by
# revoke_web_sessions()/revoke_tg_sessions() on those events, and compared
# against the token's own generation (see verify_web_session_token/
# verify_tg_session_token above) with a plain integer check: a token whose
# generation is strictly less than the subject's CURRENT generation is
# revoked, full stop. There is no clock involved in that decision, so
# there is no ambiguous ordering to get wrong - this replaces an earlier
# version of this fix that compared a wall-clock issued_at against a
# revocation timestamp, where an old token minted in the same second as a
# revocation could survive the check, and a fresh token reissued
# immediately after that revocation (e.g. right after a password change)
# could just as easily be minted in that same second, making a bare
# `<` vs `<=` choice unable to get both cases right at once. Here
# revoke_web_sessions() returns the freshly incremented generation value
# directly from its own UPDATE ... RETURNING, and that exact value is used
# to mint the reissued cookie (see main.py's _set_web_session_cookie) -
# never re-derived from a second read of anything, so there is nothing
# left to race.
#
# Both lookups are blocking DB calls - callers MUST use asyncio.to_thread,
# exactly like resolve_web_session_uid above. Deliberately UNCACHED, unlike
# resolve_web_session_uid's 30s _web_uid_cache: this process is one of
# several worker processes/replicas in production, each with its own
# memory, and a cache populated here would only ever be consulted by THIS
# worker - a logout/password-change handled by worker A bumps the
# generation in the database, but worker B (and every other worker) would
# keep accepting the token at its own stale cached generation for up to
# the cache's TTL, during which an already-revoked token is wrongly still
# honored. That window is exactly what server-side revocation exists to
# close, so it must not reopen one of its own. Nothing here needs a shared
# cache (Redis, pub/sub, etc.) to fix this safely - a single indexed-PK
# lookup per request against Postgres is cheap enough that going without
# any cache at all is the correct minimal fix, not a stopgap.
# ---------------------------------------------------------------------------

def current_web_session_generation(account_id):
 """Blocking DB lookup - call via asyncio.to_thread. Returns account_id's
 current session-generation counter (0 if its sessions have never been
 revoked - sylvex_accounts.session_generation defaults to 0). Always a
 fresh read, never cached - see the module comment above."""
 database_url=_database_url()
 if not database_url: return 0
 from services.account_identity import ensure_account_tables
 ensure_account_tables(database_url)
 from db_pool import db_connect
 conn=db_connect(database_url)
 try:
  cur=conn.cursor()
  cur.execute('SELECT session_generation FROM sylvex_accounts WHERE account_id = %s',(account_id,))
  row=cur.fetchone()
  cur.close()
 finally:
  conn.close()
 return int(row[0]) if row and row[0] else 0

def revoke_web_sessions(account_id):
 """Blocking DB write - call via asyncio.to_thread. Invalidates every
 sylvex_web_session token already issued for this account (logout/
 password-change/account-delete) and returns the freshly incremented
 generation - pass that value straight to create_web_session_token() to
 reissue a cookie for the same browser with zero ambiguity about whether
 it's "new enough" (see the module comment above)."""
 database_url=_database_url()
 if not database_url: return 0
 from services.account_identity import ensure_account_tables
 ensure_account_tables(database_url)
 from db_pool import db_connect
 conn=db_connect(database_url)
 try:
  cur=conn.cursor()
  cur.execute('UPDATE sylvex_accounts SET session_generation = session_generation + 1 WHERE account_id = %s RETURNING session_generation',(account_id,))
  row=cur.fetchone()
  conn.commit()
  cur.close()
 finally:
  conn.close()
 return int(row[0]) if row else 0

_TG_REVOCATION_TABLE_READY=False
_tg_revocation_table_lock=threading.Lock()

def _ensure_tg_revocation_table(database_url):
 global _TG_REVOCATION_TABLE_READY
 if _TG_REVOCATION_TABLE_READY or not database_url: return
 with _tg_revocation_table_lock:
  if _TG_REVOCATION_TABLE_READY: return
  from db_pool import db_connect
  conn=db_connect(database_url)
  try:
   cur=conn.cursor()
   cur.execute("""
    CREATE TABLE IF NOT EXISTS sylvex_tg_session_revocations (
     telegram_id BIGINT PRIMARY KEY,
     generation INTEGER NOT NULL DEFAULT 0
    )
   """)
   conn.commit()
   cur.close()
  finally:
   conn.close()
  _TG_REVOCATION_TABLE_READY=True

def current_tg_session_generation(telegram_id):
 """Blocking DB lookup - call via asyncio.to_thread. Returns telegram_id's
 current session-generation counter (0 if never revoked - no row at all
 means 0). Nothing in this codebase calls revoke_tg_sessions() yet (see
 its docstring below), so this always returns 0 today; it exists so the
 check is already wired and live the moment such a trigger is added,
 without a second migration. Always a fresh read, never cached - see the
 module comment above revoke_web_sessions()."""
 database_url=_database_url()
 if not database_url: return 0
 _ensure_tg_revocation_table(database_url)
 from db_pool import db_connect
 conn=db_connect(database_url)
 try:
  cur=conn.cursor()
  cur.execute('SELECT generation FROM sylvex_tg_session_revocations WHERE telegram_id = %s',(telegram_id,))
  row=cur.fetchone()
  cur.close()
 finally:
  conn.close()
 return int(row[0]) if row else 0

def revoke_tg_sessions(telegram_id):
 """Blocking DB write - call via asyncio.to_thread. Invalidates every
 sylvex_tg_session token already issued for this telegram_id and returns
 the freshly incremented generation. See current_tg_session_generation's
 docstring - not called from anywhere yet; whatever eventually does call
 this is responsible for passing the returned value through to any
 reissue it triggers, exactly as main.py's password-change route does
 for revoke_web_sessions()."""
 database_url=_database_url()
 if not database_url: return 0
 _ensure_tg_revocation_table(database_url)
 from db_pool import db_connect
 conn=db_connect(database_url)
 try:
  cur=conn.cursor()
  cur.execute("""
   INSERT INTO sylvex_tg_session_revocations (telegram_id, generation) VALUES (%s, 1)
   ON CONFLICT (telegram_id) DO UPDATE SET generation = sylvex_tg_session_revocations.generation + 1
   RETURNING generation
  """,(telegram_id,))
  row=cur.fetchone()
  conn.commit()
  cur.close()
 finally:
  conn.close()
 return int(row[0]) if row else 0

def verify_telegram_login_widget(payload, tokens=None):
 # Distinct from validated_user(): the Telegram Login Widget signs with
 # secret_key = SHA256(bot_token), not the WebAppData-keyed HMAC initData
 # uses, per https://core.telegram.org/widgets/login#checking-authorization.
 if not isinstance(payload,dict): raise SecurityError('invalid_telegram_payload')
 received=str(payload.get('hash') or '')
 if not re.fullmatch(r'[a-fA-F0-9]{64}',received): raise SecurityError('invalid_telegram_payload')
 data={k:v for k,v in payload.items() if k!='hash' and v is not None}
 check_string='\n'.join(f'{k}={data[k]}' for k in sorted(data))
 tokens=bot_tokens() if tokens is None else tokens
 if not tokens: raise SecurityError('telegram_auth_not_configured',503)
 valid=any(hmac.compare_digest(hmac.new(hashlib.sha256(t.encode()).digest(),check_string.encode(),hashlib.sha256).hexdigest(),received.lower()) for t in tokens)
 if not valid: raise SecurityError('invalid_telegram_payload')
 try:
  age=time.time()-int(payload.get('auth_date',0))
  if age<-30 or age>int(os.getenv('TELEGRAM_LOGIN_MAX_AGE_SECONDS','86400')): raise ValueError()
  user_id=int(payload.get('id',0))
  if user_id<=0: raise ValueError()
 except (TypeError,ValueError): raise SecurityError('expired_or_invalid_telegram_user')
 return {'id':user_id,'username':payload.get('username'),'first_name':payload.get('first_name'),'last_name':payload.get('last_name'),'photo_url':payload.get('photo_url')}

class LocalLimiter:
 def __init__(self): self.items=OrderedDict()
 def allow(self,key,limit,seconds):
  now=time.monotonic();count,start=self.items.pop(key,(0,now))
  if now-start>=seconds:count,start=0,now
  self.items[key]=(count+1,start)
  while len(self.items)>10000:self.items.popitem(last=False)
  return count<limit

class SecurityMiddleware:
 def __init__(self,app,quota_check=None): self.app=app;self.limiter=LocalLimiter();self.quota_check=quota_check
 async def __call__(self,scope,receive,send):
  if scope['type']!='http':return await self.app(scope,receive,send)
  path=scope['path'];method=scope['method'];headers=dict(scope.get('headers',[]))
  from services.media_access import media_key, valid_media_url, validate_input_media, sign_response_media
  media_path=path.startswith(('/webapp/generated/','/static/generated/','/generated/','/api/public/storage/'))
  media_url=path+'?'+scope.get('query_string',b'').decode()
  media_allowed=False
  if media_path:
   media_allowed=method in {'GET','HEAD'} and valid_media_url(media_url)
   if not media_allowed:
    return await JSONResponse({'ok':False,'error':'media_authorization_required'},status_code=403)(scope,receive,send)
  protected=path.startswith('/api/') or path=='/save-settings' or media_path
  if not protected:
   # Unprotected (static/webapp) responses skip secured_send entirely, but
   # this is exactly where the real Pro Studio HTML page is served from -
   # the one response frame-ancestors/CSP/HSTS actually need to reach (see
   # security_response_headers() above). A minimal wrapper, not the full
   # secured_send machinery (no body buffering/signing needed here).
   async def unprotected_send(message):
    if message['type']=='http.response.start':
     message=dict(message);hs=list(message.get('headers',[]));hs.extend(security_response_headers());message['headers']=hs
    await send(message)
   return await self.app(scope,receive,unprotected_send)
  is_public=media_allowed or (method in {'GET','HEAD'} and (path in PUBLIC_GETS or any(p.fullmatch(path) for p in PUBLIC_PATTERNS))) or (method=='POST' and path in PUBLIC_POSTS)
  is_webhook=path in WEBHOOKS
  # CSRF guard: every /api/web/* route authenticates off the sylvex_web_session
  # cookie (SameSite=None, required for the cross-origin Pro Studio iframe
  # embed - see WEB_SESSION_COOKIE above), whether or not it's in PUBLIC_POSTS,
  # so this must run before the is_public bypass below, not after it.
  # Non-mutating requests are left alone: reading state cross-origin without
  # credentials visible to the attacker page isn't the CSRF threat model.
  if method in {'POST','PUT','PATCH','DELETE'} and path.startswith('/api/web/') and not origin_allowed(headers):
   return await JSONResponse({'ok':False,'error':'origin_not_allowed'},status_code=403)(scope,receive,send)
  if path.startswith('/api/public/payments/dev/') and (os.getenv('APP_ENV','development')=='production' or os.getenv('ENABLE_DEV_PAYMENTS','0')!='1'):
   return await JSONResponse({'ok':False,'error':'not_found'},status_code=404)(scope,receive,send)
  ip=(scope.get('client') or ('unknown',))[0]
  # Do not trust forwarded headers supplied by clients. Per-user durable quotas supplement this process-local burst guard.
  if not is_webhook and not self.limiter.allow(('ip',ip),int(os.getenv('API_IP_REQUESTS_PER_MINUTE','1200')),60):
   return await JSONResponse({'ok':False,'error':'rate_limited'},status_code=429,headers={'Retry-After':'60'})(scope,receive,send)
  content_type=headers.get(b'content-type',b'').lower()
  multipart=content_type.startswith(b'multipart/form-data')
  if multipart and path not in MULTIPART_ROUTES:
   return await JSONResponse({'ok':False,'error':'unsupported_content_type'},status_code=415)(scope,receive,send)
  sdp=path in SDP_ROUTES and content_type.split(b';',1)[0].strip()==b'application/sdp'
  max_size=(201 if multipart else 16)*1024*1024
  if is_webhook or sdp:max_size=1024*1024
  try:
   if int(headers.get(b'content-length',b'0'))>max_size:raise SecurityError('request_too_large',413)
  except ValueError as exc:
   code=exc.code if isinstance(exc,SecurityError) else 'invalid_content_length';status=exc.status if isinstance(exc,SecurityError) else 400
   return await JSONResponse({'ok':False,'error':code},status_code=status)(scope,receive,send)
  query=parse_qsl(scope.get('query_string',b'').decode(),keep_blank_values=True)
  json_body=None;body=None
  try:
   # Authentication can be sent in the header for streamed multipart requests.
   if not multipart and not is_public and not is_webhook and method in {'POST','PUT','PATCH','DELETE'}:
    chunks=[];size=0
    while True:
     message=await receive()
     if message['type']=='http.disconnect':return
     chunk=message.get('body',b'');size+=len(chunk)
     if size>max_size:raise SecurityError('request_too_large',413)
     chunks.append(chunk)
     if not message.get('more_body'):break
    body=b''.join(chunks)
    if body and not sdp:
     try:json_body=json.loads(body)
     except (ValueError,UnicodeError):raise SecurityError('invalid_json',400)
     if not isinstance(json_body,dict):raise SecurityError('json_object_required',400)
   init_data=headers.get(b'x-telegram-init-data',b'').decode()
   if not init_data and json_body:init_data=str(json_body.get('initData') or json_body.get('init_data') or '')
   if not init_data:init_data=next((v for k,v in query if k in {'init_data','initData'}),'')
   uid=0
   tg_session_uid_to_refresh=0
   # The Support Bot is a separate Telegram bot/token and can never produce
   # a valid initData signature for this app's BOT_TOKEN. A matching shared
   # secret, sent as a header (never in the JSON body, so it never lands in
   # request logs of the body) on an /api/admin/ request lets it
   # authenticate as the Telegram user it names - _admin_actor still runs
   # the normal admin_users role/permission lookup for that id, so this
   # only proves the caller is the trusted support-bot backend, not that
   # the named id is an admin.
   admin_service_token=os.getenv('ADMIN_SERVICE_TOKEN','').strip()
   service_authenticated=False
   if path.startswith('/api/admin/') and admin_service_token:
    presented=headers.get(b'x-admin-service-token',b'').decode().strip()
    if not presented:
     auth_header=headers.get(b'authorization',b'').decode().strip()
     if auth_header.lower().startswith('bearer '):presented=auth_header[7:].strip()
    service_authenticated=bool(presented) and hmac.compare_digest(presented,admin_service_token)
   if not is_public and not is_webhook:
    if service_authenticated:
     try:uid=int((json_body or {}).get('telegram_id') or 0)
     except (TypeError,ValueError):uid=0
     if not uid:raise SecurityError('telegram_user_missing')
     user={'id':uid};admin=True
    else:
     admin=path.startswith('/api/admin/')
     if init_data:
      try:
       user=validated_user(init_data);uid=user['id']
       if not admin:tg_session_uid_to_refresh=uid
      except SecurityError:
       # initData present but stale (Mini App open longer than
       # TELEGRAM_AUTH_MAX_AGE_SECONDS) or otherwise invalid - fall back to
       # the sliding tg-session cookie minted on an earlier successful
       # request from this same browser, so the caller is never forced to
       # close/reopen the Mini App. Never for admin routes.
       uid=0
       if not admin:
        cookie_header=headers.get(b'cookie',b'').decode()
        uid,tg_generation=tg_session_uid_from_cookie_header(cookie_header)
        if uid:
         current_generation=await asyncio.to_thread(current_tg_session_generation,uid)
         if tg_generation<current_generation:uid=0
       if not uid:raise
       user={'id':uid};tg_session_uid_to_refresh=uid
     else:
      # No Telegram initData at all (never true inside real Telegram - see
      # api-auth.js's fetch wrapper, which only ever sends this header when
      # window.Telegram.WebApp.initData is real): the website-embedded Pro
      # Studio path. Admin routes are deliberately excluded - they must
      # still go through real Telegram initData or the support-bot service
      # token above, never a website session cookie.
      uid=0
      if not admin:
       cookie_header=headers.get(b'cookie',b'').decode()
       web_account_id,web_generation=web_session_account_id_from_cookie_header(cookie_header)
       if web_account_id:
        current_generation=await asyncio.to_thread(current_web_session_generation,web_account_id)
        if web_generation<current_generation:web_account_id=0
       if web_account_id:
        # Same CSRF guard as the /api/web/* check above, for the
        # website-embedded Pro Studio path (e.g. a PayPal order creation
        # reached with no Telegram initData at all, only this cookie).
        if method in {'POST','PUT','PATCH','DELETE'} and not origin_allowed(headers):raise SecurityError('origin_not_allowed',403)
        uid=await asyncio.to_thread(resolve_web_session_uid,web_account_id)
      if not uid:raise SecurityError('invalid_init_data')
      user={'id':uid}
     if not admin:
      ids=[v for k,v in query if k=='telegram_id']
      if json_body is not None and 'telegram_id' in json_body:ids.append(json_body['telegram_id'])
      if path.startswith('/api/cabinet/'):ids.append(path.rsplit('/',1)[-1])
      for claimed in ids:
       try:
        if isinstance(claimed, (bool, list, dict)) or int(claimed or 0) not in (0,uid):raise ValueError()
       except (ValueError,TypeError):raise SecurityError('user_mismatch',403)
      query=[(k,v) for k,v in query if k!='telegram_id']+[('telegram_id',str(uid))]
      scope['query_string']=urlencode(query).encode()
      if json_body is not None:json_body['telegram_id']=uid
    if json_body is not None:
     if not admin:
      for key in ('mode','category','model','provider','prompt'):
       if key in json_body and not isinstance(json_body[key],str):raise SecurityError('invalid_'+key,422)
      for key in ('image_options','video_options','voice_options','text_options'):
       if key in json_body and json_body[key] is not None and not isinstance(json_body[key],dict):raise SecurityError('invalid_'+key,422)
      if len(json_body.get('prompt',''))>100000:raise SecurityError('prompt_too_large',413)
      if 'history' in json_body and (not isinstance(json_body['history'],list) or len(json_body['history'])>100):raise SecurityError('invalid_history',422)
      validate_input_media(json_body)
     # Legacy handlers now see the same verified credentials as middleware.
     json_body['initData']=init_data;json_body['init_data']=init_data
     body=json.dumps(json_body,separators=(',',':')).encode()
    scope.setdefault('state',{}).update(telegram_id=uid,telegram_user=user,telegram_init_data=init_data)
    if self.quota_check and method=='POST' and not admin and path not in WEBHOOKS and path not in ASSISTANT_SELF_QUOTA_ROUTES:
     await self.quota_check(uid,path)
  except SecurityError as exc:
   return await JSONResponse({'ok':False,'error':exc.code},status_code=exc.status)(scope,receive,send)
  size=0;replayed=False
  async def bounded_receive():
   nonlocal size,replayed
   if body is not None and not replayed:
    replayed=True;return {'type':'http.request','body':body,'more_body':False}
   message=await receive();size+=len(message.get('body',b''))
   if size>max_size:raise SecurityError('request_too_large',413)
   return message
  started=False; pending_start=None; response_parts=[]
  async def secured_send(message):
   nonlocal started, pending_start
   if message['type']=='http.response.start':
    started=True;message=dict(message);hs=list(message.get('headers',[]))
    hs.extend([(b'x-content-type-options',b'nosniff'),(b'referrer-policy',b'same-origin')]);hs.extend(security_response_headers())
    if tg_session_uid_to_refresh:
     hs.append((b'set-cookie',tg_session_set_cookie_bytes(tg_session_uid_to_refresh)))
    if uid:
     hs=[(k,v) for k,v in hs if k.lower()!=b'cache-control'];hs.append((b'cache-control',b'no-store'))
    # Content-derived safe MIME prevents legacy uploads from serving active HTML.
    if media_path:
     import mimetypes
     mime=mimetypes.guess_type(path)[0] or 'application/octet-stream'
     hs=[(k,v) for k,v in hs if k.lower()!=b'content-type']+[(b'content-type',mime.encode())]
     if not mime.startswith(('image/','audio/','video/')):
      hs.append((b'content-disposition',b'attachment'))
     hs=[(k,v) for k,v in hs if k.lower()!=b'cache-control']+[(b'cache-control',b'private, max-age=300')]
    message['headers']=hs
    if not media_path and not any(k.lower()==b'content-disposition' for k,v in hs) and any(k.lower()==b'content-type' and b'application/json' in v for k,v in hs):
     pending_start=message; return
   if message['type']=='http.response.body' and pending_start is not None:
    response_parts.append(message.get('body',b''))
    if message.get('more_body'):return
    raw=b''.join(response_parts)
    try:raw=json.dumps(sign_response_media(json.loads(raw)),ensure_ascii=False,separators=(',',':')).encode()
    except (ValueError,TypeError):pass
    pending_start['headers']=[(k,v) for k,v in pending_start['headers'] if k.lower()!=b'content-length']+[(b'content-length',str(len(raw)).encode())]
    await send(pending_start);pending_start=None
    return await send({'type':'http.response.body','body':raw,'more_body':False})
   await send(message)
  token=actor_id.set(uid);itoken=actor_init_data.set(init_data)
  try:await self.app(scope,bounded_receive,secured_send)
  except SecurityError as exc:
   if started:raise
   await JSONResponse({'ok':False,'error':exc.code},status_code=exc.status)(scope,receive,send)
  finally:actor_id.reset(token);actor_init_data.reset(itoken)
