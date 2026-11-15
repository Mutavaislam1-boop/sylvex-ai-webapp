"""Runway text/image/video routes; fake HTTP, no generations."""
import json
import pytest
import services.video_router as router

@pytest.fixture
def fake_request(monkeypatch):
    monkeypatch.setenv('RUNWAY_API_KEY', 'synthetic-key')
    body = {'ratio': '16:9', 'duration': 5, 'resolution': '720p'}
    monkeypatch.setattr(router, '_build_video_payload', lambda *args: dict(body))
    endpoint = {'value': 'https://api.dev.runwayml.com/v1/image_to_video'}
    models = {'runway_gen4_5': 'gen4.5', 'runway_happyhorse_1_0': 'happyhorse_1_0', 'runway_gen4_turbo': 'gen4_turbo', 'runway_aleph2': 'aleph2'}
    monkeypatch.setattr(router, '_provider_model_for_video', lambda model: models[model])
    monkeypatch.setattr(router, '_video_model_mapping', lambda _: {'endpoint': endpoint['value']})
    monkeypatch.setattr(router, '_log_provider_response', lambda *args: None)
    sent = []
    class Response:
        status_code = 200
        text = json.dumps({'id': 'synthetic-runway-task'})
    monkeypatch.setattr(router, '_request_json', lambda url, headers, data: sent.append((url, data)) or Response())
    return body, endpoint, sent

@pytest.mark.parametrize('model', ['runway_gen4_5', 'runway_happyhorse_1_0'])
def test_text_only_supported_models_use_text_endpoint(fake_request, model):
    _, _, sent = fake_request
    result = router._call_runway(model, 'fixture', {})
    assert result['ok']
    assert sent[0][0] == 'https://api.dev.runwayml.com/v1/text_to_video'
    assert 'promptImage' not in sent[0][1]

@pytest.mark.parametrize('model', ['runway_gen4_5', 'runway_happyhorse_1_0'])
def test_existing_image_route_is_preserved(fake_request, model):
    body, _, sent = fake_request
    body['start_image'] = 'https://asset.example.test/source.png'
    result = router._call_runway(model, 'fixture', {})
    assert result['ok']
    assert sent[0][0] == 'https://api.dev.runwayml.com/v1/image_to_video'
    assert sent[0][1]['promptImage'] == body['start_image']
    if model == 'runway_happyhorse_1_0':
        assert 'ratio' not in sent[0][1]


def test_gen4_turbo_still_requires_image(fake_request):
    _, _, sent = fake_request
    result = router._call_runway('runway_gen4_turbo', 'fixture', {})
    assert not result['ok'] and not sent


def test_video_edit_route_is_unchanged(fake_request):
    body, _, sent = fake_request
    body['input_video'] = 'https://asset.example.test/source.mp4'
    result = router._call_runway('runway_aleph2', 'fixture', {})
    assert result['ok']
    assert sent[0][0] == 'https://api.dev.runwayml.com/v1/video_to_video'
    assert sent[0][1]['videoUri'] == body['input_video']


def test_explicit_custom_endpoint_is_preserved(fake_request):
    _, endpoint, sent = fake_request
    endpoint['value'] = 'https://proxy.example.test/custom-runway'
    result = router._call_runway('runway_gen4_5', 'fixture', {})
    assert result['ok'] and sent[0][0] == endpoint['value']
