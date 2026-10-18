import ast
import io
import json
import re
import unittest
import urllib.parse
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from services.error_translator import raw_error_text, translate_provider_error


SOURCE = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
FUNCTIONS = [
    node for node in TREE.body
    if isinstance(node, ast.FunctionDef) and node.name in {"normalize_grid_video_request", "sylvex_text_policy"}
]
EVENTS = []
NAMESPACE = {
    "_VIDEO_MODEL_CONFIG": {
        "runway_gen4_5": {"modes": ["text_to_video", "image_to_video"]},
    },
    "prostudio_debug": lambda stage, **data: EVENTS.append((stage, data)),
    "SYLVEX_TEXT_LINK_GUIDANCE": "links",
    "sylvex_text_catalog": lambda value: {},
}
exec(compile(ast.Module(body=FUNCTIONS, type_ignores=[]), "main.py", "exec"), NAMESPACE)
normalize_grid_video_request = NAMESPACE["normalize_grid_video_request"]
sylvex_text_policy = NAMESPACE["sylvex_text_policy"]


class GridRequestContractTests(unittest.TestCase):
    def test_start_frame_is_not_repeated_as_reference_and_mode_is_reconciled(self):
        payload = {
            "grid_project_id": "grid-1", "grid_node_id": "video-1", "mode": "video",
            "model": "runway_gen4_5",
            "video_options": {
                "model": "runway_gen4_5", "generation_mode": "text_to_video",
                "start_image": "https://cdn.example/start.jpg",
                "end_image": "https://cdn.example/end.jpg",
                "reference_images": ["https://cdn.example/start.jpg", "https://cdn.example/ref.jpg"],
                "referenceImageUrls": ["https://cdn.example/end.jpg", "https://cdn.example/ref.jpg"],
            },
        }
        result = normalize_grid_video_request(payload)
        options = result["video_options"]
        self.assertEqual(options["generation_mode"], "image_to_video")
        self.assertEqual(options["mode"], "image_to_video")
        self.assertEqual(options["reference_images"], ["https://cdn.example/ref.jpg"])
        self.assertEqual(options["referenceImageUrls"], ["https://cdn.example/ref.jpg"])

    def test_non_grid_payload_is_untouched(self):
        payload = {"mode": "video", "model": "runway_gen4_5", "video_options": {
            "start_image": "same.jpg", "reference_images": ["same.jpg"],
        }}
        before = repr(payload)
        normalize_grid_video_request(payload)
        self.assertEqual(repr(payload), before)

    def test_grid_text_policy_requires_direct_artifact_without_preamble(self):
        policy = sylvex_text_policy({"grid_direct_output": True})
        self.assertIn("Return only the requested production artifact", policy)
        self.assertIn("Do not add introductions", policy)

    def test_direct_text_timeout_is_released_and_returned_as_504(self):
        self.assertIn("except requests.Timeout as exc:", SOURCE)
        timeout_block = SOURCE.split("except requests.Timeout as exc:", 1)[1].split("except requests.RequestException", 1)[0]
        self.assertIn("release_direct_text_generation(generation_id)", timeout_block)
        self.assertIn('"retryable": True', timeout_block)
        self.assertIn("status_code=504", timeout_block)


class AudioDiagnosticsTests(unittest.TestCase):
    def test_audio_provider_log_redacts_keys_and_keeps_status(self):
        audio_source = Path(__file__).resolve().parents[1].joinpath("services/audio_router.py").read_text(encoding="utf-8")
        audio_tree = ast.parse(audio_source)
        audio_function = next(node for node in audio_tree.body if isinstance(node, ast.FunctionDef) and node.name == "_audio_error")
        namespace = {
            "Any": Any, "re": re, "json": json, "urllib": urllib,
            "raw_error_text": raw_error_text, "translate_provider_error": translate_provider_error,
        }
        exec(compile(ast.Module(body=[audio_function], type_ignores=[]), "audio_router.py", "exec"), namespace)
        _audio_error = namespace["_audio_error"]
        out = io.StringIO()
        with redirect_stdout(out):
            result = _audio_error(
                "gemini", "google_lyria_3_clip", "lyria-3-clip-preview",
                {"error": {"code": "ACCOUNT_OVERDUE", "message": "failed key=secret-token"}},
                endpoint="https://generativelanguage.googleapis.com/v1beta/interactions?key=secret-token",
                status_code=403,
            )
        logged = out.getvalue()
        self.assertIn("AUDIO_PROVIDER_FAILURE", logged)
        self.assertIn('"status_code": 403', logged)
        self.assertIn("[redacted]", logged)
        self.assertNotIn("secret-token", logged)
        self.assertNotIn("secret-token", result["raw_error"])

    def test_account_overdue_has_a_clear_non_temporary_message(self):
        message = translate_provider_error({"error": "AccountOverdueError"}, provider="byteplus")
        self.assertIn("закончился баланс", message)


if __name__ == "__main__":
    unittest.main()
