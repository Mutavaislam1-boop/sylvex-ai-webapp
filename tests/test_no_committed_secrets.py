"""Repository secret check: no real credential may be committed.

Production secret values live only in Railway / environment variables; the
code reads them by name (os.getenv("BOT_TOKEN")). This test scans every
git-tracked text file and fails on:
  1. a tracked real env file (.env, .env.*, *.env - .env.example allowed);
  2. a Telegram bot token;
  3. a private key block;
  4. a provider / API credential or a connection string with a password;
  5. a long literal assigned to a secret-named variable (KEY, SECRET, TOKEN,
     PASSWORD...) - in code, .env-style files, YAML, docs, anywhere.
Values that are obviously dummies (contain test/fake/dummy/example/
placeholder/changeme/xxxx/redacted) are allowed, so fixtures still work.
Findings are reported masked - this test never prints a secret value.
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
THIS_FILE = Path(__file__).resolve().relative_to(ROOT).as_posix()

BINARY_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".mp4", ".mp3", ".wav", ".ogg",
    ".woff", ".woff2", ".ttf", ".otf", ".pdf", ".zip", ".gz", ".pyc", ".lock", ".mp4git",
)
ENV_FILE_ALLOWED = re.compile(r"(^|/)\.env\.(example|sample|template)$|(^|/)[^/]+\.env\.example$")
ENV_FILE = re.compile(r"(^|/)(\.env(\..+)?|[^/]+\.env)$")
DUMMY = re.compile(r"(?i)test|fake|dummy|example|sample|placeholder|changeme|change_me|your[_-]|xxxx|redacted|<[^>]*>|\$\{")

PATTERNS = (
    ("telegram bot token", re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{30,}")),
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----")),
    ("OpenAI key", re.compile(r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{32,}")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("Stripe key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("webhook signing secret", re.compile(r"\bwhsec_[A-Za-z0-9]{16,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}|\bAQ\.[A-Za-z0-9_-]{40,}")),
    ("Google OAuth client secret", re.compile(r"\bGOCSPX-[A-Za-z0-9_-]{20,}")),
    ("AWS / R2 access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{30,}")),
    ("Replicate token", re.compile(r"\br8_[A-Za-z0-9]{30,}")),
    ("SendGrid key", re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}")),
    ("fal key", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:[0-9a-f]{32}\b")),
    ("connection string with password",
     re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|rediss?|amqps?)://[^:\s/'\"@]+:[^@\s'\"]{4,}@[^\s'\"]+")),
    ("secret-named literal", re.compile(
        r"(?i)\b[A-Z0-9_-]*(?:SECRET|TOKEN|PASSWORD|PASSWD|API[_-]?KA?EY|PRIVATE[_-]KEY|ACCESS[_-]KEY|CLIENT[_-]SECRET)[A-Z0-9_-]*['\"]?"
        r"\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=:]{16,})['\"]?\s*(?:[,;)}\]#]|$)")),
)


def _tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [f for f in out.splitlines() if f]


def _looks_real(kind, value):
    if DUMMY.search(value):
        return False
    if kind == "secret-named literal":
        # Another variable's NAME, an identifier, or a plain URL is not a secret.
        if re.fullmatch(r"[A-Z0-9_]+|[a-z_.]+", value) or value.startswith(("http://", "https://")):
            return False
        if not (re.search(r"[A-Za-z]", value) and re.search(r"\d", value)):
            return False
    return True


def find_secrets(name, text):
    """[(line, kind, masked)] for every real-looking credential in text."""
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for kind, rx in PATTERNS:
            for match in rx.finditer(line[:5000]):
                value = match.group(1) if rx.groups else match.group(0)
                if _looks_real(kind, value):
                    hits.append((lineno, kind, f"{value[:3]}…[{len(value)} chars]"))
    return hits


def test_no_real_env_file_is_tracked():
    tracked = [f for f in _tracked_files() if ENV_FILE.search(f) and not ENV_FILE_ALLOWED.search(f)]
    assert tracked == [], f"real env files must not be tracked (use Railway variables): {tracked}"


def test_env_example_files_hold_names_only():
    for f in _tracked_files():
        if not ENV_FILE_ALLOWED.search(f):
            continue
        for lineno, line in enumerate((ROOT / f).read_text(errors="ignore").splitlines(), 1):
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            name, value = (part.strip() for part in line.split("=", 1))
            if re.search(r"(?i)SECRET|TOKEN|PASSWORD|API_?KEY|ACCESS_KEY|DATABASE_URL|DATABASE_PUBLIC_URL", name):
                assert value == "" or DUMMY.search(value), f"{f}:{lineno} {name} must be empty in an example file"


def test_no_credentials_in_tracked_files():
    findings = []
    for f in _tracked_files():
        if f == THIS_FILE or f.lower().endswith(BINARY_SUFFIXES):
            continue
        path = ROOT / f
        if not path.is_file():
            continue
        for lineno, kind, masked in find_secrets(f, path.read_text(errors="ignore")):
            findings.append(f"{f}:{lineno} {kind} {masked}")
    assert findings == [], "credentials committed to the repository:\n" + "\n".join(findings)


@pytest.mark.parametrize("sample,kind", [
    ("BOT_TOKEN=" + "8123456789:AA" + "Hq3Lm7Pz2Wn9Kd4Rt6Yb1Vc8Xs5Fj0Gu2Me", "telegram bot token"),
    ("-----BEGIN " + "PRIVATE KEY-----", "private key block"),
    ("key = '" + "sk-proj-" + "Ab3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0eF" + "'", "OpenAI key"),
    ("DATABASE_URL=" + "postgresql://postgres:" + "Qw3rTy8Ui9Op" + "@db.host:5432/railway", "connection string with password"),
    ("PAYPAL_CLIENT_SECRET=" + "EGs3kd93Jfh2Lp0Qm8Zx7Vb6Nc5", "secret-named literal"),
    ("STRIPE_KEY = \"" + "sk_live_" + "51Hq3Lm7Pz2Wn9Kd4Rt6Yb1\"", "Stripe key"),
])
def test_scanner_detects_real_looking_credentials(sample, kind):
    assert kind in {k for _, k, _ in find_secrets("sample", sample)}


@pytest.mark.parametrize("sample", [
    'BOT_TOKEN = os.getenv("BOT_TOKEN")',
    "BOT_TOKEN=",
    'OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]',
    "token = '123456:TEST'",
    "ADMIN_SERVICE_TOKEN=test-only-service-token",
    "DATABASE_URL=postgresql://user:password@localhost/example",
    "headers = {'Authorization': f'Bearer {token}'}",
])
def test_scanner_ignores_names_lookups_and_dummies(sample):
    assert find_secrets("sample", sample) == []
