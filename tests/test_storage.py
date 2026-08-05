import importlib


def test_local_storage_roundtrip(monkeypatch, tmp_path):
    for name in ("R2_BUCKET", "R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_PUBLIC_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    import services.storage as storage
    storage = importlib.reload(storage)
    monkeypatch.setattr(storage, "LOCAL_GENERATED_DIR", tmp_path / "webapp" / "generated")
    monkeypatch.setattr(storage, "DATABASE_URL", "")
    url = storage.put_bytes(b"sylvex-r2-test", storage.generated_key("tests", "roundtrip.txt"), "text/plain")
    assert url == "/webapp/generated/tests/roundtrip.txt"
    assert storage.read_bytes(url) == b"sylvex-r2-test"
    assert storage.exists(url)
    assert storage.delete(url)
    assert not storage.exists(url)
