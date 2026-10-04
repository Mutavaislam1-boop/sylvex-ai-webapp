"""Edit history stores complete private canvases, not just result thumbnails."""
import asyncio
import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
import main
from services import edit_sessions as history


def canvas():
    source = {'id': 'edit-node-1', 'parentId': '', 'status': 'ready', 'url': 'https://cdn.example/source.png',
              'preview': 'https://cdn.example/source.png', 'x': -100, 'y': 25, 'slotWidth': 480, 'slotHeight': 320}
    child = {**source, 'id': 'edit-node-2', 'parentId': source['id'], 'url': 'https://cdn.example/result.png', 'x': 500}
    return {'sessionId': 'edit-example', 'activeNodeId': child['id'], 'chain': [source, child],
            'sourceUrl': child['url'], 'zoom': 200, 'viewport': {'x': 70, 'y': 25},
            'camera': {'horizontal': 180, 'vertical': 25, 'zoom': 5}}


def test_canvas_roundtrip_keeps_layout_and_camera():
    state = canvas()
    assert json.loads(history.validate_session(state['sessionId'], state)) == state


@pytest.mark.parametrize('change', [
    lambda s: s.update(sessionId='another'),
    lambda s: s.update(activeNodeId='missing'),
    lambda s: s['chain'][1].update(id='edit-node-1'),
    lambda s: s['chain'][0].update(parentId='edit-node-2'),
    lambda s: s['chain'][0].update(slotWidth=0),
    lambda s: s['chain'][0].update(x=float('nan')),
    lambda s: s['chain'][0].update(url='javascript:alert(1)'),
    lambda s: s['chain'][0].update(preview='blob:expired'),
    lambda s: s.update(prompt='x' * (4 * 1024 * 1024)),
])
def test_invalid_history_is_rejected(change):
    state = canvas(); change(state)
    with pytest.raises(ValueError):
        history.validate_session('edit-example', state)


def test_all_source_and_chain_media_urls_are_refreshed_without_mutating_settings(monkeypatch):
    state = canvas()
    monkeypatch.setattr(history, 'sign_media_url', lambda url: url + '?fresh=1' if url else '')
    restored = history.refresh_media(state)
    assert restored['sourceUrl'].endswith('?fresh=1')
    assert all(n['url'].endswith('?fresh=1') and n['preview'].endswith('?fresh=1') for n in restored['chain'])
    assert restored['camera'] == state['camera'] and restored['viewport'] == state['viewport']
    assert '?' not in state['sourceUrl']


@contextmanager
def database_cursor(cursor):
    class Connection:
        def cursor(self): return self
        def __enter__(self): return cursor
        def __exit__(self, *args): pass
    yield Connection()


def test_storage_scopes_every_operation_to_verified_owner():
    cursor = Mock(); cursor.fetchone.return_value = None; cursor.fetchall.return_value = []
    connect = lambda: database_cursor(cursor)
    state = canvas()
    history.save(connect, 101, 'edit-example', state)
    sql, values = cursor.execute.call_args.args
    assert 'ON CONFLICT (telegram_id, id)' in sql and values[:2] == (101, 'edit-example')
    assert json.loads(values[-1]) == state
    assert history.get(connect, 202, 'edit-example') is None
    sql, values = cursor.execute.call_args.args
    assert 'WHERE telegram_id=%s AND id=%s' in sql and values == (202, 'edit-example')
    assert history.list_sessions(connect, 202) == []
    sql, values = cursor.execute.call_args.args
    assert 'WHERE telegram_id=%s' in sql and values == (202, 0)


def test_save_handler_ignores_body_owner_and_uses_authenticated_request(monkeypatch):
    saved = []
    monkeypatch.setattr(main, 'DATABASE_URL', 'test-db-not-connected')
    monkeypatch.setattr(main, 'ensure_prostudio_table', lambda: None)
    monkeypatch.setattr(history, 'save', lambda connect, owner, id, state: saved.append((owner, id, state)))
    async def body(): return {'telegram_id': 999, 'state': canvas()}
    request = SimpleNamespace(state=SimpleNamespace(telegram_id=101), json=body)
    result = asyncio.run(main.public_save_edit_session(request, 'edit-example'))
    assert result['ok'] and saved[0][0] == 101


def test_unauthenticated_history_is_not_available(monkeypatch):
    monkeypatch.setattr(main, 'DATABASE_URL', 'test-db-not-connected')
    with pytest.raises(HTTPException) as error:
        asyncio.run(main.public_edit_sessions(SimpleNamespace(state=SimpleNamespace())))
    assert error.value.status_code == 401
