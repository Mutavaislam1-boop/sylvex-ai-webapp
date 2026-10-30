"""AI models and providers in the Admin Console.

Models can be turned off for user generations and back on. Turning a model
off only records it here: its configuration, integration and earlier
results stay untouched, and turning it back on uses the same settings.

Provider state is never assumed: a provider is "configured" only when its
credentials are present (only presence is checked, values are never read
out), "working" only when real generations succeeded recently, and "no
data" when nothing tells either way.
"""
from __future__ import annotations

import os
import re

# Credentials each provider reads (the same names the providers use).
PROVIDER_ENV = {
    "openai": ("OPENAI_API_KEY",),
    "sora": ("OPENAI_API_KEY",),
    "kling": ("KLING_API_KEY", "KLING_ACCESS_KEY"),
    "runway": ("RUNWAY_API_KEY", "RUNWAYML_API_SECRET", "RUNWAYML_API_KEY"),
    "bytedance": ("BYTEDANCE_API_KEY", "BYTEPLUS_API_KEY", "BYTEPLUS_ARK_API_KEY", "ARK_API_KEY"),
    "byteplus": ("BYTEDANCE_API_KEY", "BYTEPLUS_API_KEY", "BYTEPLUS_ARK_API_KEY", "ARK_API_KEY"),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "google": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "veo": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "grok": ("XAI_API_KEY",),
    "xai": ("XAI_API_KEY",),
    "luma": ("LUMA_AGENTS_API_KEY", "LUMA_API_KEY"),
    "minimax": ("MINIMAX_API_KEY",),
    "pixverse": ("PIXVERSE_API_KEY",),
    "heygen": ("HEYGEN_API_KEY",),
    "elevenlabs": ("ELEVENLABS_API_KEY",),
    "fal": ("FAL_KEY", "FAL_API_KEY"),
    "bfl": ("BFL_API_KEY", "FLUX_API_KEY"),
    "flux": ("BFL_API_KEY", "FLUX_API_KEY"),
    "fashn": ("FASHN_API_KEY",),
    "topaz": ("TOPAZ_API_KEY",),
    "dashscope": ("DASHSCOPE_API_KEY",),
    "qwen": ("DASHSCOPE_API_KEY",),
    "wan": ("DASHSCOPE_API_KEY",),
    "hedra": ("HEDRA_API_KEY",),
}
FAILED = ("failed", "cancelled", "canceled", "timeout", "timed_out")
# SYLVEX rule: credits = provider cost (USD) x 1.5 x 100, rounded up.
CREDITS_PER_USD = 150


def norm(model_id) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(model_id or "").lower()).strip("_")


def configured(provider):
    """True / False when the provider's credentials are known, None when
    SYLVEX has no record of what this provider needs."""
    names = PROVIDER_ENV.get(str(provider or "").lower())
    if not names:
        return None
    return any(bool((os.getenv(name) or "").strip()) for name in names)


def provider_state(is_configured, runs, completed, failed):
    """"not_configured" | "no_data" | "working" | "errors"."""
    if is_configured is False:
        return "not_configured"
    if not runs:
        return "no_data"
    if completed == 0 or failed * 2 > runs:
        return "errors"
    return "working"


def ensure_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS model_states (
            model_id TEXT PRIMARY KEY,
            disabled BOOLEAN NOT NULL DEFAULT FALSE,
            reason TEXT NOT NULL DEFAULT '',
            updated_by BIGINT,
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)


def disabled_models(cursor):
    cursor.execute("SELECT model_id, reason, updated_at FROM model_states WHERE disabled = TRUE")
    return {row[0]: {"reason": row[1] or "", "since": row[2]} for row in cursor.fetchall()}


def set_disabled(cursor, model_id, disabled, reason, actor_id):
    model_id = norm(model_id)
    cursor.execute("""
        INSERT INTO model_states (model_id, disabled, reason, updated_by, updated_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (model_id) DO UPDATE SET disabled = EXCLUDED.disabled, reason = EXCLUDED.reason,
            updated_by = EXCLUDED.updated_by, updated_at = NOW()
    """, (model_id, bool(disabled), str(reason or "")[:500], actor_id))
    return model_id
