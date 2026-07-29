"""Strict prompt assembly for persistent SYLVEX characters."""

OPERATION_PROMPTS = {
    "text_to_image": (
        "Create a new image using the selected character exactly as defined. Preserve the "
        "character's identity, face, hairstyle, hair color, eye color, skin tone, body "
        "proportions, makeup, clothing, accessories, and overall appearance without any "
        "changes. Apply only the scene, action, pose, environment, camera, and lighting "
        "described by the user."
    ),
    "reference_to_image": (
        "Integrate the selected character into the uploaded image. If a person is present, "
        "replace that person with the selected character while preserving the original pose, "
        "body position, composition, camera angle, objects, clothing placement, lighting, "
        "shadows, background, and scene structure. Change only the person's identity."
    ),
    "image_to_image_scene": (
        "Use the uploaded image as the exact scene reference and place the selected character "
        "into it. Preserve the original composition, environment, objects, perspective, camera "
        "angle, lighting, and spatial arrangement. Do not redesign or recreate the scene."
    ),
    "character_replace_image": (
        "Replace the main person in the uploaded image with the selected character. Preserve "
        "the original pose, gesture, facial direction, body position, framing, clothing shape, "
        "interaction with objects, background, lighting, and camera perspective. Do not create "
        "an additional person."
    ),
    "text_to_video": (
        "Create a new video using the selected character exactly as defined. Preserve the "
        "character's identity, face, hairstyle, hair color, eye color, skin tone, body "
        "proportions, makeup, clothing, and accessories consistently in every frame. Apply only "
        "the action, scene, camera movement, environment, and lighting described by the user."
    ),
    "image_to_video": (
        "Animate the uploaded image while preserving the selected character's exact identity "
        "and appearance. Keep the face, hairstyle, hair color, eye color, skin tone, body "
        "proportions, clothing, accessories, background, composition, and objects consistent. "
        "Add only the movement described by the user."
    ),
    "reference_to_video": (
        "Use the uploaded image as the visual reference and create a video with the selected "
        "character integrated into the same scene. Preserve the original composition, pose, "
        "objects, clothing placement, environment, camera angle, and lighting. Keep the selected "
        "character consistent throughout all frames."
    ),
    "video_character_replace": (
        "Replace the main person in the uploaded video with the selected character. Preserve the "
        "original movement, pose, gestures, facial direction, timing, camera motion, clothing "
        "behavior, object interaction, lighting, background, and scene composition. Change only "
        "the person's identity and keep it stable in every frame."
    ),
    "video_scene_transfer": (
        "Use the uploaded video as the exact motion and composition reference. Replace the main "
        "person with the selected character while preserving the original movement, timing, pose, "
        "gestures, camera motion, framing, objects, environment, and lighting. Do not alter the "
        "scene unless explicitly requested by the user."
    ),
    "style_change_image": (
        "Apply the requested visual style to the image while preserving the selected character's "
        "exact identity, facial structure, hairstyle, hair color, eye color, skin tone, body "
        "proportions, clothing, accessories, pose, and composition. Change only the artistic style."
    ),
    "style_change_video": (
        "Apply the requested visual style to the video while preserving the selected character's "
        "exact identity, facial structure, hairstyle, hair color, eye color, skin tone, body "
        "proportions, clothing, movement, timing, and consistency in every frame. Change only the "
        "artistic style."
    ),
    "outfit_change_image": (
        "Keep the selected character's identity, face, hairstyle, hair color, eye color, skin tone, "
        "body proportions, makeup, pose, and scene unchanged. Replace only the clothing and "
        "accessories according to the user's request."
    ),
    "outfit_change_video": (
        "Keep the selected character's identity, face, hairstyle, hair color, eye color, skin tone, "
        "body proportions, makeup, movement, pose, and scene unchanged throughout the video. "
        "Replace only the clothing and accessories according to the user's request."
    ),
}

REPLACEMENT_OPERATIONS = {
    "reference_to_image", "character_replace_image", "video_character_replace", "video_scene_transfer"
}

GLOBAL_CHARACTER_RULE = (
    "The selected character defines the identity and default appearance. The user prompt controls "
    "only the scene, action, environment, camera, and lighting unless the user explicitly requests "
    "a permitted change."
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
    parts = [OPERATION_PROMPTS.get(operation, ""), str(character_prompt or "").strip(),
             str(user_prompt or "").strip(), GLOBAL_CHARACTER_RULE]
    if operation in REPLACEMENT_OPERATIONS:
        parts.append(
            "Do not create a second character. Do not change the scene unless explicitly requested."
        )
    return "\n\n".join(part for part in parts if part)
