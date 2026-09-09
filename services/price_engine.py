"""Central price finalisation for SYLVEX paid operations.

Provider-specific base tariffs are resolved by the provider adapters.  This
module owns the common, auditable part of every calculation: normalisation,
SYLVEX additions, final rounding and immutable task snapshots.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from typing import Any

PRICE_VERSION = "2026-09-full"
STYLE_CREDITS = Decimal("0.1")
CHARACTER_CREDITS = Decimal("0.1")
OBJECT_CREDITS = Decimal("0.1")
REFERENCE_CREDITS = Decimal("0.3")


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return [item for item in value if item]
    return [value] if value else []


def _option(payload: dict, *keys: str) -> Any:
    for source in (payload, payload.get("image_options") or {}, payload.get("video_options") or {}, payload.get("voice_options") or {}, payload.get("music_options") or {}, payload.get("text_options") or {}):
        for key in keys:
            if source.get(key):
                return source[key]
    return None


def sylvex_additions(payload: dict) -> dict[str, Decimal]:
    """Return internal additions without conflating them with provider input fees."""
    additions: dict[str, Decimal] = {}
    if _option(payload, "style", "style_id", "selected_style"):
        additions["style"] = STYLE_CREDITS
    if _option(payload, "character", "character_id", "selected_character"):
        additions["character"] = CHARACTER_CREDITS
    if _option(payload, "object", "object_id", "selected_object"):
        additions["object"] = OBJECT_CREDITS
    references = []
    for key in ("references", "reference_images", "referenceImageUrls", "referenceImages", "video_references"):
        references.extend(_as_list(_option(payload, key)))
    video_template = _option(payload, "video_template")
    if isinstance(video_template, dict) and any(video_template.get(key) for key in ("reference_video", "video_url", "template_video_url", "preview_video")):
        references.append("video-template")
    if references:
        additions["references"] = REFERENCE_CREDITS * len(references)
    return additions


def finalise_price(base_credits: Any, payload: dict) -> dict:
    """Create the only user-facing total; round once after all additions."""
    base = max(Decimal("0"), Decimal(str(base_credits or 0)))
    additions = sylvex_additions(payload)
    additions_total = sum(additions.values(), Decimal("0"))
    total_decimal = base + additions_total
    final_credits = int(total_decimal.to_integral_value(rounding=ROUND_CEILING))
    return {
        "pricing_version": PRICE_VERSION,
        "base_credits": float(base),
        "additions": {key: float(value) for key, value in additions.items()},
        "additions_credits": float(additions_total),
        "total_before_rounding": float(total_decimal),
        "final_credits": final_credits,
        "currency": "⚡",
    }


def create_price_snapshot(payload: dict, estimate: dict) -> dict:
    """Freeze price inputs and final total before the provider receives a task."""
    snapshot = finalise_price(estimate.get("credits"), payload)
    options = {
        key: value for key, value in {
            "mode": payload.get("mode") or payload.get("category"),
            "model": payload.get("model"),
            "provider": payload.get("provider"),
            "image_options": payload.get("image_options"),
            "video_options": payload.get("video_options"),
            "voice_options": payload.get("voice_options"),
            "music_options": payload.get("music_options"),
            "text_options": payload.get("text_options"),
        }.items() if value is not None
    }
    snapshot["parameters"] = options
    snapshot["created_at"] = datetime.now(timezone.utc).isoformat()
    return snapshot


def apply_snapshot_to_estimate(payload: dict, estimate: dict) -> dict:
    snapshot = create_price_snapshot(payload, estimate)
    enriched = dict(estimate)
    enriched["credits"] = snapshot["final_credits"]
    enriched["cost_credits"] = snapshot["final_credits"]
    enriched["generation_cost"] = f"{snapshot['final_credits']} ⚡"
    enriched["price_snapshot"] = snapshot
    enriched["pricing_version"] = PRICE_VERSION
    enriched["pricing_available"] = bool(snapshot["final_credits"])
    return enriched
