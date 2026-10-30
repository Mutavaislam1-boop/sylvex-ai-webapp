"""Media constructor: blocks admins build in the Admin Console (AI tools,
video templates, photos and references, styles) and users run.

A block is a row of prostudio_references (name, description, cover
`preview_url`, the admin's own media `source_url`, prompt, model) plus
`block_type` and a `config` JSON:

    generation   "image" | "video"
    ref_mode     photos and styles: A = the admin's image goes to the model
                 as a real reference, B = it only illustrates the block and
                 the prompt drives the result, C = image and prompt together
    fields       what the user uploads: [{key, label, purpose, accept
                 ("image" | "video"), required, input}], `input` names the
                 model input it feeds ("reference", "start_image")
    placements   where it is published (the existing site / Mini App
                 catalogs, see PLACEMENTS)
    aspect, duration, resolution   optional generation settings

Prices are never stored: `generation_payload` builds the same request the
Pro Studio pipeline takes, and the existing price calculation prices it, so
the central tariff always applies. Models and their limits come from the
central capability registry (services/model_capabilities.py).
"""
from __future__ import annotations

import re

BLOCK_TYPES = ("tool", "video", "photo", "style")
REF_MODES = ("A", "B", "C")
FIELD_ACCEPT = ("image", "video")
FIELD_INPUTS = ("reference", "start_image")
MAX_FIELDS = 8
# Where a published block shows: the catalogs that already exist on the
# website (Media page, AI Tools) and in the Mini App.
PLACEMENTS = {
    "ai_tools": {"en": "AI Tools", "ru": "AI-инструменты", "types": ("tool",)},
    "video_styles": {"en": "Media · Video templates", "ru": "Media · Видеошаблоны", "types": ("video",)},
    "photo_references": {"en": "Media · Photo references", "ru": "Media · Фотореференсы", "types": ("photo",)},
    "image_styles": {"en": "Media · Image styles", "ru": "Media · Стили изображений", "types": ("style",)},
}
DEFAULT_PLACEMENT = {"tool": "ai_tools", "video": "video_styles", "photo": "photo_references", "style": "image_styles"}
# The upload count the apps allow for an image model when the provider has
# no stricter published limit (Mini App uploadLimitForTarget).
DEFAULT_IMAGE_REFERENCES = 4
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
DEFAULT_A_PROMPT = ("Recreate the reference image with the person or subject from the uploaded photo, "
                    "keeping the reference composition, style and lighting.")


class BlockError(Exception):
    def __init__(self, code, status=400, problems=None):
        super().__init__(code)
        self.code = code
        self.status = status
        self.problems = problems or []


def _text(value, limit):
    return re.sub(r"[ \t]+", " ", str(value or "")).strip()[:limit]


def clean_fields(raw):
    fields, seen = [], set()
    for index, item in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip().lower() or f"file_{index + 1}"
        key = re.sub(r"[^a-z0-9_]", "_", key)[:32]
        if not KEY_RE.match(key):
            key = f"file_{index + 1}"
        while key in seen:
            key = f"{key[:28]}_{index + 1}"
        seen.add(key)
        accept = item.get("accept") if item.get("accept") in FIELD_ACCEPT else "image"
        field_input = item.get("input") if item.get("input") in FIELD_INPUTS else "reference"
        fields.append({"key": key, "label": _text(item.get("label"), 80), "purpose": _text(item.get("purpose"), 200),
                       "accept": accept, "required": item.get("required", True) is not False, "input": field_input})
        if len(fields) >= MAX_FIELDS:
            break
    return fields


def clean_config(raw, block_type):
    raw = raw if isinstance(raw, dict) else {}
    if block_type not in BLOCK_TYPES:
        raise BlockError("invalid_block_type")
    generation = "video" if block_type == "video" else (raw.get("generation") if raw.get("generation") in ("image", "video") else "image")
    ref_mode = raw.get("ref_mode") if raw.get("ref_mode") in REF_MODES else ("C" if block_type in ("photo", "style") else "")
    placements = [p for p in (raw.get("placements") or []) if p in PLACEMENTS and block_type in PLACEMENTS[p]["types"]]
    config = {
        "generation": generation,
        "ref_mode": ref_mode if block_type in ("photo", "style") else "",
        "fields": clean_fields(raw.get("fields")),
        # No placements given: the type's own catalog. An explicit empty
        # list stays empty (and blocks publishing).
        "placements": placements if "placements" in raw else [DEFAULT_PLACEMENT[block_type]],
        "aspect": _text(raw.get("aspect"), 12),
        "duration": max(0, min(int(raw.get("duration") or 0), 60)) if str(raw.get("duration") or "0").isdigit() else 0,
        "resolution": _text(raw.get("resolution"), 12),
        "extra_references": [u for u in (raw.get("extra_references") or []) if isinstance(u, str) and u][:4],
    }
    return config


# ------------------------------------------------------------ models

def _label(model_id):
    """"seedream_5_0_pro" -> "Seedream 5.0 Pro", "kling_o3_omni" -> "Kling O3 Omni"."""
    words = []
    for part in str(model_id).split("_"):
        if part in ("gpt", "tts", "ai"):
            words.append(part.upper())
        elif re.match(r"^[a-z]\d", part):
            words.append(part.upper())
        else:
            words.append(part.capitalize())
    return re.sub(r"(?<=\d) (?=\d)", ".", " ".join(words))


MODEL_STATUSES = ("available", "turned_off", "no_keys")


def model_catalog(capabilities, *, seedream=None, labels=None, providers=None, status=None):
    """The image and video models a block can use, with what they accept:
    [{id, label, generation, provider, accepts_images, max_images,
    accepts_video, start_frame, ratios, durations, resolutions, status,
    available}]. Every model comes from the same capability registry the
    apps generate with, so it is "available" unless `status` (model id ->
    one of MODEL_STATUSES) says an admin turned it off or its provider's
    keys are missing. `providers` names the provider of models the
    registry lists without one (image models)."""
    seedream = seedream or {}
    labels = labels or {}
    providers = providers or {}
    status = status or {}
    out = []
    for model_id, cap in sorted(capabilities.items()):
        category = cap.get("category")
        if category not in ("image", "video"):
            continue
        visual = ((cap.get("character") or {}).get("visual_reference") or {})
        inputs = cap.get("reference_inputs") or {}
        if category == "image":
            accepts = visual.get("visual_mode") not in (None, "unsupported")
            max_images = int((seedream.get(model_id) or {}).get("max_references") or 0) or (DEFAULT_IMAGE_REFERENCES if accepts else 0)
            accepts_video = False
        else:
            slots = inputs.get("image_slots")
            max_images = DEFAULT_IMAGE_REFERENCES if slots is None else int(slots or 0)
            if cap.get("start_frame") and not max_images:
                max_images = 1
            accepts = max_images > 0
            accepts_video = bool(inputs.get("accepts_video") or cap.get("video_input") or cap.get("motion_reference"))
        if cap.get("avatar"):
            continue
        state = status.get(model_id) if status.get(model_id) in MODEL_STATUSES else "available"
        out.append({
            "id": model_id, "label": labels.get(model_id) or cap.get("label") or _label(model_id), "generation": category,
            "provider": cap.get("provider") or providers.get(model_id) or "", "accepts_images": accepts, "max_images": max_images,
            "accepts_video": accepts_video, "start_frame": bool(cap.get("start_frame")),
            "ratios": list(cap.get("ratios") or []), "durations": list(cap.get("durations") or []),
            "resolutions": list(cap.get("resolutions") or []), "status": state, "available": state == "available",
        })
    return out


# ------------------------------------------------------------ checks

def own_images(block):
    """The admin's images that go to the model (mode A / C, styles' extra
    references, the cover when it is the only image)."""
    config = block.get("config") or {}
    source = block.get("source_url") or ""
    images = []
    if block.get("block_type") in ("photo", "style") and config.get("ref_mode") in ("A", "C"):
        images.append(source or block.get("preview_url") or "")
    images += list(config.get("extra_references") or [])
    return [u for u in images if u]


def problems(block, models):
    """What keeps the block from being published, as (code, detail) pairs."""
    out = []
    config = block.get("config") or {}
    btype = block.get("block_type")
    fields = config.get("fields") or []
    if not (block.get("name") or "").strip():
        out.append(("name_required", ""))
    if not (block.get("preview_url") or "").strip():
        out.append(("cover_required", ""))
    model = next((m for m in models if m["id"] == block.get("model")), None)
    if not block.get("model"):
        out.append(("model_required", ""))
    elif not model:
        out.append(("model_unknown", block.get("model")))
    elif model["generation"] != config.get("generation"):
        out.append(("model_wrong_type", model["generation"]))
    elif model.get("status") == "no_keys":
        out.append(("model_no_keys", model["id"]))
    for field in fields:
        if not field.get("label"):
            out.append(("field_label_required", field["key"]))
    prompt = (block.get("prompt") or "").strip()
    if btype in ("tool", "style") and not prompt:
        out.append(("prompt_required", ""))
    if btype == "photo" and config.get("ref_mode") in ("B", "C") and not prompt:
        out.append(("prompt_required", config.get("ref_mode")))
    if btype in ("tool", "video", "photo", "style") and not any(f.get("required") for f in fields):
        out.append(("upload_field_required", ""))
    if btype == "photo" and config.get("ref_mode") in ("A", "C") and not (block.get("source_url") or block.get("preview_url")):
        out.append(("reference_image_required", config.get("ref_mode")))
    if btype == "video":
        if not block.get("source_url"):
            out.append(("reference_video_required", ""))
        if model and not model["accepts_video"]:
            out.append(("model_no_video_input", model["id"]))
    if any(f["accept"] == "video" for f in fields) and model and not model["accepts_video"]:
        out.append(("model_no_video_input", model["id"]))
    if model:
        images = len(own_images(block)) + len([f for f in fields if f["accept"] == "image"])
        if images and not model["accepts_images"]:
            out.append(("model_no_image_input", model["id"]))
        elif model["max_images"] and images > model["max_images"]:
            out.append(("too_many_images", str(model["max_images"])))
        if any(f.get("input") == "start_image" for f in fields) and not model["start_frame"] and model["generation"] == "video":
            out.append(("model_no_start_frame", model["id"]))
    if not config.get("placements"):
        out.append(("placement_required", ""))
    return out


# ------------------------------------------------------------ running

def generation_payload(block, uploads):
    """The Pro Studio generation request for this block and the user's
    uploads ({field key: signed media URL}). Mode A sends the admin's image
    as a reference with a fixed instruction, B only the prompt, C both."""
    config = block.get("config") or {}
    fields = config.get("fields") or []
    missing = [f["key"] for f in fields if f.get("required") and not uploads.get(f["key"])]
    if missing:
        raise BlockError("upload_required", 400, [("upload_required", k) for k in missing])
    user_images = [uploads[f["key"]] for f in fields if f["accept"] == "image" and f.get("input") != "start_image" and uploads.get(f["key"])]
    start_images = [uploads[f["key"]] for f in fields if f["accept"] == "image" and f.get("input") == "start_image" and uploads.get(f["key"])]
    user_videos = [uploads[f["key"]] for f in fields if f["accept"] == "video" and uploads.get(f["key"])]
    prompt = (block.get("prompt") or "").strip()
    if block.get("block_type") == "photo" and config.get("ref_mode") == "A" and not prompt:
        prompt = DEFAULT_A_PROMPT
    model = block.get("model") or ""
    base = {"prompt": prompt, "model": model, "media_block_id": block.get("id"),
            "source": "media_block"}
    if config.get("generation") == "video":
        reference_video = block.get("source_url") or (user_videos[0] if user_videos else "")
        images = user_images
        template = {
            "id": f"media_block_{block.get('id')}", "title": block.get("name") or "", "prompt": prompt,
            "reference_video": reference_video, "preview_video": block.get("source_url") or "",
            "poster_url": block.get("preview_url") or "", "aspect_ratio": config.get("aspect") or "9:16",
            "duration": config.get("duration") or 5, "resolution": config.get("resolution") or "720p",
            "preferred_model": model, "catalog_type": "video_template", "input_count": max(1, len(images)),
            "character_orientation": "image",
        }
        options = {
            "model": model, "ratio": template["aspect_ratio"], "duration": template["duration"],
            "resolution": template["resolution"], "reference_images": images, "referenceImageUrls": images,
            "video_template": template if block.get("block_type") == "video" else {},
        }
        if block.get("block_type") != "video" and reference_video:
            options["input_video"] = reference_video
        if start_images:
            options["start_image"] = start_images[0]
            options["image_url"] = start_images[0]
        elif images:
            options["image_url"] = images[0]
            options["character_image"] = images[0]
        return dict(base, mode="video", category="video", video_options=options)
    references = own_images(block) + user_images
    options = {"model": model, "modelId": model, "referenceImageUrls": references, "referenceImages": references}
    if config.get("aspect"):
        options["aspect_ratio"] = config["aspect"]
        options["aspectRatio"] = config["aspect"]
    return dict(base, mode="image", category="image", image_options=options)


def preview_uploads(block):
    """Placeholder uploads, only for pricing a block before anyone runs it."""
    return {f["key"]: f"https://sylvex.invalid/preview/{f['key']}" for f in (block.get("config") or {}).get("fields") or []}


def public_view(block, cost):
    """What the apps get for a published block (no internal notes)."""
    config = block.get("config") or {}
    return {
        "id": block["id"], "block_type": block.get("block_type"), "name": block.get("name") or "",
        "description": block.get("description") or "", "preview_url": block.get("preview_url") or "",
        "source_url": block.get("source_url") if block.get("block_type") == "video" else "",
        "generation": config.get("generation"), "model": block.get("model") or "",
        "fields": [{k: f[k] for k in ("key", "label", "purpose", "accept", "required")} for f in config.get("fields") or []],
        "placements": config.get("placements") or [], "aspect": config.get("aspect") or "", "cost": cost,
    }


# ------------------------------------------------------------ catalogs
# Published blocks join the catalogs the apps already show (Pro Studio's
# video templates and photo catalog, the website's Media page), in each
# catalog's own item format. `media_block` tells the apps to open the block
# runner (webapp/js/media-blocks.js) instead of their own flow.

def as_video_template(view):
    return {
        "id": f"media_block_{view['id']}", "title": view["name"], "description": view["description"],
        "prompt": "", "preview_video": view.get("source_url") or "", "reference_video": view.get("source_url") or "",
        "poster_url": view["preview_url"], "aspect_ratio": view.get("aspect") or "9:16",
        "preferred_model": view["model"], "cost_credits": view["cost"] or 0, "catalog_type": "video_template",
        "input_count": max(1, len([f for f in view["fields"] if f["accept"] == "image"])),
        "source": "media_block", "media_block": view,
    }


def as_quick_item(view):
    return {"id": f"media_block_{view['id']}", "title": view["name"], "description": view["description"],
            "prompt": "", "image_url": view["preview_url"], "source": "media_block", "media_block": view}


def join_catalogs(views, video_templates=None, quick_catalog=None):
    """The catalog responses with the published blocks of their places."""
    placed = lambda place: [v for v in views if place in (v.get("placements") or [])]
    if video_templates is not None:
        return [as_video_template(v) for v in placed("video_styles")] + list(video_templates)
    catalog = dict(quick_catalog or {})
    catalog["references"] = [as_quick_item(v) for v in placed("photo_references")] + list(catalog.get("references") or [])
    catalog["styles"] = [as_quick_item(v) for v in placed("image_styles")] + list(catalog.get("styles") or [])
    return catalog

