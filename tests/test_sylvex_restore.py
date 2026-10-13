import asyncio
import io

import pytest
from PIL import Image

import main
from services import sylvex_restore as sr


def png(size=(120, 80), color=(30, 40, 50, 255)):
    output = io.BytesIO()
    Image.new("RGBA", size, color).save(output, "PNG")
    return output.getvalue()


def region(region_id="region_1", reference=None, instruction=None, **extra):
    value = {
        "region_id": region_id,
        "source": "user_added",
        "region_type": "other",
        "bbox": {"x": 10, "y": 10, "width": 30, "height": 25},
        "user_action": "upload_reference" if reference else "enter_text" if instruction else "auto_restore",
        "reference_asset_id": reference,
        "text_instruction": instruction,
        "protection_mode": None,
    }
    value.update(extra)
    return value


def test_manual_regions_allow_empty_plan_and_limit_photo_references_to_four():
    assert sr.validate_regions([], 120, 80) == []
    rows = [region(f"region_{index}", reference=f"https://cdn.example.com/ref-{index}.png") for index in range(1, 5)]
    assert len(sr.validate_regions(rows, 120, 80)) == 4
    rows.append(region("region_5", reference="https://cdn.example.com/ref-5.png"))
    with pytest.raises(sr.SylvexRestoreValidationError, match="up to 4 reference images"):
        sr.validate_regions(rows, 120, 80)


def test_restore_prompt_maps_each_reference_to_its_region_and_keeps_text_independent():
    rows = sr.validate_regions([
        region("region_1", reference="https://cdn.example.com/face.png", instruction="Preserve this face."),
        region("region_2", instruction="Restore the sign text as H605."),
        region("region_3", reference="https://cdn.example.com/object.png"),
    ], 120, 80)
    prompt = sr.restore_prompt(rows, 120, 80)
    assert "Input image 2 is mapped only to region_1" in prompt
    assert "Input image 3 is mapped only to region_3" in prompt
    assert "Restore the sign text as H605." in prompt
    assert "same aspect ratio" in prompt


def test_restore_prompt_supports_full_photo_enhancement_without_regions():
    prompt = sr.restore_prompt([], 120, 80, 4)
    assert "Improve overall detail, focus, sharpness" in prompt
    assert "No local regions were selected" in prompt
    assert "final output scale is X4" in prompt


def test_final_output_scale_is_exact_for_x1_x2_x4():
    source = png((37, 23), (255, 0, 0, 255))
    restored = png((37, 23), (0, 0, 255, 255))
    for factor in (1, 2, 4):
        output = sr.final_enhance(source, restored, {"apply_global_enhance": False, "upscale_factor": factor}, [])
        with Image.open(io.BytesIO(output)) as image:
            assert image.size == (37 * factor, 23 * factor)


def test_final_restore_preserves_source_transparency():
    source = Image.new("RGBA", (8, 8), (40, 80, 120, 0))
    source.putpixel((3, 3), (40, 80, 120, 128))
    source.putpixel((4, 4), (40, 80, 120, 255))
    source_raw = io.BytesIO()
    source.save(source_raw, "PNG")
    output = sr.final_enhance(source_raw.getvalue(), png((8, 8), (200, 100, 50, 255)), {"apply_global_enhance": False, "upscale_factor": 2}, [])
    with Image.open(io.BytesIO(output)) as image:
        assert image.size == (16, 16)
        assert image.getpixel((0, 0))[3] == 0
        assert 0 < image.getpixel((6, 6))[3] < 255


def test_topaz_pricing_and_route_remain_unchanged():
    estimate = main.estimate_generation_cost({"mode": "image", "image_options": {"tool": "enhance_photo", "enhancePhotoModel": "topaz"}})
    assert estimate["credits"] == 15
    assert estimate["operation"] == "enhance_photo"
    assert not main.is_sylvex_restore_request({"image_options": {"tool": "enhance_photo"}})


def test_sylvex_restore_price_is_one_gpt_image_pass_with_or_without_regions():
    empty = main.estimate_generation_cost({"mode": "image", "image_options": {"tool": "enhance_photo", "enhancePhotoModel": "sylvex_sr", "sylvexRestoreRegions": []}})
    guided = main.estimate_generation_cost({"mode": "image", "image_options": {
        "tool": "enhance_photo", "enhancePhotoModel": "sylvex_sr",
        "sylvexRestoreRegions": [region("region_1"), region("region_2", instruction="Keep this text unchanged")],
    }})
    assert empty["pricing_available"] is True
    assert empty["operation"] == "sylvex_sr"
    assert empty["credits"] == guided["credits"]
    assert guided["region_count"] == 2


def edit_restore_payload(regions=None, scale=2):
    return {
        "mode": "image",
        "provider": "openai",
        "model": "sylvex_sr",
        "image_options": {
            "tool": "edit_workspace",
            "editWorkspaceMode": "upscale",
            "editWorkspaceSourceUrl": "https://cdn.example.com/source.png",
            "enhancePhotoSourceUrl": "https://cdn.example.com/source.png",
            "editWorkspaceUpscale": {"model": "sylvex_sr", "width": 120 * scale, "height": 80 * scale},
            "enhancePhotoModel": "sylvex_sr",
            "sylvexRestoreRegions": regions or [],
            "sylvexRestoreFinalEnhance": {"apply_global_enhance": True, "upscale_factor": scale},
        },
    }


def test_edit_upscale_sylvex_restore_uses_openai_without_analysis_id():
    payload = edit_restore_payload()
    assert main.is_edit_workspace_sylvex_restore(payload) is True
    assert main.resolve_prostudio_provider_for_slot(payload, "image", payload["model"], payload["provider"]) == "OPENAI"
    assert "sylvexRestoreAnalysisId" not in payload["image_options"]


def test_edit_upscale_dispatches_to_restore_instead_of_topaz(monkeypatch):
    calls = []

    async def fake_restore(payload):
        calls.append(payload)
        return {"ok": True, "type": "image", "image_url": "https://cdn.example.com/restored.png"}

    async def fail_topaz(payload):
        raise AssertionError("Topaz must not handle Sylvex Restore")

    monkeypatch.setattr(main, "generate_sylvex_restore_image", fake_restore)
    monkeypatch.setattr(main, "generate_enhance_photo_image", fail_topaz)
    result = asyncio.run(main.generate_edit_workspace_image(edit_restore_payload()))
    assert len(calls) == 1
    assert calls[0]["image_options"]["enhancePhotoSourceUrl"] == "https://cdn.example.com/source.png"
    assert result["ok"] is True
    assert result["tool"] == "edit_workspace"
    assert result["enhance_model"] == "sylvex_sr"
    assert result["provider"] == "openai"


def test_restore_runs_gpt_image_even_without_manual_regions_and_returns_exact_scale(monkeypatch):
    source = png()
    provider_calls = []
    monkeypatch.setattr(main, "OPENAI_API_KEY", "test")
    monkeypatch.setattr(main, "_read_image_bytes_for_generation", lambda value: source)

    def fake_restore(source_png, rows, references, upscale_factor):
        provider_calls.append((rows, references, upscale_factor))
        return source_png

    monkeypatch.setattr(main, "_sylvex_sr_provider_restore", fake_restore)
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: "https://cdn.example.com/final.png")
    monkeypatch.setattr(main, "attach_image_thumbnails", lambda value: value)
    result = asyncio.run(main.generate_sylvex_restore_image(edit_restore_payload(scale=4)))
    assert result["ok"] is True
    assert provider_calls == [([], [], 4)]
    assert result["restore_status"] == "completed"
    assert result["final_enhance"]["upscale_factor"] == 4


def test_restore_pass_receives_references_in_explicit_region_order(monkeypatch):
    source = png()
    captured = []
    monkeypatch.setattr(main, "OPENAI_API_KEY", "test")
    monkeypatch.setattr(main, "_read_image_bytes_for_generation", lambda value: source)

    def fake_restore(source_png, rows, references, upscale_factor):
        captured.extend(region_id for region_id, _ in references)
        return source_png

    monkeypatch.setattr(main, "_sylvex_sr_provider_restore", fake_restore)
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: "https://cdn.example.com/final.png")
    monkeypatch.setattr(main, "attach_image_thumbnails", lambda value: value)
    rows = [region("region_1", reference="https://cdn.example.com/a.png"), region("region_2", instruction="Preserve it"), region("region_3", reference="https://cdn.example.com/b.png")]
    result = asyncio.run(main.generate_sylvex_restore_image(edit_restore_payload(rows, scale=1)))
    assert result["ok"] is True
    assert captured == ["region_1", "region_3"]
    assert result["reference_images"] == ["https://cdn.example.com/source.png", "https://cdn.example.com/a.png", "https://cdn.example.com/b.png"]


def test_automatic_analysis_routes_are_removed():
    paths = {route.path for route in main.app.routes if hasattr(route, "path")}
    assert "/api/public/enhance/sylvex-sr/analyze" not in paths
    assert "/enhance/sylvex-sr/analyze/{analysis_id}" not in paths
