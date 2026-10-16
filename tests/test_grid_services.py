import unittest

from services.grid_montage import validate_request
from services.grid_projects import validate_project


def _state():
    return {
        "projectId": "grid_project_demo",
        "title": "Demo",
        "nodes": [
            {"id": "grid_task_demo", "type": "task", "status": "IDLE", "x": 0, "y": 0},
            {"id": "grid_video_demo", "type": "video", "status": "COMPLETED", "x": 320, "y": 0,
             "output": {"type": "video", "url": "https://cdn.example/video.mp4"}},
        ],
        "edges": [{"id": "edge_demo", "from": "grid_task_demo", "to": "grid_video_demo"}],
    }


class GridServicesTests(unittest.TestCase):
    def test_grid_project_validation_accepts_a_private_dag(self):
        encoded = validate_project("grid_project_demo", _state())
        self.assertIn("grid_video_demo", encoded)

    def test_grid_project_validation_rejects_cycles_and_active_content_urls(self):
        state = _state()
        state["edges"].append({"id": "edge_back", "from": "grid_video_demo", "to": "grid_task_demo"})
        with self.assertRaisesRegex(ValueError, "invalid_grid_cycle"):
            validate_project("grid_project_demo", state)
        state = _state()
        state["nodes"][1]["output"]["url"] = "javascript:alert(1)"
        with self.assertRaisesRegex(ValueError, "invalid_grid_media_url"):
            validate_project("grid_project_demo", state)

    def test_montage_request_preserves_order_controls_and_audio_roles(self):
        request = validate_request({
            "videos": [{"url": "https://cdn.example/a.mp4", "duration": 5, "trim_start": 1}],
            "audio_tracks": [{"url": "https://cdn.example/voice.mp3", "role": "voice", "offset": 2, "volume": 0.8}],
            "settings": {"resolution": "720p", "transition": "fade", "ducking": True},
        })
        self.assertEqual(request["settings"]["resolution"], "720p")
        self.assertEqual(request["settings"]["transition"], "fade")
        self.assertEqual(request["audio_tracks"][0]["role"], "voice")
        self.assertEqual(request["videos"][0]["trim_start"], 1)

    def test_montage_requires_at_least_one_video(self):
        with self.assertRaisesRegex(ValueError, "grid_montage_videos_required"):
            validate_request({"videos": [], "audio_tracks": []})


if __name__ == "__main__":
    unittest.main()
