"""Validation and deterministic image helpers for Sylvex Restore.

The provider calls stay in ``main.py`` beside the existing Pro Studio image
adapters.  This module owns the contract shared by analysis, restore, tests
and the browser UI: small high-value region sets, explicit region/reference
mapping, deterministic processing order, masks and protected-pixel restore.
"""

from __future__ import annotations

import io
import math
import re
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter


MODEL_KEY = "sylvex_sr"
MAX_AUTO_REGIONS = 8
MAX_TOTAL_REGIONS = 12
MAX_BY_TYPE = {"face": 5, "text": 4, "object": 3, "other": 0}
REGION_TYPES = {"face", "text", "object", "other"}
ACTIONS = {"auto_restore", "upload_reference", "enter_text", "protect_region", "skip_region"}
PROTECTION_MODES = {"hard", "soft"}
TEXT_LIMIT = 500
ACTION_ORDER = {"face": 1, "text": 2, "object": 3, "other": 4}


class SylvexRestoreValidationError(ValueError):
    pass


def analysis_prompt(width: int, height: int) -> str:
    return f"""Analyze this {width}x{height} source image for guided photo restoration.
Identify only the most important uncertain regions that are likely to affect restoration quality or user trust.
Prioritize faces, important readable text, and key foreground objects. Ignore minor background blur, tiny irrelevant details, and low-value artifacts.
Return at most 8 high-priority regions total: no more than 5 faces, 4 text regions, or 3 object regions.
Use absolute pixel coordinates inside the image. Confidence means confidence that the existing source contains enough reliable detail for automatic restoration, so a low value means high uncertainty.
Suggested action must be one of auto_restore, upload_reference, enter_text, protect_region, or skip_region.
Use concise English issue summaries. Do not invent regions outside the image."""


def analysis_json_schema() -> dict[str, Any]:
    bbox = {
        "type": "object",
        "additionalProperties": False,
        "required": ["x", "y", "width", "height"],
        "properties": {key: {"type": "number"} for key in ("x", "y", "width", "height")},
    }
    item = {
        "type": "object",
        "additionalProperties": False,
        "required": ["region_type", "bbox", "confidence", "importance_score", "issue_type", "issue_summary", "suggested_action"],
        "properties": {
            "region_type": {"type": "string", "enum": ["face", "text", "object"]},
            "bbox": bbox,
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "importance_score": {"type": "number", "minimum": 0, "maximum": 1},
            "issue_type": {"type": "string", "maxLength": 80},
            "issue_summary": {"type": "string", "maxLength": 240},
            "suggested_action": {"type": "string", "enum": sorted(ACTIONS)},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["regions"],
        "properties": {"regions": {"type": "array", "maxItems": MAX_AUTO_REGIONS, "items": item}},
    }


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def normalize_bbox(value: Any, image_width: int, image_height: int) -> dict[str, int]:
    if not isinstance(value, dict) or image_width < 1 or image_height < 1:
        raise SylvexRestoreValidationError("Invalid region coordinates.")
    x = max(0, min(image_width - 1, int(round(_number(value.get("x"))))))
    y = max(0, min(image_height - 1, int(round(_number(value.get("y"))))))
    width = max(1, int(round(_number(value.get("width"), 1))))
    height = max(1, int(round(_number(value.get("height"), 1))))
    width = min(width, image_width - x)
    height = min(height, image_height - y)
    if width < 2 or height < 2:
        raise SylvexRestoreValidationError("Region is too small.")
    return {"x": x, "y": y, "width": width, "height": height}


def _clean_text(value: Any, limit: int = TEXT_LIMIT) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value or "")).strip()[:limit]


def normalize_analysis_regions(raw_regions: Any, image_width: int, image_height: int) -> list[dict[str, Any]]:
    rows = raw_regions if isinstance(raw_regions, list) else []
    candidates: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        region_type = str(raw.get("region_type") or "").strip().lower()
        if region_type not in {"face", "text", "object"}:
            continue
        try:
            bbox = normalize_bbox(raw.get("bbox"), image_width, image_height)
        except SylvexRestoreValidationError:
            continue
        candidates.append({
            "source": "auto",
            "region_type": region_type,
            "bbox": bbox,
            "confidence": max(0.0, min(1.0, _number(raw.get("confidence"), 0.5))),
            "importance_score": max(0.0, min(1.0, _number(raw.get("importance_score"), 0.5))),
            "issue_type": _clean_text(raw.get("issue_type"), 80) or "uncertain_detail",
            "issue_summary": _clean_text(raw.get("issue_summary"), 240) or "This region may need guided restoration.",
            "suggested_action": str(raw.get("suggested_action") or "auto_restore").strip().lower(),
            "user_action": None,
            "reference_asset_id": None,
            "text_instruction": None,
            "protection_mode": None,
        })
    candidates.sort(key=lambda row: (-row["importance_score"], ACTION_ORDER[row["region_type"]]))
    selected: list[dict[str, Any]] = []
    counts = {key: 0 for key in MAX_BY_TYPE}
    for candidate in candidates:
        kind = candidate["region_type"]
        if len(selected) >= MAX_AUTO_REGIONS or counts[kind] >= MAX_BY_TYPE[kind]:
            continue
        counts[kind] += 1
        candidate["region_id"] = f"region_{len(selected) + 1}"
        if candidate["suggested_action"] not in ACTIONS:
            candidate["suggested_action"] = "auto_restore"
        selected.append(candidate)
    return selected


def validate_regions(regions: Any, image_width: int, image_height: int) -> list[dict[str, Any]]:
    if not isinstance(regions, list):
        raise SylvexRestoreValidationError("Regions must be a list.")
    if len(regions) > MAX_TOTAL_REGIONS:
        raise SylvexRestoreValidationError("You can use up to 12 regions.")
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, raw in enumerate(regions):
        if not isinstance(raw, dict):
            raise SylvexRestoreValidationError("Invalid region.")
        region_id = _clean_text(raw.get("region_id"), 64) or f"region_{index + 1}"
        if region_id in ids:
            raise SylvexRestoreValidationError("Region IDs must be unique.")
        ids.add(region_id)
        source = str(raw.get("source") or "auto").strip().lower()
        if source not in {"auto", "user_added"}:
            source = "user_added"
        region_type = str(raw.get("region_type") or "other").strip().lower()
        if region_type not in REGION_TYPES:
            raise SylvexRestoreValidationError("Unsupported region type.")
        action = str(raw.get("user_action") or raw.get("suggested_action") or "auto_restore").strip().lower()
        if action not in ACTIONS:
            raise SylvexRestoreValidationError("Unsupported region action.")
        reference = _clean_text(raw.get("reference_asset_id"), 2048)
        instruction = _clean_text(raw.get("text_instruction"), TEXT_LIMIT)
        protection = str(raw.get("protection_mode") or "").strip().lower() or None
        if action == "upload_reference" and not reference:
            raise SylvexRestoreValidationError(f"{region_id} requires a reference image.")
        if action == "enter_text" and not instruction:
            raise SylvexRestoreValidationError(f"{region_id} requires an instruction.")
        if action == "protect_region" and protection not in PROTECTION_MODES:
            raise SylvexRestoreValidationError(f"{region_id} requires Hard or Soft protection.")
        result.append({
            "region_id": region_id,
            "source": source,
            "region_type": region_type,
            "bbox": normalize_bbox(raw.get("bbox"), image_width, image_height),
            "confidence": raw.get("confidence") if raw.get("confidence") is None else max(0.0, min(1.0, _number(raw.get("confidence")))),
            "importance_score": max(0.0, min(1.0, _number(raw.get("importance_score"), 1.0 if source == "user_added" else 0.5))),
            "issue_type": _clean_text(raw.get("issue_type"), 80) or ("user_defined" if source == "user_added" else "uncertain_detail"),
            "issue_summary": _clean_text(raw.get("issue_summary"), 240) or ("User manually marked this region." if source == "user_added" else "This region may need guided restoration."),
            "suggested_action": str(raw.get("suggested_action") or "").strip().lower() or None,
            "user_action": action,
            "reference_asset_id": reference or None,
            "text_instruction": instruction or None,
            "protection_mode": protection if action == "protect_region" else None,
        })
    return result


def ordered_regions(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> tuple[int, int, str]:
        action = row.get("user_action")
        protection_first = 0 if action == "protect_region" else 1
        return protection_first, ACTION_ORDER.get(str(row.get("region_type")), 9), str(row.get("region_id"))
    return sorted(regions, key=key)


def actionable_region_count(regions: Any, retry_ids: Any = None, final_only: bool = False) -> int:
    if final_only:
        return 0
    allowed = {str(item) for item in retry_ids} if isinstance(retry_ids, list) and retry_ids else None
    count = 0
    for row in regions if isinstance(regions, list) else []:
        if not isinstance(row, dict) or (allowed is not None and str(row.get("region_id")) not in allowed):
            continue
        if str(row.get("user_action") or row.get("suggested_action") or "auto_restore") in {"auto_restore", "upload_reference", "enter_text"}:
            count += 1
    return count


def region_mask(size: tuple[int, int], bbox: dict[str, int]) -> bytes:
    """Return a GPT Image PNG mask: transparent inside bbox, opaque outside."""
    width, height = size
    mask = Image.new("RGBA", size, (0, 0, 0, 255))
    x, y = bbox["x"], bbox["y"]
    right, bottom = min(width, x + bbox["width"]), min(height, y + bbox["height"])
    alpha = mask.getchannel("A")
    alpha.paste(0, (x, y, right, bottom))
    mask.putalpha(alpha)
    output = io.BytesIO()
    mask.save(output, "PNG")
    return output.getvalue()


def composite_region(base_png: bytes, generated_bytes: bytes, bbox: dict[str, int]) -> bytes:
    with Image.open(io.BytesIO(base_png)) as base_image, Image.open(io.BytesIO(generated_bytes)) as generated_image:
        base = base_image.convert("RGBA")
        generated = generated_image.convert("RGBA").resize(base.size, Image.Resampling.LANCZOS)
        x, y = bbox["x"], bbox["y"]
        box = (x, y, x + bbox["width"], y + bbox["height"])
        # A small feather avoids a visible rectangular seam while still
        # limiting all provider changes to the selected local region.
        mask = Image.new("L", base.size, 0)
        mask.paste(255, box)
        feather = max(1, min(12, round(min(bbox["width"], bbox["height"]) * 0.035)))
        mask = mask.filter(ImageFilter.GaussianBlur(feather))
        merged = Image.composite(generated, base, mask)
        output = io.BytesIO()
        merged.save(output, "PNG")
        return output.getvalue()


def region_prompt(region: dict[str, Any], soft_protections: list[dict[str, Any]]) -> str:
    action = region["user_action"]
    bbox = region["bbox"]
    parts = [
        "Restore only the transparent masked region of the first source image.",
        f"Region ID: {region['region_id']}. Region type: {region['region_type']}.",
        f"Region bounds in source pixels: x={bbox['x']}, y={bbox['y']}, width={bbox['width']}, height={bbox['height']}.",
        "Preserve the exact composition, identity, geometry, layout, colors, lighting and all pixels outside the mask.",
        "Remove blur, compression artifacts, noise and damage only where supported by the source or the explicit user guidance. Never invent unrelated content.",
    ]
    if region.get("issue_summary"):
        parts.append(f"Observed uncertainty: {region['issue_summary']}")
    if action == "upload_reference":
        parts.append("The second input image is the explicit reference mapped to this region ID. Use it only to reconstruct this region; do not copy its background, pose, framing, or unrelated elements.")
    if region.get("text_instruction"):
        parts.append(f"User instruction for this region: {region['text_instruction']}")
    if region["region_type"] == "face":
        parts.append("Preserve the same person's identity, expression, gaze, age, pose, hair and facial proportions.")
    elif region["region_type"] == "text":
        parts.append("Preserve the sign, logo and typography layout. If exact text was supplied, reproduce it exactly and legibly.")
    for protected in soft_protections:
        parts.append(f"Soft-protected {protected['region_id']} must keep its identity and semantic meaning unchanged.")
    return " ".join(parts)


def normalize_final_enhance(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    upscale = int(_number(raw.get("upscale_factor"), 2))
    if upscale not in {1, 2, 4}:
        upscale = 2
    return {
        "apply_global_enhance": bool(raw.get("apply_global_enhance", True)),
        "upscale_factor": upscale,
        "denoise_strength": max(0.0, min(1.0, _number(raw.get("denoise_strength"), 0.2))),
        "sharpen_strength": max(0.0, min(1.0, _number(raw.get("sharpen_strength"), 0.2))),
    }


def final_enhance(source_png: bytes, working_png: bytes, settings: Any, hard_regions: list[dict[str, Any]]) -> bytes:
    options = normalize_final_enhance(settings)
    with Image.open(io.BytesIO(source_png)) as original_image, Image.open(io.BytesIO(working_png)) as working_image:
        original = original_image.convert("RGBA")
        result = working_image.convert("RGBA")
        if options["apply_global_enhance"]:
            denoise = options["denoise_strength"]
            if denoise > 0:
                filtered = result.filter(ImageFilter.MedianFilter(3))
                result = Image.blend(result, filtered, min(0.55, denoise * 0.55))
            sharpen = options["sharpen_strength"]
            if sharpen > 0:
                result = ImageEnhance.Sharpness(result).enhance(1.0 + sharpen * 1.5)
        factor = options["upscale_factor"]
        if factor > 1:
            result = result.resize((result.width * factor, result.height * factor), Image.Resampling.LANCZOS)
            original = original.resize(result.size, Image.Resampling.LANCZOS)
        for region in hard_regions:
            bbox = region["bbox"]
            box = tuple(int(round(value * factor)) for value in (
                bbox["x"], bbox["y"], bbox["x"] + bbox["width"], bbox["y"] + bbox["height"]
            ))
            result.paste(original.crop(box), box)
        output = io.BytesIO()
        result.save(output, "PNG")
        return output.getvalue()
