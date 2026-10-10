"""Server-side, per-model reference/edit video limits.

Uploads are probed once (services/video_probe.py) and the duration and
dimensions are stored next to the file; /generate then checks them, plus
extension and size, against the selected model's registry reference_inputs.
Each model is checked against its own documented limits - never one global
rule - and a model with no known limit is never restricted. No network:
storage is an in-memory dict and the videos are made locally with ffmpeg.
"""
import asyncio
import subprocess

import pytest

import main
from services import model_capabilities as mc
from services import video_probe

FFMPEG = video_probe._ffmpeg_binary()
needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="ffmpeg not available")


def _make_video(tmp_path, seconds, width, height, rotation=None):
    raw = tmp_path / "raw.mp4"
    subprocess.run([FFMPEG, "-hide_banner", "-y", "-f", "lavfi", "-i",
                    f"testsrc=duration={seconds}:size={width}x{height}:rate=24",
                    "-pix_fmt", "yuv420p", str(raw)], check=True, capture_output=True)
    if rotation is None:
        return raw.read_bytes()
    rotated = tmp_path / "rotated.mp4"
    subprocess.run([FFMPEG, "-hide_banner", "-y", "-display_rotation", str(rotation), "-i", str(raw),
                    "-c", "copy", str(rotated)], check=True, capture_output=True)
    return rotated.read_bytes()


class FakeUploadFile:
    def __init__(self, filename, content_type, data):
        self.filename, self.content_type, self._data, self._sent = filename, content_type, data, False

    async def read(self, n):
        if self._sent:
            return b""
        self._sent = True
        return self._data


@pytest.fixture
def storage(monkeypatch):
    objects = {}
    monkeypatch.setattr(main, "storage_put_bytes", lambda data, key, content_type="": objects.__setitem__(key, data) or f"https://cdn.test/{key}")
    monkeypatch.setattr(main, "storage_key_from_url", lambda url: url[len("https://cdn.test/"):] if str(url).startswith("https://cdn.test/") else "")

    def read(key):
        if key not in objects:
            raise FileNotFoundError(key)
        return objects[key]

    monkeypatch.setattr(main, "storage_read_bytes", read)
    return objects


def _limits(model):
    return mc.get_capability(model).reference_inputs


# ------------------------------------------------------------------ probe

def test_parse_ffmpeg_info_swaps_dimensions_for_portrait_rotation():
    stderr = ("  Duration: 00:00:12.48, start: 0.000000, bitrate: 59 kb/s\n"
              "  Stream #0:0[0x1](und): Video: h264 (High), yuv420p(progressive), 1920x1080 [SAR 1:1 DAR 16:9], 24 fps\n"
              "        displaymatrix: rotation of -90.00 degrees\n")
    assert video_probe.parse_ffmpeg_info(stderr) == {"duration": 12.48, "width": 1080, "height": 1920}


@needs_ffmpeg
def test_probe_reads_duration_and_display_dimensions(tmp_path):
    meta = video_probe.probe_video_bytes(_make_video(tmp_path, 4, 854, 480, rotation=90), ".mp4")
    assert meta["duration"] == pytest.approx(4, abs=0.1)
    assert (meta["width"], meta["height"]) == (480, 854)
    assert meta["extension"] == ".mp4" and meta["bytes"] > 0


def test_probe_of_unreadable_bytes_returns_none():
    assert video_probe.probe_video_bytes(b"not a video", ".mp4") is None


# ------------------------------------------------- per-model limit checks

def test_kling_motion_duration_depends_on_orientation():
    limits = _limits("kling_motion_3_0")
    clip = {"extension": ".mp4", "duration": 20, "width": 720, "height": 1280}
    assert video_probe.reference_video_limit_error(limits, clip, orientation="video") is None
    error = video_probe.reference_video_limit_error(limits, clip, orientation="image")
    assert error and "3-10 seconds" in error


def test_same_clip_judged_by_each_models_own_limits():
    # 20 s, 480x854: fine for Motion Control (video orientation), too long
    # and too small for Kling Omni, too long for Seedance 2.0.
    clip = {"extension": ".mp4", "duration": 20, "width": 480, "height": 854}
    assert video_probe.reference_video_limit_error(_limits("kling_motion_3_0"), clip, orientation="video") is None
    assert "3-15.5 seconds" in video_probe.reference_video_limit_error(_limits("kling_o3_omni"), clip)
    assert "2-15 seconds" in video_probe.reference_video_limit_error(_limits("seedance_2_0"), clip)
    short = dict(clip, duration=10)
    assert "700-4553 px" in video_probe.reference_video_limit_error(_limits("kling_o3_omni"), short)
    assert video_probe.reference_video_limit_error(_limits("seedance_2_0"), short) is None


def test_size_and_container_limits_differ_per_model():
    big = {"extension": ".mp4", "bytes": 150 * 1024 * 1024}
    assert "100 MB" in video_probe.reference_video_limit_error(_limits("kling_motion_2_6"), big)
    assert video_probe.reference_video_limit_error(_limits("kling_o3_omni"), big) is None
    assert video_probe.reference_video_limit_error(_limits("seedance_2_fast"), big) is None
    assert "MP4/MOV" in video_probe.reference_video_limit_error(_limits("seedance_2_0"), {"extension": ".webm"})


@pytest.mark.parametrize("model", ["gemini_omni_flash", "runway_aleph", "runway_aleph2", "wan_2_7_edit", "grok_video_edit", "seedance_1_5_pro"])
def test_models_without_documented_limits_are_not_restricted(model):
    clip = {"extension": ".webm", "bytes": 10 ** 9, "duration": 999, "width": 10, "height": 9000}
    assert video_probe.reference_video_limit_error(_limits(model), clip) is None


# ------------------------------------------ upload -> generate (server-side)

def _video_payload(model, url, **extra):
    return {"mode": "video", "model": model, "video_options": dict({"model": model, "input_video": url, "video_url": url}, **extra)}


@needs_ffmpeg
def test_uploaded_clip_is_probed_and_checked_at_generation(tmp_path, storage):
    data = _make_video(tmp_path, 12, 720, 1280)
    upload = asyncio.run(main.public_prostudio_upload_media(file=FakeUploadFile("clip.mp4", "video/mp4", data), kind="video"))
    assert upload["ok"] and upload["video_meta"]["duration"] == pytest.approx(12, abs=0.1)
    assert any(key.endswith(".probe.json") for key in storage)
    url = upload["url"]

    # Motion Control: 12 s is fine when following the video, too long when
    # following the character image (10 s).
    assert asyncio.run(main.validate_reference_video_media(_video_payload("kling_motion_3_0", url, character_orientation="video"))) is None
    error = asyncio.run(main.validate_reference_video_media(_video_payload("kling_motion_3_0", url, character_orientation="image")))
    assert error and error["ok"] is False and "3-10 seconds" in error["error"]
    # Seedance 2.0 takes 2-15 s; a model with no known limit takes anything.
    assert asyncio.run(main.validate_reference_video_media(_video_payload("seedance_2_0", url))) is None
    assert asyncio.run(main.validate_reference_video_media(_video_payload("gemini_omni_flash", url))) is None


def test_video_without_probe_is_checked_by_extension_only(storage):
    url = "https://cdn.test/videos/previous-result.mp4"
    assert asyncio.run(main.validate_reference_video_media(_video_payload("kling_o3_omni", url))) is None
    webm = "https://cdn.test/video-inputs/old-upload.webm"
    error = asyncio.run(main.validate_reference_video_media(_video_payload("kling_o3_omni", webm)))
    assert error and "MP4/MOV" in error["error"]
    external = "https://provider.example/result?id=1"
    assert asyncio.run(main.validate_reference_video_media(_video_payload("kling_o3_omni", external))) is None


def test_generate_route_runs_the_media_check():
    import inspect
    source = inspect.getsource(main)
    assert "validate_video_feature_request(payload) or await validate_reference_video_media(payload)" in source
