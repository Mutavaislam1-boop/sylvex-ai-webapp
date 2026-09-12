# SYLVEX Pro Studio — Full Model Integration Audit

Date: 2026-09-12
Scope: every AI model selectable in Pro Studio across Text, Image, Video, Music, and Voice/TTS.
Method: static code trace (frontend catalog → backend mapping → provider request/response code), no live provider calls — **this sandbox has no provider API keys configured** (only unrelated infra/tooling secrets), so every row's "Access Status" is genuinely unverifiable here. A companion smoke-test script is recommended separately (see end of document) to run wherever real credentials exist (Railway shell, local `.env`).

**Important correction before reading the Image section**: the initial audit pass was run against `IMAGE_MODEL_CATALOG` (webapp/js/cabinet.js:4553), which turned out to be **dead code** — it feeds a variable (`imageCapabilities`) that is never read anywhere else. The actual live model picker uses a separate array, `IMAGE_MODEL_LIST` (webapp/js/cabinet.js:672), whose ids already match the backend's `IMAGE_PROVIDER_MODEL_MAP` exactly. The Image section below has been corrected accordingly — see the note in that section for what changed.

---

## Executive summary

| Mode | Models audited | Confirmed real bugs | Hypothesis-only (needs live check) | Notes |
|---|---|---|---|---|
| Text | 18 | 2 | 1 | 4 models return HTTP 422 regardless of credentials |
| Music | 10 | 1 (affects 8 models) | 0 | Same pricing-gate bug pattern as Text, independently discovered |
| Voice | 12 | 2 | 1 | Includes a 100%-reproducible crash (Runway) |
| Image | 26 (real catalog) | 0 confirmed | 3 | Original catalog audited was dead code — corrected below |
| Video | 45 (not 36 — see note) | 6 distinct bugs affecting ~10 models | 2 | Largest and most complex mode |

**The single most severe bug found**: an infinite self-recursive function in Runway's voice/audio integration that guarantees a crash on every call — see Voice §2.

**The single highest-leverage bug found**: two separate, identical-pattern pricing-table gaps (Text §1, Music §1) that silently return HTTP 422 for 12 models total, before any provider code runs — completely independent of credentials, and the exact same bug shape discovered independently in two different modes.

---

## 1. TEXT (18 models)

Architecture: fully synchronous. `public_prostudio_generate` → `await asyncio.to_thread(text_generation, payload)`, response returned in the same HTTP call. No job queue, no polling — confirmed correct and confirmed to be what the frontend actually calls (`mode: 'text'` sent by `callGenerate`).

Internal routing: `TEXT_MODEL_VARIANTS` (main.py:10858-10877) is a 1:1 match with the frontend's `TEXT_MODEL_LIST` — no missing keys either direction. The frontend's `providerModel` field is decorative only; the backend's own `provider_model` value is what's actually sent.

### Confirmed bugs

**T1 — 4 models return HTTP 422 regardless of API keys.** `estimate_generation_cost()`'s per-million-token pricing table for text mode (main.py:13000-13007) has no entries for `grok_3`, `qwen_plus`, `qwen_turbo`, `qwen_max`. `public_prostudio_generate` (main.py:14556-14561) rejects any model with `pricing_available=False` before `text_generation()` is ever called. These 4 models are dead on arrival today.
*Fix*: add the 4 missing `(input, output)` price tuples to that dict.

**T2 — `gemini_3_1_flash`'s default provider model ID is inconsistent.** Its sibling `gemini_3_1_pro` defaults to `gemini-3.1-pro-preview` (main.py:10867, keeps ".1"), but `gemini_3_1_flash` defaults to `gemini-3-flash-preview` (main.py:10868) — dropping the ".1" that its own key, label, and the frontend's `providerModel:'gemini-3.1-flash'` all use.
*Fix*: verify against Google's current catalog and correct the `GEMINI_TEXT_FLASH_MODEL` default.

### Hypothesis (needs live check)
Model ID recency for `gpt-5.6`/`gpt-5.5`, `gemini-3.1-pro-preview`/`gemini-3-flash-preview`, and the dated BytePlus snapshot `seed-2-0-lite-260228` — plausible but unverifiable without a live call.

### Classification
VERIFIED WORKING (structurally, credential-blocked in this sandbox): gpt-5.6, gpt-5.5, gpt-5, gpt-5-mini, gpt-4.1, gpt-4.1-mini, gpt-4o, gpt-4o-mini, gemini_3_1_pro, gemini_2_5_pro, gemini_2_5_flash, grok_4_1, grok_4_fast, byteplus_seed_2_lite (14 models)
CONFIGURATION ERROR: gemini_3_1_flash (T2), grok_3, qwen_plus, qwen_turbo, qwen_max (T1) (5 models)

---

## 2. MUSIC (10 models)

### Confirmed bugs

**M1 — 8 of 10 models return HTTP 422 regardless of credentials.** Identical bug shape to T1: `estimate_generation_cost()`'s music pricing table (main.py:12953-12961) only has entries for `google_lyria_3_pro` and `google_lyria_3_clip`. Every Suno model (6), `minimax_music_2_5`, and `google_lyria_realtime` fall through to `pricing_available=False` → HTTP 422 before `audio_generation()`/`services/audio_router.py` is ever invoked.
*Fix*: add the 8 missing price entries (or a metered/provider-priced path) to that dict.

### Positive finding (no fix needed)
`google_lyria_realtime`'s WebSocket/streaming implementation (services/audio_router.py:989-1054) is **correctly engineered** — genuine `google-genai` live-music session, bounded via `asyncio.wait_for`, accumulates a finite byte target, always reaches a terminal state. It is currently unreachable only because of M1, not because of its own logic.

Also confirmed correct: `google_lyria_3_clip`'s fixed 30-second duration is enforced both frontend and backend; MiniMax's music API and MiniMax/Hailuo's video API are genuinely separate integrations (different endpoint, different API key) despite sharing a provider name.

### Classification
VERIFIED WORKING: google_lyria_3_clip, google_lyria_3_pro (2 models)
CONFIGURATION ERROR: suno_chirp_3_5, suno_chirp_4_0, suno_chirp_4_5, suno_chirp_4_5_plus, suno_chirp_5, suno_chirp_5_5, minimax_music_2_5, google_lyria_realtime (8 models, all via M1)

---

## 3. VOICE / TTS (12 models)

Chain confirmed: `voiceState.modelId` → `payload.model` → `audio_generation()` (services/audio_router.py) branches on `_is_elevenlabs_voice_model` / `_is_runway_voice_model` / else Gemini.

### Confirmed bugs

**V1 — Runway voice/audio generation crashes 100% of the time.** `_runway_audio_tool()` (services/audio_router.py:444-448) calls itself unconditionally with no base case:
```python
def _runway_audio_tool(payload):
    tool = _runway_audio_tool(payload)   # line 446 — self-recursive, no exit
    ...
```
This is the very first call made by `runway_voice_generation` (audio_router.py:2397), before any network request — every call raises `RecursionError` before reaching Telegram/Mini App with anything but a generic "failed" job. This same helper backs every Runway audio tool reachable from the upload-purpose menu (sound_effect, speech_to_speech, voice_dubbing, voice_isolation) — one bug takes down all Runway audio functionality, not just the one catalog model.
*Fix*: delete the self-recursive line; line 447 is clearly the intended real body. (This is a one-line, extremely low-risk, extremely high-confidence fix — recommend prioritizing it above everything else in this audit.)

**V2 — The two ElevenLabs STS (speech-to-speech) models are wired to the wrong request shape by default.** The model picker (`VOICE_MODEL_LIST`) and the "upload purpose" picker (`VOICE_UPLOAD_PURPOSES`) are independent, uncoupled UI controls. Selecting `elevenlabs_english_sts_v2` or `elevenlabs_multilingual_sts_v2` alone leaves `elevenlabs_tool` at its default `"text_to_speech"` (audio_router.py:427-428), so the backend sends a plain JSON TTS request carrying an STS-only `model_id` — no audio is ever collected. The correct multipart STS path (audio_router.py:2106-2126) only fires if the user separately finds and selects the unrelated "Копировать голос" upload-purpose control.
*Fix*: auto-force `elevenlabs_tool = "speech_to_speech"` and require an audio upload whenever an `*_sts_v2` model is selected; add a server-side guard rejecting an STS `provider_model` paired with `tool != "speech_to_speech"`.

### Hypothesis (needs live check)
All 3 Gemini TTS models call `POST https://generativelanguage.googleapis.com/v1beta/interactions` with a body shape (`input`/`generation_config.speech_config`) that doesn't match Google's publicly documented `generateContent` + `responseModalities`/`speechConfig` contract. **This same `/v1beta/interactions` pattern was independently flagged in Image mode (nano-banana models) and Video mode (`gemini_omni_flash`)** — three different modes, same suspicious non-standard endpoint. This consistency makes it worth a single live check that would resolve all three flags at once: either it's a real internal gateway that implements this schema intentionally, or it's a systemic integration error across every Gemini-routed generative endpoint in the app.

### Classification
VERIFIED WORKING: elevenlabs_eleven_v3, elevenlabs_multilingual_v2, elevenlabs_flash_v2_5, elevenlabs_flash_v2, elevenlabs_turbo_v2_5, elevenlabs_turbo_v2 (6 models)
MAPPING ERROR: elevenlabs_english_sts_v2, elevenlabs_multilingual_sts_v2 (V2, 2 models)
PROVIDER/API ERROR (hypothesis): gemini_3_1_flash_tts_preview, gemini_2_5_flash_preview_tts, gemini_2_5_pro_preview_tts (3 models)
NOT IMPLEMENTED (functionally — code exists but always crashes): runway_eleven_multilingual_v2 (V1, 1 model)

---

## 4. IMAGE (26 models, real catalog — corrected)

**Correction**: the first audit pass targeted `IMAGE_MODEL_CATALOG` (cabinet.js:4553-4581), confirmed dead code (feeds `imageCapabilities`, which nothing reads). The real, live model picker uses `IMAGE_MODEL_LIST` (cabinet.js:672 onward). Its ids (`seedream_5_0_lite`, `ideogram_3_0`, `ideogram_4_0`, `recraft_v4_1`, `gpt_image_1`, `gpt_image_2`, `flux_2`, `qwen_image`, `nano_banana*`, `imagen_4_*`, `grok`/`grok_pro`, etc.) were checked directly against `IMAGE_PROVIDER_MODEL_MAP` (main.py:557-595, as dumped by the original audit) and **every one resolves correctly** — no missing mappings, no Ideogram version-suffix bug (that only existed for the dead catalog's differently-spelled ids). Neither `microsoft-mai-2-5` nor `krea-2` exist in the real catalog at all, so their "NOT IMPLEMENTED" status is moot for production — they're simply not selectable.

Backend-side findings from the original pass remain valid (they're about provider code, independent of which catalog invoked it):

### Confirmed (minor)
**I1 — Qwen Image (base, non-2.0 variant) has a redundant double retry loop** (main.py: outer loop in `image_generation()` + an inner loop inside `call_qwen_image()`). Functionally still returns the correct number of images since the outer loop exits after the inner one already filled the quota — an inefficiency, not a correctness bug.

### Hypothesis (needs live check)
- Nano Banana / Nano Banana Pro / 2 / 2 Lite call `/v1beta/interactions` — same cross-mode pattern flagged in Voice §3 and Video below.
- `gpt-image-2`'s model name is unconfirmable against OpenAI's public catalog from training knowledge alone.
- Exact xAI image-model slugs (`grok-imagine-image`, `grok-imagine-image-quality`) are unconfirmable without a live call.

### Classification
VERIFIED WORKING (structurally): all 26 real-catalog models, including all 3 Seedream tiers, both Ideogram versions, all 3 Recraft versions, both GPT Image versions, Flux 2/Turbo/Kontext, all 3 Qwen Image variants, all 4 Nano Banana variants, all 3 Imagen 4 tiers, Grok/Grok Pro.
No confirmed MAPPING ERROR / NOT IMPLEMENTED models on the real catalog.

---

## 5. VIDEO (45 models — not 36; see note)

Note: the original task briefing estimated 36 models; a full read of `VIDEO_MODELS` (cabinet.js:2069-2125) found **45** selectable entries. This is the largest, most async-heavy, highest-bug-count mode.

### Confirmed bugs

**VD1 — 5 models get stuck "processing" forever once genuinely async.** `poll_video_generation` (services/video_router.py:2790-2923) has status-parsing branches only for `bytedance`, `kling`, `heygen`, `luma`, `runway`, `pixverse`, `wan`, `gemini`. There is **no branch for `minimax`, `sora`, or `veo`** — any job from these providers that doesn't finish on the very first synchronous check falls into the generic catch-all, which unconditionally returns `status="processing"`. The outer poll loop then polls every 5 seconds indefinitely and can never observe completion or failure. Affects: `minimax_hailuo_2_3`, `sora_2`, `sora_2_pro`, `veo_3_1`, `veo_3_1_fast`.
*Fix*: add a status-parsing branch per provider, polling that provider's real task/operation-status endpoint and mapping its actual terminal-state vocabulary (Veo's `predictLongRunning` returns an `Operation` object; MiniMax and Sora have their own query-status endpoints).

**VD2 — Grok Video / Grok Video Edit have the same missing-poll-branch problem**, plus no default provider-model env var (`GROK_VIDEO_MODEL`/`GROK_VIDEO_EDIT_MODEL` have no fallback, unlike every other provider), plus the request body forwards SYLVEX's raw internal payload dict rather than an explicit xAI-schema body (every other provider — Kling, Runway, Wan, Luma — builds a dedicated schema).
*Fix*: set default env values; add a `grok` poll branch; replace the raw-dict forward with an explicit xAI request schema.

**VD3 — Wan 2.7 Edit is broken end-to-end.** `_call_wan`'s `is_27 = provider_model.startswith("wan2.7")` check (video_router.py:4656) is `False` for this model's actual default provider model (`"wan2.1-vace-plus"`). Since it also has `has_media=True` (an input video was uploaded), it falls into the *image*-to-video branch, which overwrites the provider model and requires a `start_image` that this edit mode's UI never collects (`start_image:false`). Every real attempt errors "Wan image-to-video requires a first-frame image" — the uploaded video is read and then discarded.
*Fix*: add a dedicated video-edit (VACE) branch in `_call_wan` independent of the `is_27` string check.

**VD4 — Seedance 1.5 Pro has no default provider-model mapping.** Unlike its siblings Seedance 2.0/2.0 Fast (hardcoded defaults), Seedance 1.5 Pro only resolves a provider model if the operator has separately set `BYTEPLUS_SEEDANCE_1_5_PRO_MODEL`. Without it: "Unknown BytePlus video model mapping" on every attempt.
*Fix*: add a hardcoded default matching the pattern used for the other two Seedance models.

**VD5 — Sora image-to-video silently drops the reference image.** `_call_sora`'s multipart form (video_router.py:4474-4497) only sends `model/prompt/size/seconds`; `start_image` is never read or attached as OpenAI's `input_reference` file field. Selecting Sora's image-to-video mode with an uploaded image produces a text-only generation with no error shown to the user.
*Fix*: attach `input_reference` to the multipart form when `start_image` is present.

**VD6 — Luma Dream Machine silently shares Luma Ray v3.2's model ID by default** (soft config issue — `LUMA_DREAM_MACHINE_MODEL` is unset, falling back to the same `ray-3.2` id). Two UI options currently call the identical underlying model.

### Positive finding (verification confirmed)
All 16 selectable Kling model ids route through one of the 4 Kling poll functions, and **all 4 now correctly check for `"succeed"`** as a terminal state (the fix from an earlier session holds and covers every Kling model reachable from the UI).

### Backend-complete but unreachable from the UI (not a bug, a product-completeness gap)
8 `runway_seedance2*`/`runway_veo3*` ids and `kling_lip_sync` are fully implemented on the backend (correct endpoint, mapping, dispatch) but never selectable from `VIDEO_MODELS` — dead from the user's side, alive on the server side.

### Hypothesis (needs live check)
- `gemini_omni_flash` calls `/v1beta/interactions` — same cross-mode pattern as Voice §3 / Image hypothesis section.
- Luma's endpoint (`agents.lumalabs.ai`, an "Agents" product surface) vs. the public Dream Machine API (`api.lumalabs.ai`) — plausible but unconfirmed.

### Classification
VERIFIED WORKING: all 6 HeyGen, both Luma (Dream Machine flagged separately above), PixVerse v6, both Wan non-edit (2.6/2.7), all 6 Runway (both edit models confirmed correctly handling video references), all 16 Kling, Seedance 2.0/2.0 Fast (33 models)
MAPPING ERROR: wan_2_7_edit (VD3), seedance_1_5_pro (VD4)
PROVIDER/API ERROR: minimax_hailuo_2_3, sora_2, sora_2_pro, veo_3_1, veo_3_1_fast (VD1), grok_video, grok_video_edit (VD2), gemini_omni_flash (hypothesis)
CONFIGURATION ERROR: luma_dream_machine (VD6)
DEPRECATED/UNSUPPORTED (unreachable, backend-complete): 8 orphaned runway_* ids, kling_lip_sync

---

## Ranked list of confirmed, non-hypothesis, credential-independent bugs

1. **Runway voice self-recursion crash** (Voice V1) — 100% failure rate, one-line fix, near-zero risk. Highest priority.
2. **Text pricing gate** (Text T1) — 4 models dead on arrival.
3. **Music pricing gate** (Music M1) — 8 models dead on arrival, same bug shape as #2.
4. **Video missing poll branches** (Video VD1) — 5 models get stuck processing forever.
5. **Wan 2.7 Edit total failure** (Video VD3).
6. **ElevenLabs STS model/tool decoupling** (Voice V2).
7. **Sora image-to-video drops the input image** (Video VD5).
8. **Seedance 1.5 Pro missing default mapping** (Video VD4).
9. **Grok Video missing poll branch + no default model + raw payload forwarding** (Video VD2).
10. Minor: Gemini 3.1 Flash naming inconsistency (Text T2), Luma Dream Machine model overlap (Video VD6), Qwen Image redundant loop (Image I1).

## Cross-mode pattern worth a single check
Three independent audits flagged `https://generativelanguage.googleapis.com/v1beta/interactions` as a non-standard Gemini endpoint: Voice's 3 Gemini TTS models, Image's 4 Nano Banana models, Video's `gemini_omni_flash`. One live test against this endpoint (with real Gemini credentials) would confirm or rule out a problem across 8 models at once.

## Recommended smoke-test approach (once credentials are available)
A minimal, cheap-as-possible live check per provider (not per model) would cover most of the mapping surface: one text completion per LLM provider (OpenAI/Gemini/Grok/Qwen/BytePlus), one lowest-cost image generation per image provider, one minimal-duration voice/music clip per audio provider, and — separately, since video is the most expensive — a status check against each async provider's task-query endpoint using a deliberately-invalid task ID, which is enough to confirm the endpoint/auth is reachable without generating actual video. I can prepare this as a standalone script you run wherever `.env`/Railway credentials exist, if useful.
