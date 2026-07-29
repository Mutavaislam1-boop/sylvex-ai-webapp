import unittest

from services.character_prompts import (
    GLOBAL_CHARACTER_RULE,
    OPERATION_PROMPTS,
    build_character_prompt,
    infer_character_operation,
)


class CharacterPromptTests(unittest.TestCase):
    def test_all_supported_operations_have_prompts(self):
        self.assertEqual(
            set(OPERATION_PROMPTS),
            {
                "text_to_image", "reference_to_image", "image_to_image_scene",
                "character_replace_image", "text_to_video", "image_to_video",
                "reference_to_video", "video_character_replace", "video_scene_transfer",
                "style_change_image", "style_change_video", "outfit_change_image",
                "outfit_change_video",
            },
        )

    def test_assembly_order_and_replacement_guard(self):
        result = build_character_prompt("character_replace_image", "IDENTITY", "USER SCENE")
        self.assertNotIn("IDENTITY", result)
        self.assertLess(result.index(OPERATION_PROMPTS["character_replace_image"]), result.index("USER SCENE"))
        self.assertIn(GLOBAL_CHARACTER_RULE, result)
        self.assertIn("Do not create a second character", result)

    def test_inference(self):
        self.assertEqual(infer_character_operation("image"), "text_to_image")
        self.assertEqual(
            infer_character_operation("image", has_source_image=True),
            "reference_to_image",
        )
        self.assertEqual(
            infer_character_operation("video", has_source_video=True),
            "video_character_replace",
        )
        self.assertEqual(
            infer_character_operation("video", style="cinematic"),
            "style_change_video",
        )


if __name__ == "__main__":
    unittest.main()
