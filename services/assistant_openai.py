"""SYLVEX Assistant AI Mode - OpenAI Responses API streaming + Realtime proxy.

Only reached once main.py's /api/web/assistant/message handler has already
confirmed the caller has an ACTIVE subscription (see get_user_state() there)
- nothing in this module performs that check itself, by design: it is a
thin transport layer, not a policy layer. OPENAI_API_KEY is read by the
caller (main.py, which already owns it) and passed in here as a plain
argument; it is never returned, logged, or otherwise echoed back to a
caller of these functions.

There is no first-party OpenAI SDK in this codebase (see openai_responses_
text_request in main.py) - this mirrors that existing raw-requests pattern,
just adding `stream: true` and parsing the resulting SSE body, which no
other part of the codebase does yet.
"""
import json

import requests


def _build_responses_input(messages):
    """Same role/part-type mapping as main.py's openai_responses_text_request
    (assistant history must use output_text, everything else input_text) -
    duplicated rather than imported to keep this module deployable without a
    circular import against main.py."""
    response_input = []
    for message in messages or []:
        role = str(message.get("role") or "user")
        raw_content = message.get("content")
        text_part_type = "output_text" if role == "assistant" else "input_text"
        if isinstance(raw_content, list):
            content = []
            for part in raw_content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    content.append({"type": text_part_type, "text": str(part.get("text") or "")})
                elif part.get("type") == "image_url" and role != "assistant":
                    image_url = (part.get("image_url") or {}).get("url")
                    if image_url:
                        content.append({"type": "input_image", "image_url": image_url})
        else:
            content = [{"type": text_part_type, "text": str(raw_content or "")}]
        response_input.append({"role": role, "content": content})
    return response_input


def stream_assistant_reply(api_key, api_base, model, messages, timeout=90):
    """Yields text deltas from OpenAI's Responses API streaming endpoint as
    they arrive. Raises RuntimeError with a caller-safe message on failure -
    never propagates a raw provider exception/stack trace upward."""
    if not api_key:
        raise RuntimeError("openai_not_configured")

    body = json.dumps({"model": model, "input": _build_responses_input(messages), "stream": True})
    try:
        response = requests.post(
            api_base.rstrip("/") + "/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            data=body,
            stream=True,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RuntimeError("ai_connection_failed") from exc

    if response.status_code >= 400:
        try:
            error_body = response.json()
        except Exception:
            error_body = {"raw": response.text[:500]}
        print("ASSISTANT OPENAI STREAM ERROR:", response.status_code, error_body)
        raise RuntimeError("ai_temporarily_unavailable")

    saw_any_delta = False
    try:
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line or not raw_line.startswith("data:"):
                continue
            payload = raw_line[len("data:"):].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                event = json.loads(payload)
            except ValueError:
                continue
            event_type = event.get("type") or ""
            if event_type == "response.output_text.delta":
                delta = event.get("delta") or ""
                if delta:
                    saw_any_delta = True
                    yield delta
            elif event_type in ("response.failed", "error"):
                message = (
                    (event.get("response") or {}).get("error", {}).get("message")
                    or event.get("message") or "ai_generation_failed"
                )
                print("ASSISTANT OPENAI STREAM EVENT ERROR:", message)
                if not saw_any_delta:
                    raise RuntimeError("ai_temporarily_unavailable")
                return
            elif event_type == "response.completed":
                return
    finally:
        response.close()


def mint_realtime_session(api_key, sdp, instructions, safety_user_id, model, voice="marin", timeout=30):
    """Proxies a WebRTC SDP offer to OpenAI's Realtime API and returns the
    raw (content_bytes, status_code, content_type) SDP-answer response -
    OPENAI_API_KEY is attached here, server-side, and never reaches the
    caller. Mirrors main.py's existing /api/public/home-idea/realtime proxy
    exactly, just parameterized (model/instructions/voice) for Assistant's
    own gated endpoint."""
    if not api_key:
        raise RuntimeError("openai_not_configured")
    import hashlib
    safety_id = hashlib.sha256(("sylvex-assistant:" + str(safety_user_id)).encode()).hexdigest()
    session = {
        "type": "realtime",
        "model": model,
        "instructions": instructions,
        "audio": {"input": {"transcription": {"model": "gpt-4o-mini-transcribe"}}, "output": {"voice": voice}},
    }
    response = requests.post(
        "https://api.openai.com/v1/realtime/calls",
        headers={"Authorization": f"Bearer {api_key}", "OpenAI-Safety-Identifier": safety_id},
        files={"sdp": (None, sdp), "session": (None, json.dumps(session))},
        timeout=timeout,
    )
    return response.content, response.status_code, response.headers.get("content-type", "application/sdp")
