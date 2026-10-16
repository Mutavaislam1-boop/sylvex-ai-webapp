"""Central price finalisation for SYLVEX paid operations.

Provider-specific base tariffs are resolved by the provider adapters.  This
module owns the common, auditable part of every calculation: normalisation,
SYLVEX additions, final rounding and immutable task snapshots.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from typing import Any, Iterable
from services.edit_workspace import is_free_resize

PRICE_VERSION = "2026-10-audit-v2"
# SYLVEX pricing rule: user credits = ceil(provider_cost_usd * 1.5 * 100).
SYLVEX_MARKUP = Decimal("1.5")


def sylvex_credits(provider_cost_usd: Any) -> int:
    """The single provider-cost -> credits conversion. Decimal, so a
    $0.10 cost is 15 credits rather than float's 15.000000000000002 -> 16."""
    cost = Decimal(str(provider_cost_usd or 0))
    if cost <= 0:
        return 0
    return int((cost * SYLVEX_MARKUP * 100).to_integral_value(rounding=ROUND_CEILING))
# One SYLVEX credit is one US cent at the customer-facing balance layer.
# These are product fees for using SYLVEX-managed creative assets and are
# deliberately separate from whatever the provider charges for model input.
SYLVEX_ASSET_FEE_CREDITS = Decimal("1")
STYLE_CREDITS = SYLVEX_ASSET_FEE_CREDITS
CHARACTER_CREDITS = SYLVEX_ASSET_FEE_CREDITS
OBJECT_CREDITS = SYLVEX_ASSET_FEE_CREDITS
REFERENCE_CREDITS = SYLVEX_ASSET_FEE_CREDITS


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return [item for item in value if item]
    return [value] if value else []


def _sources(payload: dict) -> Iterable[dict]:
    yield payload
    for key in ("image_options", "video_options", "voice_options", "music_options", "text_options"):
        value = payload.get(key)
        if isinstance(value, dict):
            yield value


def _stable_asset_key(value: Any) -> str:
    """Canonical key used only for billing de-duplication.

    Clients retain several legacy aliases for the same attachment.  A file
    appearing in both ``references`` and ``referenceImageUrls`` is one
    SYLVEX asset use, not two billable assets.
    """
    if value is None or value is False or value == "":
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("asset_id", "assetId", "id", "url", "image_url", "video_url", "src", "storage_key"):
            candidate = value.get(key)
            if candidate:
                return str(candidate).strip()
        try:
            import json
            return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        except (TypeError, ValueError):
            return repr(value)
    try:
        import json
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(value)


def _unique_values(payload: dict, keys: tuple[str, ...]) -> list[Any]:
    unique: dict[str, Any] = {}
    for source in _sources(payload):
        for key in keys:
            for value in _as_list(source.get(key)):
                stable = _stable_asset_key(value)
                if stable:
                    unique.setdefault(stable, value)
    return list(unique.values())


def _selected_assets(payload: dict, keys: tuple[str, ...]) -> list[Any]:
    return [
        value for value in _unique_values(payload, keys)
        if str(value or "").strip().lower() not in {"auto", "none", "default", "off", "false"}
    ]


def _option(payload: dict, *keys: str) -> Any:
    for source in _sources(payload):
        for key in keys:
            if source.get(key):
                return source[key]
    return None


def sylvex_additions(payload: dict) -> dict[str, Decimal]:
    """Return internal additions without conflating them with provider input fees."""
    additions: dict[str, Decimal] = {}
    if is_free_resize(payload):
        return additions
    # Text writing style/options are prompt settings, not priced assets. An
    # uploaded image is still a SYLVEX-managed reference and keeps the same
    # one-credit project fee as an image-generation reference.
    is_text = str(payload.get("mode") or payload.get("category") or "").lower() in {"text", "chat", "pro", "lite"}
    styles = [] if is_text else _selected_assets(payload, ("style", "style_id", "selected_style"))
    characters = [] if is_text else _selected_assets(payload, ("character", "character_id", "selected_character"))
    objects = [] if is_text else _selected_assets(payload, ("object", "object_id", "selected_object"))
    if styles:
        additions["sylvex_styles"] = STYLE_CREDITS * len(styles)
    if characters:
        additions["sylvex_characters"] = CHARACTER_CREDITS * len(characters)
    if objects:
        additions["sylvex_objects"] = OBJECT_CREDITS * len(objects)
    references = _unique_values(payload, (
        "references", "reference_images", "referenceImageUrls", "referenceImages",
        "video_references", "characterReferenceUrls", "objectReferenceUrls",
    ))
    attachment = payload.get("attachment") if isinstance(payload.get("attachment"), dict) else {}
    attachment_mime = str(attachment.get("mime") or attachment.get("content_type") or "").lower()
    if is_text and attachment and attachment_mime.startswith("image/"):
        stable = _stable_asset_key(attachment)
        if stable and all(_stable_asset_key(existing) != stable for existing in references):
            references.append(attachment)
    # Sylvex Restore stores its explicit ID-mapped references inside region
    # objects rather than the legacy top-level aliases.
    for source in _sources(payload):
        regions = source.get("sylvexRestoreRegions") or source.get("regions") or []
        if isinstance(regions, list):
            for region in regions:
                if not isinstance(region, dict):
                    continue
                for key in ("reference_asset_id", "referenceAssetId", "reference_image_url", "referenceImageUrl"):
                    value = region.get(key)
                    stable = _stable_asset_key(value)
                    if stable and all(_stable_asset_key(existing) != stable for existing in references):
                        references.append(value)
    video_template = _option(payload, "video_template")
    # A catalog template is also a SYLVEX-managed reference asset. Provider
    # tariff remains in the base price; this is the independent product fee.
    if isinstance(video_template, dict) and any(video_template.get(key) for key in ("reference_video", "video_url", "template_video_url", "preview_video")):
        template_reference = next(
            (video_template.get(key) for key in ("reference_video", "video_url", "template_video_url", "preview_video") if video_template.get(key)),
            None,
        )
        if template_reference:
            references = _unique_values(
                {**payload, "video_options": {**(payload.get("video_options") or {}), "video_references": [*references, template_reference]}},
                ("references", "reference_images", "referenceImageUrls", "referenceImages", "video_references"),
            )
    if references:
        additions["sylvex_references"] = REFERENCE_CREDITS * len(references)
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
        "provider_and_model_credits": float(base),
        "sylvex_project_fee_credits": float(additions_total),
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
    enriched["pricing_available"] = bool(snapshot["final_credits"]) or is_free_resize(payload)
    return enriched


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def provider_reported_cost(result: dict) -> tuple[Decimal | None, str]:
    """Return authoritative provider cost only when the response says so.

    Locally computed ``cost_usd`` and ``cost_credits`` fields are estimates
    and are intentionally ignored here. xAI exposes exact USD ticks; Runway
    model-router responses expose realized provider credits worth $0.01 each.
    """
    if not isinstance(result, dict):
        return None, ""
    for node in _walk_dicts(result):
        if "provider_cost_usd_actual" in node:
            try:
                cost = Decimal(str(node.get("provider_cost_usd_actual")))
                if cost >= 0:
                    return cost, "provider_usage_calculation"
            except Exception:
                pass
        if "cost_in_usd_ticks" in node:
            try:
                ticks = Decimal(str(node.get("cost_in_usd_ticks")))
                if ticks >= 0:
                    return ticks / Decimal("10000000000"), "xai_cost_in_usd_ticks"
            except Exception:
                pass
    provider = str(result.get("provider") or "").strip().lower()
    if provider == "runway":
        for node in _walk_dicts(result.get("metadata") or result.get("provider_response") or {}):
            for key in ("realized_credits", "realizedCredits", "realized_cost_credits", "realizedCostCredits"):
                if key in node:
                    try:
                        credits = Decimal(str(node.get(key)))
                        if credits >= 0:
                            return credits * Decimal("0.01"), "runway_realized_credits"
                    except Exception:
                        pass
    return None, ""


def settle_media_price_snapshot(payload: dict, result: dict) -> dict:
    """Settle exact media cost without ever exceeding the held reservation.

    The project asset fee remains unchanged and separately visible. If a
    provider does not report an authoritative actual cost, the frozen
    provider-specific estimate remains the final charge.
    """
    snapshot = dict(payload.get("price_snapshot") or {})
    reserved = int(snapshot.get("final_credits") or 0)
    exact_provider_usd, source = provider_reported_cost(result)
    if exact_provider_usd is None:
        snapshot["settlement"] = {"source": "provider_specific_estimate", "reserved_credits": reserved}
        return snapshot
    project_fee = Decimal(str(snapshot.get("sylvex_project_fee_credits") or snapshot.get("additions_credits") or 0))
    exact_provider_credits = Decimal(sylvex_credits(exact_provider_usd))
    actual = int((exact_provider_credits + project_fee).to_integral_value(rounding=ROUND_CEILING))
    charged = min(reserved, max(0, actual))
    snapshot["reserved_credits"] = reserved
    snapshot["final_credits"] = charged
    snapshot["provider_and_model_credits"] = float(exact_provider_credits)
    snapshot["provider_cost_usd_actual"] = float(exact_provider_usd)
    snapshot["settlement"] = {
        "source": source,
        "reserved_credits": reserved,
        "actual_credits_before_cap": actual,
        "charged_credits": charged,
    }
    return snapshot
