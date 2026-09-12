"""Multi-image generations must reach Telegram as one media group (album),
not as N separate sendPhoto messages - matching what the Mini App shows
for the same generation. quantity=1 still uses a normal single photo.
A media-group failure must fall back to individual photos, but never
both (that would duplicate delivery)."""
import main


def _fake_response(status_code=200, json_data=None, text=""):
    class _Resp:
        def __init__(self):
            self.status_code = status_code
            self._json = json_data or {"ok": True}
            self.text = text

        def json(self):
            return self._json

    return _Resp()


def test_single_image_uses_send_photo_not_media_group(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return _fake_response()

    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "BOT_TOKEN", "test-token")

    result = main.send_generated_images_to_telegram(123, ["https://example.com/a.png"], "caption")

    assert result is True
    assert len(calls) == 1
    assert calls[0].endswith("/sendPhoto")


def test_multiple_images_use_one_media_group_call(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return _fake_response()

    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "BOT_TOKEN", "test-token")

    images = [
        "https://example.com/a.png",
        "https://example.com/b.png",
        "https://example.com/c.png",
        "https://example.com/d.png",
    ]
    result = main.send_generated_images_to_telegram(123, images, "caption")

    assert result is True
    assert len(calls) == 1, "all 4 images must go out in a single Telegram API call"
    assert calls[0].endswith("/sendMediaGroup")


def test_media_group_only_carries_caption_on_the_first_item(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["json"] = kwargs.get("json")
        return _fake_response()

    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "BOT_TOKEN", "test-token")

    main.send_generated_images_to_telegram(
        123, ["https://example.com/a.png", "https://example.com/b.png"], "hello",
    )

    media = captured["json"]["media"]
    assert len(media) == 2
    assert media[0]["caption"] == "hello"
    assert "caption" not in media[1]


def test_media_group_failure_falls_back_to_individual_photos_exactly_once(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if url.endswith("/sendMediaGroup"):
            return _fake_response(status_code=400, text="Bad Request")
        return _fake_response()

    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "BOT_TOKEN", "test-token")

    images = ["https://example.com/a.png", "https://example.com/b.png", "https://example.com/c.png"]
    result = main.send_generated_images_to_telegram(123, images, "caption")

    assert result is True
    send_photo_calls = [c for c in calls if c.endswith("/sendPhoto")]
    media_group_calls = [c for c in calls if c.endswith("/sendMediaGroup")]
    assert len(media_group_calls) == 1, "must attempt the media group exactly once before falling back"
    assert len(send_photo_calls) == 3, "fallback must send every image individually, no duplicates, no drops"


def test_media_group_success_never_also_sends_individual_photos(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return _fake_response()

    monkeypatch.setattr(main.requests, "post", fake_post)
    monkeypatch.setattr(main, "BOT_TOKEN", "test-token")

    main.send_generated_images_to_telegram(
        123, ["https://example.com/a.png", "https://example.com/b.png"], "caption",
    )

    assert not any(c.endswith("/sendPhoto") for c in calls), (
        "a successful media group must never also trigger individual sendPhoto calls"
    )


def test_empty_or_missing_images_send_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(main.requests, "post", lambda url, **kwargs: calls.append(url))
    monkeypatch.setattr(main, "BOT_TOKEN", "test-token")

    assert main.send_generated_images_to_telegram(123, [], "caption") is False
    assert main.send_generated_images_to_telegram(123, [None, "", None], "caption") is False
    assert calls == []
