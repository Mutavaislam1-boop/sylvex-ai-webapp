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
                url = item.get("url") or item.get("video_url") or item.get("href") or item.get("src") or ""
                if url:
                    urls.append(url)
        return urls
    if isinstance(data, dict):
        candidates = [
            data.get("video_url"),
            data.get("url"),
            data.get("href"),
            data.get("src"),
            data.get("video"),
        ]
        urls = [c for c in candidates if isinstance(c, str) and c.strip()]
        return urls
    return []


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


def _provider_success(provider: str, model_id: str, video_urls: list[str], status: str = "completed", task_id: str = None):
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
    return result


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


def _request_json(url: str, headers: dict, payload: dict):
    return requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)


def _call_seedance(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("BYTEDANCE_API_KEY", "BYTEPLUS_ARK_API_KEY")
    if not api_key:
        return _provider_error("seedance", model_id, "Provider API key is missing: BYTEDANCE_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    body.update({"prompt": prompt, "model": model_id})
    try:
        endpoint = f"{os.getenv('BYTEPLUS_ARK_ENDPOINT', 'https://ark.ap-southeast.bytepluses.com/api/v3').rstrip('/')}/videos/generations"
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body,
        )
        if response.status_code >= 400:
            data = _safe_provider_json_response(response, "seedance", endpoint)
            return _provider_parse_error("seedance", model_id, data)
        data = _safe_provider_json_response(response, "seedance", endpoint)
        if data.get("ok") is False:
            return _provider_parse_error("seedance", model_id, data)
        urls = _normalize_video_urls(data.get("data") or data.get("videos") or data.get("output") or data)
        if urls:
            return _provider_success("seedance", model_id, urls)
        if data.get("task_id") or data.get("id"):
            return _provider_success("seedance", model_id, [], status="processing", task_id=str(data.get("task_id") or data.get("id")))
        return _provider_error("seedance", model_id, "Provider returned no video URL")
    except Exception as exc:
        return _provider_error("seedance", model_id, f"Provider request failed: {exc}")


def _call_heygen(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("HEYGEN_API_KEY")
    if not api_key:
        return _provider_error("heygen", model_id, "Provider API key is missing: HEYGEN_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    body.update({"prompt": prompt})
    try:
        endpoint = f"{os.getenv('HEYGEN_BASE_URL', 'https://api.heygen.com/v3').rstrip('/')}/video/generate"
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body,
        )
        if response.status_code >= 400:
            data = _safe_provider_json_response(response, "heygen", endpoint)
            return _provider_parse_error("heygen", model_id, data)
        data = _safe_provider_json_response(response, "heygen", endpoint)
        if data.get("ok") is False:
            return _provider_parse_error("heygen", model_id, data)
        urls = _normalize_video_urls(data.get("data") or data.get("videos") or data.get("video") or data)
        if urls:
            return _provider_success("heygen", model_id, urls)
        if data.get("task_id") or data.get("id"):
            return _provider_success("heygen", model_id, [], status="processing", task_id=str(data.get("task_id") or data.get("id")))
        return _provider_error("heygen", model_id, "Provider returned no video URL")
    except Exception as exc:
        return _provider_error("heygen", model_id, f"Provider request failed: {exc}")


def _call_luma(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("LUMA_API_KEY")
    if not api_key:
        return _provider_error("luma", model_id, "Provider API key is missing: LUMA_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    body.update({"prompt": prompt, "model": model_id})
    try:
        endpoint = "https://api.lumalabs.ai/dream-machine/v1/generations"
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body,
        )
        if response.status_code >= 400:
            data = _safe_provider_json_response(response, "luma", endpoint)
            return _provider_parse_error("luma", model_id, data)
        data = _safe_provider_json_response(response, "luma", endpoint)
        if data.get("ok") is False:
            return _provider_parse_error("luma", model_id, data)
        urls = _normalize_video_urls(data.get("videos") or data.get("video") or data.get("data") or data)
        if urls:
            return _provider_success("luma", model_id, urls)
        if data.get("task_id") or data.get("id"):
            return _provider_success("luma", model_id, [], status="processing", task_id=str(data.get("task_id") or data.get("id")))
        return _provider_error("luma", model_id, "Provider returned no video URL")
    except Exception as exc:
        return _provider_error("luma", model_id, f"Provider request failed: {exc}")


def _call_kling(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("KLING_API_KEY", "KLING_ACCESS_KEY")
    if not api_key:
        return _provider_error("kling", model_id, "Provider API key is missing: KLING_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    body.update({"prompt": prompt, "model": model_id})
    try:
        endpoint = "https://api.klingai.com/v1/videos/generations"
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body,
        )
        if response.status_code >= 400:
            data = _safe_provider_json_response(response, "kling", endpoint)
            return _provider_parse_error("kling", model_id, data)
        data = _safe_provider_json_response(response, "kling", endpoint)
        if data.get("ok") is False:
            return _provider_parse_error("kling", model_id, data)
        urls = _normalize_video_urls(data.get("videos") or data.get("video") or data.get("data") or data)
        if urls:
            return _provider_success("kling", model_id, urls)
        if data.get("task_id") or data.get("id"):
            return _provider_success("kling", model_id, [], status="processing", task_id=str(data.get("task_id") or data.get("id")))
        return _provider_error("kling", model_id, "Provider returned no video URL")
    except Exception as exc:
        return _provider_error("kling", model_id, f"Provider request failed: {exc}")


def _call_runway(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("RUNWAY_API_KEY")
    if not api_key:
        return _provider_error("runway", model_id, "Provider API key is missing: RUNWAY_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    body.update({"prompt": prompt, "model": model_id})
    try:
        endpoint = "https://api.runwayml.com/v1/video/generations"
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body,
        )
        if response.status_code >= 400:
            data = _safe_provider_json_response(response, "runway", endpoint)
            return _provider_parse_error("runway", model_id, data)
        data = _safe_provider_json_response(response, "runway", endpoint)
        if data.get("ok") is False:
            return _provider_parse_error("runway", model_id, data)
        urls = _normalize_video_urls(data.get("videos") or data.get("video") or data.get("data") or data)
        if urls:
            return _provider_success("runway", model_id, urls)
        if data.get("task_id") or data.get("id"):
            return _provider_success("runway", model_id, [], status="processing", task_id=str(data.get("task_id") or data.get("id")))
        return _provider_error("runway", model_id, "Provider returned no video URL")
    except Exception as exc:
        return _provider_error("runway", model_id, f"Provider request failed: {exc}")


def _call_minimax(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("MINIMAX_API_KEY")
    if not api_key:
        return _provider_error("minimax", model_id, "Provider API key is missing: MINIMAX_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    body.update({"prompt": prompt, "model": model_id})
    try:
        endpoint = "https://api.minimax.io/v1/video/generation"
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body,
        )
        if response.status_code >= 400:
            data = _safe_provider_json_response(response, "minimax", endpoint)
            return _provider_parse_error("minimax", model_id, data)
        data = _safe_provider_json_response(response, "minimax", endpoint)
        if data.get("ok") is False:
            return _provider_parse_error("minimax", model_id, data)
        urls = _normalize_video_urls(data.get("videos") or data.get("video") or data.get("data") or data)
        if urls:
            return _provider_success("minimax", model_id, urls)
        if data.get("task_id") or data.get("id"):
            return _provider_success("minimax", model_id, [], status="processing", task_id=str(data.get("task_id") or data.get("id")))
        return _provider_error("minimax", model_id, "Provider returned no video URL")
    except Exception as exc:
        return _provider_error("minimax", model_id, f"Provider request failed: {exc}")


def _call_pixverse(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("PIXVERSE_API_KEY")
    if not api_key:
        return _provider_error("pixverse", model_id, "Provider API key is missing: PIXVERSE_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    body.update({"prompt": prompt, "model": model_id})
    try:
        endpoint = "https://api.pixverse.io/v1/videos/generations"
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body,
        )
        if response.status_code >= 400:
            data = _safe_provider_json_response(response, "pixverse", endpoint)
            return _provider_parse_error("pixverse", model_id, data)
        data = _safe_provider_json_response(response, "pixverse", endpoint)
        if data.get("ok") is False:
            return _provider_parse_error("pixverse", model_id, data)
        urls = _normalize_video_urls(data.get("videos") or data.get("video") or data.get("data") or data)
        if urls:
            return _provider_success("pixverse", model_id, urls)
        if data.get("task_id") or data.get("id"):
            return _provider_success("pixverse", model_id, [], status="processing", task_id=str(data.get("task_id") or data.get("id")))
        return _provider_error("pixverse", model_id, "Provider returned no video URL")
    except Exception as exc:
        return _provider_error("pixverse", model_id, f"Provider request failed: {exc}")


def _call_sora(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("OPENAI_API_KEY")
    if not api_key:
        return _provider_error("sora", model_id, "Provider API key is missing: OPENAI_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    body.update({"prompt": prompt, "model": model_id})
    try:
        endpoint = f"{os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1').rstrip('/')}/videos/generations"
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body,
        )
        if response.status_code >= 400:
            data = _safe_provider_json_response(response, "sora", endpoint)
            return _provider_parse_error("sora", model_id, data)
        data = _safe_provider_json_response(response, "sora", endpoint)
        if data.get("ok") is False:
            return _provider_parse_error("sora", model_id, data)
        urls = _normalize_video_urls(data.get("videos") or data.get("video") or data.get("data") or data)
        if urls:
            return _provider_success("sora", model_id, urls)
        if data.get("task_id") or data.get("id"):
            return _provider_success("sora", model_id, [], status="processing", task_id=str(data.get("task_id") or data.get("id")))
        return _provider_error("sora", model_id, "Provider returned no video URL")
    except Exception as exc:
        return _provider_error("sora", model_id, f"Provider request failed: {exc}")


def _call_veo(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("GOOGLE_API_KEY")
    if not api_key:
        return _provider_error("veo", model_id, "Provider API key is missing: GOOGLE_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    body.update({"prompt": prompt, "model": model_id})
    try:
        endpoint = "https://generativelanguage.googleapis.com/v1beta/models/video:generate"
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body,
        )
        if response.status_code >= 400:
            data = _safe_provider_json_response(response, "veo", endpoint)
            return _provider_parse_error("veo", model_id, data)
        data = _safe_provider_json_response(response, "veo", endpoint)
        if data.get("ok") is False:
            return _provider_parse_error("veo", model_id, data)
        urls = _normalize_video_urls(data.get("videos") or data.get("video") or data.get("data") or data)
        if urls:
            return _provider_success("veo", model_id, urls)
        if data.get("task_id") or data.get("id"):
            return _provider_success("veo", model_id, [], status="processing", task_id=str(data.get("task_id") or data.get("id")))
        return _provider_error("veo", model_id, "Provider returned no video URL")
    except Exception as exc:
        return _provider_error("veo", model_id, f"Provider request failed: {exc}")


def _call_wan(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("ALIBABA_API_KEY", "QWEN_API_KEY")
    if not api_key:
        return _provider_error("wan", model_id, "Provider API key is missing: ALIBABA_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    body.update({"prompt": prompt, "model": model_id})
    try:
        endpoint = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video/generation"
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body,
        )
        if response.status_code >= 400:
            data = _safe_provider_json_response(response, "wan", endpoint)
            return _provider_parse_error("wan", model_id, data)
        data = _safe_provider_json_response(response, "wan", endpoint)
        if data.get("ok") is False:
            return _provider_parse_error("wan", model_id, data)
        urls = _normalize_video_urls(data.get("videos") or data.get("video") or data.get("data") or data)
        if urls:
            return _provider_success("wan", model_id, urls)
        if data.get("task_id") or data.get("id"):
            return _provider_success("wan", model_id, [], status="processing", task_id=str(data.get("task_id") or data.get("id")))
        return _provider_error("wan", model_id, "Provider returned no video URL")
    except Exception as exc:
        return _provider_error("wan", model_id, f"Provider request failed: {exc}")


def _call_grok(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("XAI_API_KEY")
    if not api_key:
        return _provider_error("grok", model_id, "Provider API key is missing: XAI_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    body.update({"prompt": prompt, "model": model_id})
    try:
        endpoint = "https://api.x.ai/v1/videos/generations"
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body,
        )
        if response.status_code >= 400:
            data = _safe_provider_json_response(response, "grok", endpoint)
            return _provider_parse_error("grok", model_id, data)
        data = _safe_provider_json_response(response, "grok", endpoint)
        if data.get("ok") is False:
            return _provider_parse_error("grok", model_id, data)
        urls = _normalize_video_urls(data.get("videos") or data.get("video") or data.get("data") or data)
        if urls:
            return _provider_success("grok", model_id, urls)
        if data.get("task_id") or data.get("id"):
            return _provider_success("grok", model_id, [], status="processing", task_id=str(data.get("task_id") or data.get("id")))
        return _provider_error("grok", model_id, "Provider returned no video URL")
    except Exception as exc:
        return _provider_error("grok", model_id, f"Provider request failed: {exc}")


def _call_hedra(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("HEDRA_API_KEY")
    if not api_key:
        return _provider_error("hedra", model_id, "Provider API key is missing: HEDRA_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    body.update({"prompt": prompt, "model": model_id})
    try:
        endpoint = "https://api.hedra.com/v1/videos/generations"
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            body,
        )
        if response.status_code >= 400:
            data = _safe_provider_json_response(response, "hedra", endpoint)
            return _provider_parse_error("hedra", model_id, data)
        data = _safe_provider_json_response(response, "hedra", endpoint)
        if data.get("ok") is False:
            return _provider_parse_error("hedra", model_id, data)
        urls = _normalize_video_urls(data.get("videos") or data.get("video") or data.get("data") or data)
        if urls:
            return _provider_success("hedra", model_id, urls)
        if data.get("task_id") or data.get("id"):
            return _provider_success("hedra", model_id, [], status="processing", task_id=str(data.get("task_id") or data.get("id")))
        return _provider_error("hedra", model_id, "Provider returned no video URL")
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
