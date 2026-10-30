"""The catalog's selective base-video edit, separate from Motion Control."""


def is_catalog_video_edit(options: dict) -> bool:
    template = options.get("video_template")
    if not isinstance(template, dict) or not template:
        return False
    mode = str(options.get("generation_mode") or options.get("mode") or "").lower()
    return (
        mode in {"video_edit", "video edit", "edit"}
        and template.get("catalog_type", "video_template") == "video_template"
        and not template.get("is_kling_effect")
    )


def replacement_prompt(template: dict) -> str:
    # Catalog titles/descriptions are discovery copy, never creative directions.
    target = str(template.get("replacement_target") or "the main foreground character or object").strip()[:180]
    refinement = str(template.get("user_prompt") or "").strip()[:1200]
    instruction = (
        f"Edit the original @video_1: replace only {target} with the identity/appearance in @image_1. "
        "Keep this identity consistent through all frames, including face, head shape, age, skin, eyes, and hair. "
        "Preserve the source actions, gestures, expressions, blinking, object interactions, and their timing. "
        "Keep all other people, objects, background, lighting, shadows, colors, composition, camera movement, "
        "event sequence, speed, full duration, and original audio unchanged as closely as possible. "
        "Do not animate the photo into a new scene, restyle the scene, add events, or trim the source video."
    )
    return instruction + ("\nUser refinement (only within this selective edit): " + refinement if refinement else "")
