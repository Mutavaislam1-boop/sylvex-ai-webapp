"""Regression tests for remediation item #18 (BUG-3) in main.py's
save_text_pdf().

Before the fix, the temporary PDF file created by
tempfile.NamedTemporaryFile(...) was only ever cleaned up on the success
path, via storage_put_file(..., remove_local=True). If doc.build() raised
(malformed content, a reportlab internal error) or storage_put_file()
raised (storage/network failure), the function's outer except just logged
and returned "" - the temp file on disk was never deleted, leaking one
file per failed PDF generation.

Fix: a narrow try/finally now wraps the build+upload section. The finally
unlinks the temp file only if it still exists (so a successful upload that
already removed it - R2 mode, where services/storage.py's put_file does
`source.unlink(missing_ok=True)` in its own finally when remove_local=True
and R2 is enabled - is never double-deleted), and swallows any cleanup
error so it can never mask the real doc.build()/storage exception
propagating through the same finally.

These tests exercise the real save_text_pdf() end-to-end (real reportlab
PDF generation, a real temp file on disk), only stubbing the one thing
that must vary per scenario (reportlab's own build() method, or
storage_put_file), and inspecting the real filesystem path tempfile
actually created to prove it is gone (or correctly still absent) in every
case."""
import pathlib
import tempfile as tempfile_module

import pytest

import main


def _capture_temp_paths(monkeypatch):
    """Wrap the real tempfile.NamedTemporaryFile so the test can see
    exactly which path save_text_pdf() created, without changing its
    behavior at all."""
    created = []
    real_named_temp = tempfile_module.NamedTemporaryFile

    def spy(*args, **kwargs):
        temp = real_named_temp(*args, **kwargs)
        created.append(pathlib.Path(temp.name))
        return temp

    monkeypatch.setattr(main.tempfile, "NamedTemporaryFile", spy)
    return created


def test_doc_build_failure_removes_the_temp_file(monkeypatch):
    created = _capture_temp_paths(monkeypatch)
    from reportlab.platypus import SimpleDocTemplate

    def failing_build(self, *_args, **_kwargs):
        raise RuntimeError("reportlab build failed")

    monkeypatch.setattr(SimpleDocTemplate, "build", failing_build)

    result = main.save_text_pdf("hello world", "Title")

    assert result == ""
    assert len(created) == 1, "exactly one temp file must have been created"
    assert not created[0].exists(), "the temp file must be removed after a doc.build() failure"


def test_storage_upload_failure_removes_the_temp_file(monkeypatch):
    created = _capture_temp_paths(monkeypatch)

    def failing_put_file(path, key, content_type, remove_local=False):
        raise RuntimeError("storage upload failed")

    monkeypatch.setattr(main, "storage_put_file", failing_put_file)

    result = main.save_text_pdf("hello world", "Title")

    assert result == ""
    assert len(created) == 1
    assert not created[0].exists(), "the temp file must be removed after a storage_put_file() failure"


def test_successful_storage_still_works_and_leaves_no_local_temp_file(monkeypatch):
    created = _capture_temp_paths(monkeypatch)
    seen_paths = []

    def fake_put_file_local_mode(path, key, content_type, remove_local=False):
        # Mirrors services/storage.py's own local (non-R2) branch, which
        # never deletes the source file itself even when remove_local=True
        # (its finally only unlinks when r2_enabled() is also true) - so
        # this stub, deliberately, does NOT remove the file either. If
        # save_text_pdf's own cleanup weren't there, this exact mode would
        # leak a temp file on every successful call.
        seen_paths.append(pathlib.Path(path))
        assert pathlib.Path(path).exists(), "the file must still exist when storage_put_file is invoked"
        return "https://cdn.sylvex.ai/documents/fake-local-mode.pdf"

    monkeypatch.setattr(main, "storage_put_file", fake_put_file_local_mode)

    result = main.save_text_pdf("hello world", "Title")

    assert result == "https://cdn.sylvex.ai/documents/fake-local-mode.pdf"
    assert len(created) == 1
    assert not created[0].exists(), "a successful save must leave no local temp file behind"
    assert seen_paths == created, "storage_put_file must have been called with the exact same temp path"


def test_successful_storage_that_already_removed_the_file_is_not_double_deleted(monkeypatch):
    created = _capture_temp_paths(monkeypatch)

    def fake_put_file_r2_mode(path, key, content_type, remove_local=False):
        # Mirrors services/storage.py's R2-enabled branch, which already
        # unlinks the source file itself in its own finally when
        # remove_local=True.
        p = pathlib.Path(path)
        if remove_local:
            p.unlink(missing_ok=True)
        return "https://cdn.sylvex.ai/documents/fake-r2-mode.pdf"

    monkeypatch.setattr(main, "storage_put_file", fake_put_file_r2_mode)

    result = main.save_text_pdf("hello world", "Title")

    assert result == "https://cdn.sylvex.ai/documents/fake-r2-mode.pdf"
    assert len(created) == 1
    assert not created[0].exists(), "the file must still be gone - no double-delete exception swallowed the result"


def test_normal_successful_pdf_generation_is_otherwise_unchanged(monkeypatch):
    """No failure, no storage stub at all - storage_put_file still runs for
    real (local filesystem storage, since R2 env vars are stripped by
    conftest.py) and the function's return contract/behavior is unchanged."""
    created = _capture_temp_paths(monkeypatch)

    result = main.save_text_pdf("Hello, SYLVEX!\nSecond line.", "My Title")
    try:
        assert isinstance(result, str) and result, "a successful call must return a non-empty URL/path string"
        assert len(created) == 1
        assert not created[0].exists(), "no local temp file must remain after a real successful save"
    finally:
        # This path exercises the real local-storage write (services/storage.py) -
        # clean up the real generated artifact so the test doesn't leave stray
        # files behind in webapp/generated/.
        try:
            main.storage_delete(main.storage_key_from_url(result))
        except Exception:
            pass
