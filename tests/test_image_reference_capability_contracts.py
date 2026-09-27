"""No-provider-call contracts for model references shaped by the real composer."""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

import main


class FakeResponse:
    status_code = 200
    text = "{}"

    def __init__(self, data=None):
        self._data = data or {"data": [{"url": "https://result.example/output.png"}]}
        self.text = json.dumps(self._data)

    def json(self):
        return self._data


def frontend_payload(model_id, provider, references):
    """Mirror cabinet.js imageOptionsPayload and image generation request."""
    refs = list(references)
    return {
        "mode": "image",
        "provider": provider,
        "model": model_id,
        "prompt": "Use all uploaded references in order.",
        "image_options": {
            "modelId": model_id,
            "model": model_id,
            "referenceImageUrls": refs,
            "referenceImages": refs[:],
            "characterReferences": [],
            "objectReferences": [],
            "size": "1:1",
            "count": 1,
        },
    }


EXPECTED_REFERENCE_CONTRACTS = {
    "ideogram_3_0": (3, "style_reference_images", "/v1/ideogram-v3/generate"),
    "ideogram_4_0": (1, "image", "/v1/ideogram-v4/remix"),
    "recraft_v3": (1, "image", "/v1/images/imageToImage"),
    "recraft_v4_1": (1, "image", "/v1/images/imageToImage"),
    "recraft_v4_1_pro": (1, "image", "/v1/images/imageToImage"),
    "recraft_v4_1_pro_vector": (10, "style_reference_urls", "/v1/images/generations/vector"),
    "seedream_4_0": (10, "image", "/images/generations"),
    "seedream_4_5": (10, "image", "/images/generations"),
    "seedream_5_0": (10, "image", "/images/generations"),
    "seedream_5_0_lite": (10, "image", "/images/generations"),
    "seedream_5_0_pro": (10, "image", "/images/generations"),
    "gpt_image_1": (10, "image[]", "/images/edits"),
    "gpt_image_2": (10, "image[]", "/images/edits"),
    "gpt_image_2_5_sunburst": (10, "image[]", "/images/edits"),
    "gpt-image-2.5-sunburst": (10, "image[]", "/images/edits"),
    "flux_pro_kontext": (4, "input_image, input_image_2..input_image_4", "/flux-kontext-pro"),
    "flux_2": (8, "input_image, input_image_2..input_image_8", "/flux-2-pro"),
    "flux_2_turbo": (8, "input_image, input_image_2..input_image_8", "/flux-2-flex"),
    "qwen_image": (3, "input.messages[0].content[].image", "/multimodal-generation/generation"),
    "qwen_image_2": (3, "input.messages[0].content[].image", "/multimodal-generation/generation"),
    "qwen_image_2_pro": (3, "input.messages[0].content[].image", "/multimodal-generation/generation"),
    "nano_banana_pro": (10, "input[].data (type=image)", "/v1beta/interactions"),
    "nano_banana_2": (10, "input[].data (type=image)", "/v1beta/interactions"),
    "nano_banana_2_lite": (10, "input[].data (type=image)", "/v1beta/interactions"),
    "nano_banana": (3, "input[].data (type=image)", "/v1beta/interactions"),
    "gemini-3.1-flash-image": (10, "input[].data (type=image)", "/v1beta/interactions"),
    "gemini-3.1-flash-lite-image": (10, "input[].data (type=image)", "/v1beta/interactions"),
    "gemini-3-pro-image": (10, "input[].data (type=image)", "/v1beta/interactions"),
    "gemini-2.5-flash-image": (3, "input[].data (type=image)", "/v1beta/interactions"),
    "grok_pro": (5, "image.url + image.type; images[].url + images[].type", "/images/edits"),
    "grok": (5, "image.url + image.type; images[].url + images[].type", "/images/edits"),
    "grok_imagine_image_quality": (5, "image.url + image.type; images[].url + images[].type", "/images/edits"),
    "grok_imagine_image": (5, "image.url + image.type; images[].url + images[].type", "/images/edits"),
    "imagen_4_fast": (0, None, ""),
    "imagen_4_standard": (0, None, ""),
    "imagen_4_ultra": (0, None, ""),
    "imagen-4.0-fast-generate-001": (0, None, ""),
    "imagen-4.0-generate-001": (0, None, ""),
    "imagen-4.0-ultra-generate-001": (0, None, ""),
    "krea_2": (0, None, ""),
    "microsoft_mai_image_2_5": (0, None, ""),
}


class ImageReferenceCapabilityContracts(unittest.TestCase):
    def test_every_selectable_mapped_model_has_a_valid_reference_contract(self):
        selectable = set(main.IMAGE_PROVIDER_MODEL_MAP) | {"krea_2", "microsoft_mai_image_2_5"}
        self.assertEqual(selectable, set(main.IMAGE_REFERENCE_CAPABILITY_MATRIX))
        self.assertEqual(selectable, set(EXPECTED_REFERENCE_CONTRACTS))
        for model_id in sorted(selectable):
            with self.subTest(model=model_id):
                mapping = main.IMAGE_PROVIDER_MODEL_MAP.get(model_id) or {}
                caps = main.image_reference_capabilities(model_id, mapping.get("provider_model", ""))
                self.assertIn("supports_references", caps)
                self.assertIn("max_references", caps)
                self.assertIn("endpoint", caps)
                self.assertIn("reference_param", caps)
                self.assertGreaterEqual(caps["max_references"], 0)
                self.assertLessEqual(caps["max_references"], 10)
                self.assertEqual(caps["supports_references"], caps["max_references"] > 0)
                self.assertEqual(bool(caps["reference_param"]), caps["supports_references"])
                self.assertNotIn("{model}", caps["endpoint"])
                expected_limit, expected_param, expected_endpoint_suffix = EXPECTED_REFERENCE_CONTRACTS[model_id]
                self.assertEqual(caps["max_references"], expected_limit)
                self.assertEqual(caps["reference_param"], expected_param)
                if expected_endpoint_suffix:
                    self.assertTrue(caps["endpoint"].endswith(expected_endpoint_suffix), caps["endpoint"])
                else:
                    self.assertEqual(caps["endpoint"], "")
                if model_id.startswith("imagen"):
                    self.assertEqual(caps["endpoint_status"], "retired")

                refs = [f"https://uploads.example/{model_id}-{index}.png" for index in range(min(2, caps["max_references"]))]
                payload = frontend_payload(model_id, mapping.get("provider", ""), refs)
                self.assertEqual(main.image_reference_urls(payload), refs)
                self.assertIsNone(main.validate_image_reference_count(model_id, mapping.get("provider_model", ""), refs))
                too_many = [f"https://uploads.example/{model_id}-over-{index}.png" for index in range(caps["max_references"] + 1)]
                self.assertIsNotNone(main.validate_image_reference_count(model_id, mapping.get("provider_model", ""), too_many))

    def test_retired_imagen_models_have_no_active_capability_endpoint(self):
        caps = main.image_reference_capabilities("imagen_4_fast", "imagen-4.0-fast-generate-001")
        self.assertEqual(caps["endpoint"], "")
        self.assertEqual(caps["endpoint_status"], "retired")

    def test_capabilities_api_returns_the_shared_matrix(self):
        with patch.object(main, "IMAGE_MODELS_JSON", json.dumps({"models": [
            {"id": "flux_2", "api_model": "flux-2-pro", "provider": "flux"},
        ]})):
            response = main.get_image_capabilities()
        self.assertEqual(response["reference_capabilities"], main.get_image_reference_capability_matrix())
        self.assertEqual(response["models"][0]["supports_references"], True)
        self.assertEqual(response["models"][0]["max_references"], 8)
        for item in response["models"]:
            self.assertIn("supports_references", item)
            self.assertIn("max_references", item)

    def test_flux2_sends_all_references_as_numbered_input_image_fields(self):
        refs = ["https://uploads.example/source.png", "https://uploads.example/style.png"]
        payload = frontend_payload("flux_2", "flux", refs)
        with patch.object(main, "flux_headers", return_value={"x-key": "test"}), \
             patch.object(main.requests, "post", return_value=FakeResponse({"polling_url": "https://poll.example/task"})) as post, \
             patch.object(main, "poll_flux_image", return_value=([], {})):
            main.call_flux_image("flux_2", "flux-2-pro", "https://api.bfl.ai/v1", "prompt", payload, "1:1")
        body = post.call_args.kwargs["json"]
        self.assertEqual([body["input_image"], body["input_image_2"]], refs)
        self.assertTrue(post.call_args.args[0].endswith("/flux-2-pro"))

    def test_qwen_sends_all_references_as_ordered_image_content_parts(self):
        refs = ["https://uploads.example/source.png", "https://uploads.example/style.png"]
        payload = frontend_payload("qwen_image_2", "qwen", refs)
        with patch.object(main, "qwen_headers", return_value={"Authorization": "Bearer test"}), \
             patch.object(main.requests, "post", return_value=FakeResponse()) as post:
            main.call_qwen_image("qwen_image_2", "qwen-image-2.0", "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation", "prompt", payload, "1:1")
        body = json.loads(post.call_args.kwargs["data"])
        parts = body["input"]["messages"][0]["content"]
        self.assertEqual([part["image"] for part in parts if "image" in part], refs)

    def test_grok_uses_edit_endpoint_and_sends_all_references(self):
        refs = ["https://uploads.example/source.png", "https://uploads.example/style.png"]
        payload = frontend_payload("grok", "grok", refs)
        with patch.object(main, "grok_headers", return_value={"Authorization": "Bearer test"}), \
             patch.object(main.requests, "post", return_value=FakeResponse()) as post:
            main.call_grok_image("grok", "grok-imagine-image", "https://api.x.ai/v1/images/generations", "prompt", payload, "1:1")
        self.assertTrue(post.call_args.args[0].endswith("/images/edits"))
        self.assertEqual([item["url"] for item in post.call_args.kwargs["json"]["images"]], refs)

    def test_google_interactions_payload_keeps_all_image_parts(self):
        refs = ["https://uploads.example/source.png", "https://uploads.example/style.png"]
        payload = frontend_payload("nano_banana_2", "google", refs)
        image_part = {"type": "image", "mime_type": "image/png", "data": "cG5n"}
        with patch.object(main, "google_image_headers", return_value={"x-goog-api-key": "test"}), \
             patch.object(main, "google_local_or_remote_image_part", return_value=image_part), \
             patch.object(main.requests, "post", return_value=FakeResponse()) as post:
            main.call_google_image("nano_banana_2", "gemini-3.1-flash-image", "https://generativelanguage.googleapis.com/v1beta/interactions", "prompt", payload, "1:1")
        body = json.loads(post.call_args.kwargs["data"])
        self.assertEqual(body["input"], [{"type": "text", "text": "prompt"}, image_part, image_part])

    def test_ideogram3_sends_every_style_reference_file(self):
        refs = ["https://uploads.example/source.png", "https://uploads.example/style.png"]
        payload = frontend_payload("ideogram_3_0", "ideogram", refs)
        file_part = ("image[]", ("reference.png", b"png", "image/png"))
        with patch.object(main, "ideogram_headers", return_value={"Api-Key": "test"}), \
             patch.object(main, "openai_image_reference_file", return_value=file_part), \
             patch.object(main.requests, "post", return_value=FakeResponse()) as post:
            main.call_ideogram_image("ideogram_3_0", "ideogram-v3", "https://api.ideogram.ai/v1/ideogram-v3/generate", "prompt", payload, "1:1")
        sent = post.call_args.kwargs["files"]
        self.assertEqual([key for key, _value in sent if key == "style_reference_images"], ["style_reference_images"] * 2)

    def test_ideogram4_uses_remix_with_the_single_image_parameter(self):
        refs = ["https://uploads.example/source.png"]
        payload = frontend_payload("ideogram_4_0", "ideogram", refs)
        file_part = ("image[]", ("reference.png", b"png", "image/png"))
        with patch.object(main, "ideogram_headers", return_value={"Api-Key": "test"}), \
             patch.object(main, "openai_image_reference_file", return_value=file_part), \
             patch.object(main.requests, "post", return_value=FakeResponse()) as post:
            main.call_ideogram_image("ideogram_4_0", "ideogram-v4", "https://api.ideogram.ai/v1/ideogram-v4/generate", "prompt", payload, "1:1")
        self.assertTrue(post.call_args.args[0].endswith("/ideogram-v4/remix"))
        self.assertEqual([key for key, _value in post.call_args.kwargs["files"] if key == "image"], ["image"])

    def test_recraft_switches_to_image_to_image_and_sends_selected_image(self):
        refs = ["https://uploads.example/source.png"]
        payload = frontend_payload("recraft_v3", "recraft", refs)
        file_part = ("image[]", ("reference.png", b"png", "image/png"))
        with patch.object(main, "recraft_headers", return_value={"Authorization": "Bearer test"}), \
             patch.object(main, "openai_image_reference_file", return_value=file_part), \
             patch.object(main.requests, "post", return_value=FakeResponse()) as post:
            main.call_recraft_image("recraft_v3", "recraftv3", "https://external.api.recraft.ai/v1/images/generations", "prompt", payload, "1:1")
        self.assertTrue(post.call_args.args[0].endswith("/images/imageToImage"))
        self.assertEqual(post.call_args.kwargs["files"][0][0], "image")

    def test_recraft_vector_passes_all_style_urls_to_vector_generation(self):
        refs = ["https://uploads.example/style-a.png", "https://uploads.example/style-b.png"]
        payload = frontend_payload("recraft_v4_1_pro_vector", "recraft", refs)
        with patch.object(main, "recraft_headers", return_value={"Authorization": "Bearer test"}), \
             patch.object(main.requests, "post", return_value=FakeResponse()) as post:
            main.call_recraft_image("recraft_v4_1_pro_vector", "recraftv4_1_pro_vector", "https://external.api.recraft.ai/v1/images/generations/vector", "prompt", payload, "1:1")
        self.assertTrue(post.call_args.args[0].endswith("/images/generations/vector"))
        self.assertEqual(json.loads(post.call_args.kwargs["data"])["style_reference_urls"], refs)

    def test_openai_edits_endpoint_passes_every_multipart_image(self):
        refs = ["https://uploads.example/source.png", "https://uploads.example/style.png"]
        payload = frontend_payload("gpt_image_1", "openai", refs)
        file_part = ("image[]", ("reference.png", b"png", "image/png"))
        with patch.object(main, "OPENAI_API_KEY", "test"), \
             patch.object(main, "openai_image_reference_file", return_value=file_part), \
             patch.object(main.requests, "post", return_value=FakeResponse()) as post, \
             patch.object(main, "finalize_image_result", new=AsyncMock(return_value={"ok": True, "images": ["https://result.example/output.png"]})):
            result = asyncio.run(main.image_generation(payload))
        self.assertTrue(result["ok"])
        self.assertTrue(post.call_args.args[0].endswith("/images/edits"))
        files = post.call_args.kwargs["files"]
        self.assertEqual(len(files), len(refs))
        self.assertEqual([key for key, _value in files], ["image[]", "image[]"])


if __name__ == "__main__":
    unittest.main()
