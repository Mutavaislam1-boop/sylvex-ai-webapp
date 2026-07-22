from fastapi import APIRouter, HTTPException

from services.video_templates import (
    get_all_templates,
    get_template,
)

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