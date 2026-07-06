import os
import json
import re
import requests
import httpx


VIDEO_MODEL_CONFIG = {
    "seedance_2_fast": {"provider": "bytedance", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": False, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "seedance_2_0": {"provider": "bytedance", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": False, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "seedance_1_5_pro": {"provider": "bytedance", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": False, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "heygen_v3_video_agent": {"provider": "heygen", "modes": ["text_to_video"], "durations": [5], "ratios": ["16:9", "9:16"], "resolutions": ["720p", "1080p"], "sound": True, "start_image": False, "end_image": False, "video_upload": False, "video_edit": False},
    "luma_ray_v3_2": {"provider": "luma", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": False, "start_image": True, "end_image": True, "video_upload": False, "video_edit": False},
    "luma_dream_machine": {"provider": "luma", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p"], "sound": False, "start_image": True, "end_image": True, "video_upload": False, "video_edit": False},
    "kling_motion_2_6": {"provider": "kling", "modes": ["motion_control", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": True, "start_image": True, "end_image": True, "video_upload": False, "video_edit": False},
    "kling_motion_3_0": {"provider": "kling", "modes": ["motion_control", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": True, "start_image": True, "end_image": True, "video_upload": False, "video_edit": False},
    "kling_3_0": {"provider": "kling", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": True, "start_image": True, "end_image": True, "video_upload": False, "video_edit": False},
    "kling_o3_omni": {"provider": "kling", "modes": ["text_to_video", "image_to_video", "motion_control"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": True, "start_image": True, "end_image": True, "video_upload": False, "video_edit": False},
    "kling_o3_edit": {"provider": "kling", "modes": ["video_edit"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": True, "start_image": False, "end_image": False, "video_upload": True, "video_edit": True},
    "runway_aleph": {"provider": "runway", "modes": ["video_edit", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": False, "start_image": True, "end_image": True, "video_upload": True, "video_edit": True},
    "runway_gen": {"provider": "runway", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": False, "start_image": True, "end_image": True, "video_upload": False, "video_edit": False},
    "minimax_hailuo_2_3": {"provider": "minimax", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": False, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "pixverse_v6": {"provider": "pixverse", "modes": ["text_to_video", "image_to_video"], "durations": [5, 8], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": False, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "sora_2": {"provider": "sora", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p"], "sound": True, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "sora_2_pro": {"provider": "sora", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": True, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "veo_3_1": {"provider": "veo", "modes": ["text_to_video", "image_to_video"], "durations": [5, 8], "ratios": ["16:9", "9:16"], "resolutions": ["720p", "1080p"], "sound": True, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "veo_3_1_fast": {"provider": "veo", "modes": ["text_to_video", "image_to_video"], "durations": [5, 8], "ratios": ["16:9", "9:16"], "resolutions": ["720p"], "sound": True, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "gemini_omni_flash": {"provider": "veo", "modes": ["text_to_video", "image_to_video"], "durations": [5, 8], "ratios": ["16:9", "9:16"], "resolutions": ["720p", "1080p"], "sound": True, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "wan_2_7": {"provider": "wan", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": False, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "wan_2_7_edit": {"provider": "wan", "modes": ["video_edit"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": False, "start_image": False, "end_image": False, "video_upload": True, "video_edit": True},
    "wan_2_6": {"provider": "wan", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p"], "sound": False, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "grok_video": {"provider": "grok", "modes": ["text_to_video"], "durations": [5], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p"], "sound": True, "start_image": False, "end_image": False, "video_upload": False, "video_edit": False},
    "grok_video_edit": {"provider": "grok", "modes": ["video_edit"], "durations": [5], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p"], "sound": True, "start_image": False, "end_image": False, "video_upload": True, "video_edit": True},
}

BYTEPLUS_SEEDANCE_MODEL_MAP = {
    "seedance_2_fast": os.getenv("BYTEPLUS_SEEDANCE_2_FAST_MODEL", "dreamina-seedance-2-0-fast-260128"),
    "seedance_2_0": os.getenv("BYTEPLUS_SEEDANCE_2_MODEL", "dreamina-seedance-2-0-260128"),
}

_seedance_1_5_pro_model = os.getenv("BYTEPLUS_SEEDANCE_1_5_PRO_MODEL")
if _seedance_1_5_pro_model:
    BYTEPLUS_SEEDANCE_MODEL_MAP["seedance_1_5_pro"] = _seedance_1_5_pro_model

for _provider_model_id in tuple(BYTEPLUS_SEEDANCE_MODEL_MAP.values()):
    BYTEPLUS_SEEDANCE_MODEL_MAP.setdefault(_provider_model_id, _provider_model_id)


def _get_env(*names):
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _normalize_video_urls(data):
    if not data:
        return []
    if isinstance(data, str):
        return [data] if data.strip() else []
    if isinstance(data, list):
        urls = []
        for item in data:
            if isinstance(item, str) and item.strip():
                urls.append(item.strip())
            elif isinstance(item, dict):
                urls.extend(_normalize_video_urls(item))
        return urls
    if isinstance(data, dict):
        candidates = []
        for key in (
            "video_url", "videoUrl", "url", "href", "src", "download_url",
            "asset_url", "output_url", "result_url", "file_url",
        ):
            value = data.get(key)
            if isinstance(value, str):
                candidates.append(value)
        for key in ("video", "output", "outputs", "result", "results", "data", "assets", "files"):
            value = data.get(key)
            if isinstance(value, (dict, list, str)):
                candidates.extend(_normalize_video_urls(value))
        urls = [c.strip() for c in candidates if isinstance(c, str) and c.strip() and re.match(r"^(https?://|data:video)", c.strip(), re.I)]
        return urls
    return []


def _first_value(data, keys):
    if not isinstance(data, dict):
        return None
    for key in keys:
        if data.get(key):
            return data.get(key)
    for value in data.values():
        if isinstance(value, dict):
            found = _first_value(value, keys)
            if found:
                return found
    return None


def _task_id_from_response(data):
    value = _first_value(data, ("task_id", "taskId", "id", "generation_id", "generationId", "operation", "name"))
    return str(value) if value else None


def _map_seedance_video_model_to_provider_model(frontend_model: str):
    value = (frontend_model or "").strip()
    if not value:
        return None
    normalized = value.lower()
    return BYTEPLUS_SEEDANCE_MODEL_MAP.get(normalized) or BYTEPLUS_SEEDANCE_MODEL_MAP.get(normalized.replace("-", "_"))


def _unknown_seedance_video_model_response(frontend_model: str):
    return {
        "ok": False,
        "type": "video",
        "error": "Unknown BytePlus video model mapping",
        "frontend_model": frontend_model or "",
        "provider": "bytedance",
    }


def _provider_processing(provider: str, model_id: str, data: dict, endpoint: str):
    task_id = _task_id_from_response(data)
    poll_url = data.get("poll_url") or data.get("status_url") if isinstance(data, dict) else None
    if not poll_url and task_id:
        poll_url = endpoint.rstrip("/") + "/" + task_id
    return _provider_success(provider, model_id, [], status="processing", task_id=task_id, poll_url=poll_url)


def _size_for_video(ratio: str, resolution: str):
    res = str(resolution or "720p").lower()
    if ratio == "9:16":
        return "1080x1920" if "1080" in res else "720x1280"
    if ratio == "1:1":
        return "1024x1024"
    return "1920x1080" if "1080" in res else "1280x720"


def _runway_ratio(ratio: str, resolution: str):
    size = _size_for_video(ratio, resolution)
    return size.replace("x", ":")


def _openai_sora_model(model_id: str):
    return "sora-2-pro" if "pro" in (model_id or "").lower() else "sora-2"


def _openai_sora_seconds(duration):
    try:
        value = int(duration or 16)
    except Exception:
        value = 16
    return "20" if value >= 20 else "16"


def _veo_model(model_id: str):
    if "fast" in (model_id or "").lower():
        return os.getenv("VEO_FAST_MODEL", "veo-3.1-fast-generate-preview")
    if "gemini" in (model_id or "").lower():
        return os.getenv("GEMINI_VIDEO_MODEL", "veo-3.1-generate-preview")
    return os.getenv("VEO_MODEL", "veo-3.1-generate-preview")


def _request_json(url: str, headers: dict, payload: dict):
    return requests.post(url, headers=headers, json=payload, timeout=120)


def _request_get(url: str, headers: dict):
    return requests.get(url, headers=headers, timeout=60)


def _request_form(url: str, headers: dict, data: dict, files=None):
    return requests.post(url, headers=headers, data=data, files=files, timeout=120)


def _provider_for_model(model_id: str):
    value = (model_id or "").strip().lower()
    if value in VIDEO_MODEL_CONFIG:
        return VIDEO_MODEL_CONFIG[value].get("provider") or "sylvex-router"
    if not value:
        return "sylvex-router"
    if re.search(r"seedance", value):
        return "seedance"
    if re.search(r"heygen", value):
        return "heygen"
    if re.search(r"hedra", value):
        return "hedra"
    if re.search(r"sora", value):
        return "sora"
    if re.search(r"luma|dream_machine|ray", value):
        return "luma"
    if re.search(r"kling", value):
        return "kling"
    if re.search(r"runway", value):
        return "runway"
    if re.search(r"minimax|hailuo", value):
        return "minimax"
    if re.search(r"pixverse", value):
        return "pixverse"
    if re.search(r"veo|gemini", value):
        return "veo"
    if re.search(r"wan", value):
        return "wan"
    if re.search(r"grok", value):
        return "grok"
    return "sylvex-router"


def _defaults_for_model(model_id: str):
    config = VIDEO_MODEL_CONFIG.get((model_id or "").strip(), {})
    return {
        "provider": config.get("provider") or "sylvex-router",
        "duration": (config.get("durations") or [5])[0],
        "ratio": (config.get("ratios") or ["16:9"])[0],
        "resolution": (config.get("resolutions") or ["720p"])[0],
        "sound": bool(config.get("sound")),
        "mode": (config.get("modes") or ["text_to_video"])[0],
    }


def _coerce_supported(value, supported, fallback):
    return value if value in supported else fallback


def _build_video_payload(model_id: str, prompt: str, payload: dict):
    opts = payload.get("video_options") or payload.get("options") or {}
    defaults = _defaults_for_model(model_id)
    config = VIDEO_MODEL_CONFIG.get(model_id, {})
    durations = config.get("durations") or [defaults.get("duration") or 5]
    ratios = config.get("ratios") or [defaults.get("ratio") or "16:9"]
    resolutions = config.get("resolutions") or [defaults.get("resolution") or "720p"]
    modes = config.get("modes") or [defaults.get("mode") or "text_to_video"]

    duration = int(opts.get("duration") or payload.get("duration") or defaults.get("duration") or 5)
    if duration not in durations:
        duration = durations[0]
    ratio = _coerce_supported(opts.get("ratio") or payload.get("ratio") or defaults.get("ratio") or "16:9", ratios, ratios[0])
    resolution = _coerce_supported(opts.get("resolution") or payload.get("resolution") or defaults.get("resolution") or "720p", resolutions, resolutions[0])
    quality = opts.get("quality") or payload.get("quality") or defaults.get("quality") or "standard"
    mode = _coerce_supported(
        opts.get("generation_mode") or opts.get("mode") or payload.get("mode") or defaults.get("mode") or "text_to_video",
        modes,
        modes[0],
    )
    reference_images = opts.get("reference_images") or opts.get("referenceImageUrls") or []
    if not reference_images and isinstance(payload.get("reference_images"), list):
        reference_images = payload.get("reference_images")
    sound = bool(opts.get("sound")) if config.get("sound") else False
    return {
        "model": model_id,
        "prompt": prompt,
        "duration": duration,
        "ratio": ratio,
        "resolution": resolution,
        "quality": quality,
        "mode": mode,
        "generation_mode": mode,
        "section": opts.get("section") or "generate",
        "sound": sound,
        "start_image": opts.get("start_image") or (reference_images[0] if reference_images else ""),
        "end_image": opts.get("end_image") or "",
        "reference_images": reference_images,
        "input_video": opts.get("input_video") or "",
        "video_url": opts.get("video_url") or "",
        "image_url": opts.get("image_url") or "",
        "motion_preset": opts.get("motion_preset") or "",
        "character_image": opts.get("character_image") or "",
        "advanced": opts.get("advanced") or {},
        "telegram_id": payload.get("telegram_id"),
    }


def _byteplus_ark_base_url():
    return (
        os.getenv("BYTEPLUS_ARK_BASE_URL")
        or os.getenv("BYTEPLUS_ARK_ENDPOINT", "https://ark.ap-southeast.bytepluses.com/api/v3")
    ).rstrip("/")


def _byteplus_project():
    return os.getenv("BYTEPLUS_PROJECT", "default")


def _seedance_headers(api_key: str):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    project = _byteplus_project()
    if project:
        headers["X-Project-Name"] = project
    return headers


def _seedance_submit_endpoint():
    return os.getenv("BYTEDANCE_VIDEO_ENDPOINT") or os.getenv(
        "BYTEPLUS_SEEDANCE_TASK_ENDPOINT",
        f"{_byteplus_ark_base_url()}/contents/generations/tasks",
    )


def _seedance_status_endpoint(task_id: str):
    template = os.getenv("BYTEPLUS_SEEDANCE_STATUS_URL_TEMPLATE")
    if template:
        return template.format(task_id=task_id)
    return f"{_byteplus_ark_base_url()}/contents/generations/tasks/{task_id}"


def _seedance_resolution_for_model(provider_model: str, resolution: str):
    value = str(resolution or "720p").strip().lower()
    if value not in {"480p", "720p", "1080p", "4k"}:
        value = "720p"
    if provider_model in {
        BYTEPLUS_SEEDANCE_MODEL_MAP.get("seedance_2_fast"),
        os.getenv("BYTEPLUS_SEEDANCE_2_MINI_MODEL", "dreamina-seedance-2-0-mini-260615"),
    } and value in {"1080p", "4k"}:
        return None
    return value


def _seedance_ratio(body: dict):
    ratio = str(body.get("ratio") or "16:9").replace("_", ":")
    if body.get("start_image") and ratio in {"auto", "adaptive"}:
        return "adaptive"
    if ratio in {"21:9", "16:9", "4:3", "1:1", "3:4", "9:16"}:
        return ratio
    return "16:9"


def _seedance_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _seedance_reference_content(content: list, media_type: str, urls: list):
    role_by_type = {
        "image_url": "reference_image",
        "video_url": "reference_video",
        "audio_url": "reference_audio",
    }
    for url in dict.fromkeys([u for u in urls if isinstance(u, str) and u.strip()]):
        content.append({
            "type": media_type,
            media_type: {"url": url},
            "role": role_by_type[media_type],
        })


def _seedance_body(frontend_model: str, prompt: str, payload: dict):
    provider_model = _map_seedance_video_model_to_provider_model(frontend_model)
    if not provider_model:
        return None

    body = _build_video_payload(frontend_model, prompt, payload)
    content = [{"type": "text", "text": prompt}]
    image_refs = []
    if body.get("start_image"):
        image_refs.append(body.get("start_image"))
    image_refs.extend(body.get("reference_images") or [])
    if body.get("image_url"):
        image_refs.append(body.get("image_url"))
    if body.get("character_image"):
        image_refs.append(body.get("character_image"))

    video_refs = []
    if body.get("input_video"):
        video_refs.append(body.get("input_video"))
    if body.get("video_url"):
        video_refs.append(body.get("video_url"))

    _seedance_reference_content(content, "image_url", image_refs)
    _seedance_reference_content(content, "video_url", video_refs)

    seedance_payload = {
        "model": provider_model,
        "content": content,
        "duration": int(body.get("duration") or 5),
        "ratio": _seedance_ratio(body),
        "generate_audio": _seedance_bool((payload.get("video_options") or {}).get("sound"), default=True),
        "watermark": False,
        "safety_identifier": str(body.get("telegram_id") or payload.get("telegram_id") or "sylvex-prostudio"),
    }
    resolution = _seedance_resolution_for_model(provider_model, body.get("resolution"))
    if resolution:
        seedance_payload["resolution"] = resolution
    return seedance_payload


def _seedance_extract_video_url(data: dict):
    result = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(result, dict):
        return None
    content = result.get("content") if isinstance(result.get("content"), dict) else {}
    video = result.get("video")
    video_url = video.get("url") if isinstance(video, dict) else video
    return (
        video_url
        or content.get("video_url")
        or result.get("video_url")
        or result.get("url")
        or (result.get("assets") or {}).get("video")
    )


def _seedance_status(data: dict):
    result = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(result, dict):
        return ""
    return str(result.get("status") or result.get("state") or "").lower()


def _seedance_poll_task(task_id: str, headers: dict):
    endpoint = _seedance_status_endpoint(task_id)
    response = _request_get(endpoint, headers)
    data = _safe_provider_json_response(response, "bytedance", endpoint)
    status = getattr(response, "status_code", None) or 0
    if status >= 400 or data.get("ok") is False:
        return _provider_parse_error("bytedance", task_id, data)
    state = _seedance_status(data)
    video_url = _seedance_extract_video_url(data)
    if state in {"succeeded", "completed", "success", "done"} and video_url:
        return _provider_success("bytedance", task_id, [video_url], status="completed", task_id=task_id)
    if state in {"failed", "error", "cancelled"}:
        return _provider_parse_error("bytedance", task_id, data)
    return _provider_success(
        "bytedance",
        task_id,
        [],
        status="processing",
        task_id=task_id,
        poll_url=endpoint,
    )


async def _send_generated_videos_to_telegram(telegram_id: int, videos: list[str], caption: str = ""):
    bot_token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return False
    if not telegram_id or not videos:
        return False

    sent_any = False
    async with httpx.AsyncClient(timeout=120.0) as client:
        for index, video_url in enumerate(videos):
            try:
                video_response = await client.get(video_url)
                if video_response.status_code >= 400 or not video_response.content:
                    continue
                content_type = video_response.headers.get("content-type") or "video/mp4"
                ext = ".mp4" if "mp4" in content_type else ".bin"
                filename = f"sylvex-video-{index + 1}{ext}"
                data = {"chat_id": str(telegram_id), "caption": caption if index == 0 else ""}
                files = {"video": (filename, video_response.content, content_type)}
                tg_response = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendVideo",
                    data=data,
                    files=files,
                )
                if tg_response.status_code < 400:
                    sent_any = True
            except Exception:
                continue
    return sent_any


def _provider_error(provider: str, model_id: str, detail: str):
    return {
        "ok": False,
        "type": "video",
        "provider": provider,
        "model": model_id,
        "error": detail,
    }


async def safe_provider_json_response(response, provider: str, endpoint: str):
    status = getattr(response, "status_code", None) or getattr(response, "status", None)

    try:
        text = response.text
        if callable(text):
            text = text()
    except Exception:
        try:
            text = await response.text()
        except Exception:
            text = ""

    if not text:
        return {
            "ok": False,
            "provider": provider,
            "status_code": status,
            "error": "Provider returned empty response",
            "endpoint": endpoint,
            "body_preview": "",
        }

    try:
        return json.loads(text)
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider,
            "status_code": status,
            "error": "Provider returned non-JSON response",
            "details": str(exc),
            "endpoint": endpoint,
            "body_preview": text[:1000],
        }


def _safe_provider_json_response(response, provider: str, endpoint: str):
    status = getattr(response, "status_code", None) or getattr(response, "status", None)

    try:
        text = response.text
        if callable(text):
            text = text()
    except Exception:
        text = ""

    if not text:
        return {
            "ok": False,
            "provider": provider,
            "status_code": status,
            "error": "Provider returned empty response",
            "endpoint": endpoint,
            "body_preview": "",
        }

    try:
        return json.loads(text)
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider,
            "status_code": status,
            "error": "Provider returned non-JSON response",
            "details": str(exc),
            "endpoint": endpoint,
            "body_preview": text[:1000],
        }


def _provider_parse_error(provider: str, model_id: str, data: dict):
    result = {
        "ok": False,
        "type": "video",
        "provider": provider,
        "model": model_id,
        "error": data.get("error") or "Provider returned invalid response",
    }
    for key in ("status_code", "details", "endpoint", "body_preview"):
        if key in data:
            result[key] = data.get(key)
    return result


def _provider_success(provider: str, model_id: str, video_urls: list[str], status: str = "completed", task_id: str = None, poll_url: str = None):
    result = {
        "ok": True,
        "type": "video",
        "provider": provider,
        "model": model_id,
        "status": status,
        "videos": video_urls,
        "video_url": video_urls[0] if video_urls else None,
    }
    if task_id:
        result["task_id"] = task_id
    if poll_url:
        result["poll_url"] = poll_url
    return result


def _provider_result_from_response(provider: str, model_id: str, response, endpoint: str):
    data = _safe_provider_json_response(response, provider, endpoint)
    status = getattr(response, "status_code", None) or getattr(response, "status", None) or 0
    if status >= 400 or data.get("ok") is False:
        return _provider_parse_error(provider, model_id, data)
    urls = _normalize_video_urls(data)
    if urls:
        return _provider_success(provider, model_id, urls)
    if _task_id_from_response(data):
        return _provider_processing(provider, model_id, data, endpoint)
    return _provider_error(provider, model_id, "Provider returned no video URL or task id")


def _telegram_caption(model_id: str, provider: str, payload: dict):
    opts = _build_video_payload(model_id, payload.get("prompt") or "", payload)
    sound = "вкл" if opts.get("sound") else "выкл"
    return (
        "SYLVEX Pro Studio\n"
        "Видео готово\n\n"
        f"Модель: {model_id}\n"
        f"Провайдер: {provider}\n"
        f"Режим: {opts.get('mode')}\n"
        f"Формат: {opts.get('ratio')}\n"
        f"Разрешение: {opts.get('resolution')}\n"
        f"Длительность: {opts.get('duration')} сек\n"
        f"Звук: {sound}"
    )


def _call_seedance(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("BYTEDANCE_API_KEY", "BYTEPLUS_ARK_API_KEY")
    if not api_key:
        return _provider_error("seedance", model_id, "Provider API key is missing: BYTEDANCE_API_KEY")
    body = _seedance_body(model_id, prompt, payload)
    if not body:
        return _unknown_seedance_video_model_response(model_id)
    try:
        endpoint = _seedance_submit_endpoint()
        headers = _seedance_headers(api_key)
        response = _request_json(
            endpoint,
            headers,
            body,
        )
        data = _safe_provider_json_response(response, "bytedance", endpoint)
        status = getattr(response, "status_code", None) or 0
        if status not in (200, 201, 202) or data.get("ok") is False:
            return _provider_parse_error("bytedance", model_id, data)
        video_urls = _normalize_video_urls(data)
        if video_urls:
            return _provider_success("bytedance", model_id, video_urls)
        task_id = _task_id_from_response(data)
        if not task_id:
            return _provider_error("bytedance", model_id, "Seedance task id not found")
        poll_url = _seedance_status_endpoint(task_id)
        if os.getenv("BYTEPLUS_SEEDANCE_POLL_ON_SUBMIT", "").strip().lower() in {"1", "true", "yes", "on"}:
            polled = _seedance_poll_task(task_id, headers)
            polled["model"] = model_id
            polled["provider_model"] = body.get("model")
            return polled
        result = _provider_success("bytedance", model_id, [], status="processing", task_id=task_id, poll_url=poll_url)
        result["provider_model"] = body.get("model")
        return result
    except Exception as exc:
        return _provider_error("bytedance", model_id, f"Provider request failed: {exc}")


def _call_heygen(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("HEYGEN_API_KEY")
    if not api_key:
        return _provider_error("heygen", model_id, "Provider API key is missing: HEYGEN_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    body.update({
        "prompt": prompt,
        "model": os.getenv("HEYGEN_VIDEO_MODEL", model_id),
        "caption": False,
    })
    if os.getenv("HEYGEN_AVATAR_ID"):
        body["avatar_id"] = os.getenv("HEYGEN_AVATAR_ID")
    if os.getenv("HEYGEN_VOICE_ID"):
        body["voice_id"] = os.getenv("HEYGEN_VOICE_ID")
    try:
        endpoint = os.getenv("HEYGEN_VIDEO_ENDPOINT", f"{os.getenv('HEYGEN_BASE_URL', 'https://api.heygen.com/v3').rstrip('/')}/video/generate")
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "x-api-key": api_key, "Content-Type": "application/json"},
            body,
        )
        return _provider_result_from_response("heygen", model_id, response, endpoint)
    except Exception as exc:
        return _provider_error("heygen", model_id, f"Provider request failed: {exc}")


def _call_luma(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("LUMA_API_KEY")
    if not api_key:
        return _provider_error("luma", model_id, "Provider API key is missing: LUMA_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    body.update({"prompt": prompt, "model": model_id})
    try:
        endpoint = os.getenv("LUMA_API_ENDPOINT", "https://api.lumalabs.ai/dream-machine/v1/generations")
        luma_body = {
            "prompt": prompt,
            "aspect_ratio": body.get("ratio") or "16:9",
            "model": os.getenv("LUMA_VIDEO_MODEL", "ray-2"),
        }
        if body.get("start_image"):
            luma_body["keyframes"] = {"frame0": {"type": "image", "url": body.get("start_image")}}
        if body.get("end_image"):
            luma_body.setdefault("keyframes", {})["frame1"] = {"type": "image", "url": body.get("end_image")}
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            luma_body,
        )
        return _provider_result_from_response("luma", model_id, response, endpoint)
    except Exception as exc:
        return _provider_error("luma", model_id, f"Provider request failed: {exc}")


def _call_kling(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("KLING_API_KEY", "KLING_ACCESS_KEY")
    if not api_key:
        return _provider_error("kling", model_id, "Provider API key is missing: KLING_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    body.update({"prompt": prompt, "model": model_id})
    try:
        endpoint = os.getenv("KLING_API_ENDPOINT", "https://api.klingai.com/v1/videos/generations")
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body,
        )
        return _provider_result_from_response("kling", model_id, response, endpoint)
    except Exception as exc:
        return _provider_error("kling", model_id, f"Provider request failed: {exc}")


def _call_runway(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("RUNWAY_API_KEY")
    if not api_key:
        return _provider_error("runway", model_id, "Provider API key is missing: RUNWAY_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    try:
        endpoint = os.getenv("RUNWAY_API_ENDPOINT", "https://api.dev.runwayml.com/v1/image_to_video")
        runway_body = {
            "model": os.getenv("RUNWAY_VIDEO_MODEL", "gen4_turbo" if model_id == "runway_gen" else "aleph"),
            "promptText": prompt,
            "ratio": _runway_ratio(body.get("ratio"), body.get("resolution")),
            "duration": int(body.get("duration") or 5),
        }
        if body.get("start_image"):
            runway_body["promptImage"] = body.get("start_image")
        if body.get("input_video"):
            runway_body["videoUri"] = body.get("input_video")
        response = _request_json(
            endpoint,
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-Runway-Version": os.getenv("RUNWAY_API_VERSION", "2024-11-06"),
            },
            runway_body,
        )
        return _provider_result_from_response("runway", model_id, response, endpoint)
    except Exception as exc:
        return _provider_error("runway", model_id, f"Provider request failed: {exc}")


def _call_minimax(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("MINIMAX_API_KEY")
    if not api_key:
        return _provider_error("minimax", model_id, "Provider API key is missing: MINIMAX_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    minimax_body = {
        "model": os.getenv("MINIMAX_VIDEO_MODEL", model_id),
        "prompt": prompt,
        "duration": int(body.get("duration") or 5),
        "resolution": body.get("resolution") or "720p",
        "aspect_ratio": body.get("ratio") or "16:9",
    }
    if body.get("start_image"):
        minimax_body["first_frame_image"] = body.get("start_image")
    try:
        endpoint = os.getenv("MINIMAX_API_ENDPOINT", "https://api.minimax.io/v1/video/generation")
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            minimax_body,
        )
        return _provider_result_from_response("minimax", model_id, response, endpoint)
    except Exception as exc:
        return _provider_error("minimax", model_id, f"Provider request failed: {exc}")


def _call_pixverse(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("PIXVERSE_API_KEY")
    if not api_key:
        return _provider_error("pixverse", model_id, "Provider API key is missing: PIXVERSE_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    pixverse_body = {
        "model": os.getenv("PIXVERSE_VIDEO_MODEL", model_id),
        "prompt": prompt,
        "aspect_ratio": body.get("ratio") or "16:9",
        "duration": int(body.get("duration") or 5),
        "quality": body.get("resolution") or body.get("quality") or "720p",
    }
    if body.get("start_image"):
        pixverse_body["image_url"] = body.get("start_image")
    try:
        endpoint = os.getenv("PIXVERSE_API_ENDPOINT", "https://api.pixverse.io/v1/videos/generations")
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            pixverse_body,
        )
        return _provider_result_from_response("pixverse", model_id, response, endpoint)
    except Exception as exc:
        return _provider_error("pixverse", model_id, f"Provider request failed: {exc}")


def _call_sora(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("OPENAI_API_KEY")
    if not api_key:
        return _provider_error("sora", model_id, "Provider API key is missing: OPENAI_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    try:
        endpoint = f"{os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1').rstrip('/')}/videos"
        form = {
            "model": _openai_sora_model(model_id),
            "prompt": prompt,
            "size": _size_for_video(body.get("ratio"), body.get("resolution")),
            "seconds": _openai_sora_seconds(body.get("duration")),
        }
        response = _request_form(
            endpoint,
            {"Authorization": f"Bearer {api_key}"},
            form,
        )
        return _provider_result_from_response("sora", model_id, response, endpoint)
    except Exception as exc:
        return _provider_error("sora", model_id, f"Provider request failed: {exc}")


def _call_veo(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("GOOGLE_API_KEY")
    if not api_key:
        return _provider_error("veo", model_id, "Provider API key is missing: GOOGLE_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    try:
        google_model = _veo_model(model_id)
        endpoint = os.getenv(
            "GOOGLE_VEO_ENDPOINT",
            f"https://generativelanguage.googleapis.com/v1beta/models/{google_model}:predictLongRunning",
        )
        veo_body = {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "aspectRatio": body.get("ratio") or "16:9",
                "durationSeconds": int(body.get("duration") or 5),
                "sampleCount": 1,
            },
        }
        if body.get("start_image"):
            veo_body["instances"][0]["image"] = {"url": body.get("start_image")}
        response = _request_json(
            endpoint,
            {"x-goog-api-key": api_key, "Content-Type": "application/json"},
            veo_body,
        )
        return _provider_result_from_response("veo", model_id, response, endpoint)
    except Exception as exc:
        return _provider_error("veo", model_id, f"Provider request failed: {exc}")


def _call_wan(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("ALIBABA_API_KEY", "QWEN_API_KEY")
    if not api_key:
        return _provider_error("wan", model_id, "Provider API key is missing: ALIBABA_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    wan_body = {
        "model": os.getenv("WAN_VIDEO_MODEL", model_id),
        "input": {"prompt": prompt},
        "parameters": {
            "duration": int(body.get("duration") or 5),
            "size": _size_for_video(body.get("ratio"), body.get("resolution")),
            "resolution": body.get("resolution") or "720p",
        },
    }
    if body.get("start_image"):
        wan_body["input"]["img_url"] = body.get("start_image")
    if body.get("input_video"):
        wan_body["input"]["video_url"] = body.get("input_video")
    try:
        endpoint = os.getenv("WAN_API_ENDPOINT", "https://dashscope.aliyuncs.com/api/v1/services/aigc/video/generation")
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "X-DashScope-Async": "enable"},
            wan_body,
        )
        return _provider_result_from_response("wan", model_id, response, endpoint)
    except Exception as exc:
        return _provider_error("wan", model_id, f"Provider request failed: {exc}")


def _call_grok(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("XAI_API_KEY")
    if not api_key:
        return _provider_error("grok", model_id, "Provider API key is missing: XAI_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    body.update({"prompt": prompt, "model": model_id})
    try:
        endpoint = os.getenv("XAI_VIDEO_ENDPOINT", "https://api.x.ai/v1/videos/generations")
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body,
        )
        return _provider_result_from_response("grok", model_id, response, endpoint)
    except Exception as exc:
        return _provider_error("grok", model_id, f"Provider request failed: {exc}")


def _call_hedra(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("HEDRA_API_KEY")
    if not api_key:
        return _provider_error("hedra", model_id, "Provider API key is missing: HEDRA_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    body.update({"prompt": prompt, "model": model_id})
    try:
        endpoint = os.getenv("HEDRA_API_ENDPOINT", "https://api.hedra.com/v1/videos/generations")
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body,
        )
        return _provider_result_from_response("hedra", model_id, response, endpoint)
    except Exception as exc:
        return _provider_error("hedra", model_id, f"Provider request failed: {exc}")


async def video_generation(payload: dict) -> dict:
    prompt = (payload.get("prompt") or "").strip()
    model_id = (payload.get("model") or "seedance_2_fast").strip()
    provider = (payload.get("provider") or _provider_for_model(model_id) or "sylvex-router").strip().lower()

    if not prompt:
        return {"ok": False, "type": "video", "model": model_id, "provider": provider, "error": "Prompt is required"}

    if provider == "seedance" or re.search(r"seedance", model_id, re.I):
        result = _call_seedance(model_id, prompt, payload)
    elif provider == "heygen" or re.search(r"heygen", model_id, re.I):
        result = _call_heygen(model_id, prompt, payload)
    elif provider == "hedra" or re.search(r"hedra", model_id, re.I):
        result = _call_hedra(model_id, prompt, payload)
    elif provider == "sora" or re.search(r"sora", model_id, re.I):
        result = _call_sora(model_id, prompt, payload)
    elif provider == "luma" or re.search(r"luma|dream_machine|ray", model_id, re.I):
        result = _call_luma(model_id, prompt, payload)
    elif provider == "kling" or re.search(r"kling", model_id, re.I):
        result = _call_kling(model_id, prompt, payload)
    elif provider == "runway" or re.search(r"runway", model_id, re.I):
        result = _call_runway(model_id, prompt, payload)
    elif provider == "minimax" or re.search(r"minimax|hailuo", model_id, re.I):
        result = _call_minimax(model_id, prompt, payload)
    elif provider == "pixverse" or re.search(r"pixverse", model_id, re.I):
        result = _call_pixverse(model_id, prompt, payload)
    elif provider == "veo" or re.search(r"veo|gemini", model_id, re.I):
        result = _call_veo(model_id, prompt, payload)
    elif provider == "wan" or re.search(r"wan", model_id, re.I):
        result = _call_wan(model_id, prompt, payload)
    elif provider == "grok" or re.search(r"grok", model_id, re.I):
        result = _call_grok(model_id, prompt, payload)
    else:
        result = _provider_error(provider, model_id, f"Unsupported video provider: {provider}")

    if result.get("ok") and result.get("videos"):
        telegram_id = int(payload.get("telegram_id") or 0)
        sent_to_telegram = False
        if telegram_id:
            try:
                sent_to_telegram = await _send_generated_videos_to_telegram(
                    telegram_id=telegram_id,
                    videos=result.get("videos", []),
                    caption=_telegram_caption(model_id, result.get("provider") or provider, payload),
                )
            except Exception as exc:
                print("TELEGRAM SEND GENERATED VIDEOS FAILED:", str(exc))
        result["sent_to_telegram"] = sent_to_telegram
    return result
