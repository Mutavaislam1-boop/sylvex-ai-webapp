import ast
from pathlib import Path
import re
import unittest


MAIN_SOURCE = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
MAIN_TREE = ast.parse(MAIN_SOURCE)
PLANNER_FUNCTIONS = [
    node for node in MAIN_TREE.body
    if isinstance(node, ast.FunctionDef) and node.name in {"grid_requested_duration_seconds", "clean_grid_plan"}
]
PLANNER_NAMESPACE = {"re": re}
exec(compile(ast.Module(body=PLANNER_FUNCTIONS, type_ignores=[]), "main.py", "exec"), PLANNER_NAMESPACE)
grid_requested_duration_seconds = PLANNER_NAMESPACE["grid_requested_duration_seconds"]
clean_grid_plan = PLANNER_NAMESPACE["clean_grid_plan"]


CATALOG = {
    "image": {"models": ["gpt_image_2"]},
    "video": {"models": {"seedance_2_0": {}}},
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
                "key": "shared_script",
                "type": "text",
                "title": "Full script",
                "output": "A complete advertising script.",
            },
            {
                "key": "video_1",
                "type": "video",
                "title": "Opening shot",
                "model": "seedance_2_0",
                "prompt": "Macro reveal of the exact sneaker, then a runner launches forward.",
                "reference_ids": ["sneaker_1"],
                "settings": {"duration": 10},
                "timeline": {"start": 0, "duration": 30, "order": 1},
            },
            {
                "key": "video_2",
                "type": "video",
                "title": "Closing shot",
                "model": "seedance_2_0",
                "prompt": "The same sneaker lands on a clean hero podium for the final packshot.",
                "reference_ids": ["sneaker_1"],
                "settings": {"duration": 10},
                "timeline": {"start": 30, "duration": second_duration, "order": 2},
            },
        ],
        "edges": [
            {"from": "shared_script", "output": "text", "to": "video_1", "input": "text"},
            {"from": "shared_script", "output": "text", "to": "video_2", "input": "text"},
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
        self.assertIn("optional product/brand name or product reference", MAIN_SOURCE)
        self.assertIn("do not block the plan if the user skips it", MAIN_SOURCE)


if __name__ == "__main__":
    unittest.main()
