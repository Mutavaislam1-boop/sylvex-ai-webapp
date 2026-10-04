"""Updated character photos must bypass WebView cache and remain valid inputs."""
import ast
import hashlib
import pathlib
import tempfile
import unittest
import urllib.parse
import os


class CharacterAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        source = (pathlib.Path(__file__).parents[1] / "main.py").read_text()
        names = {"_preset_file_url", "image_file_tuple_from_url"}
        functions = [node for node in ast.parse(source).body
                     if isinstance(node, ast.FunctionDef) and node.name in names]
        self.scope = {
            "pathlib": pathlib, "urllib": urllib, "hashlib": hashlib, "os": os,
            "PRESET_CATALOG_DIR": self.root,
            "PRESET_IMAGE_EXTENSIONS": {".png", ".jpg", ".jpeg", ".webp", ".gif"},
            "storage_key_from_url": lambda value: None,
            "prostudio_error": lambda *args, **kwargs: None,
            "_sql_text": lambda value, limit: value[:limit],
        }
        exec(compile(ast.Module(body=functions, type_ignores=[]), "main.py", "exec"), self.scope)

    def asset(self, relative, content=b"original-image"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_same_photo_keeps_url_and_replacement_changes_cache_version(self):
        photo = self.asset("characters/amina/avatar.png")
        url = self.scope["_preset_file_url"](photo)
        self.assertEqual(url, self.scope["_preset_file_url"](photo))
        photo.write_bytes(b"updated-image")
        updated = self.scope["_preset_file_url"](photo)
        self.assertNotEqual(url, updated)
        self.assertEqual(urllib.parse.urlsplit(url).path, urllib.parse.urlsplit(updated).path)

    def test_versioned_and_legacy_urls_load_the_same_reference_bytes(self):
        photo = self.asset("characters/naomi/Снимок экрана.png", b"reference-bytes")
        url = self.scope["_preset_file_url"](photo)
        load = self.scope["image_file_tuple_from_url"]
        expected = (photo.name, photo.read_bytes(), "image/png")
        self.assertEqual(expected, load(url))
        self.assertEqual(expected, load(urllib.parse.urlsplit(url).path))

    def test_object_and_video_urls_stay_unchanged(self):
        for relative in ["objects/book/reference.png", "characters/sylvex/video_reference.mp4"]:
            path = self.asset(relative)
            self.assertEqual("/preset_catalog/" + relative, self.scope["_preset_file_url"](path))


if __name__ == "__main__":
    unittest.main()
