"""Stage E of the latency/reliability audit: compare Ideogram's and a
working provider's (Seedream/BytePlus) R2 persistence path side by side.
Tracing persist_generation_media -> _persist_remote_media_url ->
storage_put_bytes -> the single lru_cached r2_client() shows they are
byte-for-byte identical: same client, same bucket, same endpoint, same
function, no provider-specific branching anywhere in this path, and the
R2 object key is always a fresh uuid4().hex - never derived from the
provider's own filename - so a provider-specific persistence bug is not
present at the code level.

Since a real per-provider difference can't be found in the code, this
adds the requested safe instrumentation (provider + asset_type label on
every R2 upload attempt, no secrets) so a future recurrence can be told
apart from a global credentials problem: a provider-specific bug would
show only that provider's asset_type failing while others succeed in the
same window: a global credentials problem shows every provider/asset_type
failing identically."""
import main


def test_r2_upload_start_and_done_carry_provider_and_asset_type_no_secrets(monkeypatch):
    events = []
    monkeypatch.setattr(main, "prostudio_debug", lambda event, **fields: events.append((event, fields)))
    monkeypatch.setattr(main, "r2_enabled", lambda: False)
    monkeypatch.setattr(main, "storage_key_from_url", lambda url: "")

    class _FakeResponse:
        headers = {"content-type": "image/png"}
        content = b"fake-bytes"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(main, "safe_get", lambda url, timeout=240: _FakeResponse())
    monkeypatch.setattr(main, "storage_put_bytes", lambda data, key, content_type: f"https://r2.example/{key}")

    result = main._persist_remote_media_url(
        "https://ideogram.ai/api/images/ephemeral/abc.png?exp=1&sig=deadbeef",
        "images",
        provider="ideogram",
    )

    assert result == "https://r2.example/" + [f for e, f in events if e == "R2_UPLOAD_START"][0]["object_key"]
    start_events = [f for e, f in events if e == "R2_UPLOAD_START"]
    done_events = [f for e, f in events if e == "R2_UPLOAD_DONE"]
    assert len(start_events) == 1 and len(done_events) == 1
    for fields in start_events + done_events:
        assert fields["provider"] == "ideogram"
        assert fields["asset_type"] == "images"
        assert fields["object_key"]
        serialized = repr(fields)
        assert "sig=deadbeef" not in serialized
        assert "R2_SECRET" not in serialized.upper()


def test_r2_upload_failed_labels_the_failing_provider_and_asset_type_no_secrets(monkeypatch):
    error_events = []
    monkeypatch.setattr(main, "prostudio_error", lambda event, exc, **fields: error_events.append((event, fields)))
    monkeypatch.setattr(main, "r2_enabled", lambda: False)
    monkeypatch.setattr(main, "storage_key_from_url", lambda url: "")

    class _FakeResponse:
        headers = {"content-type": "image/png"}
        content = b"fake-bytes"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(main, "safe_get", lambda url, timeout=240: _FakeResponse())

    def failing_put(data, key, content_type):
        raise RuntimeError("An error occurred (SignatureDoesNotMatch) when calling the PutObject operation")

    monkeypatch.setattr(main, "storage_put_bytes", failing_put)

    result = main._persist_remote_media_url(
        "https://ideogram.ai/api/images/ephemeral/abc.png?exp=1&sig=deadbeef",
        "images",
        provider="ideogram",
    )

    # Falls back to the original (still-usable) provider URL - a storage
    # failure here must not raise, matching persist_generation_media's
    # already-established fail-open contract.
    assert result.startswith("https://ideogram.ai/")

    upload_failed = [f for e, f in error_events if e == "R2_UPLOAD_FAILED"]
    assert len(upload_failed) == 1
    fields = upload_failed[0]
    assert fields["provider"] == "ideogram"
    assert fields["asset_type"] == "images"
    assert fields["object_key"]
    assert "sig=deadbeef" not in repr(fields)


def test_persist_generation_media_threads_the_provider_label_through(monkeypatch):
    seen = []

    def fake_persist_url(url, category, provider=""):
        seen.append((url, category, provider))
        return url

    monkeypatch.setattr(main, "_persist_remote_media_url", fake_persist_url)

    main.persist_generation_media(
        {"provider": "bytedance", "image_url": "https://byteplus.example/img.png", "images": ["https://byteplus.example/img.png"]},
        "image",
    )

    assert all(provider == "bytedance" for _url, _category, provider in seen)
