"""Strict prompt assembly for persistent SYLVEX characters."""

OPERATION_PROMPTS = {
    "text_to_image": (
        "Create a new image using the person shown in the selected avatar and three character "
        "reference images. Treat those four images as the only source for the character. The "
        "user request controls only the scene and action."
    ),
    "reference_to_image": (
        "Replace the person in the uploaded image with the person shown in the selected avatar "
        "and three character reference images. Preserve the uploaded image's pose, clothing, "
        "background, objects, lighting, framing, and spatial arrangement. Change only the person."
    ),
    "image_to_image_scene": (
        "Use the uploaded image as the exact scene and place the person shown in the selected "
        "avatar and three character reference images into it. Preserve the composition, objects, "
        "perspective, camera, lighting, and spatial arrangement."
    ),
    "character_replace_image": (
        "Replace the main person in the uploaded image with the person shown in the selected "
        "avatar and three character reference images. Preserve pose, expression, clothing, "
        "framing, objects, background, lighting, and camera. Do not create an additional person."
    ),
    "text_to_video": (
        "Create a new video using the person shown in the selected avatar and three character "
        "reference images. Treat those four images as the only source for the character in every "
        "frame. The user request controls only the scene and action."
    ),
    "image_to_video": (
        "Animate the uploaded image using the person shown in the selected avatar and three "
        "character reference images. Preserve the source image's clothing, background, "
        "composition, and objects. Add only the requested movement."
    ),
    "reference_to_video": (
        "Use the uploaded image as the scene and create a video with the person shown in the "
        "selected avatar and three character reference images. Preserve composition, pose, "
        "clothing, objects, environment, camera, and lighting throughout all frames."
    ),
    "video_character_replace": (
        "Replace the main person in the uploaded video with the person shown in the selected "
        "avatar and three character reference images. Preserve movement, expression, pose, "
        "clothing, timing, camera, background, objects, and their interactions in every frame."
    ),
    "video_scene_transfer": (
        "Use the uploaded video as the exact motion and composition source. Replace its main "
        "person with the person shown in the selected avatar and three character reference images. "
        "Preserve movement, expression, pose, clothing, timing, camera, background, and all objects."
    ),
    "style_change_image": (
        "Apply only the requested visual style. Use the selected avatar and three character "
        "reference images as the only source for the person, and preserve pose and composition."
    ),
    "style_change_video": (
        "Apply only the requested visual style. Use the selected avatar and three character "
        "reference images as the only source for the person, and preserve movement and timing."
    ),
    "outfit_change_image": (
        "Use the selected avatar and three character reference images as the only source for the "
        "person. Preserve the pose and scene. Change only the clothing requested by the user."
    ),
    "outfit_change_video": (
        "Use the selected avatar and three character reference images as the only source for the "
        "person. Preserve movement, pose, and scene. Change only the clothing requested by the user."
    ),
}

REPLACEMENT_OPERATIONS = {
    "reference_to_image", "character_replace_image", "video_character_replace", "video_scene_transfer"
}

GLOBAL_CHARACTER_RULE = (
    "Use only the selected avatar and three character reference images to determine the person. "
    "Do not infer the person from any textual character description."
)


def infer_character_operation(media: str, requested: str = "", has_source_image: bool = False,
                              has_source_video: bool = False, style: str = "") -> str:
    requested = str(requested or "").strip().lower()
    if requested in OPERATION_PROMPTS:
        return requested
    media = str(media or "").strip().lower()
    if style and str(style).lower() not in {"", "auto"}:
        return "style_change_video" if media == "video" else "style_change_image"
    if media == "video":
        if has_source_video:
            return "video_character_replace"
        if has_source_image:
            return "image_to_video"
        return "text_to_video"
    return "reference_to_image" if has_source_image else "text_to_image"


def build_character_prompt(operation: str, character_prompt: str, user_prompt: str) -> str:
    # character_prompt is intentionally ignored for backward compatibility with old clients.
    parts = [OPERATION_PROMPTS.get(operation, ""), str(user_prompt or "").strip(), GLOBAL_CHARACTER_RULE]
    if operation in REPLACEMENT_OPERATIONS:
        parts.append(
            "Do not create a second character. Do not change the scene unless explicitly requested."
        )
    return "\n\n".join(part for part in parts if part)
