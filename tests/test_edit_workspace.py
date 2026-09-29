"""The nine Edit modes must use their own inputs and real provider parameters."""
import asyncio
import base64
import io
import json

import pytest
from PIL import Image
import main
from services import edit_workspace as edit


def image_bytes(size=(64, 48), color=(20, 40, 60, 255)):
    return edit.png(Image.new('RGBA', size, color))


def uri(raw):
    return 'data:image/png;base64,' + base64.b64encode(raw).decode()


def payload(mode='edit', **settings):
    return {'mode': 'image', 'model': 'gpt_image_2_5_sunburst', 'prompt': 'IGNORE COMPOSER PROMPT', 'image_options': {
        'tool': 'edit_workspace', 'editWorkspaceMode': mode,
        'editWorkspaceSourceUrl': uri(image_bytes()), 'editWorkspacePrompt': 'Make it blue',
        'characterReferences': ['UNRELATED'], 'referenceImageUrls': ['UNRELATED'], **settings}}


class Response:
    def __init__(self, data):
        self.status_code = 200
        self.text = json.dumps(data)


@pytest.fixture
def provider(monkeypatch):
    calls, stored = [], []
    generated = image_bytes(color=(200, 120, 50, 255))
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response({'data': [{'b64_json': base64.b64encode(generated).decode()}]})
    def put(raw, key, content_type):
        stored.append(raw)
        return 'https://cdn.example.com/' + key
    monkeypatch.setattr(main, 'OPENAI_API_KEY', 'test-key')
    monkeypatch.setattr(main.requests, 'post', post)
    monkeypatch.setattr(main, 'storage_put_bytes', put)
    monkeypatch.setattr(main, '_persist_remote_media_url', lambda *a, **k: 'https://cdn.example.com/result.png')
    monkeypatch.setattr(main, 'attach_image_thumbnails', lambda result: result)
    return calls, stored


@pytest.mark.parametrize(('mode', 'settings', 'fragment'), [
    ('edit', {}, 'Make it blue'),
    ('background', {'editWorkspaceBackgroundMode': 'transparent'}, 'true transparency'),
    ('background', {'editWorkspaceBackgroundMode': 'replace'}, 'only the background'),
    ('translate', {'editWorkspaceTranslateLanguage': 'Turkish'}, 'Turkish'),
])
def test_openai_contract_and_isolation(provider, mode, settings, fragment):
    result = asyncio.run(main.generate_edit_workspace_image(payload(mode, **settings)))
    assert result['ok']
    call = provider[0][0][1]
    assert fragment in call['data']['prompt']
    assert 'IGNORE COMPOSER' not in call['data']['prompt']
    assert 'UNRELATED' not in str(call)
    assert call['data']['output_format'] == 'png'
    assert call['data'].get('background') == ('transparent' if settings.get('editWorkspaceBackgroundMode') == 'transparent' else None)


def test_retouch_transmits_alpha_mask_and_preserves_unselected_pixels(provider):
    mark = Image.new('RGBA', (64, 48));mark.paste((0, 255, 0, 255), (20, 10, 30, 20))
    result = asyncio.run(main.generate_edit_workspace_image(payload('retouch', editWorkspaceMaskUrl=uri(edit.png(mark)), editWorkspaceBrush={'mode': 'erase'})))
    assert result['ok']
    call = provider[0][0][1]
    files = dict(call['files'])
    mask = Image.open(io.BytesIO(files['mask'][1]))
    assert mask.getpixel((21, 11))[3] == 0
    assert mask.getpixel((0, 0))[3] == 255
    final = Image.open(io.BytesIO(provider[1][0]))
    assert final.getpixel((0, 0)) == (20, 40, 60, 255)
    assert final.getpixel((21, 11)) == (200, 120, 50, 255)
    assert 'Remove the content' in call['data']['prompt']


def test_empty_mask_rejected_before_provider(provider):
    result = asyncio.run(main.generate_edit_workspace_image(payload('retouch', editWorkspaceMaskUrl=uri(image_bytes(color=(0, 0, 0, 0))), editWorkspaceBrush={'mode': 'erase'})))
    assert not result['ok']
    assert not provider[0]


def test_expand_sends_padded_source_and_protects_original_pixels(provider):
    result = asyncio.run(main.generate_edit_workspace_image(payload('expand', editWorkspaceExpand={'left': 10, 'top': 20, 'right': 30, 'bottom': 0})))
    assert result['ok']
    files = dict(provider[0][0][1]['files'])
    source = Image.open(io.BytesIO(files['image'][1]));mask = Image.open(io.BytesIO(files['mask'][1]))
    assert source.size == mask.size == (104, 68)
    assert mask.getpixel((0, 0))[3] == 0
    assert mask.getpixel((10, 20))[3] == 255
    final = Image.open(io.BytesIO(provider[1][0]))
    assert final.size == (104, 68)
    assert final.getpixel((10, 20)) == (20, 40, 60, 255)
    assert final.getpixel((0, 0)) == (200, 120, 50, 255)


def test_resize_is_exact_free_and_never_calls_ai(provider):
    request = payload('resize', editWorkspaceResize={'width': 180, 'height': 75})
    result = asyncio.run(main.generate_edit_workspace_image(request))
    assert result['ok'] and result['provider'] == 'local'
    assert Image.open(io.BytesIO(provider[1][0])).size == (180, 75)
    assert not provider[0]
    price = main.calculate_generation_price(request)
    assert price['pricing_available'] and price['credits'] == price['price_snapshot']['final_credits'] == 0


@pytest.mark.parametrize(('mode','settings'), [
    ('nonsense', {}), ('edit', {'editWorkspacePrompt': ''}),
    ('translate', {}), ('background', {'editWorkspaceBackgroundMode': 'replace', 'editWorkspacePrompt': ''}),
    ('retouch', {'editWorkspaceBrush': {'mode': 'erase'}}),
    ('resize', {'editWorkspaceResize': {'width': float('nan'), 'height': 500}}),
    ('resize', {'editWorkspaceResize': {'width': 8192, 'height': 8192}}),
    ('camera', {'editWorkspaceCamera': {'zoom': 'oops'}}),
    ('expand', {'editWorkspaceExpand': {'left': 0, 'right': 0, 'top': 0, 'bottom': 0}}),
    ('lighting', {'editWorkspaceLight': {'layers': [{'enabled': False}]}}),
])
def test_bad_settings_fail_in_route_validation_and_adapter(provider, mode, settings):
    request = payload(mode, **settings)
    assert main.validate_image_feature_request(request)['ok'] is False
    assert asyncio.run(main.generate_edit_workspace_image(request))['ok'] is False
    assert not provider[0]


@pytest.mark.parametrize(('mode', 'brightness'), [('camera', 1.5), ('lighting', 1.5), ('lighting', None)])
def test_fal_contract_uses_enabled_lights_and_numeric_camera(monkeypatch, provider, mode, brightness):
    calls = []
    monkeypatch.setattr(main, 'FAL_API_KEY', 'fake')
    def post(url, **kw):
        calls.append((url, kw))
        return Response({'status_url': 'https://queue.fal.run/status', 'response_url': 'https://queue.fal.run/result'})
    monkeypatch.setattr(main.requests, 'post', post)
    monkeypatch.setattr(main.requests, 'get', lambda url, **kw: Response({'status': 'COMPLETED'} if url.endswith('status') else {'images': [{'url': 'https://cdn.example.com/generated.png'}]}))
    request = payload(mode, editWorkspaceCamera={'horizontal': 270, 'vertical': -30, 'zoom': 0}, editWorkspaceLight={'active': 0, 'layers': [
        {'enabled': False, 'horizontal': -90, 'color': '#ff0000'},
        {'enabled': True, 'horizontal': 70, 'vertical': 0, 'brightness': brightness, 'color': '#00ff00'}]})
    assert asyncio.run(main.generate_edit_workspace_image(request))['ok']
    data = calls[0][1]['json']
    assert data['output_format'] == 'png'
    if mode == 'camera':
        assert (data['horizontal_angle'], data['vertical_angle'], data['zoom']) == (270, -30, 0)
    else:
        assert data['initial_latent'] == 'Right'
        assert '#00ff00' in data['prompt'] and '#ff0000' not in data['prompt']


def test_topaz_workspace_passes_controls_and_preserves_ratio(monkeypatch, provider):
    from test_enhance_photo_tool import _apply_success_mocks, _FakeResponse
    _apply_success_mocks(monkeypatch)
    sent = []
    monkeypatch.setattr(main.requests, 'post', lambda url, **kw: sent.append(kw) or _FakeResponse(200, {'process_id': 'test'}))
    result = asyncio.run(main.generate_edit_workspace_image(payload('upscale', editWorkspaceUpscale={
        'width': 128, 'height': 96, 'sharpness': 33, 'denoise': 44, 'subject': 'Background',
        'faceEnhancement': True, 'strength': 0, 'creativity': 18, 'modelStrength': 25, 'fixCompression': 30})))
    assert result['ok']
    assert sent[0]['data']['outputHeight'] == '96'
    assert sent[0]['data']['subjectDetection'] == 'background'
    assert sent[0]['data']['faceEnhancementStrength'] == '0'
    assert sent[0]['data']['strength'] == '0.25'
    assert sent[0]['data']['fixCompression'] == '0.3'


def test_upscale_rotates_exif_source_before_preserving_aspect_ratio(monkeypatch, provider):
    from test_enhance_photo_tool import _apply_success_mocks, _FakeResponse
    _apply_success_mocks(monkeypatch)
    photo = Image.new('RGB', (64, 48))
    exif = photo.getexif()
    exif[274] = 6
    raw = io.BytesIO()
    photo.save(raw, 'JPEG', exif=exif)
    sent = []
    monkeypatch.setattr(main.requests, 'post', lambda url, **kw: sent.append(kw) or _FakeResponse(200, {'process_id': 'test'}))
    request = payload('upscale', editWorkspaceSourceUrl=uri(raw.getvalue()), editWorkspaceUpscale={'width': 96, 'height': 128})
    assert asyncio.run(main.generate_edit_workspace_image(request))['ok']
    assert Image.open(io.BytesIO(sent[0]['files']['image'][1])).size == (48, 64)
    assert sent[0]['data']['outputHeight'] == '128'


@pytest.mark.parametrize(('width', 'height', 'provider_credits'), [(6000, 4000, 1), (8000, 5000, 2), (8000, 6000, 3), (10000, 10000, 5)])
def test_upscale_estimate_uses_provider_megapixel_tiers(width, height, provider_credits):
    estimate = main.calculate_generation_price(payload('upscale', editWorkspaceUpscale={'width': width, 'height': height}))
    assert estimate['provider_cost_usd'] == pytest.approx(main.TOPAZ_CREDIT_COST_USD * provider_credits)


@pytest.mark.parametrize('size', [(10, 10), (320, 4000), (8192, 4096), (4096, 4096), (123, 300)])
def test_openai_sizes_satisfy_provider_contract(size):
    width, height = map(int, edit.output_size(size).split('x'))
    assert width % 16 == height % 16 == 0
    assert max(width, height) <= 3840
    assert max(width, height) / min(width, height) <= 3
    assert 655360 <= width * height <= 8294400


def test_resize_route_queues_without_credits_but_requires_subscription(monkeypatch):
    request_payload = payload('resize', editWorkspaceResize={'width': 120, 'height': 80})
    request_payload['telegram_id'] = 10
    class Request:
        async def json(self):
            return request_payload
    recorded = []
    monkeypatch.setattr(main, 'get_user_state', lambda uid: {'balance': 0, 'subscription_status': 'active'})
    monkeypatch.setattr(main, 'get_active_prostudio_job', lambda uid: {})
    monkeypatch.setattr(main, 'create_prostudio_generation_job', lambda p: recorded.append(p) or 'resize-test')
    monkeypatch.setattr(main, 'log_user_event', lambda *a, **kw: None)
    result = asyncio.run(main.public_prostudio_generate(Request()))
    assert result['status'] == 'queued'
    assert recorded[0]['price_snapshot']['final_credits'] == 0
    monkeypatch.setattr(main, 'get_user_state', lambda uid: {'balance': 0, 'subscription_status': 'inactive'})
    assert asyncio.run(main.public_prostudio_generate(Request())).status_code == 403


def test_resize_does_not_waive_other_generation_prices():
    request = payload('resize', editWorkspaceResize={'width': 120, 'height': 80})
    request.update(mode='music', model='suno_chirp_5')
    assert not edit.is_free_resize(request)
    assert main.calculate_generation_price(request)['credits'] > 0


def test_resize_worker_does_not_acquire_ai_provider_slot(monkeypatch, provider):
    def fail(*a, **kw):
        pytest.fail('Local resize must not use provider leases or retry')
    monkeypatch.setattr(main, 'provider_slot', fail)
    monkeypatch.setattr(main, 'provider_call_with_retry', fail)
    request = payload('resize', editWorkspaceResize={'width': 90, 'height': 60})
    result, status = asyncio.run(main.run_prostudio_provider_request('test', request, 'image', 'gpt_image_2_5_sunburst', 'openai', {'text'}, 'OPENAI'))
    assert result['ok'] and status == 'completed' and not provider[0]
