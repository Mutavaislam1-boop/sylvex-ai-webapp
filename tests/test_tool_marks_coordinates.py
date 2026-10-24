"""Remove/Replace Object mark the object on the photo in one shared editor,
and only the marks' coordinates (plus the size of the photo they were drawn
on) go to the server - no picture of the marks. The server draws the edit
area from them and also tells the model where the object is, in percent of
the image. Watermark removal needs no mark at all."""
import asyncio
import base64
import io
import json

import main


def _png_data_uri(size=(40, 20), color=(10, 20, 30, 255)):
    from PIL import Image

    img = Image.new("RGBA", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.text = json.dumps(payload)


def test_annotation_region_text_is_the_marked_area_in_percent():
    strokes = [{"width": 2, "points": [{"x": 20, "y": 10}, {"x": 40, "y": 30}]}]
    text = main.annotation_region_text((100, 100), strokes, (100, 100))
    assert text.startswith("The user marked the target object at x 19–42% and y 9–32%")
    assert "centre at x 30%, y 20%" in text


def test_annotation_editor_size_accepts_only_positive_sizes():
    assert main.annotation_editor_size({"width": 640, "height": "480"}) == (640, 480)
    assert main.annotation_editor_size({"width": 0, "height": 480}) == ()
    assert main.annotation_editor_size(None) == ()


def test_replace_object_takes_marks_and_editor_size_without_a_marked_picture(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        captured["data"] = data
        captured["files"] = [name for name, _ in files]
        return _FakeResponse(200, {"data": [{"b64_json": _png_data_uri().split(",", 1)[1]}]})

    monkeypatch.setattr(main, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "storage_put_bytes", lambda data, key, mime: "https://cdn.example.com/replaced.png")
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)
    payload = {"telegram_id": 0, "job_id": "", "image_options": {
        "tool": "replace_object",
        "replaceObjectSourceUrl": _png_data_uri(),
        "replaceObjectReferenceUrl": _png_data_uri(color=(200, 0, 0, 255)),
        "replaceObjectMaskStrokes": [{"width": 2, "points": [{"x": 4, "y": 4}, {"x": 6, "y": 6}]}],
        "replaceObjectEditorSize": {"width": 40, "height": 20},
    }}
    result = asyncio.run(main.generate_replace_object_image(payload))
    assert result["ok"] is True
    assert captured["files"] == ["image[]", "image[]", "mask"]
    assert "The user marked the target object at x" in captured["data"]["prompt"]
    assert "third image" not in captured["data"]["prompt"]


def test_replace_object_needs_the_marks():
    payload = {"image_options": {"replaceObjectSourceUrl": _png_data_uri(), "replaceObjectReferenceUrl": _png_data_uri(),
                                 "replaceObjectMaskStrokes": [], "replaceObjectEditorSize": {"width": 40, "height": 20}}}
    main_key = main.OPENAI_API_KEY
    try:
        main.OPENAI_API_KEY = "test-key"
        result = asyncio.run(main.generate_replace_object_image(payload))
    finally:
        main.OPENAI_API_KEY = main_key
    assert result["ok"] is False


def test_watermark_removal_without_a_mark_removes_every_overlay(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        captured["data"] = data
        captured["files"] = [name for name, _ in files]
        return _FakeResponse(200, {"data": [{"url": "https://cdn.example.com/clean.png"}]})

    monkeypatch.setattr(main, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "send_generated_images_to_telegram", lambda *a, **k: True)
    result = asyncio.run(main.generate_watermark_removal_image({"telegram_id": 0, "job_id": "", "image_options": {
        "tool": "watermark_removal", "watermarkSourceUrl": _png_data_uri()}}))
    assert result["ok"] is True
    assert captured["files"] == ["image"]
    assert captured["data"]["prompt"].startswith("Find and remove every watermark")
    assert result["mask_applied"] is False
