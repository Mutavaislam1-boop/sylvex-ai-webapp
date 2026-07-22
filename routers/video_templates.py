from pathlib import Path
from fastapi import APIRouter, HTTPException, Body

from services.video_templates import (
    get_all_templates,
    get_template,
)
from services.video_generation import generate_video as generate_video_kling

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
    folder = Path(__file__).resolve().parent.parent / "webapp" / "video-templates" / template_id

    preview_path = folder / "preview.mp4"
    poster_path = folder / "poster.jpg"
    prompt_path = folder / "prompt.txt"

    if not preview_path.exists():
        raise HTTPException(status_code=404, detail="preview.mp4 not found")

    if not prompt_path.exists():
        raise HTTPException(status_code=404, detail="prompt.txt not found")

    with open(prompt_path, "r", encoding="utf-8") as f:
        template_prompt = f.read().strip()

    user_prompt = (body.get("prompt") or "").strip()
    final_prompt = (
        f"{template_prompt}\n\n{user_prompt}" if user_prompt else template_prompt
    )

    package = {
        "template_id": template_id,
        "template": template,
        "preview_video": str(preview_path),
        "poster": str(poster_path),
        "user_photo": body.get("photo"),
        "provider": body.get("provider", "kling"),
        "model": body.get("model"),
        "template_prompt": template_prompt,
        "final_prompt": final_prompt,
    }

    result = await generate_video_kling(package)
    return result