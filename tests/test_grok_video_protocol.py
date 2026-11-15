"""xAI REST contract regressions; fake HTTP only, never provider generation."""
import asyncio
import json

import pytest
import services.video_router as router


class Response:
    def __init__(self, data, status=200):
        self.status_code = status
        self.text = json.dumps(data)


@pytest.fixture
def fake_provider(monkeypatch):
    for key in ('XAI_API_KEY', 'XAI-API-KEY', 'GROK_API_KEY', 'GROK-API-KEY', 'XAI_VIDEO_ENDPOINT'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('XAI_API_KEY', 'synthetic-key')
    monkeypatch.setattr(router, '_provider_model_for_video', lambda _: 'grok-imagine-video')
    body = {'ratio': '16:9', 'duration': 5, 'resolution': '720p'}
    monkeypatch.setattr(router, '_build_video_payload', lambda *args: dict(body))
    sent = []
    monkeypatch.setattr(router, '_request_json', lambda url, headers, data: sent.append((url, headers, data)) or Response({'request_id': 'synthetic-task'}))
    return body, sent


@pytest.mark.parametrize('key', ['XAI_API_KEY', 'XAI-API-KEY', 'GROK_API_KEY', 'GROK-API-KEY'])
def test_installed_grok_alias_is_used(monkeypatch, fake_provider, key):
    _, sent = fake_provider
    monkeypatch.delenv('XAI_API_KEY', raising=False)
    monkeypatch.setenv(key, 'synthetic-key')
    result = router._call_grok('grok_video', 'fixture', {})
    assert sent and sent[0][1]['Authorization'] == 'Bearer synthetic-key'
    assert result['ok'] and result['task_id'] == 'synthetic-task'


def test_request_id_becomes_durable_task_and_uses_status_endpoint(fake_provider):
    _, sent = fake_provider
    result = router._call_grok('grok_video', 'fixture', {'video_options': {'sound': True}})
    assert result['ok'] and result['status'] == 'processing'
    assert result['task_id'] == 'synthetic-task'
    assert result['poll_url'] == 'https://api.x.ai/v1/videos/synthetic-task'
    assert sent[0][0] == 'https://api.x.ai/v1/videos/generations'
    assert sent[0][2]['generate_audio'] is True
    assert sent[0][2]['duration'] == 5 and sent[0][2]['resolution'] == '720p'


def test_source_image_is_passed_in_xai_shape(fake_provider):
    body, sent = fake_provider
    body['start_image'] = 'https://asset.example.test/first.png'
    router._call_grok('grok_video', 'fixture', {})
    assert sent[0][2]['image'] == {'url': body['start_image']}
    assert 'start_image' not in sent[0][2]


def test_edit_uses_official_endpoint_and_source_only(fake_provider):
    body, sent = fake_provider
    body['input_video'] = 'https://asset.example.test/source.mp4'
    result = router._call_grok('grok_video_edit', 'fixture', {})
    assert result['ok']
    assert sent[0][0] == 'https://api.x.ai/v1/videos/edits'
    assert sent[0][2] == {'model': 'grok-imagine-video', 'prompt': 'fixture', 'video': {'url': body['input_video']}}


def test_missing_edit_source_does_not_submit(fake_provider):
    _, sent = fake_provider
    result = router._call_grok('grok_video_edit', 'fixture', {})
    assert not result['ok'] and not sent


def test_poll_done_uses_existing_task_and_never_posts(monkeypatch, fake_provider):
    _, sent = fake_provider
    got = []
    monkeypatch.setattr(router, '_request_get', lambda url, headers: got.append(url) or Response({'status': 'done', 'video': {'url': 'https://asset.example.test/result.mp4'}, 'usage': {'cost_in_usd_ticks': 500000000}}))
    result = asyncio.run(router.poll_video_generation({'provider': 'grok', 'model': 'grok_video', 'task_id': 'synthetic-task'}))
    assert got == ['https://api.x.ai/v1/videos/synthetic-task']
    assert result['status'] == 'completed' and not sent
    assert result['provider_response']['usage']['cost_in_usd_ticks'] == 500000000


def test_poll_pending_keeps_id_without_submit(monkeypatch, fake_provider):
    _, sent = fake_provider
    monkeypatch.setattr(router, '_request_get', lambda *args: Response({'status': 'pending'}))
    result = asyncio.run(router.poll_video_generation({'provider': 'grok', 'model': 'grok_video', 'task_id': 'synthetic-task'}))
    assert result['status'] == 'processing' and result['task_id'] == 'synthetic-task'
    assert result['poll_url'] == 'https://api.x.ai/v1/videos/synthetic-task' and not sent


def test_poll_http_failure_is_not_a_new_generation(monkeypatch, fake_provider):
    _, sent = fake_provider
    monkeypatch.setattr(router, '_request_get', lambda *args: Response({'error': 'fixture unauthorized'}, 401))
    result = asyncio.run(router.poll_video_generation({'provider': 'grok', 'model': 'grok_video', 'task_id': 'synthetic-task'}))
    assert not result['ok'] and not sent


def test_other_providers_do_not_treat_trace_request_id_as_a_task():
    result = router._provider_result_from_response('other', 'fixture', Response({'request_id': 'trace-only'}), 'https://provider.example.test/create')
    assert not result['ok']


def test_custom_video_base_is_preserved(monkeypatch, fake_provider):
    monkeypatch.setenv('XAI_VIDEO_ENDPOINT', 'https://proxy.example.test/v1/videos/generations')
    result = router._call_grok('grok_video', 'fixture', {})
    assert result['poll_url'] == 'https://proxy.example.test/v1/videos/synthetic-task'


def test_canonical_key_precedence_is_preserved(monkeypatch, fake_provider):
    _, sent = fake_provider
    monkeypatch.setenv('GROK_API_KEY', 'other-synthetic-key')
    router._call_grok('grok_video', 'fixture', {})
    assert sent[0][1]['Authorization'] == 'Bearer synthetic-key'


def test_missing_keys_do_not_submit(monkeypatch, fake_provider):
    _, sent = fake_provider
    monkeypatch.delenv('XAI_API_KEY')
    result = router._call_grok('grok_video', 'fixture', {})
    assert not result['ok'] and not sent
