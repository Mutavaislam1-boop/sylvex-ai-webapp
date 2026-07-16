import os
import json
import re
import time
import copy
import base64
import binascii
import pathlib
from uuid import uuid4
import requests
import httpx
from urllib.parse import urlparse

from services.error_translator import raw_error_text, translate_provider_error
from services.prompt_optimizer import optimize_prompt_for_model

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
WEBAPP_DIR = ROOT_DIR / "webapp"
GENERATED_VIDEOS_DIR = WEBAPP_DIR / "generated" / "videos"

VIDEO_MODEL_CONFIG = {
    "seedance_2_fast": {"provider": "bytedance", "modes": ["text_to_video", "image_to_video"], "durations": [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15], "ratios": ["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16", "21:9"], "resolutions": ["720p", "480p"], "sound": True, "start_image": True, "end_image": False, "video_input": True, "video_upload": True, "video_edit": False},
    "seedance_2_0": {"provider": "bytedance", "modes": ["text_to_video", "image_to_video"], "durations": [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15], "ratios": ["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16", "21:9"], "resolutions": ["720p", "480p", "1080p"], "sound": True, "start_image": True, "end_image": False, "video_input": True, "video_upload": True, "video_edit": False},
    "seedance_1_5_pro": {"provider": "bytedance", "modes": ["text_to_video", "image_to_video"], "durations": [4, 5, 6, 7, 8, 9, 10, 11, 12], "ratios": ["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16", "21:9"], "resolutions": ["720p", "480p", "1080p"], "sound": True, "start_image": True, "end_image": False, "video_input": True, "video_upload": True, "video_edit": False},
    "heygen_v3_video_agent": {"provider": "heygen", "modes": ["text_to_video"], "durations": [5], "ratios": ["16:9", "9:16"], "resolutions": ["720p", "1080p"], "sound": True, "start_image": False, "end_image": False, "video_upload": False, "video_edit": False},
    "heygen_avatar_iv": {"provider": "heygen", "modes": ["text_to_video"], "durations": [5], "ratios": ["auto", "16:9", "9:16", "4:5", "5:4", "1:1"], "resolutions": ["720p", "1080p"], "sound": True, "avatar": True, "start_image": False, "end_image": False, "video_upload": False, "video_edit": False},
    "heygen_avatar_v": {"provider": "heygen", "modes": ["text_to_video"], "durations": [5], "ratios": ["auto", "16:9", "9:16", "4:5", "5:4", "1:1"], "resolutions": ["720p", "1080p"], "sound": True, "avatar": True, "start_image": False, "end_image": False, "video_upload": False, "video_edit": False},
    "heygen_avatar_iii": {"provider": "heygen", "modes": ["text_to_video"], "durations": [5], "ratios": ["auto", "16:9", "9:16", "4:5", "5:4", "1:1"], "resolutions": ["720p", "1080p", "4k"], "sound": True, "avatar": True, "start_image": False, "end_image": False, "video_upload": False, "video_edit": False},
    "heygen_image_video": {"provider": "heygen", "modes": ["image_to_video"], "durations": [5], "ratios": ["auto", "16:9", "9:16", "4:5", "5:4", "1:1"], "resolutions": ["720p", "1080p"], "sound": True, "avatar": False, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "heygen_cinematic_avatar": {"provider": "heygen", "modes": ["text_to_video", "image_to_video"], "durations": [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": True, "avatar": True, "start_image": True, "end_image": False, "video_upload": True, "video_edit": False},
    "luma_ray_v3_2": {"provider": "luma", "modes": ["text_to_video", "image_to_video", "video_edit", "video_reframe"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": False, "start_image": True, "end_image": True, "video_upload": True, "video_edit": True},
    "luma_dream_machine": {"provider": "luma", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p"], "sound": False, "start_image": True, "end_image": True, "video_upload": False, "video_edit": False},
    "runway_aleph": {"provider": "runway", "modes": ["video_edit", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": False, "start_image": True, "end_image": True, "video_upload": True, "video_edit": True},
    "runway_gen": {"provider": "runway", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": False, "start_image": True, "end_image": True, "video_upload": False, "video_edit": False},
    "minimax_hailuo_2_3": {"provider": "minimax", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": False, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "pixverse_v6": {"provider": "pixverse", "modes": ["text_to_video", "image_to_video"], "durations": [5, 8], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": False, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "sora_2": {"provider": "sora", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p"], "sound": True, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "sora_2_pro": {"provider": "sora", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": True, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "veo_3_1": {"provider": "veo", "modes": ["text_to_video", "image_to_video"], "durations": [5, 8], "ratios": ["16:9", "9:16"], "resolutions": ["720p", "1080p"], "sound": True, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "veo_3_1_fast": {"provider": "veo", "modes": ["text_to_video", "image_to_video"], "durations": [5, 8], "ratios": ["16:9", "9:16"], "resolutions": ["720p"], "sound": True, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "gemini_omni_flash": {"provider": "gemini", "modes": ["text_to_video", "image_to_video", "video_edit"], "durations": [5, 8], "ratios": ["16:9", "9:16"], "resolutions": ["720p"], "sound": True, "start_image": True, "end_image": False, "video_upload": True, "video_edit": True},
    "wan_2_7": {"provider": "wan", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": False, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "wan_2_7_edit": {"provider": "wan", "modes": ["video_edit"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p", "1080p"], "sound": False, "start_image": False, "end_image": False, "video_upload": True, "video_edit": True},
    "wan_2_6": {"provider": "wan", "modes": ["text_to_video", "image_to_video"], "durations": [5, 10], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p"], "sound": False, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "grok_video": {"provider": "grok", "modes": ["text_to_video"], "durations": [5], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p"], "sound": True, "start_image": False, "end_image": False, "video_upload": False, "video_edit": False},
    "grok_video_edit": {"provider": "grok", "modes": ["video_edit"], "durations": [5], "ratios": ["16:9", "9:16", "1:1"], "resolutions": ["720p"], "sound": True, "start_image": False, "end_image": False, "video_upload": True, "video_edit": True},
}

KLING_BASE_RATIOS = ["16:9", "9:16", "1:1"]
KLING_FULL_RESOLUTIONS = ["720p", "1080p", "4K"]
KLING_STANDARD_RESOLUTIONS = ["720p", "1080p"]
KLING_LONG_DURATIONS = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
KLING_O1_DURATIONS = [3, 4, 5, 6, 7, 8, 9, 10]
KLING_SHORT_DURATIONS = [5, 10]
KLING_DURATIONS = [5, 10, 15]

VIDEO_MODEL_CONFIG.update({
    "kling_3_0_turbo": {"provider": "kling", "modes": ["text_to_video", "image_to_video"], "durations": KLING_LONG_DURATIONS, "ratios": KLING_BASE_RATIOS, "resolutions": KLING_STANDARD_RESOLUTIONS, "sound": True, "native_audio": True, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "kling_3_0": {"provider": "kling", "modes": ["text_to_video", "image_to_video"], "durations": KLING_LONG_DURATIONS, "ratios": KLING_BASE_RATIOS, "resolutions": KLING_FULL_RESOLUTIONS, "sound": True, "native_audio": True, "start_image": True, "end_image": True, "video_upload": False, "video_edit": False},
    "kling_motion_3_0": {"provider": "kling", "modes": ["motion_control"], "durations": KLING_LONG_DURATIONS, "ratios": KLING_BASE_RATIOS, "resolutions": KLING_STANDARD_RESOLUTIONS, "sound": False, "motion_control": True, "start_image": True, "end_image": False, "video_upload": True, "video_edit": False},
    "kling_o3_omni": {"provider": "kling", "modes": ["text_to_video", "image_to_video", "video_edit"], "durations": KLING_LONG_DURATIONS, "ratios": KLING_BASE_RATIOS, "resolutions": KLING_FULL_RESOLUTIONS, "sound": True, "native_audio": True, "omni": True, "video_input": True, "start_image": True, "end_image": True, "video_upload": True, "video_edit": True},
    "kling_o3_edit": {"provider": "kling", "modes": ["video_edit"], "durations": KLING_LONG_DURATIONS, "ratios": KLING_BASE_RATIOS, "resolutions": KLING_FULL_RESOLUTIONS, "sound": True, "native_audio": True, "video_input": True, "start_image": False, "end_image": False, "video_upload": True, "video_edit": True},
    "kling_o1": {"provider": "kling", "modes": ["text_to_video", "image_to_video", "video_edit"], "durations": KLING_O1_DURATIONS, "ratios": KLING_BASE_RATIOS, "resolutions": KLING_STANDARD_RESOLUTIONS, "sound": False, "video_input": True, "start_image": True, "end_image": True, "video_upload": True, "video_edit": True},
    "kling_2_6": {"provider": "kling", "modes": ["text_to_video", "image_to_video"], "durations": KLING_SHORT_DURATIONS, "ratios": KLING_BASE_RATIOS, "resolutions": KLING_STANDARD_RESOLUTIONS, "sound": True, "native_audio": True, "start_image": True, "end_image": True, "video_upload": False, "video_edit": False},
    "kling_motion_2_6": {"provider": "kling", "modes": ["motion_control"], "durations": KLING_SHORT_DURATIONS, "ratios": KLING_BASE_RATIOS, "resolutions": KLING_STANDARD_RESOLUTIONS, "sound": False, "motion_control": True, "start_image": True, "end_image": False, "video_upload": True, "video_edit": False},
    "kling_2_5_turbo": {"provider": "kling", "modes": ["text_to_video", "image_to_video"], "durations": KLING_SHORT_DURATIONS, "ratios": KLING_BASE_RATIOS, "resolutions": KLING_STANDARD_RESOLUTIONS, "sound": False, "start_image": True, "end_image": True, "video_upload": False, "video_edit": False},
    "kling_2_1": {"provider": "kling", "modes": ["image_to_video"], "durations": KLING_SHORT_DURATIONS, "ratios": KLING_BASE_RATIOS, "resolutions": KLING_STANDARD_RESOLUTIONS, "sound": False, "start_image": True, "end_image": True, "video_upload": False, "video_edit": False},
    "kling_2_1_master": {"provider": "kling", "modes": ["text_to_video", "image_to_video"], "durations": KLING_SHORT_DURATIONS, "ratios": KLING_BASE_RATIOS, "resolutions": ["1080p"], "sound": False, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "kling_2_0_master": {"provider": "kling", "modes": ["text_to_video", "image_to_video"], "durations": KLING_SHORT_DURATIONS, "ratios": KLING_BASE_RATIOS, "resolutions": ["1080p"], "sound": False, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
    "kling_1_6": {"provider": "kling", "modes": ["text_to_video", "image_to_video"], "durations": KLING_SHORT_DURATIONS, "ratios": KLING_BASE_RATIOS, "resolutions": KLING_STANDARD_RESOLUTIONS, "sound": False, "multi_image": False, "multi_element_editing": False, "video_extension": False, "start_image": True, "end_image": True, "video_upload": False, "video_edit": False},
    "kling_1_5": {"provider": "kling", "modes": ["image_to_video"], "durations": KLING_SHORT_DURATIONS, "ratios": KLING_BASE_RATIOS, "resolutions": KLING_STANDARD_RESOLUTIONS, "sound": False, "video_extension": False, "start_image": True, "end_image": True, "video_upload": False, "video_edit": False},
    "kling_1_0": {"provider": "kling", "modes": ["text_to_video", "image_to_video"], "durations": KLING_SHORT_DURATIONS, "ratios": KLING_BASE_RATIOS, "resolutions": KLING_STANDARD_RESOLUTIONS, "sound": False, "video_extension": False, "start_image": True, "end_image": False, "video_upload": False, "video_edit": False},
})

BYTEPLUS_SEEDANCE_MODEL_MAP = {
    "seedance_2_fast": os.getenv("BYTEPLUS_SEEDANCE_2_FAST_MODEL", "dreamina-seedance-2-0-fast-260128"),
    "seedance_2_0": os.getenv("BYTEPLUS_SEEDANCE_2_MODEL", "dreamina-seedance-2-0-260128"),
}

_seedance_1_5_pro_model = os.getenv("BYTEPLUS_SEEDANCE_1_5_PRO_MODEL")
if _seedance_1_5_pro_model:
    BYTEPLUS_SEEDANCE_MODEL_MAP["seedance_1_5_pro"] = _seedance_1_5_pro_model

for _provider_model_id in tuple(BYTEPLUS_SEEDANCE_MODEL_MAP.values()):
    BYTEPLUS_SEEDANCE_MODEL_MAP.setdefault(_provider_model_id, _provider_model_id)

VIDEO_PROVIDER_MODEL_MAP = {
    "heygen_v3_video_agent": {"provider": "heygen", "provider_model": os.getenv("HEYGEN_VIDEO_MODEL", "video-agent"), "endpoint": os.getenv("HEYGEN_VIDEO_ENDPOINT", f"{os.getenv('HEYGEN_BASE_URL', 'https://api.heygen.com').rstrip('/')}/v3/video-agents")},
    "heygen_avatar_iv": {"provider": "heygen", "provider_model": "avatar_iv", "endpoint": os.getenv("HEYGEN_DIRECT_VIDEO_ENDPOINT", f"{os.getenv('HEYGEN_BASE_URL', 'https://api.heygen.com').rstrip('/')}/v3/videos")},
    "heygen_avatar_v": {"provider": "heygen", "provider_model": "avatar_v", "endpoint": os.getenv("HEYGEN_DIRECT_VIDEO_ENDPOINT", f"{os.getenv('HEYGEN_BASE_URL', 'https://api.heygen.com').rstrip('/')}/v3/videos")},
    "heygen_avatar_iii": {"provider": "heygen", "provider_model": "avatar_iii", "endpoint": os.getenv("HEYGEN_DIRECT_VIDEO_ENDPOINT", f"{os.getenv('HEYGEN_BASE_URL', 'https://api.heygen.com').rstrip('/')}/v3/videos")},
    "heygen_image_video": {"provider": "heygen", "provider_model": "image", "endpoint": os.getenv("HEYGEN_DIRECT_VIDEO_ENDPOINT", f"{os.getenv('HEYGEN_BASE_URL', 'https://api.heygen.com').rstrip('/')}/v3/videos")},
    "heygen_cinematic_avatar": {"provider": "heygen", "provider_model": "cinematic_avatar", "endpoint": os.getenv("HEYGEN_DIRECT_VIDEO_ENDPOINT", f"{os.getenv('HEYGEN_BASE_URL', 'https://api.heygen.com').rstrip('/')}/v3/videos")},
    "luma_ray_v3_2": {"provider": "luma", "provider_model": os.getenv("LUMA_RAY_V3_2_MODEL", os.getenv("LUMA_VIDEO_MODEL", "ray-3.2")), "endpoint": os.getenv("LUMA_AGENTS_ENDPOINT", os.getenv("LUMA_API_ENDPOINT", "https://agents.lumalabs.ai/v1/generations"))},
    "luma_dream_machine": {"provider": "luma", "provider_model": os.getenv("LUMA_DREAM_MACHINE_MODEL", os.getenv("LUMA_VIDEO_MODEL", "ray-3.2")), "endpoint": os.getenv("LUMA_AGENTS_ENDPOINT", os.getenv("LUMA_API_ENDPOINT", "https://agents.lumalabs.ai/v1/generations"))},
    "minimax_hailuo_2_3": {"provider": "minimax", "provider_model": os.getenv("MINIMAX_HAILUO_2_3_MODEL"), "endpoint": os.getenv("MINIMAX_API_ENDPOINT", "https://api.minimax.io/v1/video/generation")},
    "pixverse_v6": {"provider": "pixverse", "provider_model": os.getenv("PIXVERSE_V6_MODEL"), "endpoint": os.getenv("PIXVERSE_API_ENDPOINT", "https://api.pixverse.io/v1/videos/generations")},
    "sora_2_pro": {"provider": "sora", "provider_model": "sora-2-pro", "endpoint": f"{os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1').rstrip('/')}/videos"},
    "wan_2_7": {"provider": "wan", "provider_model": os.getenv("WAN_2_7_MODEL"), "endpoint": os.getenv("WAN_API_ENDPOINT", "https://dashscope.aliyuncs.com/api/v1/services/aigc/video/generation")},
    "veo_3_1": {"provider": "veo", "provider_model": os.getenv("VEO_MODEL", "veo-3.1-generate-preview"), "endpoint": os.getenv("GOOGLE_VEO_ENDPOINT")},
    "grok_video_edit": {"provider": "grok", "provider_model": os.getenv("GROK_VIDEO_EDIT_MODEL"), "endpoint": os.getenv("XAI_VIDEO_ENDPOINT", "https://api.x.ai/v1/videos/generations")},
    "wan_2_7_edit": {"provider": "wan", "provider_model": os.getenv("WAN_2_7_EDIT_MODEL"), "endpoint": os.getenv("WAN_API_ENDPOINT", "https://dashscope.aliyuncs.com/api/v1/services/aigc/video/generation")},
    "runway_aleph": {"provider": "runway", "provider_model": os.getenv("RUNWAY_ALEPH_MODEL", "act_two"), "endpoint": os.getenv("RUNWAY_API_ENDPOINT", "https://api.dev.runwayml.com/v1/image_to_video")},
    "seedance_1_5_pro": {"provider": "bytedance", "provider_model": BYTEPLUS_SEEDANCE_MODEL_MAP.get("seedance_1_5_pro"), "endpoint": _seedance_1_5_pro_model and os.getenv("BYTEPLUS_SEEDANCE_TASK_ENDPOINT")},
    "wan_2_6": {"provider": "wan", "provider_model": os.getenv("WAN_2_6_MODEL"), "endpoint": os.getenv("WAN_API_ENDPOINT", "https://dashscope.aliyuncs.com/api/v1/services/aigc/video/generation")},
    "seedance_2_fast": {"provider": "bytedance", "provider_model": BYTEPLUS_SEEDANCE_MODEL_MAP.get("seedance_2_fast"), "endpoint": os.getenv("BYTEPLUS_SEEDANCE_TASK_ENDPOINT")},
    "seedance_2_0": {"provider": "bytedance", "provider_model": BYTEPLUS_SEEDANCE_MODEL_MAP.get("seedance_2_0"), "endpoint": os.getenv("BYTEPLUS_SEEDANCE_TASK_ENDPOINT")},
    "gemini_omni_flash": {"provider": "gemini", "provider_model": os.getenv("GEMINI_VIDEO_MODEL", "gemini-omni-flash-preview"), "endpoint": os.getenv("GEMINI_INTERACTIONS_ENDPOINT", "https://generativelanguage.googleapis.com/v1beta/interactions")},
    "sora_2": {"provider": "sora", "provider_model": "sora-2", "endpoint": f"{os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1').rstrip('/')}/videos"},
    "grok_video": {"provider": "grok", "provider_model": os.getenv("GROK_VIDEO_MODEL"), "endpoint": os.getenv("XAI_VIDEO_ENDPOINT", "https://api.x.ai/v1/videos/generations")},
    "veo_3_1_fast": {"provider": "veo", "provider_model": os.getenv("VEO_FAST_MODEL", "veo-3.1-fast-generate-preview"), "endpoint": os.getenv("GOOGLE_VEO_ENDPOINT")},
    "runway_gen": {"provider": "runway", "provider_model": os.getenv("RUNWAY_GEN_MODEL", "gen4_turbo"), "endpoint": os.getenv("RUNWAY_API_ENDPOINT", "https://api.dev.runwayml.com/v1/image_to_video")},
}

VIDEO_PROVIDER_MODEL_MAP.update({
    "kling_3_0_turbo": {"provider": "kling", "provider_model": os.getenv("KLING_3_0_TURBO_MODEL", "kling-3.0-turbo"), "endpoint": os.getenv("KLING_API_ENDPOINT", "https://api-singapore.klingai.com")},
    "kling_3_0": {"provider": "kling", "provider_model": os.getenv("KLING_3_0_MODEL", "kling-3.0"), "endpoint": os.getenv("KLING_API_ENDPOINT", "https://api-singapore.klingai.com")},
    "kling_motion_3_0": {"provider": "kling", "provider_model": os.getenv("KLING_MOTION_3_0_MODEL", os.getenv("KLING_3_0_MOTION_MODEL", "kling-3.0")), "endpoint": os.getenv("KLING_API_ENDPOINT", "https://api-singapore.klingai.com")},
    "kling_o3_omni": {"provider": "kling", "provider_model": os.getenv("KLING_3_0_OMNI_MODEL", os.getenv("KLING_O3_OMNI_MODEL", "kling-3.0-omni")), "endpoint": os.getenv("KLING_API_ENDPOINT", "https://api-singapore.klingai.com")},
    "kling_o3_edit": {"provider": "kling", "provider_model": os.getenv("KLING_3_0_OMNI_MODEL", os.getenv("KLING_O3_EDIT_MODEL", "kling-3.0-omni")), "endpoint": os.getenv("KLING_API_ENDPOINT", "https://api-singapore.klingai.com")},
    "kling_o1": {"provider": "kling", "provider_model": os.getenv("KLING_O1_MODEL", "kling-o1"), "endpoint": os.getenv("KLING_API_ENDPOINT", "https://api-singapore.klingai.com")},
    "kling_2_6": {"provider": "kling", "provider_model": os.getenv("KLING_2_6_MODEL", "kling-2.6"), "endpoint": os.getenv("KLING_API_ENDPOINT", "https://api-singapore.klingai.com")},
    "kling_motion_2_6": {"provider": "kling", "provider_model": os.getenv("KLING_MOTION_2_6_MODEL", os.getenv("KLING_2_6_MOTION_MODEL", "kling-2.6")), "endpoint": os.getenv("KLING_API_ENDPOINT", "https://api-singapore.klingai.com")},
    "kling_2_5_turbo": {"provider": "kling", "provider_model": os.getenv("KLING_2_5_TURBO_MODEL", "kling-2.5-turbo"), "endpoint": os.getenv("KLING_API_ENDPOINT", "https://api-singapore.klingai.com")},
    "kling_2_1": {"provider": "kling", "provider_model": os.getenv("KLING_2_1_MODEL", "kling-2.1"), "endpoint": os.getenv("KLING_API_ENDPOINT", "https://api-singapore.klingai.com")},
    "kling_2_1_master": {"provider": "kling", "provider_model": os.getenv("KLING_2_1_MASTER_MODEL", "kling-2.1-master"), "endpoint": os.getenv("KLING_API_ENDPOINT", "https://api-singapore.klingai.com")},
    "kling_2_0_master": {"provider": "kling", "provider_model": os.getenv("KLING_2_0_MASTER_MODEL", "kling-2.0-master"), "endpoint": os.getenv("KLING_API_ENDPOINT", "https://api-singapore.klingai.com")},
    "kling_1_6": {"provider": "kling", "provider_model": os.getenv("KLING_1_6_MODEL", "kling-1.6"), "endpoint": os.getenv("KLING_API_ENDPOINT", "https://api-singapore.klingai.com")},
    "kling_1_5": {"provider": "kling", "provider_model": os.getenv("KLING_1_5_MODEL", "kling-1.5"), "endpoint": os.getenv("KLING_API_ENDPOINT", "https://api-singapore.klingai.com")},
    "kling_1_0": {"provider": "kling", "provider_model": os.getenv("KLING_1_0_MODEL", "kling-1.0"), "endpoint": os.getenv("KLING_API_ENDPOINT", "https://api-singapore.klingai.com")},
})


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


def _video_model_mapping(frontend_model: str):
    value = (frontend_model or "").strip()
    normalized = value.lower()
    return VIDEO_PROVIDER_MODEL_MAP.get(normalized) or VIDEO_PROVIDER_MODEL_MAP.get(normalized.replace("-", "_")) or {}


def _provider_model_for_video(frontend_model: str):
    return _video_model_mapping(frontend_model).get("provider_model")


def _unknown_video_model_mapping_response(frontend_model: str, provider: str = ""):
    mapping = _video_model_mapping(frontend_model)
    return {
        "ok": False,
        "type": "video",
        "error": "Unknown provider model mapping",
        "frontend_model": frontend_model or "",
        "provider": provider or mapping.get("provider") or "",
        "endpoint": mapping.get("endpoint") or "",
    }


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


def _public_generated_url(path: str):
    text = str(path or "").strip()
    if not text:
        return ""
    if re.match(r"^https?://", text, re.I):
        return text
    base = (
        os.getenv("WEBAPP_URL")
        or os.getenv("PUBLIC_WEBAPP_URL")
        or os.getenv("PUBLIC_BASE_URL")
        or ""
    ).rstrip("/")
    return f"{base}{text}" if base else text


def _guess_mime_from_url(url: str, default: str = "application/octet-stream"):
    path = urlparse(str(url or "")).path.lower()
    if path.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if path.endswith(".png"):
        return "image/png"
    if path.endswith(".webp"):
        return "image/webp"
    if path.endswith(".mp4"):
        return "video/mp4"
    if path.endswith(".mov"):
        return "video/quicktime"
    return default


def _load_media_content_part(url: str, media_type: str):
    raw = str(url or "").strip()
    if not raw:
        return {}
    default_mime = "video/mp4" if media_type == "video" else "image/jpeg"
    try:
        if raw.startswith("data:") and ";base64," in raw:
            header, data = raw.split(";base64,", 1)
            mime_type = header.replace("data:", "").split(";", 1)[0] or default_mime
            return {"type": media_type, "mime_type": mime_type, "data": data.strip()}
        if raw.startswith("/webapp/"):
            local_path = WEBAPP_DIR / raw.replace("/webapp/", "", 1)
            content = local_path.read_bytes()
            return {
                "type": media_type,
                "mime_type": _guess_mime_from_url(raw, default_mime),
                "data": base64.b64encode(content).decode("utf-8"),
            }
        if raw.startswith("/generated/"):
            local_path = WEBAPP_DIR / raw.replace("/generated/", "generated/", 1)
            content = local_path.read_bytes()
            return {
                "type": media_type,
                "mime_type": _guess_mime_from_url(raw, default_mime),
                "data": base64.b64encode(content).decode("utf-8"),
            }
        response = requests.get(raw, timeout=60)
        response.raise_for_status()
        mime_type = (response.headers.get("content-type") or "").split(";", 1)[0].strip() or _guess_mime_from_url(raw, default_mime)
        return {
            "type": media_type,
            "mime_type": mime_type,
            "data": base64.b64encode(response.content).decode("utf-8"),
        }
    except Exception as exc:
        print("GEMINI MEDIA LOAD FAILED:", {"type": media_type, "url": raw[:180], "error": type(exc).__name__})
        return {}


def _read_media_bytes(url: str, media_type: str):
    raw = str(url or "").strip()
    if not raw:
        return b"", ""
    default_mime = "video/mp4" if media_type == "video" else "image/jpeg"
    try:
        if raw.startswith("data:") and ";base64," in raw:
            header, data = raw.split(";base64,", 1)
            mime_type = header.replace("data:", "").split(";", 1)[0] or default_mime
            return base64.b64decode(data, validate=True), mime_type
        if raw.startswith("/webapp/"):
            local_path = WEBAPP_DIR / raw.replace("/webapp/", "", 1)
            return local_path.read_bytes(), _guess_mime_from_url(raw, default_mime)
        if raw.startswith("/generated/"):
            local_path = WEBAPP_DIR / raw.replace("/generated/", "generated/", 1)
            return local_path.read_bytes(), _guess_mime_from_url(raw, default_mime)
        response = requests.get(raw, timeout=120)
        response.raise_for_status()
        mime_type = (response.headers.get("content-type") or "").split(";", 1)[0].strip() or _guess_mime_from_url(raw, default_mime)
        return response.content, mime_type
    except Exception as exc:
        print("GEMINI MEDIA READ FAILED:", {"type": media_type, "url": raw[:180], "error": type(exc).__name__})
        return b"", ""


def _gemini_upload_file_from_url(url: str, api_key: str, media_type: str):
    content, mime_type = _read_media_bytes(url, media_type)
    if not content:
        return {}
    display_name = f"sylvex-{media_type}-{uuid4().hex}"
    start_url = "https://generativelanguage.googleapis.com/upload/v1beta/files"
    start_headers = {
        "x-goog-api-key": api_key,
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(len(content)),
        "X-Goog-Upload-Header-Content-Type": mime_type,
        "Content-Type": "application/json",
    }
    metadata = {"file": {"display_name": display_name}}
    try:
        start_response = requests.post(start_url, headers=start_headers, json=metadata, timeout=60)
        upload_url = start_response.headers.get("x-goog-upload-url") or start_response.headers.get("X-Goog-Upload-URL")
        if start_response.status_code >= 400 or not upload_url:
            data = _safe_provider_json_response(start_response, "gemini", start_url)
            _log_provider_response("gemini", "FILE_UPLOAD_START", start_url, metadata, start_response, data)
            return {}
        upload_headers = {
            "Content-Length": str(len(content)),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        }
        upload_response = requests.post(upload_url, headers=upload_headers, data=content, timeout=180)
        data = _safe_provider_json_response(upload_response, "gemini", upload_url)
        _log_provider_response("gemini", "FILE_UPLOAD", upload_url, {"display_name": display_name, "mime_type": mime_type, "bytes": len(content)}, upload_response, data)
        if upload_response.status_code >= 400:
            return {}
        file_info = data.get("file") if isinstance(data.get("file"), dict) else data
        file_name = file_info.get("name") if isinstance(file_info, dict) else ""
        file_uri = file_info.get("uri") if isinstance(file_info, dict) else ""
        for _ in range(18):
            raw_state = (file_info or {}).get("state") if isinstance(file_info, dict) else ""
            state = str(raw_state.get("name") if isinstance(raw_state, dict) else raw_state or "").upper()
            if state in {"ACTIVE", "FAILED"}:
                break
            if not file_name:
                break
            time.sleep(5)
            status_url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}"
            status_response = requests.get(status_url, headers={"x-goog-api-key": api_key}, timeout=30)
            status_data = _safe_provider_json_response(status_response, "gemini", status_url)
            file_info = status_data.get("file") if isinstance(status_data.get("file"), dict) else status_data
            file_uri = file_info.get("uri") if isinstance(file_info, dict) else file_uri
        if file_uri:
            return {"type": media_type, "uri": file_uri, "mime_type": mime_type}
    except Exception as exc:
        print("GEMINI FILE UPLOAD FAILED:", {"type": media_type, "error": type(exc).__name__})
    return {}


def _save_gemini_video_bytes(content: bytes, suffix: str = "mp4"):
    if not content:
        return ""
    GENERATED_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    ext = "mp4" if suffix not in {"mp4", "mov", "webm"} else suffix
    filename = f"{uuid4().hex}.{ext}"
    path = GENERATED_VIDEOS_DIR / filename
    path.write_bytes(content)
    return _public_generated_url(f"/webapp/generated/videos/{filename}")


def _gemini_file_id_from_uri(uri: str):
    text = str(uri or "")
    match = re.search(r"/files/([^/:?]+)", text)
    return match.group(1) if match else ""


def _download_gemini_video_uri(uri: str, api_key: str):
    file_id = _gemini_file_id_from_uri(uri)
    headers = {"x-goog-api-key": api_key}
    if file_id:
        status_url = f"https://generativelanguage.googleapis.com/v1beta/files/{file_id}"
        for _ in range(24):
            try:
                status_response = requests.get(status_url, headers=headers, timeout=30)
                info = _safe_provider_json_response(status_response, "gemini", status_url)
                raw_state = info.get("state")
                state = str(raw_state.get("name") if isinstance(raw_state, dict) else raw_state or "").upper()
                if state == "FAILED":
                    return ""
                if not state or state == "ACTIVE":
                    break
            except Exception:
                break
            time.sleep(5)
    download_url = uri
    if file_id:
        download_url = f"https://generativelanguage.googleapis.com/v1beta/files/{file_id}:download?alt=media"
    try:
        response = requests.get(download_url, headers=headers, timeout=180)
        if response.status_code < 400 and response.content:
            return _save_gemini_video_bytes(response.content, "mp4")
    except Exception as exc:
        print("GEMINI VIDEO URI DOWNLOAD FAILED:", {"uri": uri[:180], "error": type(exc).__name__})
    return ""


def _extract_gemini_videos(data: dict, api_key: str):
    videos = []

    def add_data(value, mime_type="video/mp4"):
        if isinstance(value, str) and value.strip():
            try:
                content = base64.b64decode(value.strip(), validate=True)
            except (binascii.Error, ValueError):
                content = b""
            if content:
                suffix = "mov" if "quicktime" in str(mime_type).lower() else "mp4"
                url = _save_gemini_video_bytes(content, suffix)
                if url:
                    videos.append(url)

    def add_uri(value):
        if isinstance(value, str) and value.strip():
            local = _download_gemini_video_uri(value.strip(), api_key)
            videos.append(local or value.strip())

    def walk(node):
        if isinstance(node, dict):
            mime_type = node.get("mime_type") or node.get("mimeType") or "video/mp4"
            if node.get("type") == "video":
                add_data(node.get("data"), mime_type)
                add_uri(node.get("uri") or node.get("url"))
            output_video = node.get("output_video")
            if isinstance(output_video, dict):
                walk(output_video)
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    clean = []
    for url in videos:
        if url and url not in clean:
            clean.append(url)
    return clean


def _request_json(url: str, headers: dict, payload: dict):
    return requests.post(url, headers=headers, json=payload, timeout=120)


def _request_get(url: str, headers: dict):
    return requests.get(url, headers=headers, timeout=60)


def _request_form(url: str, headers: dict, data: dict, files=None):
    return requests.post(url, headers=headers, data=data, files=files, timeout=120)


def _safe_response_text(response):
    try:
        text = response.text
        if callable(text):
            text = text()
        return text or ""
    except Exception:
        return ""


def _response_headers_dict(response):
    try:
        return dict(response.headers or {})
    except Exception:
        return {}


def _log_provider_response(provider: str, label: str, url: str, payload: dict, response, data=None):
    status = getattr(response, "status_code", None) or getattr(response, "status", None)
    body_preview = _safe_response_text(response)[:4000]
    print(f"{provider.upper()} {label} RESPONSE DEBUG:", {
        "request_url": url,
        "request_payload": _sanitize_debug_payload(payload),
        "http_status": status,
        "response_headers": _response_headers_dict(response),
        "response_body": body_preview,
        "json_body": data if isinstance(data, dict) else None,
    })


def _sanitize_debug_payload(value, limit: int = 260):
    if isinstance(value, dict):
        return {key: _sanitize_debug_payload(item, limit) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_debug_payload(item, limit) for item in value]
    if isinstance(value, str) and len(value) > limit:
        prefix = value[:80]
        if value.startswith("data:") or len(value) > 1000:
            return f"{prefix}... [{len(value)} chars]"
        return f"{value[:limit]}... [{len(value)} chars]"
    return value


def _provider_for_model(model_id: str):
    value = (model_id or "").strip().lower()
    mapping = _video_model_mapping(value)
    if mapping.get("provider"):
        return mapping.get("provider")
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
        "start_image": opts.get("start_image") or payload.get("start_image") or "",
        "end_image": opts.get("end_image") or "",
        "reference_images": reference_images,
        "input_video": opts.get("input_video") or "",
        "video_url": opts.get("video_url") or "",
        "reference_video": opts.get("reference_video") or "",
        "template_video_url": opts.get("template_video_url") or opts.get("template_video") or "",
        "preview_video": opts.get("preview_video") or "",
        "image_url": opts.get("image_url") or payload.get("image_url") or "",
        "motion_preset": opts.get("motion_preset") or "",
        "video_template": opts.get("video_template") or {},
        "character_image": opts.get("character_image") or "",
        "seed": opts.get("seed") if opts.get("seed") not in (None, "") else payload.get("seed"),
        "native_audio": bool(opts.get("native_audio")),
        "motion_control": bool(opts.get("motion_control")),
        "video_input": bool(opts.get("video_input")),
        "avatar": bool(opts.get("avatar")),
        "lip_sync": bool(opts.get("lip_sync")),
        "multi_image": bool(opts.get("multi_image")),
        "multi_element_editing": bool(opts.get("multi_element_editing")),
        "video_extension": bool(opts.get("video_extension")),
        "advanced": opts.get("advanced") or {},
        "telegram_id": payload.get("telegram_id"),
    }


KLING_COST_MATRIX = {
    "kling_3_0_turbo": {
        "native_audio": {
            "720p": {5: 84, 10: 168, 15: 252},
            "1080p": {5: 105, 10: 210, 15: 315},
        },
    },
    "kling_3_0": {
        "standard": {
            "720p": {5: 63, 10: 126, 15: 189},
            "1080p": {5: 84, 10: 168, 15: 252},
            "4k": {5: 315, 10: 630, 15: 945},
        },
        "native_audio": {
            "720p": {5: 95, 10: 189, 15: 284},
            "1080p": {5: 126, 10: 252, 15: 378},
            "4k": {5: 315, 10: 630, 15: 945},
        },
    },
    "kling_motion_3_0": {
        "motion_control": {
            "720p": {5: 95, 10: 189, 15: 284},
            "1080p": {5: 126, 10: 252, 15: 378},
        },
    },
    "kling_o3_omni": {
        "standard": {
            "720p": {5: 63, 10: 126, 15: 189},
            "1080p": {5: 84, 10: 168, 15: 252},
            "4k": {5: 315, 10: 630, 15: 945},
        },
        "native_audio": {
            "720p": {5: 84, 10: 168, 15: 252},
            "1080p": {5: 105, 10: 210, 15: 315},
            "4k": {5: 315, 10: 630, 15: 945},
        },
        "video_input": {
            "720p": {5: 95, 10: 189, 15: 284},
            "1080p": {5: 126, 10: 252, 15: 378},
            "4k": {5: 315, 10: 630, 15: 945},
        },
    },
    "kling_o3_edit": {
        "video_input": {
            "720p": {5: 95, 10: 189, 15: 284},
            "1080p": {5: 126, 10: 252, 15: 378},
            "4k": {5: 315, 10: 630, 15: 945},
        },
    },
    "kling_o1": {
        "standard": {
            "720p": {5: 63, 10: 126, 15: 189},
            "1080p": {5: 84, 10: 168, 15: 252},
        },
        "video_input": {
            "720p": {5: 95, 10: 189, 15: 284},
            "1080p": {5: 126, 10: 252, 15: 378},
        },
    },
    "kling_2_6": {
        "standard": {
            "720p": {5: 32, 10: 63, 15: 95},
            "1080p": {5: 53, 10: 105, 15: 158},
        },
        "native_audio": {
            "1080p": {5: 105, 10: 210, 15: 315},
        },
        "voice_control": {
            "1080p": {5: 126, 10: 252, 15: 378},
        },
    },
    "kling_motion_2_6": {
        "motion_control": {
            "720p": {5: 53, 10: 105, 15: 158},
            "1080p": {5: 84, 10: 168, 15: 252},
        },
    },
    "kling_2_5_turbo": {
        "standard": {
            "720p": {5: 32, 10: 63, 15: 95},
            "1080p": {5: 53, 10: 105, 15: 158},
        },
    },
    "kling_2_1": {
        "standard": {
            "720p": {5: 42, 10: 84, 15: 126},
            "1080p": {5: 74, 10: 147, 15: 221},
        },
    },
    "kling_2_1_master": {
        "standard": {
            "1080p": {5: 210, 10: 420, 15: 630},
        },
    },
    "kling_2_0_master": {
        "standard": {
            "1080p": {5: 210, 10: 420, 15: 630},
        },
    },
    "kling_1_6": {
        "standard": {
            "720p": {5: 42, 10: 84, 15: 126},
            "1080p": {5: 74, 10: 147, 15: 221},
        },
        "multi_element_editing": {
            "720p": {5: 63, 10: 126, 15: 189},
            "1080p": {5: 105, 10: 210, 15: 315},
        },
        "video_extension": {
            "720p": {5: 42, 10: 42, 15: 42},
            "1080p": {5: 74, 10: 74, 15: 74},
        },
    },
    "kling_1_5": {
        "standard": {
            "720p": {5: 42, 10: 84, 15: 126},
            "1080p": {5: 74, 10: 147, 15: 221},
        },
        "video_extension": {
            "720p": {5: 42, 10: 42, 15: 42},
            "1080p": {5: 74, 10: 74, 15: 74},
        },
    },
    "kling_1_0": {
        "standard": {
            "720p": {5: 21, 10: 42, 15: 63},
            "1080p": {5: 74, 10: 147, 15: 221},
        },
        "video_extension": {
            "720p": {5: 42, 10: 42, 15: 42},
            "1080p": {5: 74, 10: 74, 15: 74},
        },
    },
    "kling_avatar": {
        "avatar": {
            "720p": {5: 42, 10: 84, 15: 126},
            "1080p": {5: 84, 10: 168, 15: 252},
        },
    },
    "kling_lip_sync": {
        "lip_sync": {
            "720p": {5: 11, 10: 21, 15: 32},
        },
    },
}


def _kling_resolution_key(value):
    raw = str(value or "720p").strip().lower().replace(" ", "")
    if raw in {"4k", "2160p", "uhd"}:
        return "4k"
    if raw in {"1080", "1080p", "fhd"}:
        return "1080p"
    return "720p"


def _kling_duration_key(value):
    try:
        duration = int(value or 5)
    except Exception:
        duration = 5
    if duration <= 5:
        return 5
    if duration <= 10:
        return 10
    return 15


def _kling_has_video_input(body: dict):
    if not isinstance(body, dict):
        return False
    mode = str(body.get("mode") or body.get("generation_mode") or "").lower()
    return bool(body.get("video_input") or body.get("input_video") or body.get("video_url") or mode in {"video_edit", "video_extension"})


def _kling_cost_variant(model_id: str, body: dict):
    mode = str((body or {}).get("mode") or (body or {}).get("generation_mode") or "").lower()
    advanced = (body or {}).get("advanced") if isinstance((body or {}).get("advanced"), dict) else {}
    if model_id == "kling_3_0_turbo":
        return "native_audio"
    if body.get("lip_sync") or mode in {"lip_sync", "lip sync"} or model_id == "kling_lip_sync":
        return "lip_sync"
    if body.get("avatar") or mode == "avatar" or model_id == "kling_avatar":
        return "avatar"
    if body.get("motion_control") or mode in {"motion_control", "motion control"} or "motion" in model_id:
        return "motion_control"
    if body.get("multi_element_editing") or mode in {"multi_element_editing", "multi element editing"}:
        return "multi_element_editing"
    if body.get("video_extension") or mode in {"video_extension", "video extension"}:
        return "video_extension"
    if advanced.get("voice_control"):
        return "voice_control"
    if model_id in {"kling_o1", "kling_o3_omni", "kling_o3_edit"} and _kling_has_video_input(body):
        return "video_input"
    if body.get("native_audio") or body.get("sound"):
        return "native_audio"
    return "standard"


def _kling_cost_info(model_id: str, body: dict):
    matrix = KLING_COST_MATRIX.get(model_id) or {}
    variant = _kling_cost_variant(model_id, body)
    variant_matrix = matrix.get(variant) or matrix.get("standard") or next(iter(matrix.values()), {})
    resolution = _kling_resolution_key((body or {}).get("resolution"))
    if resolution not in variant_matrix and variant_matrix:
        resolution = next(iter(variant_matrix.keys()))
    duration = _kling_duration_key((body or {}).get("duration"))
    duration_matrix = variant_matrix.get(resolution) or {}
    unit_credits = int(duration_matrix.get(duration) or duration_matrix.get(5) or 0)
    return {
        "cost_credits": unit_credits,
        "unit_cost_credits": unit_credits,
        "cost_usd": 0,
        "unit_cost_usd": 0,
        "generation_cost": f"{unit_credits} ⚡" if unit_credits else "",
        "cost_variant": variant,
        "cost_resolution": resolution,
        "cost_duration": duration,
    }


def estimate_video_generation_cost(payload: dict):
    model_id = (
        (payload.get("video_options") or {}).get("model")
        or payload.get("model")
        or ""
    )
    if not model_id:
        return {"credits": 0, "cost_usd": 0, "generation_cost": ""}
    mapping = _video_model_mapping(model_id)
    provider = (mapping.get("provider") or payload.get("provider") or "").strip().lower()
    if provider != "kling":
        return {"credits": 0, "cost_usd": 0, "generation_cost": ""}
    body = _build_video_payload(model_id, payload.get("prompt") or "", payload)
    info = _kling_cost_info(model_id, body)
    return {
        "credits": int(info.get("cost_credits") or 0),
        "cost_usd": info.get("cost_usd") or 0,
        "generation_cost": info.get("generation_cost") or "",
        "unit_cost_credits": info.get("unit_cost_credits") or 0,
        "unit_cost_usd": info.get("unit_cost_usd") or 0,
        "cost_variant": info.get("cost_variant") or "",
        "cost_resolution": info.get("cost_resolution") or "",
        "cost_duration": info.get("cost_duration") or "",
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
    if value not in {"480p", "720p", "1080p"}:
        value = "720p"
    if provider_model in {
        BYTEPLUS_SEEDANCE_MODEL_MAP.get("seedance_2_fast"),
        os.getenv("BYTEPLUS_SEEDANCE_2_MINI_MODEL", "dreamina-seedance-2-0-mini-260615"),
    } and value == "1080p":
        return None
    return value


def _seedance_ratio(body: dict):
    ratio = str(body.get("ratio") or "16:9").replace("_", ":")
    if ratio in {"auto", "adaptive"}:
        return "adaptive"
    if ratio in {"21:9", "16:9", "4:3", "1:1", "3:4", "9:16"}:
        return ratio
    return "16:9"


def _seedance_seed(body: dict):
    advanced = body.get("advanced") if isinstance(body.get("advanced"), dict) else {}
    value = body.get("seed")
    if value in (None, ""):
        value = advanced.get("seed")
    if value in (None, ""):
        return None
    try:
        seed = int(value)
    except Exception:
        return None
    if seed < -1:
        return None
    return min(seed, 4294967295)


def _seedance_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _seedance_safety_identifier(value):
    raw = str(value or "sylvex-prostudio")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", raw).strip("-_")
    return (safe or "sylvex-prostudio")[:64]


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
        "safety_identifier": _seedance_safety_identifier(body.get("telegram_id") or payload.get("telegram_id") or "sylvex-prostudio"),
    }
    resolution = _seedance_resolution_for_model(provider_model, body.get("resolution"))
    if resolution:
        seedance_payload["resolution"] = resolution
    seed = _seedance_seed(body)
    if seed is not None:
        seedance_payload["seed"] = seed
    advanced = body.get("advanced") if isinstance(body.get("advanced"), dict) else {}
    if advanced.get("return_last_frame") is not None:
        seedance_payload["return_last_frame"] = _seedance_bool(advanced.get("return_last_frame"), default=False)
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


def _seedance_task_metadata(data: dict):
    result = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(result, dict):
        return {}
    content = result.get("content") if isinstance(result.get("content"), dict) else {}
    metadata = {}
    for key in (
        "id", "model", "status", "created_at", "updated_at", "seed",
        "resolution", "ratio", "duration", "frames", "framespersecond",
        "generate_audio", "safety_identifier", "priority", "draft",
        "draft_task_id", "service_tier", "execution_expires_after", "usage",
    ):
        if key in result:
            metadata[key] = result.get(key)
    if content.get("last_frame_url"):
        metadata["last_frame_url"] = content.get("last_frame_url")
    return metadata


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
        return _seedance_provider_success(task_id, [video_url], data, status="completed", task_id=task_id)
    if state in {"failed", "error", "cancelled", "expired"}:
        return _provider_parse_error("bytedance", task_id, data)
    return _seedance_provider_success(
        task_id,
        [],
        data,
        status="processing",
        task_id=task_id,
        poll_url=endpoint,
    )


def _seedance_poll_until_ready(task_id: str, headers: dict, max_attempts: int = None, interval_seconds: int = None):
    try:
        attempts = int(max_attempts or os.getenv("BYTEPLUS_SEEDANCE_POLL_ATTEMPTS") or 60)
    except Exception:
        attempts = 60
    try:
        interval = int(interval_seconds or os.getenv("BYTEPLUS_SEEDANCE_POLL_INTERVAL") or 5)
    except Exception:
        interval = 5
    attempts = max(1, min(attempts, 60))
    interval = max(1, interval)

    last_result = None
    for attempt in range(1, attempts + 1):
        result = _seedance_poll_task(task_id, headers)
        last_result = result
        video_url = result.get("video_url") or ""
        print("SEEDANCE VIDEO POLL:", {
            "attempt": attempt,
            "task_id": task_id,
            "status": result.get("status") or ("error" if not result.get("ok") else ""),
            "has_video_url": bool(video_url),
            "video_url": video_url,
        })
        if not result.get("ok"):
            return result
        if result.get("status") == "completed" and video_url:
            return result
        if attempt < attempts:
            time.sleep(interval)

    if last_result and last_result.get("ok"):
        last_result["status"] = "processing"
        last_result["task_id"] = task_id
        last_result["poll_url"] = _seedance_status_endpoint(task_id)
        return last_result
    return _provider_success(
        "bytedance",
        task_id,
        [],
        status="processing",
        task_id=task_id,
        poll_url=_seedance_status_endpoint(task_id),
    )


def _poll_attempt_settings(prefix: str, default_attempts: int = 60, default_interval: int = 5):
    try:
        attempts = int(os.getenv(f"{prefix}_POLL_ATTEMPTS") or default_attempts)
    except Exception:
        attempts = default_attempts
    try:
        interval = int(os.getenv(f"{prefix}_POLL_INTERVAL") or default_interval)
    except Exception:
        interval = default_interval
    return max(1, min(attempts, 60)), max(1, interval)


def _kling_poll_attempt_settings(default_attempts: int = 60, default_interval: int = 5):
    attempts, interval = _poll_attempt_settings("KLING", default_attempts, default_interval)
    # Kling Motion Control can stay in "submitted" for more than 50 seconds.
    # Keep env overrides useful for longer waits, but never let a short
    # production value end an accepted provider task before it can finish.
    return max(attempts, default_attempts), interval


def _kling_base_url():
    return os.getenv("KLING_API_ENDPOINT", "https://api-singapore.klingai.com").rstrip("/")


def _kling_submit_endpoint(provider_model: str, body: dict):
    kind = "image-to-video" if body.get("start_image") else "text-to-video"
    return f"{_kling_base_url()}/{kind}/{_kling_motion_provider_model(provider_model)}"


def _kling_omni_endpoint(provider_model: str):
    return f"{_kling_base_url()}/omni-video/{_kling_motion_provider_model(provider_model)}"


def _kling_motion_provider_model(provider_model: str):
    model = str(provider_model or "").strip()
    if model.endswith("-motion"):
        model = model[: -len("-motion")]
    return model or "kling-3.0"


def _kling_motion_endpoint(provider_model: str):
    return f"{_kling_base_url()}/motion-control/{_kling_motion_provider_model(provider_model)}"


def _kling_resolution(value: str, supported=None):
    resolution = str(value or "720p").strip().lower()
    if resolution == "4K".lower():
        resolution = "4k"
    supported_values = list(supported or ["720p", "1080p", "4k"])
    return resolution if resolution in supported_values else supported_values[0]


def _kling_duration(value, supported=None):
    supported_values = supported or {5, 10, 15}
    try:
        duration = int(value or 5)
    except Exception:
        duration = 5
    return duration if duration in supported_values else sorted(supported_values)[0]


def _kling_aspect_ratio(value):
    ratio = str(value or "16:9").strip()
    return ratio if ratio in {"16:9", "9:16", "1:1"} else "16:9"


def _kling_options(payload: dict):
    options = {"watermark_info": {"enabled": False}}
    if payload.get("job_id"):
        options["external_task_id"] = str(payload.get("job_id"))
    return options


def _kling_model_family(provider_model: str):
    return _kling_motion_provider_model(provider_model).lower()


def _kling_supports_last_frame(provider_model: str):
    model = _kling_model_family(provider_model)
    return model in {"kling-3.0", "kling-3.0-omni", "kling-2.6"}


def _kling_text_settings(provider_model: str, body: dict):
    model = _kling_model_family(provider_model)
    supported_resolutions = {"720p", "1080p"}
    if model in {"kling-3.0", "kling-3.0-omni"}:
        supported_resolutions.add("4k")
    duration_values = {5, 10} if model in {"kling-2.6", "kling-2.5-turbo"} else {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}
    if model == "kling-2.6" and body.get("sound"):
        supported_resolutions = {"1080p"}
    settings = {
        "duration": _kling_duration(body.get("duration"), duration_values),
        "resolution": _kling_resolution(body.get("resolution"), supported_resolutions),
        "aspect_ratio": _kling_aspect_ratio(body.get("ratio")),
    }
    if model in {"kling-3.0", "kling-3.0-omni"}:
        settings["audio"] = "native" if body.get("sound") else "off"
        settings["multi_shot"] = True
    if model == "kling-2.6":
        settings["audio"] = "native" if body.get("sound") else "off"
    return settings


def _kling_image_settings(provider_model: str, body: dict, has_last_frame=False):
    model = _kling_model_family(provider_model)
    supported_resolutions = {"720p", "1080p"}
    if model in {"kling-3.0", "kling-3.0-omni"} and not has_last_frame:
        supported_resolutions.add("4k")
    if model == "kling-2.6" and has_last_frame:
        supported_resolutions = {"720p"}
    if model == "kling-2.6" and body.get("sound") and not has_last_frame:
        supported_resolutions = {"1080p"}
    if model == "kling-2.5-turbo" and has_last_frame:
        supported_resolutions = {"1080p"}
    duration_values = {5, 10} if model in {"kling-2.6", "kling-2.5-turbo"} else {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}
    settings = {
        "duration": _kling_duration(body.get("duration"), duration_values),
        "resolution": _kling_resolution(body.get("resolution"), supported_resolutions),
    }
    if model in {"kling-3.0", "kling-3.0-omni"}:
        settings["audio"] = "native" if body.get("sound") else "off"
        settings["multi_shot"] = True
    if model == "kling-2.6":
        settings["audio"] = "native" if body.get("sound") and not has_last_frame else "off"
    return settings


def _kling_motion_settings(provider_model: str, body: dict, raw_options: dict):
    model = _kling_model_family(provider_model)
    supported_resolutions = {"720p", "1080p"}
    if model not in {"kling-3.0", "kling-2.6"}:
        supported_resolutions = {"720p", "1080p"}
    orientation = str(raw_options.get("character_orientation") or "video").strip().lower()
    if orientation not in {"image", "video"}:
        orientation = "video"
    audio = "original" if body.get("sound") else "off"
    return {
        "character_orientation": orientation,
        "resolution": _kling_resolution(body.get("resolution"), supported_resolutions),
        "audio": audio,
    }


def _kling_omni_settings(provider_model: str, body: dict, has_video=False, base_video=False):
    model = _kling_model_family(provider_model)
    supported_resolutions = {"720p", "1080p"}
    if model == "kling-3.0-omni":
        supported_resolutions.add("4k")
    duration_values = (
        {3, 4, 5, 6, 7, 8, 9, 10}
        if model == "kling-o1"
        else {3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}
    )
    settings = {
        "resolution": _kling_resolution(body.get("resolution"), supported_resolutions),
        "duration": _kling_duration(body.get("duration"), duration_values),
        "audio": "original" if has_video and body.get("sound") else "off",
        "aspect_ratio": _kling_aspect_ratio(body.get("ratio")),
    }
    if model == "kling-3.0-omni":
        settings["multi_shot"] = False if base_video else True
    return settings


def _kling_task_endpoint(task_id: str):
    return f"{_kling_base_url()}/tasks?task_ids={task_id}"


KLING_LEGACY_MODEL_NAMES = {
    "kling_2_1": "kling-v2-1",
    "kling_2_1_master": "kling-v2-1-master",
    "kling_2_0_master": "kling-v2-master",
    "kling_1_6": "kling-v1-6",
    "kling_1_5": "kling-v1-5",
    "kling_1_0": "kling-v1",
}


def _kling_is_legacy_model(model_id: str):
    return str(model_id or "").strip() in KLING_LEGACY_MODEL_NAMES


def _kling_legacy_submit_endpoint(kind: str):
    path = "image2video" if kind == "image" else "text2video"
    return f"{_kling_base_url()}/v1/videos/{path}"


def _kling_legacy_task_endpoint(task_id: str, kind: str):
    path = "image2video" if kind == "image" else "text2video"
    return f"{_kling_base_url()}/v1/videos/{path}/{task_id}"


def _kling_legacy_mode(resolution: str):
    value = _kling_resolution_key(resolution)
    if value == "4k":
        return "4k"
    if value == "1080p":
        return "pro"
    return "std"


def _kling_extract_video_url(data: dict):
    tasks = data.get("data") if isinstance(data.get("data"), list) else []
    task = tasks[0] if tasks else (data.get("data") if isinstance(data.get("data"), dict) else data)
    if not isinstance(task, dict):
        return None
    task_result = task.get("task_result") if isinstance(task.get("task_result"), dict) else {}
    legacy_videos = task_result.get("videos") if isinstance(task_result.get("videos"), list) else []
    for item in legacy_videos:
        if isinstance(item, dict) and item.get("url"):
            return item.get("url")
    outputs = task.get("outputs") or []
    if isinstance(outputs, list):
        for item in outputs:
            if isinstance(item, dict) and (item.get("type") == "video" or item.get("url")):
                return item.get("url")
    return task.get("video_url") or task.get("url") or (task.get("assets") or {}).get("video")


def _kling_status(data: dict):
    tasks = data.get("data") if isinstance(data.get("data"), list) else []
    task = tasks[0] if tasks else (data.get("data") if isinstance(data.get("data"), dict) else data)
    if not isinstance(task, dict):
        return ""
    return str(task.get("status") or task.get("state") or task.get("task_status") or "").lower()


def _kling_poll_until_ready(task_id: str, headers: dict):
    attempts, interval = _kling_poll_attempt_settings(60, 5)
    last_result = None
    for attempt in range(1, attempts + 1):
        endpoint = _kling_task_endpoint(task_id)
        response = _request_get(endpoint, headers)
        data = _safe_provider_json_response(response, "kling", endpoint)
        _log_provider_response("kling", "POLL", endpoint, {"task_id": task_id, "attempt": attempt}, response, data)
        status_code = getattr(response, "status_code", None) or 0
        if status_code >= 400 or data.get("ok") is False or data.get("code") not in (None, 0):
            return _provider_parse_error("kling", task_id, data)
        state = _kling_status(data)
        video_url = _kling_extract_video_url(data)
        print("KLING VIDEO POLL:", {
            "attempt": attempt,
            "task_id": task_id,
            "status": state,
            "has_video_url": bool(video_url),
            "video_url": video_url or "",
        })
        if state in {"succeeded", "completed", "success", "done"} and video_url:
            return _provider_success("kling", task_id, [video_url], status="completed", task_id=task_id)
        if state in {"failed", "error", "cancelled"}:
            return _provider_parse_error("kling", task_id, data)
        last_result = _provider_success("kling", task_id, [], status="processing", task_id=task_id, poll_url=endpoint)
        if attempt < attempts:
            time.sleep(interval)
    return last_result or _provider_success("kling", task_id, [], status="processing", task_id=task_id, poll_url=_kling_task_endpoint(task_id))


def _kling_legacy_poll_until_ready(task_id: str, kind: str, headers: dict):
    attempts, interval = _kling_poll_attempt_settings(60, 5)
    last_result = None
    for attempt in range(1, attempts + 1):
        endpoint = _kling_legacy_task_endpoint(task_id, kind)
        response = _request_get(endpoint, headers)
        data = _safe_provider_json_response(response, "kling", endpoint)
        _log_provider_response("kling", "POLL_LEGACY", endpoint, {"task_id": task_id, "attempt": attempt}, response, data)
        status_code = getattr(response, "status_code", None) or 0
        if status_code >= 400 or data.get("ok") is False or data.get("code") not in (None, 0):
            return _provider_parse_error("kling", task_id, data)
        state = _kling_status(data)
        video_url = _kling_extract_video_url(data)
        print("KLING LEGACY VIDEO POLL:", {
            "attempt": attempt,
            "task_id": task_id,
            "status": state,
            "has_video_url": bool(video_url),
            "video_url": video_url or "",
        })
        if state in {"succeed", "succeeded", "completed", "success", "done"} and video_url:
            return _provider_success("kling", task_id, [video_url], status="completed", task_id=task_id)
        if state in {"failed", "error", "cancelled"}:
            return _provider_parse_error("kling", task_id, data)
        last_result = _provider_success("kling", task_id, [], status="processing", task_id=task_id, poll_url=endpoint)
        if attempt < attempts:
            time.sleep(interval)
    return last_result or _provider_success("kling", task_id, [], status="processing", task_id=task_id, poll_url=_kling_legacy_task_endpoint(task_id, kind))


def _luma_base_url():
    endpoint = os.getenv("LUMA_AGENTS_ENDPOINT", os.getenv("LUMA_API_ENDPOINT", "https://agents.lumalabs.ai/v1/generations"))
    return endpoint.rsplit("/generations", 1)[0].rstrip("/")


def _luma_task_endpoint(task_id: str):
    return f"{_luma_base_url()}/generations/{task_id}"


def _luma_poll_until_ready(task_id: str, headers: dict):
    attempts, interval = _poll_attempt_settings("LUMA", 60, 5)
    last_result = None
    for attempt in range(1, attempts + 1):
        endpoint = _luma_task_endpoint(task_id)
        response = _request_get(endpoint, headers)
        data = _safe_provider_json_response(response, "luma", endpoint)
        status_code = getattr(response, "status_code", None) or 0
        if status_code >= 400 or data.get("ok") is False:
            return _provider_parse_error("luma", task_id, data)
        state = str(data.get("state") or data.get("status") or "").lower()
        urls = _normalize_video_urls(data)
        video_url = (data.get("assets") or {}).get("video") or (urls[0] if urls else "")
        print("LUMA VIDEO POLL:", {
            "attempt": attempt,
            "task_id": task_id,
            "status": state,
            "has_video_url": bool(video_url),
            "video_url": video_url or "",
        })
        if state in {"completed", "succeeded", "success", "done"} and video_url:
            return _provider_success("luma", task_id, [video_url], status="completed", task_id=task_id)
        if state in {"failed", "error", "cancelled"}:
            return _provider_parse_error("luma", task_id, data)
        last_result = _provider_success("luma", task_id, [], status="processing", task_id=task_id, poll_url=endpoint)
        if attempt < attempts:
            time.sleep(interval)
    return last_result or _provider_success("luma", task_id, [], status="processing", task_id=task_id, poll_url=_luma_task_endpoint(task_id))


async def _send_generated_videos_to_telegram(telegram_id: int, videos: list[str], caption: str = ""):
    bot_token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("TELEGRAM VIDEO SEND:", {"telegram_id": telegram_id, "has_video_url": bool(videos), "error": "bot token missing"})
        return False
    if not telegram_id or not videos:
        print("TELEGRAM VIDEO SEND:", {"telegram_id": telegram_id, "has_video_url": bool(videos), "error": "telegram_id or video_url missing"})
        return False

    sent_any = False
    async with httpx.AsyncClient(timeout=120.0) as client:
        for index, video_url in enumerate(videos):
            try:
                video_response = await client.get(video_url)
                if video_response.status_code >= 400 or not video_response.content:
                    print("TELEGRAM VIDEO SEND:", {
                        "telegram_id": telegram_id,
                        "has_video_url": bool(video_url),
                        "error": f"download failed: {video_response.status_code}",
                    })
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
                    print("TELEGRAM VIDEO SEND:", {"telegram_id": telegram_id, "has_video_url": bool(video_url), "ok": True})
                else:
                    print("TELEGRAM VIDEO SEND:", {
                        "telegram_id": telegram_id,
                        "has_video_url": bool(video_url),
                        "error": tg_response.text[:500],
                    })
            except Exception:
                print("TELEGRAM VIDEO SEND:", {"telegram_id": telegram_id, "has_video_url": bool(video_url), "error": "exception"})
                continue
    return sent_any


def _provider_error(provider: str, model_id: str, detail: str):
    user_message = translate_provider_error(detail, provider=provider, model=model_id)
    return {
        "ok": False,
        "type": "video",
        "provider": provider,
        "model": model_id,
        "error": user_message,
        "message": user_message,
        "raw_error": raw_error_text(detail, ""),
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
        data = json.loads(text)
        if isinstance(data, dict):
            data.setdefault("status_code", status)
            data.setdefault("endpoint", endpoint)
        return data
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
        data = json.loads(text)
        if isinstance(data, dict):
            data.setdefault("status_code", status)
            data.setdefault("endpoint", endpoint)
        return data
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
    provider_message = ""
    if isinstance(data, dict):
        nested_data = data.get("data")
        if isinstance(nested_data, list) and nested_data:
            first_item = nested_data[0] if isinstance(nested_data[0], dict) else {}
            if isinstance(first_item, dict):
                provider_message = first_item.get("message") or first_item.get("error") or ""
        elif isinstance(nested_data, dict):
            provider_message = nested_data.get("message") or nested_data.get("error") or ""
        provider_message = (
            provider_message
            or data.get("message")
            or data.get("msg")
            or data.get("detail")
            or data.get("details")
            or data.get("body_preview")
            or ""
        )
        if not provider_message and data.get("code") not in (None, 0):
            provider_message = f"Provider error code {data.get('code')}"
    raw_message = provider_message or raw_error_text(data, "")
    user_message = translate_provider_error(raw_message or data, provider=provider, model=model_id)
    result = {
        "ok": False,
        "type": "video",
        "provider": provider,
        "model": model_id,
        "error": user_message,
        "message": user_message,
        "raw_error": raw_message or data.get("error") or provider_message or "",
    }
    for key in ("status_code", "details", "endpoint", "body_preview", "code", "message", "msg"):
        if key in data:
            result[key] = data.get(key)
    if isinstance(data, dict):
        result["provider_response"] = data
    return result


async def poll_video_generation(result: dict) -> dict:
    if not isinstance(result, dict):
        return _provider_error("video", "", "Generation status is unavailable")
    provider = str(result.get("provider") or "").lower()
    model_id = result.get("model") or ""
    task_id = result.get("task_id") or result.get("workId") or result.get("id") or ""
    if not task_id:
        return _provider_error(provider or "video", model_id, "Generation task id is unavailable")
    if provider in {"bytedance", "seedance"}:
        api_key = _get_env("BYTEDANCE_API_KEY", "BYTEPLUS_API_KEY", "ARK_API_KEY")
        if not api_key:
            return _provider_error("bytedance", model_id, "Provider API key is missing: BYTEDANCE_API_KEY")
        return _seedance_poll_until_ready(str(task_id), _seedance_headers(api_key), max_attempts=1, interval_seconds=1)
    if provider == "kling":
        api_key = _get_env("KLING_API_KEY", "KLING_ACCESS_KEY")
        if not api_key:
            return _provider_error("kling", model_id, "Provider API key is missing: KLING_API_KEY")
        return _kling_poll_until_ready(str(task_id), {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    if provider == "heygen":
        api_key = _get_env("HEYGEN_API_KEY")
        if not api_key:
            return _provider_error("heygen", model_id, "Provider API key is missing: HEYGEN_API_KEY")
        session_id = result.get("session_id") or ""
        poll_url = str(result.get("poll_url") or "")
        video_id = str(task_id) if "/v3/videos/" in poll_url or str(task_id).startswith(("vid", "v_")) else ""
        if not session_id and not video_id:
            session_id = str(task_id)
        return _heygen_poll_until_ready(session_id=session_id, video_id=video_id, headers=_heygen_headers(api_key))
    if provider == "luma":
        api_key = _get_env("LUMA_AGENTS_API_KEY", "LUMA_API_KEY")
        if not api_key:
            return _provider_error("luma", model_id, "Provider API key is missing: LUMA_AGENTS_API_KEY")
        return _luma_poll_until_ready(str(task_id), {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    if provider == "gemini":
        api_key = _get_env("GEMINI_API_KEY", "GOOGLE_API_KEY")
        if not api_key:
            return _provider_error("gemini", model_id, "Provider API key is missing: GEMINI_API_KEY")
        endpoint = (result.get("poll_url") or f"https://generativelanguage.googleapis.com/v1beta/interactions/{task_id}").rstrip("/")
        try:
            response = _request_get(endpoint, {"x-goog-api-key": api_key})
            data = _safe_provider_json_response(response, "gemini", endpoint)
            _log_provider_response("gemini", "POLL", endpoint, {}, response, data)
            if getattr(response, "status_code", 0) >= 400 or data.get("ok") is False:
                return _provider_parse_error("gemini", model_id, data)
            videos = _extract_gemini_videos(data, api_key)
            if videos:
                return _provider_success("gemini", model_id, videos, status="completed", task_id=str(task_id))
            state = str(data.get("status") or "").lower()
            if state in {"failed", "cancelled", "canceled"}:
                return _provider_parse_error("gemini", model_id, data)
            return _provider_success("gemini", model_id, [], status="processing", task_id=str(task_id), poll_url=endpoint)
        except Exception as exc:
            return _provider_error("gemini", model_id, f"Provider polling failed: {exc}")
    return _provider_success(provider or "video", model_id, [], status="processing", task_id=str(task_id), poll_url=result.get("poll_url") or "")


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


def _seedance_provider_success(model_id: str, video_urls: list[str], data: dict, status: str = "completed", task_id: str = None, poll_url: str = None):
    result = _provider_success("bytedance", model_id, video_urls, status=status, task_id=task_id, poll_url=poll_url)
    result["metadata"] = _seedance_task_metadata(data)
    meta = result["metadata"]
    if isinstance(meta, dict):
        if meta.get("duration") is not None:
            result["duration"] = meta.get("duration")
        if meta.get("resolution") is not None:
            result["resolution"] = meta.get("resolution")
        if meta.get("ratio") is not None:
            result["ratio"] = meta.get("ratio")
        if meta.get("seed") is not None:
            result["seed"] = meta.get("seed")
        if meta.get("last_frame_url"):
            result["last_frame_url"] = meta.get("last_frame_url")
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


def _heygen_headers(api_key: str):
    return {
        "X-Api-Key": api_key,
        "Content-Type": "application/json",
    }


def _heygen_base_url():
    return os.getenv("HEYGEN_BASE_URL", "https://api.heygen.com").rstrip("/")


def _heygen_video_url_from_data(data: dict):
    if not isinstance(data, dict):
        return ""
    item = data.get("data") if isinstance(data.get("data"), dict) else data
    return (
        item.get("video_url")
        or item.get("url")
        or item.get("download_url")
        or item.get("file_url")
        or ""
    )


def _heygen_video_status(data: dict):
    if not isinstance(data, dict):
        return ""
    item = data.get("data") if isinstance(data.get("data"), dict) else data
    return str(item.get("status") or item.get("state") or "").lower()


def _heygen_video_id_from_session(data: dict):
    if not isinstance(data, dict):
        return ""
    item = data.get("data") if isinstance(data.get("data"), dict) else data
    return str(item.get("video_id") or item.get("videoId") or "").strip()


def _public_input_url(value: str):
    text = str(value or "").strip()
    if not text:
        return ""
    if re.match(r"^https?://", text, re.I):
        return text
    if text.startswith("/"):
        base = (
            os.getenv("WEBAPP_URL")
            or os.getenv("PUBLIC_WEBAPP_URL")
            or os.getenv("PUBLIC_BASE_URL")
            or "https://sylvex-ai-webapp-production.up.railway.app"
        ).rstrip("/")
        return f"{base}{text}" if base else text
    return text


def _heygen_asset_input(value):
    if isinstance(value, dict):
        if value.get("type") in {"url", "asset_id", "base64"}:
            return value
        for key in ("asset_id", "url", "image_url", "video_url", "src", "href"):
            if value.get(key):
                if key == "asset_id":
                    return {"type": "asset_id", "asset_id": str(value.get(key))}
                return _heygen_asset_input(value.get(key))
    text = str(value or "").strip()
    if not text:
        return {}
    if text.startswith("data:") and ";base64," in text:
        header, data = text.split(";base64,", 1)
        media_type = header.replace("data:", "").split(";", 1)[0] or "application/octet-stream"
        return {"type": "base64", "media_type": media_type, "data": data.strip()}
    if re.match(r"^https?://", text, re.I):
        return {"type": "url", "url": text}
    if text.startswith("/"):
        content, mime_type = _read_media_bytes(text, "image")
        if content:
            return {"type": "base64", "media_type": mime_type or "application/octet-stream", "data": base64.b64encode(content).decode("utf-8")}
        public_url = _public_input_url(text)
        if public_url:
            return {"type": "url", "url": public_url}
    return {}


def _heygen_files_from_payload(body: dict, payload: dict):
    raw_options = payload.get("video_options") or payload.get("options") or {}
    candidates = []
    explicit_files = raw_options.get("files") or raw_options.get("heygen_files") or payload.get("files") or []
    if isinstance(explicit_files, list):
        candidates.extend(explicit_files)
    for key in ("start_image", "image_url", "input_video", "video_url", "reference_video"):
        if body.get(key):
            candidates.append(body.get(key))
        if raw_options.get(key):
            candidates.append(raw_options.get(key))
        if payload.get(key):
            candidates.append(payload.get(key))
    for key in ("reference_images", "referenceImageUrls", "uploadedImageUrls"):
        value = raw_options.get(key) or payload.get(key) or body.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    files = []
    seen = set()
    for item in candidates:
        asset = _heygen_asset_input(item)
        if not asset:
            continue
        marker = json.dumps(asset, sort_keys=True, ensure_ascii=False)
        if marker in seen:
            continue
        seen.add(marker)
        files.append(asset)
        if len(files) >= 20:
            break
    return files


def _heygen_poll_until_ready(session_id: str = "", video_id: str = "", headers: dict = None):
    headers = headers or {}
    base = _heygen_base_url()
    attempts, interval = _poll_attempt_settings("HEYGEN", 90, 5)
    last_result = None
    current_video_id = video_id or ""
    for attempt in range(1, attempts + 1):
        if not current_video_id and session_id:
            session_url = f"{base}/v3/video-agents/{session_id}"
            session_response = _request_get(session_url, headers)
            session_data = _safe_provider_json_response(session_response, "heygen", session_url)
            _log_provider_response("heygen", "SESSION_POLL", session_url, {"session_id": session_id, "attempt": attempt}, session_response, session_data)
            if getattr(session_response, "status_code", 0) >= 400 or session_data.get("ok") is False:
                return _provider_parse_error("heygen", session_id, session_data)
            current_video_id = _heygen_video_id_from_session(session_data)
            status = _heygen_video_status(session_data) or "processing"
            last_result = _provider_success("heygen", session_id, [], status=status, task_id=session_id, poll_url=session_url)

        if current_video_id:
            video_url = f"{base}/v3/videos/{current_video_id}"
            video_response = _request_get(video_url, headers)
            video_data = _safe_provider_json_response(video_response, "heygen", video_url)
            _log_provider_response("heygen", "VIDEO_POLL", video_url, {"video_id": current_video_id, "attempt": attempt}, video_response, video_data)
            if getattr(video_response, "status_code", 0) >= 400 or video_data.get("ok") is False:
                return _provider_parse_error("heygen", current_video_id, video_data)
            status = _heygen_video_status(video_data) or "processing"
            ready_url = _heygen_video_url_from_data(video_data)
            if status in {"completed", "done", "success"} and ready_url:
                return _provider_success("heygen", current_video_id, [ready_url], status="completed", task_id=current_video_id)
            if status in {"failed", "error"}:
                return _provider_parse_error("heygen", current_video_id, video_data)
            last_result = _provider_success("heygen", current_video_id, [], status="processing", task_id=current_video_id, poll_url=video_url)

        if attempt < attempts:
            time.sleep(interval)
    return last_result or _provider_success("heygen", session_id or current_video_id, [], status="processing", task_id=session_id or current_video_id)


def _telegram_caption(model_id: str, provider: str, payload: dict):
    opts = _build_video_payload(model_id, payload.get("prompt") or "", payload)
    model_labels = {
        "seedance_2_fast": "Seedance 2.0 Fast",
        "seedance_2_0": "Seedance 2.0",
        "seedance_1_5_pro": "Seedance 1.5 Pro",
    }
    provider_labels = {
        "bytedance": "BytePlus",
        "seedance": "BytePlus",
    }
    model_label = model_labels.get(model_id, model_id)
    provider_label = provider_labels.get((provider or "").lower(), provider)
    return (
        "SYLVEX Pro Studio\n"
        "Видео готово ✅\n\n"
        f"Модель: {model_label}\n"
        f"Провайдер: {provider_label}\n"
        f"Формат: {opts.get('ratio')}\n"
        f"Длительность: {opts.get('duration')} сек"
    )


def _call_seedance(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("BYTEDANCE_API_KEY", "BYTEPLUS_API_KEY", "BYTEPLUS_ARK_API_KEY", "ARK_API_KEY")
    if not api_key:
        return _provider_error("seedance", model_id, "Provider API key is missing: BYTEDANCE_API_KEY / BYTEPLUS_API_KEY / BYTEPLUS_ARK_API_KEY / ARK_API_KEY")
    body = _seedance_body(model_id, prompt, payload)
    if not body:
        return _unknown_seedance_video_model_response(model_id)
    try:
        endpoint = _seedance_submit_endpoint()
        headers = _seedance_headers(api_key)
        print("SEEDANCE VIDEO SUBMIT DEBUG:", {
            "endpoint": endpoint,
            "model": model_id,
            "provider_model": body.get("model"),
            "duration": body.get("duration"),
            "ratio": body.get("ratio"),
            "resolution": body.get("resolution"),
            "generate_audio": body.get("generate_audio"),
            "content_types": [item.get("type") for item in body.get("content", []) if isinstance(item, dict)],
            "has_image_refs": any(isinstance(item, dict) and item.get("type") == "image_url" for item in body.get("content", [])),
            "has_video_refs": any(isinstance(item, dict) and item.get("type") == "video_url" for item in body.get("content", [])),
        })
        response = _request_json(
            endpoint,
            headers,
            body,
        )
        data = _safe_provider_json_response(response, "bytedance", endpoint)
        status = getattr(response, "status_code", None) or 0
        print("SEEDANCE VIDEO SUBMIT RESPONSE:", {
            "http_status": status,
            "response_keys": sorted(list(data.keys())) if isinstance(data, dict) else [],
            "task_id": _task_id_from_response(data) if isinstance(data, dict) else None,
            "status": _seedance_status(data) if isinstance(data, dict) else "",
            "has_video_url": bool(_normalize_video_urls(data)),
        })
        if status not in (200, 201, 202) or data.get("ok") is False:
            return _provider_parse_error("bytedance", model_id, data)
        video_urls = _normalize_video_urls(data)
        if video_urls:
            return _provider_success("bytedance", model_id, video_urls)
        task_id = _task_id_from_response(data)
        submit_status = _seedance_status(data) or data.get("status") or data.get("state") or "processing"
        print("SEEDANCE VIDEO SUBMIT RESPONSE:", {
            "task_id": task_id,
            "status": submit_status,
        })
        if not task_id:
            return _provider_error("bytedance", model_id, "Seedance task id not found")
        result = _seedance_poll_until_ready(task_id, headers)
        result["model"] = model_id
        result["provider_model"] = body.get("model")
        return result
    except Exception as exc:
        return _provider_error("bytedance", model_id, f"Provider request failed: {exc}")


def _call_heygen(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("HEYGEN_API_KEY")
    if not api_key:
        return _provider_error("heygen", model_id, "Provider API key is missing: HEYGEN_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    raw_options = payload.get("video_options") or payload.get("options") or {}

    heygen_body = {
        "prompt": prompt,
    }
    mode = str(raw_options.get("heygen_mode") or raw_options.get("session_mode") or raw_options.get("mode") or "generate").strip().lower()
    if mode in {"generate", "chat"}:
        heygen_body["mode"] = mode
    avatar_id = raw_options.get("avatar_id") or raw_options.get("heygen_avatar_id") or os.getenv("HEYGEN_AVATAR_ID")
    voice_id = raw_options.get("voice_id") or raw_options.get("heygen_voice_id") or os.getenv("HEYGEN_VOICE_ID")
    style_id = raw_options.get("style_id") or raw_options.get("heygen_style_id") or os.getenv("HEYGEN_STYLE_ID")
    brand_kit_id = raw_options.get("brand_kit_id") or raw_options.get("heygen_brand_kit_id") or os.getenv("HEYGEN_BRAND_KIT_ID")
    for key, value in (
        ("avatar_id", avatar_id),
        ("voice_id", voice_id),
        ("style_id", style_id),
        ("brand_kit_id", brand_kit_id),
    ):
        if value:
            heygen_body[key] = str(value)
    orientation = str(raw_options.get("orientation") or "").strip().lower()
    if orientation not in {"landscape", "portrait"}:
        orientation = "portrait" if body.get("ratio") == "9:16" else "landscape" if body.get("ratio") == "16:9" else ""
    if orientation:
        heygen_body["orientation"] = orientation
    files = _heygen_files_from_payload(body, payload)
    if files:
        heygen_body["files"] = files
    callback_url = raw_options.get("callback_url") or payload.get("callback_url") or os.getenv("HEYGEN_CALLBACK_URL")
    callback_id = raw_options.get("callback_id") or payload.get("callback_id") or payload.get("job_id") or payload.get("generation_id")
    if callback_url:
        heygen_body["callback_url"] = str(callback_url)
    if callback_id:
        heygen_body["callback_id"] = str(callback_id)
    if raw_options.get("incognito_mode") is not None:
        heygen_body["incognito_mode"] = bool(raw_options.get("incognito_mode"))

    try:
        endpoint = os.getenv(
            "HEYGEN_VIDEO_ENDPOINT",
            "https://api.heygen.com/v3/video-agents"
        )

        response = _request_json(
            endpoint,
            _heygen_headers(api_key),
            heygen_body,
        )
        data = _safe_provider_json_response(response, "heygen", endpoint)
        _log_provider_response("heygen", "CREATE_VIDEO_AGENT", endpoint, heygen_body, response, data)

        if getattr(response, "status_code", 0) >= 400:
            return _provider_parse_error("heygen", model_id, data)

        session = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
        session_id = session.get("session_id") or session.get("id") or ""
        video_id = session.get("video_id") or ""
        status = session.get("status") or "processing"

        if video_id:
            result = _heygen_poll_until_ready(session_id=session_id, video_id=video_id, headers=_heygen_headers(api_key))
            result["model"] = model_id
            result["session_id"] = session_id
            return result

        return {
            "ok": True,
            "type": "video",
            "provider": "heygen",
            "model": model_id,
            "status": status,
            "task_id": session_id,
            "session_id": session_id,
            "poll_url": f"{_heygen_base_url()}/v3/video-agents/{session_id}" if session_id else None,
            "metadata": {
                "heygen_session_id": session_id,
                "heygen_status": status,
            },
        }

    except Exception as exc:
        return _provider_error(
            "heygen",
            model_id,
            f"Provider request failed: {exc}",
        )


def _heygen_direct_common_fields(request_body: dict, body: dict, raw_options: dict, payload: dict):
    ratio = body.get("ratio") or raw_options.get("aspect_ratio") or "auto"
    if ratio not in {"auto", "16:9", "9:16", "4:5", "5:4", "1:1"}:
        ratio = "auto"
    resolution = str(body.get("resolution") or raw_options.get("resolution") or "1080p").lower()
    if resolution not in {"720p", "1080p", "4k"}:
        resolution = "1080p"
    request_body["aspect_ratio"] = ratio
    request_body["resolution"] = resolution
    for key in ("title", "fit", "remove_background", "output_format", "background", "caption", "voice_settings", "audio_url", "audio_asset_id"):
        if raw_options.get(key) not in (None, ""):
            request_body[key] = raw_options.get(key)
    callback_url = raw_options.get("callback_url") or payload.get("callback_url") or os.getenv("HEYGEN_CALLBACK_URL")
    callback_id = raw_options.get("callback_id") or payload.get("callback_id") or payload.get("job_id") or payload.get("generation_id")
    if callback_url:
        request_body["callback_url"] = str(callback_url)
    if callback_id:
        request_body["callback_id"] = str(callback_id)
    return request_body


def _call_heygen_direct_video(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("HEYGEN_API_KEY")
    if not api_key:
        return _provider_error("heygen", model_id, "Provider API key is missing: HEYGEN_API_KEY")
    body = _build_video_payload(model_id, prompt, payload)
    raw_options = payload.get("video_options") or payload.get("options") or {}
    provider_model = _provider_model_for_video(model_id)
    endpoint = _video_model_mapping(model_id).get("endpoint") or f"{_heygen_base_url()}/v3/videos"
    request_body = {}

    if provider_model in {"avatar_iv", "avatar_v", "avatar_iii"}:
        avatar_id = raw_options.get("avatar_id") or raw_options.get("heygen_avatar_id") or os.getenv("HEYGEN_AVATAR_ID")
        if not avatar_id:
            return _provider_error("heygen", model_id, "Для HeyGen Avatar нужно указать avatar_id")
        request_body = {
            "type": "avatar",
            "avatar_id": str(avatar_id),
            "script": raw_options.get("script") or prompt,
            "engine": {"type": provider_model},
        }
        voice_id = raw_options.get("voice_id") or raw_options.get("heygen_voice_id") or os.getenv("HEYGEN_VOICE_ID")
        if voice_id:
            request_body["voice_id"] = str(voice_id)
        if raw_options.get("motion_prompt"):
            request_body["motion_prompt"] = str(raw_options.get("motion_prompt"))
        elif provider_model in {"avatar_iv", "avatar_v"} and body.get("motion_control"):
            request_body["motion_prompt"] = prompt
        if provider_model == "avatar_v" and raw_options.get("reference_look_id"):
            request_body["engine"]["reference_look_id"] = str(raw_options.get("reference_look_id"))
        if provider_model == "avatar_iv" and raw_options.get("expressiveness") in {"low", "medium", "high"}:
            request_body["expressiveness"] = raw_options.get("expressiveness")

    elif provider_model == "image":
        image_source = body.get("start_image") or body.get("image_url") or raw_options.get("image_url") or ""
        image_asset = _heygen_asset_input(image_source)
        if not image_asset:
            return _provider_error("heygen", model_id, "Для HeyGen Image Video нужно загрузить изображение")
        request_body = {
            "type": "image",
            "image": image_asset,
            "script": raw_options.get("script") or prompt,
        }
        voice_id = raw_options.get("voice_id") or raw_options.get("heygen_voice_id") or os.getenv("HEYGEN_VOICE_ID")
        if voice_id:
            request_body["voice_id"] = str(voice_id)
        if raw_options.get("motion_prompt"):
            request_body["motion_prompt"] = str(raw_options.get("motion_prompt"))
        if raw_options.get("expressiveness") in {"low", "medium", "high"}:
            request_body["expressiveness"] = raw_options.get("expressiveness")

    elif provider_model == "cinematic_avatar":
        avatar_ids = raw_options.get("avatar_id") or raw_options.get("avatar_ids") or raw_options.get("heygen_avatar_id") or os.getenv("HEYGEN_AVATAR_ID")
        if isinstance(avatar_ids, str):
            avatar_ids = [item.strip() for item in avatar_ids.split(",") if item.strip()]
        if not isinstance(avatar_ids, list) or not avatar_ids:
            return _provider_error("heygen", model_id, "Для HeyGen Cinematic Avatar нужно указать 1–3 avatar_id")
        request_body = {
            "type": "cinematic_avatar",
            "prompt": prompt,
            "avatar_id": avatar_ids[:3],
            "references": _heygen_files_from_payload(body, payload),
            "aspect_ratio": body.get("ratio") if body.get("ratio") in {"16:9", "9:16", "1:1"} else "16:9",
            "resolution": body.get("resolution") if body.get("resolution") in {"720p", "1080p"} else "720p",
        }
        duration = int(body.get("duration") or 10)
        if 4 <= duration <= 15 and not raw_options.get("auto_duration"):
            request_body["duration"] = duration
        if raw_options.get("auto_duration") is not None:
            request_body["auto_duration"] = bool(raw_options.get("auto_duration"))
        if raw_options.get("enhance_prompt") is not None:
            request_body["enhance_prompt"] = bool(raw_options.get("enhance_prompt"))

    else:
        return _provider_error("heygen", model_id, f"Unsupported HeyGen direct model: {provider_model}")

    if provider_model != "cinematic_avatar":
        _heygen_direct_common_fields(request_body, body, raw_options, payload)
    try:
        headers = _heygen_headers(api_key)
        idempotency_key = payload.get("job_id") or payload.get("generation_id") or ""
        if idempotency_key:
            headers["Idempotency-Key"] = str(idempotency_key)[:255]
        response = _request_json(endpoint, headers, request_body)
        data = _safe_provider_json_response(response, "heygen", endpoint)
        _log_provider_response("heygen", "CREATE_VIDEO", endpoint, request_body, response, data)
        if getattr(response, "status_code", 0) >= 400 or data.get("ok") is False:
            return _provider_parse_error("heygen", model_id, data)
        item = data.get("data") if isinstance(data.get("data"), dict) else data
        video_id = str(item.get("video_id") or item.get("id") or "").strip()
        status = item.get("status") or "processing"
        if not video_id:
            return _provider_parse_error("heygen", model_id, data)
        return _provider_success("heygen", model_id, [], status=status, task_id=video_id, poll_url=f"{_heygen_base_url()}/v3/videos/{video_id}")
    except Exception as exc:
        return _provider_error("heygen", model_id, f"Provider request failed: {exc}")


def _call_luma(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("LUMA_AGENTS_API_KEY", "LUMA_API_KEY")
    if not api_key:
        return _provider_error("luma", model_id, "Provider API key is missing: LUMA_AGENTS_API_KEY")
    provider_model = _provider_model_for_video(model_id)
    if not provider_model:
        return _unknown_video_model_mapping_response(model_id, "luma")
    body = _build_video_payload(model_id, prompt, payload)
    try:
        endpoint = _video_model_mapping(model_id).get("endpoint") or os.getenv("LUMA_AGENTS_ENDPOINT", "https://agents.lumalabs.ai/v1/generations")
        mode = str(body.get("mode") or body.get("generation_mode") or "text_to_video").strip().lower()
        luma_type = "video"
        if mode in {"video_edit", "edit"} or body.get("input_video") or body.get("video_url") or body.get("reference_video"):
            luma_type = "video_edit"
        if mode in {"video_reframe", "reframe"}:
            luma_type = "video_reframe"
        luma_body = {
            "model": provider_model,
            "type": luma_type,
            "prompt": prompt,
            "aspect_ratio": body.get("ratio") or "16:9",
        }
        user_id = str(payload.get("telegram_id") or payload.get("user_id") or "").strip()
        if user_id:
            luma_body["user_id"] = user_id[:256]
        if luma_type == "video":
            video_options = {
                "resolution": body.get("resolution") or "720p",
                "duration": f"{int(body.get('duration') or 5)}s",
            }
            if body.get("start_image"):
                video_options["start_frame"] = {"url": _public_input_url(body.get("start_image"))}
            if body.get("end_image"):
                video_options["end_frame"] = {"url": _public_input_url(body.get("end_image"))}
            luma_body["video"] = video_options
        else:
            source_video = (
                body.get("input_video")
                or body.get("video_url")
                or body.get("reference_video")
                or body.get("template_video_url")
                or (payload.get("video_options") or {}).get("input_video")
                or (payload.get("video_options") or {}).get("video_url")
                or payload.get("video_url")
            )
            if not source_video:
                return _provider_error("luma", model_id, "Для Luma video edit/reframe нужно загрузить видео")
            luma_body["source"] = {"url": _public_input_url(source_video)}
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            luma_body,
        )
        data = _safe_provider_json_response(response, "luma", endpoint)
        _log_provider_response("luma", "SUBMIT", endpoint, luma_body, response, data)
        status = getattr(response, "status_code", None) or 0
        if status not in (200, 201, 202) or data.get("ok") is False:
            return _provider_parse_error("luma", model_id, data)
        urls = _normalize_video_urls(data)
        if urls:
            return _provider_success("luma", model_id, urls)
        task_id = _task_id_from_response(data)
        if not task_id:
            return _provider_error("luma", model_id, "Luma task id not found")
        result = _luma_poll_until_ready(task_id, {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        result["model"] = model_id
        result["provider_model"] = provider_model
        return result
    except Exception as exc:
        return _provider_error("luma", model_id, f"Provider request failed: {exc}")


def _call_kling(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("KLING_API_KEY", "KLING_ACCESS_KEY")
    if not api_key:
        return _provider_error("kling", model_id, "Provider API key is missing: KLING_API_KEY")
    provider_model = _provider_model_for_video(model_id)
    if not provider_model:
        return _unknown_video_model_mapping_response(model_id, "kling")

    prompt_report = optimize_prompt_for_model(prompt, model=model_id, provider="kling", mode="video")
    print("KLING PROMPT OPTIMIZER:", {
        "model": model_id,
        "provider_model": provider_model,
        "prompt_length": prompt_report.get("original_length"),
        "metric": prompt_report.get("metric"),
        "model_limit": prompt_report.get("limit"),
        "optimized": prompt_report.get("optimized"),
        "new_length": prompt_report.get("optimized_length"),
        "failed_reason": prompt_report.get("failed_reason") or "",
    })
    if prompt and not prompt_report.get("ok"):
        return _provider_error("kling", model_id, "Prompt optimization failed to reach limit")
    if prompt_report.get("optimized"):
        prompt = prompt_report.get("prompt") or prompt
        payload["prompt"] = prompt

    body = _build_video_payload(model_id, prompt, payload)
    raw_options = payload.get("video_options") or payload.get("options") or {}

    def _first_url(value):
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
                if isinstance(item, dict):
                    for key in ("url", "image_url", "src", "full_url", "result_url", "thumbnail_url", "thumb_url"):
                        candidate = item.get(key)
                        if isinstance(candidate, str) and candidate.strip():
                            return candidate.strip()
        if isinstance(value, str) and value.strip():
            return value.strip()
        return ""

    def _is_data_image(value):
        return isinstance(value, str) and value.strip().lower().startswith("data:image/")

    def _strip_data_url(value):
        if not isinstance(value, str):
            return ""
        text = value.strip()
        if ";base64," in text:
            return text.split(";base64,", 1)[1].strip()
        return text

    def _absolute_public_url(value):
        if not isinstance(value, str):
            return ""
        text = value.strip()
        if not text:
            return ""
        parsed = urlparse(text)
        if parsed.scheme in {"http", "https"}:
            return text
        if text.startswith("data:"):
            return text
        if text.startswith("/"):
            base = (
                os.getenv("WEBAPP_URL")
                or os.getenv("PUBLIC_WEBAPP_URL")
                or os.getenv("PUBLIC_BASE_URL")
                or "https://sylvex-ai-webapp-production.up.railway.app"
            ).rstrip("/")
            return f"{base}{text}" if base else text
        return text

    def _short_debug_value(value, limit=220):
        text = str(value or "")
        if text.startswith("data:image/"):
            return text[:80] + f"... [data image {len(text)} chars]"
        return text if len(text) <= limit else text[:limit] + f"... [{len(text)} chars]"

    def _guess_image_ext(content, mime_hint=""):
        hint = str(mime_hint or "").lower()
        if "jpeg" in hint or "jpg" in hint:
            return "jpg"
        if "webp" in hint:
            return "webp"
        if "gif" in hint:
            return "gif"
        if content.startswith(b"\xff\xd8\xff"):
            return "jpg"
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
            return "webp"
        if content.startswith(b"GIF87a") or content.startswith(b"GIF89a"):
            return "gif"
        return "png"

    def _materialize_data_image_to_public_url(value):
        if not _is_data_image(value):
            return _absolute_public_url(value)
        text = value.strip()
        if ";base64," not in text:
            return text
        header, raw = text.split(";base64,", 1)
        try:
            content = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError):
            return text
        if not content:
            return text
        mime_hint = header.split(":", 1)[1].split(";", 1)[0] if ":" in header else ""
        ext = _guess_image_ext(content, mime_hint)
        root = pathlib.Path(__file__).resolve().parents[1]
        image_dir = root / "webapp" / "generated" / "video-inputs"
        image_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid4().hex}.{ext}"
        path = image_dir / filename
        path.write_bytes(content)
        public_path = f"/webapp/generated/video-inputs/{filename}"
        print("KLING DEBUG MATERIALIZED_INPUT_IMAGE:", {
            "path": str(path),
            "url": public_path,
            "bytes": len(content),
            "exists": path.exists(),
        })
        return _absolute_public_url(public_path)

    def _normalize_kling_image_input(value):
        if not isinstance(value, str):
            return ""
        value = value.strip()
        if not value:
            return ""
        return value

    def _kling_image_content_value(value):
        if not isinstance(value, str):
            return ""
        text = value.strip()
        if not text:
            return ""
        if _is_data_image(text):
            return _strip_data_url(text)
        return _absolute_public_url(text)

    input_image = (
        body.get("start_image")
        or raw_options.get("start_image")
        or payload.get("start_image")
        or body.get("image_url")
        or raw_options.get("image_url")
        or payload.get("image_url")
        or _first_url(body.get("reference_images"))
        or _first_url(raw_options.get("reference_images"))
        or _first_url(raw_options.get("referenceImageUrls"))
        or _first_url(payload.get("reference_images"))
        or _first_url(payload.get("referenceImageUrls"))
        or _first_url(raw_options.get("uploadedImageUrls"))
        or _first_url(payload.get("uploadedImageUrls"))
    )
    input_image = _normalize_kling_image_input(input_image)
    input_image_content = _kling_image_content_value(input_image)
    input_image_public_url = _materialize_data_image_to_public_url(input_image)
    end_image = (
        body.get("end_image")
        or raw_options.get("end_image")
        or payload.get("end_image")
        or ""
    )
    end_image = _normalize_kling_image_input(end_image)
    end_image_content = _kling_image_content_value(end_image)
    end_image_public_url = _materialize_data_image_to_public_url(end_image)

    video_template = body.get("video_template") if isinstance(body.get("video_template"), dict) else {}
    input_video = (
        body.get("input_video")
        or body.get("video_url")
        or body.get("reference_video")
        or body.get("template_video_url")
        or body.get("preview_video")
        or raw_options.get("input_video")
        or raw_options.get("video_url")
        or raw_options.get("reference_video")
        or raw_options.get("template_video_url")
        or raw_options.get("template_video")
        or raw_options.get("preview_video")
        or video_template.get("reference_video")
        or video_template.get("video_url")
        or video_template.get("template_video_url")
        or video_template.get("preview_video")
        or payload.get("input_video")
        or payload.get("video_url")
    )
    input_video = _absolute_public_url(input_video)

    video_mode = str(
        body.get("mode")
        or body.get("generation_mode")
        or raw_options.get("generation_mode")
        or raw_options.get("mode")
        or raw_options.get("kling_mode")
        or payload.get("mode")
        or payload.get("kling_mode")
        or ""
    ).strip().lower()

    requires_image = (
        video_mode in {"image_to_video", "image to video", "motion_control", "motion control"}
        or bool(input_image_content)
    )
    is_official_omni_model = _kling_model_family(provider_model) in {"kling-3.0-omni", "kling-o1"}

    print("KLING DEBUG MODE:", video_mode)
    print("KLING DEBUG BODY START IMAGE:", _short_debug_value(body.get("start_image")))
    print("KLING DEBUG BODY IMAGE_URL:", _short_debug_value(body.get("image_url")))
    print("KLING DEBUG BODY REFERENCES:", _short_debug_value(body.get("reference_images")))
    print("KLING DEBUG RAW OPTIONS START IMAGE:", _short_debug_value(raw_options.get("start_image")))
    print("KLING DEBUG RAW OPTIONS IMAGE_URL:", _short_debug_value(raw_options.get("image_url")))
    print("KLING DEBUG RAW OPTIONS REFERENCES:", _short_debug_value(raw_options.get("reference_images") or raw_options.get("referenceImageUrls")))
    print("KLING DEBUG INPUT_IMAGE:", _short_debug_value(input_image_public_url or input_image_content))
    print("KLING DEBUG INPUT_IMAGE_CONTENT:", _short_debug_value(input_image_content))
    print("KLING DEBUG INPUT_VIDEO:", _short_debug_value(input_video))

    if requires_image and not input_image_content:
        return _provider_error("kling", model_id, "Для Kling Image to Video нужно загрузить изображение")

    model_family = _kling_model_family(provider_model)
    is_motion_reference = video_mode in {"motion_control", "motion control"} and bool(input_video)
    is_omni_video_reference = (
        is_official_omni_model
        and bool(input_video)
        and video_mode not in {"motion_control", "motion control"}
    )
    is_omni_unified_generation = model_family in {"kling-o1", "kling-3.0-omni"} and not is_motion_reference
    is_legacy_model = _kling_is_legacy_model(model_id)
    legacy_kind = "image" if (input_image_public_url or input_image_content) else "text"

    if is_legacy_model:
        legacy_model_name = KLING_LEGACY_MODEL_NAMES.get(model_id) or _kling_motion_provider_model(provider_model)
        kling_body = {
            "model_name": legacy_model_name,
            "prompt": prompt or "",
            "duration": str(_kling_duration(body.get("duration"), {5, 10})),
            "mode": _kling_legacy_mode(body.get("resolution")),
            "watermark_info": {"enabled": False},
            "sound": "on" if body.get("sound") else "off",
        }
        if payload.get("job_id"):
            kling_body["external_task_id"] = str(payload.get("job_id"))
        if input_image_public_url or input_image_content:
            kling_body["image"] = input_image_public_url or input_image_content
            if (end_image_public_url or end_image_content) and model_id in {"kling_2_1", "kling_1_6", "kling_1_5"}:
                kling_body["image_tail"] = end_image_public_url or end_image_content
        else:
            kling_body["aspect_ratio"] = _kling_aspect_ratio(body.get("ratio"))
    elif is_motion_reference:
        kling_body = {
            "contents": [],
            "settings": _kling_motion_settings(provider_model, body, raw_options),
            "options": _kling_options(payload),
        }
        if prompt:
            kling_body["contents"].append({"type": "prompt", "text": prompt})
        if input_image_content:
            kling_body["contents"].append({"type": "image", "url": input_image_content})
        kling_body["contents"].append({"type": "video", "url": input_video})
    elif is_omni_video_reference or is_omni_unified_generation:
        contents = []
        if prompt:
            contents.append({"type": "prompt", "text": prompt})
        if input_image_content:
            contents.append({"type": "first_frame", "url": input_image_content, "id": "image_1"})
        reference_type = "base_video" if video_mode in {"video_edit", "video edit", "edit"} else "feature_video"
        if input_video:
            contents.append({"type": reference_type, "url": input_video, "id": "video_1"})
        if end_image_content and reference_type != "base_video" and input_image_content:
            contents.append({"type": "last_frame", "url": end_image_content, "id": "image_2"})
        kling_body = {
            "contents": contents,
            "settings": _kling_omni_settings(provider_model, body, has_video=bool(input_video), base_video=reference_type == "base_video" and bool(input_video)),
            "options": _kling_options(payload),
        }
    else:
        if input_image_content:
            contents = []
            if prompt:
                contents.append({"type": "prompt", "text": prompt})
            contents.append({"type": "first_frame", "url": input_image_content})
            if end_image_content and _kling_supports_last_frame(provider_model):
                contents.append({"type": "last_frame", "url": end_image_content})
            kling_body = {
                "contents": contents,
                "settings": _kling_image_settings(provider_model, body, bool(end_image_content and _kling_supports_last_frame(provider_model))),
                "options": _kling_options(payload),
            }
        else:
            kling_body = {
                "prompt": prompt or "",
                "settings": _kling_text_settings(provider_model, body),
                "options": _kling_options(payload),
            }

    cost_body = dict(body)
    settings_for_cost = kling_body.get("settings") if isinstance(kling_body.get("settings"), dict) else {}
    if settings_for_cost:
        if settings_for_cost.get("resolution"):
            cost_body["resolution"] = settings_for_cost.get("resolution")
        if settings_for_cost.get("duration"):
            cost_body["duration"] = settings_for_cost.get("duration")
        if settings_for_cost.get("audio") in {"native", "original"}:
            cost_body["sound"] = True
            cost_body["native_audio"] = True
        elif settings_for_cost.get("audio") == "off":
            cost_body["sound"] = False
            cost_body["native_audio"] = False
    if is_legacy_model:
        cost_body["duration"] = kling_body.get("duration") or cost_body.get("duration")
        legacy_mode = kling_body.get("mode")
        if legacy_mode == "pro":
            cost_body["resolution"] = "1080p"
        elif legacy_mode == "4k":
            cost_body["resolution"] = "4k"
        else:
            cost_body["resolution"] = "720p"
        cost_body["sound"] = kling_body.get("sound") == "on"
        cost_body["native_audio"] = kling_body.get("sound") == "on"
    cost_info = _kling_cost_info(model_id, cost_body)

    def _kling_prompt_too_long(data):
        text = raw_error_text(data, "").lower()
        return bool(re.search(r"prompt.*size.*between|prompt too long|maximum length exceeded|context length exceeded|input too large", text))

    def _replace_kling_prompt(body_payload, next_prompt):
        body_payload["prompt"] = next_prompt
        for item in body_payload.get("contents") or []:
            if isinstance(item, dict) and item.get("type") in {"text", "prompt"}:
                item["text"] = next_prompt

    def _kling_zero_billing_failure(result_payload):
        response_payload = result_payload.get("provider_response") if isinstance(result_payload, dict) else {}
        data_items = response_payload.get("data") if isinstance(response_payload, dict) else []
        task_payload = data_items[0] if isinstance(data_items, list) and data_items and isinstance(data_items[0], dict) else {}
        billing_items = task_payload.get("billing") if isinstance(task_payload, dict) else []
        if not billing_items:
            return True
        for item in billing_items:
            if not isinstance(item, dict):
                continue
            try:
                if float(item.get("amount") or 0) > 0:
                    return False
            except Exception:
                return False
        return True

    def _kling_should_retry_file_content_error(result_payload):
        if not isinstance(result_payload, dict) or result_payload.get("ok"):
            return False
        raw_text = raw_error_text(result_payload.get("raw_error") or result_payload.get("provider_response") or result_payload, "").lower()
        if not re.search(r"get.*contents.*file|contents of the file", raw_text):
            return False
        return _kling_zero_billing_failure(result_payload)

    def _kling_prepare_retry_payload(body_payload, suffix):
        retry_payload = copy.deepcopy(body_payload)
        options_payload = retry_payload.setdefault("options", {})
        external_id = str(options_payload.get("external_task_id") or payload.get("job_id") or uuid4().hex)
        options_payload["external_task_id"] = f"{external_id}-{suffix}"[:255]
        return retry_payload

    try:
        endpoint_body = dict(body)
        if input_image_public_url or input_image_content:
            endpoint_body["start_image"] = input_image_public_url or input_image_content
        if is_legacy_model:
            endpoint = _kling_legacy_submit_endpoint(legacy_kind)
        else:
            if is_motion_reference:
                endpoint = _kling_motion_endpoint(provider_model)
            elif is_omni_video_reference or is_omni_unified_generation:
                endpoint = _kling_omni_endpoint(provider_model)
            else:
                endpoint = _kling_submit_endpoint(provider_model, endpoint_body)
        print("KLING DEBUG ENDPOINT:", endpoint)
        print("KLING DEBUG PAYLOAD:", _sanitize_debug_payload(kling_body))
        print("KLING DEBUG COST:", cost_info)
        response = _request_json(
            endpoint,
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            kling_body,
        )
        data = _safe_provider_json_response(response, "kling", endpoint)
        _log_provider_response("kling", "SUBMIT", endpoint, kling_body, response, data)
        status = getattr(response, "status_code", None) or 0
        if status >= 400 and _kling_prompt_too_long(data):
            retry_report = optimize_prompt_for_model(kling_body.get("prompt") or prompt, model=model_id, provider="kling", mode="video")
            if retry_report.get("ok") and retry_report.get("prompt") and retry_report.get("prompt") != kling_body.get("prompt"):
                _replace_kling_prompt(kling_body, retry_report.get("prompt"))
                print("KLING PROMPT RETRY:", {
                    "model": model_id,
                    "prompt_length": retry_report.get("original_length"),
                    "metric": retry_report.get("metric"),
                    "model_limit": retry_report.get("limit"),
                    "new_length": retry_report.get("optimized_length"),
                })
                response = _request_json(
                    endpoint,
                    {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    kling_body,
                )
                data = _safe_provider_json_response(response, "kling", endpoint)
                _log_provider_response("kling", "SUBMIT_RETRY", endpoint, kling_body, response, data)
                status = getattr(response, "status_code", None) or 0
        if status >= 400 or data.get("ok") is False or data.get("code") not in (None, 0):
            return _provider_parse_error("kling", model_id, data)
        task_id = _task_id_from_response(data.get("data") if isinstance(data.get("data"), dict) else data)
        if not task_id:
            return _provider_error("kling", model_id, "Kling task id not found")
        if is_legacy_model:
            result = _kling_legacy_poll_until_ready(task_id, legacy_kind, {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        else:
            result = _kling_poll_until_ready(task_id, {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        if _kling_should_retry_file_content_error(result):
            retry_body = _kling_prepare_retry_payload(kling_body, "retry1")
            print("KLING FILE CONTENT RETRY:", {
                "model": model_id,
                "task_id": task_id,
                "raw_error": result.get("raw_error"),
                "external_task_id": (retry_body.get("options") or {}).get("external_task_id"),
            })
            retry_response = _request_json(
                endpoint,
                {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                retry_body,
            )
            retry_data = _safe_provider_json_response(retry_response, "kling", endpoint)
            _log_provider_response("kling", "SUBMIT_FILE_RETRY", endpoint, retry_body, retry_response, retry_data)
            retry_status = getattr(retry_response, "status_code", None) or 0
            if retry_status >= 400 or retry_data.get("ok") is False or retry_data.get("code") not in (None, 0):
                result = _provider_parse_error("kling", model_id, retry_data)
            else:
                retry_task_id = _task_id_from_response(retry_data.get("data") if isinstance(retry_data.get("data"), dict) else retry_data)
                if retry_task_id:
                    if is_legacy_model:
                        result = _kling_legacy_poll_until_ready(retry_task_id, legacy_kind, {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
                    else:
                        result = _kling_poll_until_ready(retry_task_id, {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
                else:
                    result = _provider_error("kling", model_id, "Kling retry task id not found")
        result["model"] = model_id
        result["provider_model"] = provider_model
        result.update(cost_info)
        return result
    except Exception as exc:
        return _provider_error("kling", model_id, f"Provider request failed: {exc}")


def _call_runway(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("RUNWAY_API_KEY")
    if not api_key:
        return _provider_error("runway", model_id, "Provider API key is missing: RUNWAY_API_KEY")
    provider_model = _provider_model_for_video(model_id)
    if not provider_model:
        return _unknown_video_model_mapping_response(model_id, "runway")
    body = _build_video_payload(model_id, prompt, payload)
    try:
        endpoint = os.getenv("RUNWAY_API_ENDPOINT", "https://api.dev.runwayml.com/v1/image_to_video")
        runway_body = {
            "model": provider_model,
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
    provider_model = _provider_model_for_video(model_id)
    if not provider_model:
        return _unknown_video_model_mapping_response(model_id, "minimax")
    body = _build_video_payload(model_id, prompt, payload)
    minimax_body = {
        "model": provider_model,
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
    provider_model = _provider_model_for_video(model_id)
    if not provider_model:
        return _unknown_video_model_mapping_response(model_id, "pixverse")
    body = _build_video_payload(model_id, prompt, payload)
    pixverse_body = {
        "model": provider_model,
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
    provider_model = _provider_model_for_video(model_id)
    if not provider_model:
        return _unknown_video_model_mapping_response(model_id, "sora")
    body = _build_video_payload(model_id, prompt, payload)
    try:
        endpoint = f"{os.getenv('OPENAI_API_BASE', 'https://api.openai.com/v1').rstrip('/')}/videos"
        form = {
            "model": provider_model,
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
    provider_model = _provider_model_for_video(model_id)
    if not provider_model:
        return _unknown_video_model_mapping_response(model_id, "veo")
    body = _build_video_payload(model_id, prompt, payload)
    try:
        google_model = provider_model
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


def _call_gemini_video(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("GEMINI_API_KEY", "GOOGLE_API_KEY")
    if not api_key:
        return _provider_error("gemini", model_id, "Provider API key is missing: GEMINI_API_KEY")
    provider_model = _provider_model_for_video(model_id) or "gemini-omni-flash-preview"
    endpoint = (_video_model_mapping(model_id).get("endpoint") or os.getenv("GEMINI_INTERACTIONS_ENDPOINT") or "https://generativelanguage.googleapis.com/v1beta/interactions").rstrip("/")
    body = _build_video_payload(model_id, prompt, payload)
    mode = str(body.get("mode") or "text_to_video").strip().lower()
    input_items = []
    task = "text_to_video"

    if mode in {"image_to_video", "reference_to_video"} or body.get("start_image") or body.get("reference_images"):
        for image_url in ([body.get("start_image")] if body.get("start_image") else []) + list(body.get("reference_images") or []):
            part = _load_media_content_part(image_url, "image")
            if part:
                input_items.append(part)
        task = "reference_to_video" if len(input_items) > 1 else "image_to_video"

    if mode in {"video_edit", "edit"} or body.get("input_video") or body.get("video_url") or body.get("reference_video"):
        video_url = body.get("input_video") or body.get("video_url") or body.get("reference_video")
        part = _gemini_upload_file_from_url(video_url, api_key, "video") or _load_media_content_part(video_url, "video")
        if not part:
            return _provider_error("gemini", model_id, "Для Gemini Video Edit нужно загрузить видео")
        input_items = [part]
        task = "edit"

    if input_items:
        input_items.append({"type": "text", "text": prompt})
        interaction_input = input_items
    else:
        interaction_input = prompt

    response_format = {
        "type": "video",
        "delivery": "uri",
        "aspect_ratio": body.get("ratio") if body.get("ratio") in {"16:9", "9:16"} else "16:9",
    }
    request_payload = {
        "model": provider_model,
        "input": interaction_input,
        "background": False,
        "store": False,
        "response_format": response_format,
        "generation_config": {
            "video_config": {
                "task": task,
            }
        },
    }
    try:
        print("GEMINI VIDEO REQUEST:", {
            "endpoint": endpoint,
            "model": provider_model,
            "task": task,
            "aspect_ratio": response_format.get("aspect_ratio"),
            "has_media": bool(input_items),
        })
        response = _request_json(
            endpoint,
            {"x-goog-api-key": api_key, "Content-Type": "application/json"},
            request_payload,
        )
        data = _safe_provider_json_response(response, "gemini", endpoint)
        _log_provider_response("gemini", "SUBMIT", endpoint, request_payload, response, data)
        status = getattr(response, "status_code", None) or 0
        if status >= 400 or data.get("ok") is False:
            return _provider_parse_error("gemini", model_id, data)
        videos = _extract_gemini_videos(data, api_key)
        if videos:
            result = _provider_success("gemini", model_id, videos, status="completed", task_id=data.get("id"))
            result["provider_model"] = provider_model
            result["metadata"] = {
                "interaction_id": data.get("id") or "",
                "gemini_status": data.get("status") or "",
                "task": task,
                "response_format": response_format,
            }
            return result
        if data.get("id") and str(data.get("status") or "").lower() not in {"completed", "failed"}:
            return _provider_success("gemini", model_id, [], status="processing", task_id=data.get("id"), poll_url=f"{endpoint}/{data.get('id')}")
        return _provider_error("gemini", model_id, "Provider returned no video URL")
    except Exception as exc:
        return _provider_error("gemini", model_id, f"Provider request failed: {exc}")


def _call_wan(model_id: str, prompt: str, payload: dict):
    api_key = _get_env("ALIBABA_API_KEY", "QWEN_API_KEY")
    if not api_key:
        return _provider_error("wan", model_id, "Provider API key is missing: ALIBABA_API_KEY")
    provider_model = _provider_model_for_video(model_id)
    if not provider_model:
        return _unknown_video_model_mapping_response(model_id, "wan")
    body = _build_video_payload(model_id, prompt, payload)
    wan_body = {
        "model": provider_model,
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
    provider_model = _provider_model_for_video(model_id)
    if not provider_model:
        return _unknown_video_model_mapping_response(model_id, "grok")
    body = _build_video_payload(model_id, prompt, payload)
    body.update({"prompt": prompt, "model": provider_model})
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
    prompt_report = optimize_prompt_for_model(prompt, model=model_id, provider=provider, mode="video")
    print("VIDEO PROMPT OPTIMIZER:", {
        "model": model_id,
        "provider": provider,
        "prompt_length": prompt_report.get("original_length"),
        "model_limit": prompt_report.get("limit"),
        "optimized": prompt_report.get("optimized"),
        "new_length": prompt_report.get("optimized_length"),
        "failed_reason": prompt_report.get("failed_reason") or "",
    })
    if prompt and not prompt_report.get("ok"):
        limit = prompt_report.get("limit")
        provider_name = "Kling" if "kling" in f"{provider} {model_id}".lower() else "выбранной модели"
        return {
            "ok": False,
            "type": "video",
            "provider": provider,
            "model": model_id,
            "error": (
                f"Ваше описание слишком большое для {provider_name}.\n\n"
                f"Максимальный размер описания — {limit} символов.\n\n"
                "Попробуйте сделать описание немного короче или выберите другую модель."
            ),
            "raw_error": "Prompt optimization failed to reach limit",
            "prompt_limit": limit,
            "prompt_length": prompt_report.get("original_length"),
            "optimized_length": prompt_report.get("optimized_length"),
        }
    if prompt_report.get("optimized"):
        prompt = prompt_report.get("prompt") or prompt
        payload["prompt"] = prompt

    raw_options = payload.get("video_options") or payload.get("options") or {}
    if not prompt:
        return {"ok": False, "type": "video", "model": model_id, "provider": provider, "error": "Prompt is required"}

    if provider == "seedance" or re.search(r"seedance", model_id, re.I):
        result = _call_seedance(model_id, prompt, payload)
    elif provider == "heygen" or re.search(r"heygen", model_id, re.I):
        if model_id == "heygen_v3_video_agent":
            result = _call_heygen(model_id, prompt, payload)
        else:
            result = _call_heygen_direct_video(model_id, prompt, payload)
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
    elif provider == "gemini" or re.search(r"gemini", model_id, re.I):
        result = _call_gemini_video(model_id, prompt, payload)
    elif provider == "veo" or re.search(r"veo", model_id, re.I):
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
