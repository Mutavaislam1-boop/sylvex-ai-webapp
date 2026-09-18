"""Google / Apple Sign-In ID token verification via each provider's own
published JWKS - no client secret needed, only a public audience/client id
to check `aud` against. Uses PyJWT's PyJWKClient (fetches + caches the
provider's public signing keys and does the actual RS256/ES256 signature
verification) so no hand-rolled crypto is needed.

Google: fully functional once GOOGLE_OAUTH_CLIENT_ID is set (a public
value, safe to configure immediately).

Apple: the same verification code works, but actually receiving an Apple
ID token requires a paid Apple Developer Program enrollment, a configured
Services ID, and a generated private key for the "Sign in with Apple"
flow on the client side - none of which can be provisioned or tested in
this environment. Set APPLE_OAUTH_CLIENT_ID (the Services ID identifier)
once that's done; until then verify_apple_id_token raises
apple_oauth_not_configured, which the endpoint surfaces as a clear 503.
"""
from __future__ import annotations
import os
import jwt

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ["accounts.google.com", "https://accounts.google.com"]
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"

_jwks_clients = {}


def _jwks_client(url):
    client = _jwks_clients.get(url)
    if client is None:
        client = jwt.PyJWKClient(url)
        _jwks_clients[url] = client
    return client


class OAuthVerifyError(Exception):
    def __init__(self, code, status=400):
        self.code = code
        self.status = status
        super().__init__(code)


def verify_google_id_token(id_token: str) -> dict:
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    if not client_id:
        raise OAuthVerifyError("google_oauth_not_configured", 503)
    try:
        signing_key = _jwks_client(GOOGLE_JWKS_URL).get_signing_key_from_jwt(id_token)
        claims = jwt.decode(id_token, signing_key.key, algorithms=["RS256"], audience=client_id, issuer=GOOGLE_ISSUERS)
    except Exception:
        raise OAuthVerifyError("invalid_google_token")
    subject = claims.get("sub")
    if not subject:
        raise OAuthVerifyError("invalid_google_token")
    return {
        "subject": str(subject),
        "email": claims.get("email"),
        "email_verified": bool(claims.get("email_verified")),
        "name": claims.get("name"),
        # Preserved for possible future Website avatar support - not
        # persisted or used anywhere yet (see oauth_login_or_register()).
        "picture": claims.get("picture"),
    }


def verify_apple_id_token(id_token: str) -> dict:
    client_id = os.getenv("APPLE_OAUTH_CLIENT_ID", "").strip()
    if not client_id:
        raise OAuthVerifyError("apple_oauth_not_configured", 503)
    try:
        signing_key = _jwks_client(APPLE_JWKS_URL).get_signing_key_from_jwt(id_token)
        claims = jwt.decode(id_token, signing_key.key, algorithms=["ES256"], audience=client_id, issuer=APPLE_ISSUER)
    except Exception:
        raise OAuthVerifyError("invalid_apple_token")
    subject = claims.get("sub")
    if not subject:
        raise OAuthVerifyError("invalid_apple_token")
    email_verified = str(claims.get("email_verified", "")).lower() == "true"
    return {
        "subject": str(subject),
        "email": claims.get("email"),
        "email_verified": email_verified,
        "name": None,
    }
