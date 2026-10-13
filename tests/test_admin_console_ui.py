"""The built Admin Console is served at /admin with its own strict CSP."""
import httpx
import pytest

import main


async def get(path):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="https://api.test") as c:
        return await c.get(path)


@pytest.fixture
def dist(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>SYLVEX Admin</title>")
    (tmp_path / "assets" / "app-1.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("nope")
    monkeypatch.setattr(main, "ADMIN_CONSOLE_DIST", tmp_path.resolve())
    return tmp_path


@pytest.mark.asyncio
async def test_admin_shell_and_assets(dist):
    r = await get("/admin")
    assert r.status_code == 307 and r.headers["location"] == "/admin/"
    r = await get("/admin/")
    assert r.status_code == 200 and "SYLVEX Admin" in r.text
    assert r.headers["cache-control"] == "no-store"
    csp = r.headers.get_list("content-security-policy")
    console = next(p for p in csp if "default-src 'self'" in p)
    assert "script-src 'self' https://telegram.org;" in console and "connect-src 'self'" in console
    assert "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org" in console
    r = await get("/admin/assets/app-1.js")
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]


@pytest.mark.asyncio
async def test_client_routes_fall_back_to_the_shell_and_paths_cannot_escape(dist):
    r = await get("/admin/users/s123")
    assert r.status_code == 200 and "SYLVEX Admin" in r.text
    for path in ("/admin/../secret.txt", "/admin/%2e%2e/secret.txt", "/admin/..%2fsecret.txt"):
        r = await get(path)
        assert "nope" not in r.text


@pytest.mark.asyncio
async def test_missing_build_is_a_clear_503(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "ADMIN_CONSOLE_DIST", (tmp_path / "missing").resolve())
    r = await get("/admin/")
    assert r.status_code == 503 and r.json()["error"] == "admin_console_not_built"


def test_committed_build_exists():
    index = main.BASE_DIR / "admin_console" / "dist" / "index.html"
    assert index.is_file(), "run `npm run build` in admin_console and commit dist/"
    assert "/admin/assets/" in index.read_text()
