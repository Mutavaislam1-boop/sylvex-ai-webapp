import unittest

from services.grid_references import public_catalog_reference, resolve_grid_catalog_references


class GridReferenceTests(unittest.TestCase):
    def test_grid_catalog_references_become_public_provider_urls(self):
        payload = {
            "grid_project_id": "grid_project_demo",
            "grid_node_id": "grid_image_demo",
            "image_options": {
                "referenceImageUrls": [
                    "/preset_catalog/characters/Ada/reference 1.png?v=abc",
                    "https://cdn.example/upload.png",
                ],
                "referenceImages": ["/preset_catalog/objects/shoe.webp"],
            },
            "video_options": {
                "start_image": "/preset_catalog/characters/Ada/reference 1.png?v=abc",
                "reference_images": ["/preset_catalog/objects/shoe.webp"],
            },
        }
        changed = resolve_grid_catalog_references(payload, "https://sylvex.ai/")
        self.assertEqual(changed, 4)
        self.assertEqual(
            payload["image_options"]["referenceImageUrls"][0],
            "https://sylvex.ai/preset_catalog/characters/Ada/reference%201.png?v=abc",
        )
        self.assertEqual(
            payload["video_options"]["start_image"],
            "https://sylvex.ai/preset_catalog/characters/Ada/reference%201.png?v=abc",
        )
        self.assertEqual(payload["image_options"]["referenceImageUrls"][1], "https://cdn.example/upload.png")

    def test_non_grid_requests_and_unsafe_catalog_paths_are_unchanged(self):
        regular = {"image_options": {"referenceImages": ["/preset_catalog/characters/a.png"]}}
        self.assertEqual(resolve_grid_catalog_references(regular, "https://sylvex.ai"), 0)
        self.assertEqual(regular["image_options"]["referenceImages"][0], "/preset_catalog/characters/a.png")
        unsafe = "/preset_catalog/characters/../private.png"
        self.assertEqual(public_catalog_reference(unsafe, "https://sylvex.ai"), unsafe)


if __name__ == "__main__":
    unittest.main()
