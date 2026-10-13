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


def region(region_id="region_1", region_type="face", action="auto_restore", **extra):
    value = {
        "region_id": region_id,
        "source": "auto",
        "region_type": region_type,
        "bbox": {"x": 10, "y": 10, "width": 30, "height": 25},
        "confidence": 0.2,
        "importance_score": 0.9,
        "issue_type": "uncertain",
        "issue_summary": "Important detail is uncertain.",
        "suggested_action": "upload_reference",
        "user_action": action,
        "reference_asset_id": None,
        "text_instruction": None,
        "protection_mode": None,
    }
    value.update(extra)
    return value


def test_analysis_keeps_only_high_priority_regions_and_enforces_type_caps():
    rows = []
    for index in range(9):
        rows.append({
            "region_type": "face" if index < 6 else "text",
            "bbox": {"x": index * 5, "y": 2, "width": 20, "height": 20},
            "confidence": 0.1,
            "importance_score": 1 - index / 20,
            "issue_type": "blur",
            "issue_summary": f"Issue {index}",
            "suggested_action": "upload_reference",
        })
    normalized = sr.normalize_analysis_regions(rows, 200, 100)
    assert len(normalized) == 8
    assert sum(item["region_type"] == "face" for item in normalized) == 5
    assert sum(item["region_type"] == "text" for item in normalized) == 3
    assert [item["region_id"] for item in normalized] == [f"region_{index}" for index in range(1, 9)]


def test_region_validation_requires_explicit_action_inputs():
    with pytest.raises(sr.SylvexRestoreValidationError, match="reference"):
        sr.validate_regions([region(action="upload_reference")], 120, 80)
    with pytest.raises(sr.SylvexRestoreValidationError, match="instruction"):
        sr.validate_regions([region(action="enter_text")], 120, 80)
    with pytest.raises(sr.SylvexRestoreValidationError, match="Hard or Soft"):
        sr.validate_regions([region(action="protect_region")], 120, 80)


def test_manual_region_is_valid_and_processed_after_faces_text_and_objects():
    rows = [
        region("region_4", "other", "auto_restore", source="user_added"),
        region("region_2", "text", "enter_text", text_instruction="Correct text: H605"),
        region("region_1", "face", "protect_region", protection_mode="soft"),
        region("region_3", "object", "auto_restore"),
    ]
    validated = sr.validate_regions(rows, 120, 80)
    assert [item["region_id"] for item in sr.ordered_regions(validated)] == ["region_1", "region_2", "region_3", "region_4"]


def test_gpt_mask_is_transparent_only_inside_region():
    mask = sr.region_mask((40, 30), {"x": 10, "y": 8, "width": 12, "height": 10})
    with Image.open(io.BytesIO(mask)) as image:
        alpha = image.getchannel("A")
        assert alpha.getpixel((0, 0)) == 255
        assert alpha.getpixel((12, 10)) == 0


def test_hard_protection_restores_original_pixels_after_global_enhance():
    source = png((20, 20), (255, 0, 0, 255))
    working = png((20, 20), (0, 0, 255, 255))
    protected = [{"bbox": {"x": 5, "y": 5, "width": 5, "height": 5}}]
    output = sr.final_enhance(source, working, {"apply_global_enhance": False, "upscale_factor": 2}, protected)
    with Image.open(io.BytesIO(output)) as image:
        assert image.size == (40, 40)
        assert image.getpixel((12, 12))[:3] == (255, 0, 0)
        assert image.getpixel((2, 2))[:3] == (0, 0, 255)


def test_topaz_pricing_and_route_remain_unchanged():
    estimate = main.estimate_generation_cost({"mode": "image", "image_options": {"tool": "enhance_photo", "enhancePhotoModel": "topaz"}})
    assert estimate["credits"] == 15
    assert estimate["operation"] == "enhance_photo"
    assert not main.is_sylvex_restore_request({"image_options": {"tool": "enhance_photo"}})


def test_sylvex_restore_price_scales_with_actionable_regions():
    estimate = main.estimate_generation_cost({"mode": "image", "image_options": {
        "tool": "enhance_photo", "enhancePhotoModel": "sylvex_sr",
        "sylvexRestoreRegions": [region("region_1"), region("region_2", "text", "skip_region")],
    }})
    assert estimate["pricing_available"] is True
    assert estimate["operation"] == "sylvex_sr"
    assert estimate["region_count"] == 1
    assert estimate["credits"] == 32


def edit_restore_payload():
    return {
        "mode": "image",
        "provider": "topaz",
        "model": "topaz_enhance_photo",
        "image_options": {
            "tool": "edit_workspace",
            "editWorkspaceMode": "upscale",
            "editWorkspaceSourceUrl": "https://cdn.example.com/source.png",
            "editWorkspaceUpscale": {
                "model": "sylvex_sr",
                "width": 120,
                "height": 80,
            },
            "enhancePhotoModel": "sylvex_sr",
            "sylvexRestoreAnalysisId": "anl_123",
            "sylvexRestoreRegions": [region("region_1")],
            "sylvexRestoreFinalEnhance": {"apply_global_enhance": True, "upscale_factor": 1},
        },
    }


def test_edit_upscale_sylvex_restore_uses_openai_route_and_region_pricing():
    payload = edit_restore_payload()
    assert main.is_edit_workspace_sylvex_restore(payload) is True
    assert main.resolve_prostudio_provider_for_slot(payload, "image", payload["model"], payload["provider"]) == "OPENAI"
    estimate = main.calculate_generation_price(payload)
    assert estimate["operation"] == "sylvex_sr"
    assert estimate["region_count"] == 1
    assert estimate["credits"] == 32


def test_edit_upscale_dispatches_to_guided_restore_instead_of_topaz(monkeypatch):
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


def test_restore_continues_after_one_region_failure_and_returns_partial_result(monkeypatch):
    source = png()
    monkeypatch.setattr(main, "OPENAI_API_KEY", "test")
    monkeypatch.setattr(main, "_read_image_bytes_for_generation", lambda value: source)
    calls = []
    def fake_edit(working, row, reference=b"", soft=None):
        calls.append(row["region_id"])
        if row["region_id"] == "region_1":
            raise RuntimeError("provider failure")
        return working
    monkeypatch.setattr(main, "_sylvex_sr_provider_edit", fake_edit)
    monkeypatch.setattr(main, "storage_put_bytes", lambda content, key, content_type: "https://cdn.example.com/final.png")
    monkeypatch.setattr(main, "attach_image_thumbnails", lambda value: value)
    payload = {
        "mode": "image", "telegram_id": 0,
        "image_options": {
            "tool": "enhance_photo", "enhancePhotoModel": "sylvex_sr",
            "enhancePhotoSourceUrl": "https://cdn.example.com/source.png",
            "sylvexRestoreAnalysisId": "anl_123",
            "sylvexRestoreRegions": [region("region_1"), region("region_2", "object", "auto_restore")],
            "sylvexRestoreFinalEnhance": {"apply_global_enhance": False, "upscale_factor": 1},
        },
    }
    result = asyncio.run(main.generate_sylvex_restore_image(payload))
    assert result["ok"] is True
    assert result["restore_status"] == "partially_failed"
    assert result["failed_region_ids"] == ["region_1"]
    assert calls == ["region_1", "region_2"]
    assert result["output_asset_id"] == "https://cdn.example.com/final.png"


def test_analysis_prompt_explicitly_prevents_over_detection():
    prompt = sr.analysis_prompt(1280, 1280)
    assert "only the most important uncertain regions" in prompt
    assert "at most 8" in prompt
    assert "Ignore minor background blur" in prompt
