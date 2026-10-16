import ast
import json
from pathlib import Path
import re
import requests
import time
import unittest


MAIN_SOURCE = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
MAIN_TREE = ast.parse(MAIN_SOURCE)
PLANNER_FUNCTIONS = [
    node for node in MAIN_TREE.body
    if isinstance(node, ast.FunctionDef) and node.name in {
        "grid_requested_duration_seconds", "clean_grid_plan",
        "grid_planner_retryable_result", "grid_planner_generation_with_fallback",
    }
]
PLANNER_NAMESPACE = {
    "re": re, "json": json, "requests": requests, "time": time,
    "GRID_TEXT_NODE_MODELS": ("gpt-5.6", "gpt-5.5"),
}
exec(compile(ast.Module(body=PLANNER_FUNCTIONS, type_ignores=[]), "main.py", "exec"), PLANNER_NAMESPACE)
grid_requested_duration_seconds = PLANNER_NAMESPACE["grid_requested_duration_seconds"]
clean_grid_plan = PLANNER_NAMESPACE["clean_grid_plan"]
grid_planner_generation_with_fallback = PLANNER_NAMESPACE["grid_planner_generation_with_fallback"]


CATALOG = {
    "text": {"models": ["gpt-5.6", "gpt-5.5"], "default": "gpt-5.6"},
    "image": {"models": ["gpt_image_2"], "capabilities": {"gpt_image_2": {"character_reference": True, "object_reference": True}}},
    "video": {"models": {"seedance_2_0": {"durations": list(range(4, 16)), "start_image": True}}},
    "music": {"models": ["google_lyria_3_clip"]},
    "voice": {"models": ["elevenlabs_eleven_v3"]},
    "montage": {"model": "final_montage"},
}


def video_plan(second_duration=30):
    return {
        "action": "plan",
        "title": "Sneaker commercial",
        "summary": "A continuous one-minute product story.",
        "reference_requests": [
            {
                "id": "sneaker_1",
                "kind": "product",
                "label": "Sneaker or brand",
                "used_by": ["video_1", "video_2"],
            }
        ],
        "nodes": [
            {
                "key": "shot_1_text",
                "type": "text",
                "title": "Opening prompt",
                "model": "gpt-5.6",
                "output": "Macro reveal of the exact sneaker, then a runner launches forward.",
            },
            {
                "key": "shot_2_text",
                "type": "text",
                "title": "Closing prompt",
                "model": "gpt-5.6",
                "output": "The same sneaker lands on a clean hero podium for the final packshot.",
            },
            {
                "key": "video_1",
                "type": "video",
                "title": "Opening shot",
                "model": "seedance_2_0",
                "reference_ids": ["sneaker_1"],
                "settings": {"duration": 10},
                "timeline": {"start": 0, "duration": 30, "order": 1},
            },
            {
                "key": "video_2",
                "type": "video",
                "title": "Closing shot",
                "model": "seedance_2_0",
                "reference_ids": ["sneaker_1"],
                "settings": {"duration": 10},
                "timeline": {"start": 30, "duration": second_duration, "order": 2},
            },
        ],
        "edges": [
            {"from": "shot_1_text", "output": "text", "to": "video_1", "input": "text"},
            {"from": "shot_2_text", "output": "text", "to": "video_2", "input": "text"},
        ],
    }


class GridPlannerContractTests(unittest.TestCase):
    def test_duration_reader_understands_common_video_briefs(self):
        self.assertEqual(grid_requested_duration_seconds("Create a one-minute sneaker ad"), 60)
        self.assertEqual(grid_requested_duration_seconds("Реклама кроссовок на 1 минуту"), 60)
        self.assertEqual(grid_requested_duration_seconds("Podcast for 1 minute 30 seconds"), 90)

    def test_each_video_gets_its_own_finished_text_prompt(self):
        clean = clean_grid_plan(video_plan(), "gpt-5.5", CATALOG, task="Create a one-minute sneaker ad")
        videos = [node for node in clean["nodes"] if node["type"] == "video"]
        incoming = {
            node["key"]: [edge for edge in clean["edges"] if edge["to"] == node["key"] and edge["output"] == "text"]
            for node in videos
        }
        self.assertEqual(len(videos), 2)
        self.assertTrue(all(len(edges) == 1 for edges in incoming.values()))
        self.assertEqual(len({edges[0]["from"] for edges in incoming.values()}), 2)
        text_by_key = {node["key"]: node for node in clean["nodes"] if node["type"] == "text"}
        self.assertIn("Macro reveal", text_by_key[incoming["video_1"][0]["from"]]["output"])
        self.assertIn("hero podium", text_by_key[incoming["video_2"][0]["from"]]["output"])

    def test_explicit_total_duration_must_be_complete(self):
        with self.assertRaisesRegex(ValueError, "planner_video_duration_mismatch"):
            clean_grid_plan(video_plan(second_duration=10), "gpt-5.5", CATALOG, task="Create a one-minute sneaker ad")

    def test_generic_product_brief_requests_optional_identity_and_can_continue(self):
        self.assertIn("add one concise optional reference_requests item", MAIN_SOURCE)
        self.assertIn("explicitly continue without it", MAIN_SOURCE)

    def test_image_comparison_can_share_one_prompt_across_distinct_models(self):
        catalog = {**CATALOG, "image": {
            "models": ["gpt_image_2", "flux_2"],
            "capabilities": {
                "gpt_image_2": {"character_reference": True, "object_reference": True},
                "flux_2": {"character_reference": True, "object_reference": True},
            },
        }}
        plan = {
            "action": "plan", "nodes": [
                {"key": "prompt", "type": "text", "model": "gpt-5.6", "output": "Same fair prompt"},
                {"key": "a", "type": "image", "model": "gpt_image_2", "settings": {}},
                {"key": "b", "type": "image", "model": "flux_2", "settings": {}},
            ], "edges": [
                {"from": "prompt", "output": "text", "to": "a", "input": "text"},
                {"from": "prompt", "output": "text", "to": "b", "input": "text"},
            ],
        }
        clean = clean_grid_plan(plan, "gpt-5.6", catalog)
        self.assertEqual(len(clean["nodes"]), 3)
        self.assertEqual({node["model"] for node in clean["nodes"] if node["type"] == "image"}, {"gpt_image_2", "flux_2"})

    def test_reference_plan_must_use_a_compatible_model(self):
        catalog = {**CATALOG, "image": {
            "models": ["gpt_image_2", "prompt_only"],
            "capabilities": {
                "gpt_image_2": {"character_reference": True, "object_reference": True},
                "prompt_only": {"character_reference": False, "object_reference": False},
            },
        }}
        plan = {
            "action": "plan", "nodes": [
                {"key": "prompt", "type": "text", "model": "gpt-5.6", "output": "Keep the product identity"},
                {"key": "image", "type": "image", "model": "prompt_only", "reference_ids": ["product_1"]},
            ], "edges": [{"from": "prompt", "output": "text", "to": "image", "input": "text"}],
        }
        with self.assertRaisesRegex(ValueError, "planner_image_reference_unsupported"):
            clean_grid_plan(plan, "gpt-5.6", catalog)

    def test_timeout_retries_once_with_fast_model(self):
        calls = []

        def fake_generation(payload):
            calls.append((payload["model"], payload["_provider_timeout_seconds"]))
            if len(calls) == 1:
                raise requests.ReadTimeout("slow")
            return {"ok": True, "text": json.dumps({"action": "clarify", "question": "Which format?"}),
                    "provider": "openai", "model": payload["model"], "metadata": {}}

        namespace = grid_planner_generation_with_fallback.__globals__
        previous = {key: namespace.get(key) for key in (
            "text_generation", "GRID_PLAN_MAX_OUTPUT_TOKENS", "GRID_PLAN_FALLBACK_MAX_OUTPUT_TOKENS",
            "GRID_PLANNER_PRIMARY_TIMEOUT_SECONDS", "GRID_PLANNER_FALLBACK_TIMEOUT_SECONDS", "GRID_PLANNER_FALLBACK_MODEL",
        )}
        namespace.update({
            "text_generation": fake_generation, "GRID_PLAN_MAX_OUTPUT_TOKENS": 8000,
            "GRID_PLAN_FALLBACK_MAX_OUTPUT_TOKENS": 6000, "GRID_PLANNER_PRIMARY_TIMEOUT_SECONDS": 50,
            "GRID_PLANNER_FALLBACK_TIMEOUT_SECONDS": 25, "GRID_PLANNER_FALLBACK_MODEL": "gpt-6.1-sol",
        })
        try:
            result = grid_planner_generation_with_fallback({}, "gpt-6-astra", CATALOG, "promo")
        finally:
            namespace.update(previous)
        self.assertTrue(result["ok"])
        self.assertEqual(result["planner_attempt"], "fallback")
        self.assertEqual(calls, [("gpt-6-astra", 50), ("gpt-6.1-sol", 25)])

    def test_two_timeouts_return_real_failure_without_a_template_plan(self):
        def always_timeout(_payload):
            raise requests.ReadTimeout("slow")

        namespace = grid_planner_generation_with_fallback.__globals__
        previous = {key: namespace.get(key) for key in (
            "text_generation", "GRID_PLAN_MAX_OUTPUT_TOKENS", "GRID_PLAN_FALLBACK_MAX_OUTPUT_TOKENS",
            "GRID_PLANNER_PRIMARY_TIMEOUT_SECONDS", "GRID_PLANNER_FALLBACK_TIMEOUT_SECONDS", "GRID_PLANNER_FALLBACK_MODEL",
        )}
        namespace.update({
            "text_generation": always_timeout, "GRID_PLAN_MAX_OUTPUT_TOKENS": 8000,
            "GRID_PLAN_FALLBACK_MAX_OUTPUT_TOKENS": 6000, "GRID_PLANNER_PRIMARY_TIMEOUT_SECONDS": 50,
            "GRID_PLANNER_FALLBACK_TIMEOUT_SECONDS": 25, "GRID_PLANNER_FALLBACK_MODEL": "gpt-6.1-sol",
        })
        try:
            result = grid_planner_generation_with_fallback({}, "gpt-6-astra", CATALOG, "Create a one-minute sneaker ad")
        finally:
            namespace.update(previous)
        self.assertFalse(result["ok"])
        self.assertEqual(result["provider"], "openai")
        self.assertEqual(result["error"], "planner_temporarily_unavailable")
        self.assertEqual(result["planner_attempt"], "failed")


if __name__ == "__main__":
    unittest.main()
