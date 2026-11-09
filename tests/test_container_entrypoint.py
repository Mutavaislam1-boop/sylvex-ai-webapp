"""B09: the API keeps running as the unprivileged user sylvex.

Railway mounts volumes root-owned, so the API is started as root
(RAILWAY_RUN_UID=0) only for the entrypoint to prepare the erasure journal
directory; the service process itself always runs as uid 10001."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "docker-entrypoint.sh"


def test_dockerfile_keeps_sylvex_and_a_root_owned_entrypoint():
    text = (ROOT / "Dockerfile").read_text()
    assert "COPY --chown=root:root docker-entrypoint.sh /usr/local/bin/sylvex-entrypoint" in text
    assert "command -v setpriv" in text
    assert text.index("USER sylvex") < text.index('ENTRYPOINT ["/usr/local/bin/sylvex-entrypoint"]')
    assert 'CMD ["sh", "-c", "exec python -m uvicorn main:app' in text


def test_entrypoint_drops_to_sylvex_and_hands_over_the_journal():
    if os.geteuid() != 0 or not shutil.which("setpriv"):
        pytest.skip("needs root and setpriv, like the container start")
    volume = Path(tempfile.mkdtemp(dir="/var/tmp"))
    volume.chmod(0o755)
    journal = volume / "journal"
    out = subprocess.run(["sh", str(SCRIPT), "sh", "-c", 'echo "$(id -u) $HOME"; stat -c "%u %a" "$SYLVEX_ERASURE_JOURNAL_DIR"'],
                         env={**os.environ, "SYLVEX_ERASURE_JOURNAL_DIR": str(journal)},
                         capture_output=True, text=True, check=True).stdout.split("\n")
    assert out[0] == "10001 /home/sylvex"
    assert out[1] == "10001 700"


def test_entrypoint_refuses_unsafe_journal_paths():
    if os.geteuid() != 0 or not shutil.which("setpriv"):
        pytest.skip("needs root and setpriv, like the container start")
    volume = Path(tempfile.mkdtemp(dir="/var/tmp"))
    (volume / "link").symlink_to("/etc")
    for path in (str(volume / "link"), "relative/path"):
        result = subprocess.run(["sh", str(SCRIPT), "true"], env={**os.environ, "SYLVEX_ERASURE_JOURNAL_DIR": path},
                                capture_output=True, text=True)
        assert result.returncode == 1
