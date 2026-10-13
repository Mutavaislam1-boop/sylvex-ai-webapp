"""Validation and deterministic image helpers for Sylvex Restore.

The provider calls stay in ``main.py`` beside the existing Pro Studio image
adapters. This module owns the manual-region contract shared by the restore
route and the Edit canvas: explicit coordinates, explicit region/reference
mapping, a four-reference limit and exact final output scaling.
"""

from __future__ import annotations

import io
import json
import math
import re
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter


MODEL_KEY = "sylvex_sr"
MAX_TOTAL_REGIONS = 12
MAX_REFERENCE_IMAGES = 4
REGION_TYPES = {"face", "text", "object", "other"}
ACTIONS = {"auto_restore", "upload_reference", "enter_text", "protect_region", "skip_region"}
PROTECTION_MODES = {"hard", "soft"}
TEXT_LIMIT = 500


class SylvexRestoreValidationError(ValueError):
    pass


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
        source = str(raw.get("source") or "user_added").strip().lower()
        if source not in {"auto", "user_added"}:
            source = "user_added"
        region_type = str(raw.get("region_type") or "other").strip().lower()
        if region_type not in REGION_TYPES:
            raise SylvexRestoreValidationError("Unsupported region type.")
        reference = _clean_text(raw.get("reference_asset_id"), 2048)
        instruction = _clean_text(raw.get("text_instruction"), TEXT_LIMIT)
        default_action = "upload_reference" if reference else "enter_text" if instruction else "auto_restore"
        action = str(raw.get("user_action") or default_action).strip().lower()
        if action not in ACTIONS:
            raise SylvexRestoreValidationError("Unsupported region action.")
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
    reference_count = sum(bool(row.get("reference_asset_id")) for row in result)
    if reference_count > MAX_REFERENCE_IMAGES:
        raise SylvexRestoreValidationError("You can use up to 4 reference images.")
    return result


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


def restore_prompt(regions: list[dict[str, Any]], image_width: int, image_height: int, upscale_factor: int = 1) -> str:
    """Build one explicit prompt for the source plus its mapped references."""
    parts = [
        "Restore and enhance the first input image as one coherent photograph.",
        "Improve overall detail, focus, sharpness, texture fidelity, noise and compression artifacts while preserving the exact composition, framing, subject identities, poses, geometry, colors, lighting and all important scene content.",
        "Do not redesign, restage, replace or invent subjects or objects unless a manual region instruction explicitly requests it.",
        f"The source coordinate system is {image_width} by {image_height} pixels with origin at the top-left.",
        f"The requested final output scale is X{upscale_factor}; restore fine detail suitable for that scale while keeping the source aspect ratio.",
    ]
    reference_index = 2
    structured_regions = []
    for number, region in enumerate(regions, start=1):
        bbox = region["bbox"]
        left = bbox["x"] / image_width * 100
        top = bbox["y"] / image_height * 100
        width = bbox["width"] / image_width * 100
        height = bbox["height"] / image_height * 100
        mapped_input = reference_index if region.get("reference_asset_id") else None
        line = (
            f"Region number {number}, ID {region['region_id']}: pixels x={bbox['x']}, y={bbox['y']}, "
            f"width={bbox['width']}, height={bbox['height']} "
            f"({left:.3f}% from left, {top:.3f}% from top, {width:.3f}% wide, {height:.3f}% high)."
        )
        if region.get("reference_asset_id"):
            line += (
                f" Input image {reference_index} is mapped only to {region['region_id']}; "
                "use its identity and object detail for this region only, without copying its background, pose, framing or unrelated content."
            )
            reference_index += 1
        if region.get("text_instruction"):
            line += f" User instruction: {region['text_instruction']}"
        action = region.get("user_action") or "auto_restore"
        protection = region.get("protection_mode")
        if action == "skip_region":
            line += " Skip restoration for this region and preserve it from the source image."
        elif action == "protect_region" and protection == "hard":
            line += " Hard protection: preserve the original source pixels in this region exactly."
        elif action == "protect_region":
            line += " Soft protection: enhancement is allowed, but identity, meaning, geometry and content must remain unchanged."
        elif not region.get("text_instruction") and not region.get("reference_asset_id"):
            line += " Restore this selected area conservatively from the source image without inventing new semantic content."
        parts.append(line)
        structured_regions.append({
            "number": number,
            "region_id": region["region_id"],
            "region_type": region.get("region_type") or "other",
            "bbox_pixels": bbox,
            "bbox_percent": {
                "x": round(left, 3),
                "y": round(top, 3),
                "width": round(width, 3),
                "height": round(height, 3),
            },
            "reference_input_image": mapped_input,
            "text_instruction": region.get("text_instruction") or None,
            "action": region.get("user_action") or "auto_restore",
        })
    if not regions:
        parts.append("No local regions were selected. Apply only a faithful global photo restoration and quality enhancement.")
    else:
        # Keep a machine-readable plan inside the prompt so region numbers,
        # pixel coordinates, reference slots and notes stay bound together.
        # Input image 1 is always the original; referenced inputs start at 2.
        parts.append(
            "Authoritative region-to-reference plan (JSON; apply every entry exactly): "
            + json.dumps(structured_regions, ensure_ascii=False, separators=(",", ":"))
        )
    parts.append("Return one clean final image with the same aspect ratio as the first input image and no boxes, labels, lines or UI overlays.")
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
        # A transparent source remains a transparent Edit object even when
        # the image provider returns an opaque PNG. Preserve the original
        # soft alpha at the requested final scale.
        source_alpha = original.getchannel("A")
        if source_alpha.getextrema() != (255, 255):
            result.putalpha(source_alpha)
        for region in hard_regions:
            bbox = region["bbox"]
            box = tuple(int(round(value * factor)) for value in (
                bbox["x"], bbox["y"], bbox["x"] + bbox["width"], bbox["y"] + bbox["height"]
            ))
            result.paste(original.crop(box), box)
        output = io.BytesIO()
        result.save(output, "PNG")
        return output.getvalue()
