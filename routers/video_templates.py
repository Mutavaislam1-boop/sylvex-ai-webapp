from pathlib import Path
from fastapi import APIRouter, HTTPException, Body

from services.video_templates import (
    get_all_templates,
    get_template,
)
from services.video_router import video_generation

router = APIRouter(
    prefix="/api/public/video/templates",
    tags=["Video Templates"]
)


@router.get("")
async def list_templates():
    return get_all_templates()


@router.get("/{template_id}")
async def template_info(template_id: str):
    template = get_template(template_id)

    if template is None:
        raise HTTPException(
            status_code=404,
            detail="Template not found"
        )

    return template


# Новый POST-эндпоинт: генерация видео по шаблону (точка входа для Template → Video)
@router.post("/{template_id}/generate")
async def generate_video_from_template(template_id: str, body: dict = Body(...)):
    template = get_template(template_id)
    if template is None:
        raise HTTPException(
            status_code=404,
            detail="Template not found"
        )
    base_dir = Path(__file__).resolve().parent.parent / "webapp"
    folder = base_dir / "video-templates" / template_id
    if not folder.exists():
        slot = str(template.get("slot") or template_id).replace("builtin_video_template_", "").zfill(2)
        folder = base_dir / "assets" / "video-templates" / slot

    preview_path = folder / "preview.mp4"
    poster_path = folder / "poster.jpg"
    prompt_path = folder / "prompt.txt"

    if not prompt_path.exists():
        template_prompt = (template.get("prompt") or template.get("video_prompt") or template.get("description") or template.get("title") or "").strip()
    else:
        with open(prompt_path, "r", encoding="utf-8") as f:
            template_prompt = f.read().strip()

    if not template_prompt:
        raise HTTPException(status_code=400, detail="Template prompt is empty")

    user_prompt = (body.get("prompt") or "").strip()
    final_prompt = (
        f"{template_prompt}\n\n{user_prompt}" if user_prompt else template_prompt
    )
    user_photo = body.get("photo") or body.get("image") or body.get("start_image") or body.get("image_url")
    if not user_photo:
        raise HTTPException(status_code=400, detail="User image is required")
    ratio = str(body.get("ratio") or template.get("aspect_ratio") or "16:9")
    if ratio not in {"16:9", "1:1", "9:16"}:
        ratio = "16:9"
    model = body.get("model") or template.get("preferred_model") or "kling_3_0_turbo"

    package = {
        "mode": "video",
        "category": "video",
        "provider": body.get("provider", "kling"),
        "model": model,
        "prompt": final_prompt,
        "template_id": template_id,
        "template": template,
        "preview_video": str(preview_path) if preview_path.exists() else "",
        "poster": str(poster_path),
        "user_photo": body.get("photo"),
        "template_prompt": template_prompt,
        "final_prompt": final_prompt,
        "video_options": {
            "section": "generate",
            "generation_mode": "image_to_video",
            "mode": "image_to_video",
            "ratio": ratio,
            "resolution": body.get("resolution") or template.get("resolution") or "720p",
            "duration": int(body.get("duration") or template.get("duration") or 5),
            "sound": bool(body.get("sound", False)),
            "start_image": user_photo,
            "video_template": {
                "id": template_id,
                "title": template.get("title") or template_id,
                "prompt": template_prompt,
                "preview_video": str(preview_path) if preview_path.exists() else "",
                "aspect_ratio": ratio,
                "catalog_type": "video_template",
            },
            "model": model,
        },
    }

    result = await video_generation(package)
    return result
