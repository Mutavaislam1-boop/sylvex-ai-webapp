"""Deterministic local Final Montage for completed Grid media nodes."""
from __future__ import annotations

import mimetypes
import pathlib
import re
import shutil
import subprocess
import tempfile
import urllib.parse
from uuid import uuid4

from services.safe_io import safe_get
from services.storage import generated_key, get_object, key_from_url, put_file


MAX_VIDEOS = 24
MAX_AUDIO_TRACKS = 16
MAX_TOTAL_SECONDS = 15 * 60


def _ffmpeg_binary() -> str:
    binary = shutil.which("ffmpeg")
    if binary:
        return binary
    try:
        import imageio_ffmpeg
        return str(imageio_ffmpeg.get_ffmpeg_exe() or "")
    except Exception:
        return ""


def _read_owned_or_remote(url: str, max_bytes: int = 1024 * 1024 * 1024) -> bytes:
    key = key_from_url(url)
    if key:
        body, _, size = get_object(key)
        if size is not None and int(size) > max_bytes:
            body.close()
            raise ValueError("grid_montage_media_too_large")
        try:
            data = body.read(max_bytes + 1)
        finally:
            body.close()
    else:
        response = safe_get(url, timeout=240)
        response.raise_for_status()
        data = response.content
    if not data or len(data) > max_bytes:
        raise ValueError("grid_montage_media_too_large")
    return data


def _materialize(url: str, folder: pathlib.Path, index: int, fallback: str) -> pathlib.Path:
    if not isinstance(url, str) or not url.startswith(("https://", "http://", "/")) or url.startswith("//"):
        raise ValueError("invalid_grid_montage_url")
    suffix = pathlib.Path(urllib.parse.urlparse(url).path).suffix.lower()
    if not suffix or len(suffix) > 8:
        suffix = fallback
    path = folder / f"input-{index}{suffix}"
    path.write_bytes(_read_owned_or_remote(url))
    return path


def _media_info(ffmpeg: str, path: pathlib.Path) -> tuple[float, bool]:
    completed = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
    )
    text = (completed.stderr or b"").decode("utf-8", "ignore")
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    duration = (int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))) if match else 0.0
    return duration, bool(re.search(r"Stream #.*Audio:", text))


def _number(value, default=0.0, minimum=0.0, maximum=MAX_TOTAL_SECONDS):
    try:
        return max(minimum, min(maximum, float(value)))
    except (TypeError, ValueError):
        return default


def validate_request(payload: dict) -> dict:
    videos = payload.get("videos") if isinstance(payload, dict) else None
    audios = payload.get("audio_tracks") if isinstance(payload, dict) else None
    if not isinstance(videos, list) or not 1 <= len(videos) <= MAX_VIDEOS:
        raise ValueError("grid_montage_videos_required")
    if audios is None:
        audios = []
    if not isinstance(audios, list) or len(audios) > MAX_AUDIO_TRACKS:
        raise ValueError("invalid_grid_montage_audio")
    clean_videos = []
    for item in videos:
        if not isinstance(item, dict) or not str(item.get("url") or "").strip():
            raise ValueError("invalid_grid_montage_video")
        clean_videos.append({
            "url": str(item["url"]).strip(),
            "duration": _number(item.get("duration"), 0),
            "trim_start": _number(item.get("trim_start"), 0),
        })
    clean_audio = []
    for item in audios:
        if not isinstance(item, dict) or not str(item.get("url") or "").strip():
            raise ValueError("invalid_grid_montage_audio")
        role = str(item.get("role") or "music").lower()
        clean_audio.append({
            "url": str(item["url"]).strip(),
            "role": role if role in {"music", "voice", "dialogue", "sfx", "atmosphere"} else "music",
            "offset": _number(item.get("offset"), 0),
            "volume": _number(item.get("volume"), 1, 0, 2),
        })
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    resolution = str(settings.get("resolution") or "1080p").lower()
    width, height = (1920, 1080) if resolution == "1080p" else (1280, 720)
    return {
        "videos": clean_videos,
        "audio_tracks": clean_audio,
        "settings": {
            "resolution": "1080p" if width == 1920 else "720p", "width": width, "height": height,
            "transition": str(settings.get("transition") or "cut").lower(),
            "ducking": bool(settings.get("ducking", True)),
        },
    }


def render(payload: dict) -> dict:
    request = validate_request(payload)
    ffmpeg = _ffmpeg_binary()
    if not ffmpeg:
        raise RuntimeError("ffmpeg_unavailable")
    with tempfile.TemporaryDirectory(prefix="sylvex-grid-montage-") as folder_name:
        folder = pathlib.Path(folder_name)
        video_paths = [_materialize(item["url"], folder, index, ".mp4") for index, item in enumerate(request["videos"])]
        audio_paths = [_materialize(item["url"], folder, len(video_paths) + index, ".mp3") for index, item in enumerate(request["audio_tracks"])]
        info = [_media_info(ffmpeg, path) for path in video_paths]
        durations = []
        total = 0.0
        for item, (source_duration, _) in zip(request["videos"], info):
            available = max(0.1, source_duration - item["trim_start"]) if source_duration else item["duration"]
            duration = item["duration"] or available
            duration = min(duration, available) if available else duration
            duration = max(0.1, duration)
            durations.append(duration)
            total += duration
        if total > MAX_TOTAL_SECONDS:
            raise ValueError("grid_montage_too_long")

        command = [ffmpeg, "-y"]
        for path in video_paths + audio_paths:
            command.extend(["-i", str(path)])
        width, height = request["settings"]["width"], request["settings"]["height"]
        filters = []
        concat_inputs = []
        for index, (duration, (_, has_audio), item) in enumerate(zip(durations, info, request["videos"])):
            transition = request["settings"]["transition"]
            fade = ""
            if transition in {"fade", "dissolve"} and duration > .5:
                fade = f",fade=t=in:st=0:d=.2,fade=t=out:st={max(.2, duration - .2):.3f}:d=.2"
            filters.append(
                f"[{index}:v]trim=start={item['trim_start']:.3f}:duration={duration:.3f},setpts=PTS-STARTPTS,"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
                f"fps=30,format=yuv420p{fade}[v{index}]"
            )
            if has_audio:
                filters.append(
                    f"[{index}:a]atrim=start={item['trim_start']:.3f}:duration={duration:.3f},asetpts=PTS-STARTPTS,"
                    f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{index}]"
                )
            else:
                filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={duration:.3f}[a{index}]")
            concat_inputs.append(f"[v{index}][a{index}]")
        filters.append(f"{''.join(concat_inputs)}concat=n={len(video_paths)}:v=1:a=1[vcat][native]")

        bed_inputs = ["[native]"]
        voice_inputs = []
        for offset, track in enumerate(request["audio_tracks"]):
            input_index = len(video_paths) + offset
            delay = int(track["offset"] * 1000)
            volume = track["volume"] * (0.32 if track["role"] == "music" else 1.0)
            label = f"extra{offset}"
            filters.append(
                f"[{input_index}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"adelay={delay}|{delay},volume={volume:.3f}[{label}]"
            )
            (voice_inputs if track["role"] in {"voice", "dialogue"} else bed_inputs).append(f"[{label}]")
        if len(bed_inputs) > 1:
            filters.append(f"{''.join(bed_inputs)}amix=inputs={len(bed_inputs)}:duration=first:dropout_transition=2[bed]")
        else:
            filters.append("[native]anull[bed]")
        if voice_inputs:
            if len(voice_inputs) > 1:
                filters.append(f"{''.join(voice_inputs)}amix=inputs={len(voice_inputs)}:duration=longest:dropout_transition=1[voices]")
            else:
                filters.append(f"{voice_inputs[0]}anull[voices]")
            if request["settings"]["ducking"]:
                filters.append("[bed][voices]sidechaincompress=threshold=.035:ratio=8:attack=20:release=400[ducked]")
                filters.append("[ducked][voices]amix=inputs=2:duration=first:normalize=0[aout]")
            else:
                filters.append("[bed][voices]amix=inputs=2:duration=first:normalize=0[aout]")
        else:
            filters.append("[bed]anull[aout]")
        output_path = folder / f"final-montage-{uuid4().hex}.mp4"
        command.extend([
            "-filter_complex", ";".join(filters), "-map", "[vcat]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{total:.3f}", str(output_path),
        ])
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1800, check=False)
        if completed.returncode != 0 or not output_path.exists() or output_path.stat().st_size <= 0:
            message = (completed.stderr or b"").decode("utf-8", "ignore")[-1600:]
            raise RuntimeError("grid_montage_failed: " + message)
        url = put_file(output_path, generated_key("videos", output_path.name), "video/mp4")
        return {"ok": True, "type": "video", "video_url": url, "url": url, "duration": round(total, 3), "provider": "local-ffmpeg", "model": "final_montage"}
