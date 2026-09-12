"""seedance_1_5_pro had no hardcoded default provider model, unlike its
siblings seedance_2_fast/seedance_2_0 (both default to a hardcoded
"dreamina-seedance-*" model id). Without BYTEPLUS_SEEDANCE_1_5_PRO_MODEL
set in the environment, _map_seedance_video_model_to_provider_model
returned None, so every Seedance 1.5 Pro request failed with "unknown
provider model mapping" before any API key or provider call was even
attempted."""
import importlib

import services.video_router as video_router


def test_seedance_1_5_pro_has_a_hardcoded_default_model(monkeypatch):
    monkeypatch.delenv("BYTEPLUS_SEEDANCE_1_5_PRO_MODEL", raising=False)
    reloaded = importlib.reload(video_router)
    try:
        assert reloaded.BYTEPLUS_SEEDANCE_MODEL_MAP.get("seedance_1_5_pro"), (
            "seedance_1_5_pro must resolve to a provider model even without "
            "BYTEPLUS_SEEDANCE_1_5_PRO_MODEL set"
        )
        assert reloaded._map_seedance_video_model_to_provider_model("seedance_1_5_pro")
    finally:
        importlib.reload(video_router)


def test_seedance_1_5_pro_env_override_still_wins(monkeypatch):
    monkeypatch.setenv("BYTEPLUS_SEEDANCE_1_5_PRO_MODEL", "custom-seedance-1-5-pro")
    reloaded = importlib.reload(video_router)
    try:
        assert reloaded.BYTEPLUS_SEEDANCE_MODEL_MAP.get("seedance_1_5_pro") == "custom-seedance-1-5-pro"
    finally:
        monkeypatch.delenv("BYTEPLUS_SEEDANCE_1_5_PRO_MODEL", raising=False)
        importlib.reload(video_router)


def test_seedance_1_5_pro_body_is_built_without_the_env_override(monkeypatch):
    monkeypatch.delenv("BYTEPLUS_SEEDANCE_1_5_PRO_MODEL", raising=False)
    reloaded = importlib.reload(video_router)
    try:
        body = reloaded._seedance_body("seedance_1_5_pro", "a slow zoom over a canyon", {"video_options": {}})
        assert body is not None, "seedance_1_5_pro must build a request body with the default model"
        assert body["model"] == reloaded.BYTEPLUS_SEEDANCE_MODEL_MAP["seedance_1_5_pro"]
    finally:
        importlib.reload(video_router)
