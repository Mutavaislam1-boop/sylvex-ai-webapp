"""Resolve Grid-only internal catalog references before provider dispatch."""
from __future__ import annotations

from urllib.parse import quote, unquote, urlsplit, urlunsplit


IMAGE_LIST_FIELDS = (
    "referenceImageUrls",
    "reference_image_urls",
    "referenceImages",
    "images",
    "characterReferences",
    "objectReferences",
)
VIDEO_LIST_FIELDS = (
    "reference_images",
    "referenceImageUrls",
    "characterReferences",
    "objectReferences",
)
VIDEO_SINGLE_FIELDS = (
    "start_image",
    "end_image",
    "image_url",
    "character_image",
)


def public_catalog_reference(value, public_base_url: str):
    """Turn a safe ``/preset_catalog/...`` path into a public HTTPS URL.

    Other values are returned unchanged. This deliberately only handles the
    built-in catalog namespace; uploads and generated media retain their
    signed URLs and their existing authorization behavior.
    """
    if not isinstance(value, str):
        return value
    raw = value.strip()
    if not raw.startswith("/preset_catalog/"):
        return value
    parsed = urlsplit(raw)
    decoded_path = unquote(parsed.path)
    parts = decoded_path.replace("\\", "/").split("/")
    if any(part in {".", ".."} for part in parts):
        return value
    base = str(public_base_url or "").rstrip("/")
    if not base:
        return value
    encoded_path = quote(decoded_path, safe="/-._~")
    return base + urlunsplit(("", "", encoded_path, parsed.query, ""))


def _resolve_field(options: dict, field: str, public_base_url: str) -> int:
    value = options.get(field)
    changed = 0
    if isinstance(value, list):
        resolved = []
        for item in value:
            updated = public_catalog_reference(item, public_base_url)
            changed += int(updated != item)
            resolved.append(updated)
        options[field] = resolved
    elif isinstance(value, str):
        updated = public_catalog_reference(value, public_base_url)
        changed += int(updated != value)
        options[field] = updated
    return changed


def resolve_grid_catalog_references(payload: dict, public_base_url: str) -> int:
    """Resolve every catalog image field used by a Grid generation request.

    The mutation is restricted to payloads carrying ``grid_project_id`` so
    regular Pro Studio, Edit and Mini App provider behavior remains intact.
    Returns the number of rewritten values for safe, URL-free logging.
    """
    if not isinstance(payload, dict) or not str(payload.get("grid_project_id") or "").strip():
        return 0
    changed = 0
    image_options = payload.get("image_options")
    if isinstance(image_options, dict):
        for field in IMAGE_LIST_FIELDS:
            changed += _resolve_field(image_options, field, public_base_url)
    video_options = payload.get("video_options")
    if isinstance(video_options, dict):
        for field in (*VIDEO_LIST_FIELDS, *VIDEO_SINGLE_FIELDS):
            changed += _resolve_field(video_options, field, public_base_url)
    return changed
