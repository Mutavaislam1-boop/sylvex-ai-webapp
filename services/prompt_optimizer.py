import json
import os
import re
from typing import Any


DEFAULT_PROMPT_LIMIT = 6000

PROMPT_LIMITS = {
    "kling_3_0_turbo": 3072,
    "kling_3_0": 3072,
    "kling_motion_3_0": 3072,
    "kling_o3_omni": 3072,
    "kling_o3_edit": 3072,
    "kling_o1": 3072,
    "kling_2_6": 3072,
    "kling_motion_2_6": 3072,
    "kling_2_5_turbo": 3072,
    "kling_2_1": 3072,
    "kling_2_1_master": 3072,
    "kling_2_0_master": 3072,
    "kling_1_6": 3072,
    "kling_1_5": 3072,
    "kling_1_0": 3072,
    "kling_avatar": 3072,
    "kling_lip_sync": 3072,
    "heygen_v3_video_agent": 2000,
    "runway_aleph": 1000,
    "runway_gen": 1000,
    "veo_3_1": 4000,
    "veo_3_1_fast": 4000,
    "gemini_omni_flash": 4000,
    "sora_2": 4000,
    "sora_2_pro": 4000,
    "luma_ray_v3_2": 5000,
    "luma_dream_machine": 5000,
    "seedance_2_fast": 4000,
    "seedance_2_0": 4000,
    "seedance_1_5_pro": 4000,
}


def _configured_limits() -> dict:
    raw = os.getenv("PROMPT_LIMITS_JSON") or ""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def prompt_limit_for_model(model: str = "", provider: str = "", mode: str = "") -> int:
    key = (model or "").strip()
    limits = dict(PROMPT_LIMITS)
    limits.update(_configured_limits())
    for candidate in (key, key.lower(), key.replace("-", "_").lower()):
        if candidate in limits:
            try:
                return max(1, int(limits[candidate]))
            except Exception:
                return DEFAULT_PROMPT_LIMIT
    provider_key = f"{(provider or '').strip().lower()}:{(mode or '').strip().lower()}"
    if provider_key in limits:
        try:
            return max(1, int(limits[provider_key]))
        except Exception:
            return DEFAULT_PROMPT_LIMIT
    return DEFAULT_PROMPT_LIMIT


def prompt_metric_for_model(model: str = "", provider: str = "") -> str:
    value = f"{provider or ''} {model or ''}".lower()
    if "kling" in value:
        return "utf8_bytes"
    return "characters"


def _measure_prompt(text: str, metric: str) -> int:
    if metric == "utf8_bytes":
        return len(str(text or "").encode("utf-8"))
    return len(str(text or ""))


def _trim_to_limit(text: str, limit: int, metric: str) -> str:
    value = str(text or "")
    if _measure_prompt(value, metric) <= limit:
        return value
    if metric != "utf8_bytes":
        return value[:limit].rsplit(" ", 1)[0].strip()
    total = 0
    chars = []
    for char in value:
        size = len(char.encode("utf-8"))
        if total + size > limit:
            break
        chars.append(char)
        total += size
    return "".join(chars).rsplit(" ", 1)[0].strip()


def _normalize_prompt(prompt: str) -> str:
    text = str(prompt or "").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _sentence_key(sentence: str) -> str:
    value = re.sub(r"\W+", " ", sentence.lower(), flags=re.U)
    return re.sub(r"\s+", " ", value).strip()


def _dedupe_sentences(text: str) -> str:
    parts = re.split(r"(?<=[.!?。！？])\s+|\n+", text)
    seen = set()
    kept = []
    for part in parts:
        sentence = part.strip()
        if not sentence:
            continue
        key = _sentence_key(sentence)
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append(sentence)
    return " ".join(kept).strip()


def _fit_by_sentences(text: str, limit: int, metric: str) -> str:
    if _measure_prompt(text, metric) <= limit:
        return text
    parts = re.split(r"(?<=[.!?。！？])\s+", text)
    kept = []
    total = 0
    for part in parts:
        item = part.strip()
        if not item:
            continue
        add_len = _measure_prompt(item, metric) + (1 if kept else 0)
        if total + add_len > limit:
            continue
        kept.append(item)
        total += add_len
    result = " ".join(kept).strip()
    return result if result else _trim_to_limit(text, limit, metric)


def optimize_prompt_for_model(prompt: str, model: str = "", provider: str = "", mode: str = "") -> dict[str, Any]:
    original = str(prompt or "")
    limit = prompt_limit_for_model(model, provider, mode)
    metric = prompt_metric_for_model(model, provider)
    normalized = _normalize_prompt(original)
    optimized = normalized
    reason = ""
    if _measure_prompt(optimized, metric) > limit:
        optimized = _dedupe_sentences(optimized)
    if _measure_prompt(optimized, metric) > limit:
        optimized = _fit_by_sentences(optimized, limit, metric)
    if _measure_prompt(optimized, metric) > limit:
        optimized = _trim_to_limit(optimized, limit, metric)
    if _measure_prompt(optimized, metric) > limit:
        reason = "Optimization failed to reach limit"
    return {
        "prompt": optimized,
        "ok": bool(optimized) and _measure_prompt(optimized, metric) <= limit,
        "limit": limit,
        "metric": metric,
        "original_length": _measure_prompt(original, metric),
        "normalized_length": _measure_prompt(normalized, metric),
        "optimized_length": _measure_prompt(optimized, metric),
        "original_characters": len(original),
        "optimized_characters": len(optimized),
        "optimized": optimized != original,
        "failed_reason": reason,
    }
