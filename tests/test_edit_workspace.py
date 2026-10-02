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


@pytest.mark.parametrize('brightness', [1.5, None])
def test_sunburst_lighting_uses_enabled_legacy_lights(provider, brightness):
    request = payload('lighting', editWorkspaceCamera={'horizontal': 270, 'vertical': -30, 'zoom': 0}, editWorkspaceLight={'active': 0, 'layers': [
        {'enabled': False, 'horizontal': -90, 'color': '#ff0000'},
        {'enabled': True, 'horizontal': 70, 'vertical': 0, 'brightness': brightness, 'color': '#00ff00'}]})
    assert asyncio.run(main.generate_edit_workspace_image(request))['ok']
    (url, call), = provider[0]
    data = call['data']
    assert data['output_format'] == 'png'
    assert url == f'{main.OPENAI_API_BASE}/images/edits'
    assert 'azimuth 63 degrees' in data['prompt']
    assert f"brightness {brightness if brightness is not None else 1:g}/2" in data['prompt']
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
    assert sent[0]['headers'] == {'X-API-KEY': 'test-topaz-key'}
    assert sent[0]['data']['sharpen'] == '0.33'
    assert sent[0]['data']['denoise'] == '0.44'
    assert sent[0]['data']['faceEnhancementCreativity'] == '0.18'
    assert (result['canvas_width'], result['canvas_height']) == (128, 96)
    assert result['upscale_settings']['strength'] == 0
    assert 'prompt' not in sent[0]['data']
    assert set(sent[0]['files']) == {'image'}


def test_upscale_face_toggle_omits_face_controls(monkeypatch, provider):
    from test_enhance_photo_tool import _apply_success_mocks, _FakeResponse
    _apply_success_mocks(monkeypatch)
    sent = []
    monkeypatch.setattr(main.requests, 'post', lambda url, **kw: sent.append((url, kw)) or _FakeResponse(200, {'process_id': 'test'}))
    request = payload('upscale', editWorkspaceUpscale={'width': 64, 'height': 48, 'faceEnhancement': False})
    result = asyncio.run(main.generate_edit_workspace_image(request))
    assert result['ok']
    assert sent[0][0] == main.TOPAZ_ENHANCE_ENDPOINT
    assert sent[0][1]['data']['faceEnhancement'] == 'false'
    assert 'faceEnhancementStrength' not in sent[0][1]['data']
    assert 'faceEnhancementCreativity' not in sent[0][1]['data']


@pytest.mark.parametrize('settings', [
    {'width': 0}, {'width': 128.5}, {'width': True}, {'height': float('nan')},
    {'width': 24001}, {'width': 10001, 'height': 10000}, {'width': 127},
    {'faceEnhancement': 'false'}, {'subject': 'Face'}, {'modelStrength': 0}, {'denoise': 101},
])
def test_invalid_upscale_never_submits_paid_provider_request(monkeypatch, provider, settings):
    from test_enhance_photo_tool import _apply_success_mocks
    _apply_success_mocks(monkeypatch)
    monkeypatch.setattr(main.requests, 'post', lambda *a, **k: pytest.fail('Invalid Upscale reached Topaz'))
    result = asyncio.run(main.generate_edit_workspace_image(payload('upscale', editWorkspaceUpscale={'width': 128, 'height': 96, **settings})))
    assert result['ok'] is False


@pytest.mark.parametrize(('size', 'target'), [((3000, 2000), (6000, 4000)), ((4000, 2500), (8000, 5000)),
    ((4000, 2500), (8002, 5001)), ((8000, 1000), (24000, 3000)), ((3, 2), (5, 3))])
def test_upscale_result_cost_matches_estimate_at_tier_and_rounding_boundaries(monkeypatch, provider, size, target):
    from test_enhance_photo_tool import _apply_success_mocks
    _apply_success_mocks(monkeypatch)
    # Avoid allocating giant test images; dimensions are independent of transport.
    monkeypatch.setattr(main, '_detect_image_dimensions', lambda _: size)
    request = payload('upscale', editWorkspaceUpscale={'width': target[0], 'height': target[1]})
    estimate = main.calculate_generation_price(request)
    result = asyncio.run(main.generate_edit_workspace_image(request))
    assert result['ok']
    assert result['cost_credits'] == estimate['credits']
    assert result['cost_usd'] == estimate['cost_usd']
    assert (result['canvas_width'], result['canvas_height']) == target


def test_enhance_quick_tool_ignores_workspace_settings(monkeypatch, provider):
    from test_enhance_photo_tool import _apply_success_mocks, _FakeResponse
    _apply_success_mocks(monkeypatch)
    sent = []
    monkeypatch.setattr(main.requests, 'post', lambda url, **kw: sent.append(kw) or _FakeResponse(200, {'process_id': 'test'}))
    request = {'image_options': {'tool': 'enhance_photo', 'enhancePhotoSourceUrl': uri(image_bytes()),
        'editWorkspaceUpscale': {'width': 1, 'height': 1, 'denoise': 100}, 'editWorkspaceMode': 'upscale'}}
    result = asyncio.run(main.generate_enhance_photo_image(request))
    assert result['ok']
    assert sent[0]['data'] == {'model': 'High Fidelity V2', 'outputHeight': '96'}
    assert result['cost_credits'] == 15
    assert result['tool'] == 'enhance_photo'


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


@pytest.mark.parametrize('camera', [
    {'horizontal': 180, 'vertical': 25, 'zoom': 10},
    {'horizontal': 217.4, 'vertical': 38.2, 'zoom': 6.7},
    {'horizontal': 360, 'vertical': -30, 'zoom': 0},
    {'horizontal': 0, 'vertical': 90, 'zoom': 10},
])
def test_camera_uses_sunburst_with_exact_angles_and_saved_result(monkeypatch, provider, camera, capsys):
    calls = []
    monkeypatch.setattr(main, 'OPENAI_API_KEY', 'test-openai-camera-key')
    monkeypatch.delenv('QWEN_API_KEY', raising=False)
    monkeypatch.delenv('QWEN-API-KEY', raising=False)
    monkeypatch.setattr(main, 'FAL_API_KEY', '')
    def post(url, **kw):
        assert url == f'{main.OPENAI_API_BASE}/images/edits'
        assert kw['headers']['Authorization'] == 'Bearer test-openai-camera-key'
        assert 'Content-Type' not in kw['headers']  # requests supplies the multipart boundary.
        assert 'json' not in kw
        assert kw['files'] == [('image', ('source.png', image_bytes(), 'image/png'))]
        calls.append(kw['data'])
        return Response({'data': [{'b64_json': base64.b64encode(image_bytes()).decode()}]})
    monkeypatch.setattr(main.requests, 'post', post)
    monkeypatch.setattr(main.requests, 'get', lambda *a, **kw: pytest.fail('Sunburst camera must not poll another provider'))
    result = asyncio.run(main.generate_edit_workspace_image(payload('camera', editWorkspaceCamera=camera)))
    assert result['ok']
    assert len(calls) == 1
    assert result['provider'] == 'openai'
    assert result['provider_model'] == 'gpt-image-2.5-sunburst'
    data = calls[0]
    assert set(data) == {'model', 'prompt', 'size', 'quality', 'n', 'output_format'}
    assert data['model'] == 'gpt-image-2.5-sunburst'
    assert data['quality'] == 'high' and data['n'] == '1' and data['output_format'] == 'png'
    assert data['size'] == edit.output_size((64, 48))
    text = data['prompt']
    scene_prompt, coordinate_prompt, position = text.rsplit('\n\n', 2)
    assert scene_prompt.startswith('Reconstruct the input image as the exact same frozen three-dimensional scene')
    assert 'ONLY THE CAMERA MAY MOVE. The entire scene must remain fixed in world space.' in scene_prompt
    assert "head orientation, facial direction, and gaze vector in world space" in scene_prompt
    assert 'Never duplicate, replace, relocate, redesign, or independently rotate an element' in scene_prompt
    assert 'preserving the same world-space geometry and lighting configuration' in scene_prompt
    assert scene_prompt.endswith('photograph of the exact same frozen scene taken from the requested new camera position.')
    assert 'Camera position:' not in scene_prompt
    assert coordinate_prompt == edit.CAMERA_COORDINATE_PROMPT
    assert 'Azimuth 0° = the exact original camera viewpoint.' in coordinate_prompt
    assert 'Azimuth 180° = camera moved to the exact opposite side of the frozen scene, producing the exact rear viewpoint.' in coordinate_prompt
    assert 'These angles describe the camera position around the unchanged world, never the rotation of the scene or its contents.' in coordinate_prompt
    assert position == (f"Camera position: azimuth {camera['horizontal']:g}°, "
                        f"elevation {camera['vertical']:g}°, zoom {camera['zoom']:g}/10.\n"
                        f"Semantic viewpoint: {edit.camera_semantic_viewpoint(camera['horizontal'])}.")
    assert result['edit_camera'] == camera
    assert result['camera_prompt'] == text
    assert 'UNRELATED' not in str(data) and 'IGNORE COMPOSER' not in str(data) and 'Make it blue' not in text
    assert 'test-openai-camera-key' not in capsys.readouterr().out


@pytest.mark.parametrize(('horizontal', 'semantic'), [
    (0, 'exact original camera viewpoint'),
    (360, 'exact original camera viewpoint'),
    (45, 'front-right three-quarter view'),
    (90, 'exact right-side view'),
    (135, 'rear-right three-quarter view'),
    (180, 'exact rear view'),
    (225, 'rear-left three-quarter view'),
    (270, 'exact left-side view'),
    (315, 'front-left three-quarter view'),
])
def test_camera_semantic_viewpoint_maps_absolute_azimuth(horizontal, semantic):
    assert edit.camera_semantic_viewpoint(horizontal) == semantic


@pytest.mark.parametrize(('horizontal', 'quadrant'), [
    (0.1, 'front-right'), (22.5, 'front-right'), (89.9, 'front-right'),
    (90.1, 'rear-right'), (150, 'rear-right'), (157.5, 'rear-right'),
    (170, 'rear-right'), (179.9, 'rear-right'),
    (180.1, 'rear-left'), (202.5, 'rear-left'), (220, 'rear-left'), (269.9, 'rear-left'),
    (270.1, 'front-left'), (337.5, 'front-left'), (359.9, 'front-left'),
])
def test_intermediate_camera_azimuth_is_not_rounded_to_an_exact_view(provider, horizontal, quadrant):
    camera = {'horizontal': horizontal, 'vertical': 0, 'zoom': 5}
    result = asyncio.run(main.generate_edit_workspace_image(payload('camera', editWorkspaceCamera=camera)))
    assert result['ok']
    prompt = provider[0][0][1]['data']['prompt']
    position, semantic = prompt.rsplit('\n', 2)[-2:]
    assert position == f'Camera position: azimuth {horizontal:g}°, elevation 0°, zoom 5/10.'
    assert semantic.startswith(f'Semantic viewpoint: {quadrant} oblique view at {horizontal:g}° azimuth')
    assert 'do not snap to another angle' in semantic
    assert 'exact' not in semantic and 'three-quarter' not in semantic
    assert result['edit_camera'] == camera and result['camera_prompt'] == prompt


@pytest.mark.parametrize('mode', ['camera', 'lighting'])
def test_camera_and_lighting_without_openai_key_do_not_use_other_provider_keys(monkeypatch, provider, mode):
    monkeypatch.setattr(main, 'OPENAI_API_KEY', '')
    monkeypatch.setenv('QWEN_API_KEY', 'unrelated-key')
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'unrelated-key')
    monkeypatch.setattr(main, 'FAL_API_KEY', 'unrelated-key')
    result = asyncio.run(main.generate_edit_workspace_image(payload(mode)))
    assert not result['ok']
    assert not provider[0]


@pytest.mark.parametrize('status', [200, 401, 429, 500])
@pytest.mark.parametrize('mode', ['camera', 'lighting'])
def test_camera_and_lighting_failed_or_empty_sunburst_response_never_falls_back(monkeypatch, provider, status, mode):
    calls = []
    def post(url, **kw):
        calls.append(url)
        response = Response({} if status == 200 else {'error': {'code': 'TestError', 'message': 'Request failed'}})
        response.status_code = status
        return response
    monkeypatch.setattr(main.requests, 'post', post)
    result = asyncio.run(main.generate_edit_workspace_image(payload(mode)))
    assert not result['ok']
    assert calls == [f'{main.OPENAI_API_BASE}/images/edits']


@pytest.mark.parametrize(('provider_name', 'model'), [
    ('fal', 'qwen_image_edit_2511_multiple_angles'), ('qwen', 'qwen-image-3.0-pro'),
    ('fal', 'iclight_v2'),
    ('openai', 'gpt_image_2_5_sunburst'),
])
@pytest.mark.parametrize('mode', ['camera', 'lighting'])
def test_camera_and_lighting_worker_uses_openai_slot_even_for_legacy_jobs(mode, provider_name, model):
    assert main.resolve_prostudio_provider_for_slot(
        payload(mode), 'image', model, provider_name) == 'OPENAI'


@pytest.mark.parametrize(('provider_name', 'model'), [
    ('fal', 'qwen_image_edit_2511_multiple_angles'), ('qwen', 'qwen-image-3.0-pro'),
    ('fal', 'iclight_v2'),
    ('openai', 'gpt_image_2_5_sunburst'),
])
@pytest.mark.parametrize('mode', ['camera', 'lighting'])
def test_camera_and_lighting_route_stores_sunburst_in_job_and_price_snapshot(monkeypatch, provider_name, model, mode):
    request_payload = payload(mode)
    request_payload.update(telegram_id=10, provider=provider_name, model=model)
    class Request:
        async def json(self):
            return request_payload
    recorded = []
    monkeypatch.setattr(main, 'get_user_state', lambda uid: {'balance': 100, 'subscription_status': 'active'})
    monkeypatch.setattr(main, 'get_active_prostudio_job', lambda uid: {})
    monkeypatch.setattr(main, 'create_prostudio_generation_job', lambda p: recorded.append(p) or 'camera-test')
    monkeypatch.setattr(main, 'log_user_event', lambda *a, **kw: None)
    result = asyncio.run(main.public_prostudio_generate(Request()))
    assert result['status'] == 'queued'
    job, = recorded
    assert job['provider'] == job['price_snapshot']['parameters']['provider'] == 'openai'
    assert job['model'] == job['price_snapshot']['parameters']['model'] == 'gpt_image_2_5_sunburst'
    assert job['price_snapshot']['final_credits'] == main.calculate_generation_price(payload('edit'))['credits'] > 0


def test_lighting_exact_sources_reach_sunburst_and_saved_result(monkeypatch, provider, capsys):
    monkeypatch.setattr(main, 'OPENAI_API_KEY', 'test-openai-lighting-key')
    monkeypatch.setattr(main, 'FAL_API_KEY', '')
    monkeypatch.setattr(main.requests, 'get', lambda *a, **kw: pytest.fail('Sunburst lighting must not poll another provider'))
    lighting = {'coordinateSystem': 'spherical-degrees', 'active': 2, 'layers': [
        {'horizontal': 217.4, 'vertical': -38.2, 'brightness': 1.7, 'color': '#6633cc', 'enabled': True},
        {'horizontal': 45, 'vertical': 20, 'brightness': .6, 'color': '#aabbcc', 'enabled': True},
        {'horizontal': 90, 'vertical': 0, 'brightness': 2, 'color': '#ff0000', 'enabled': False},
        {'horizontal': 270, 'vertical': 0, 'brightness': 0, 'color': '#00ff00', 'enabled': True},
    ]}
    result = asyncio.run(main.generate_edit_workspace_image(payload('lighting', editWorkspaceLight=lighting)))
    assert result['ok']
    assert result['provider'] == 'openai' and result['provider_model'] == 'gpt-image-2.5-sunburst'
    (url, call), = provider[0]
    assert url == f'{main.OPENAI_API_BASE}/images/edits'
    assert call['headers']['Authorization'] == 'Bearer test-openai-lighting-key'
    assert 'Content-Type' not in call['headers'] and 'json' not in call
    assert call['files'] == [('image', ('source.png', image_bytes(), 'image/png'))]
    data = call['data']
    assert set(data) == {'model', 'prompt', 'size', 'quality', 'n', 'output_format'}
    assert data['model'] == 'gpt-image-2.5-sunburst'
    assert data['quality'] == 'high' and data['n'] == '1' and data['output_format'] == 'png'
    assert '2 light source(s)' in data['prompt']
    assert 'azimuth 217.4 degrees (back-left)' in data['prompt']
    assert 'elevation -38.2 degrees' in data['prompt'] and 'brightness 1.7/2' in data['prompt']
    assert '#aabbcc' in data['prompt'] and '#6633cc' in data['prompt']
    assert '#ff0000' not in data['prompt'] and '#00ff00' not in data['prompt']
    assert 'Change only illumination and shadows.' in data['prompt']
    assert result['edit_lighting']['layers'] == lighting['layers']
    assert result['lighting_prompt'] == data['prompt']
    assert data['size'] == edit.output_size((64, 48))
    assert 'UNRELATED' not in str(call) and 'IGNORE COMPOSER' not in str(data) and 'Make it blue' not in data['prompt']
    assert 'test-openai-lighting-key' not in capsys.readouterr().out


@pytest.mark.parametrize(('horizontal', 'vertical'), [
    (0, 0), (360, 0), (90, 0), (270, 0),
    (180, 0), (180, 90), (45, -90), (270, 80),
])
def test_lighting_orbit_angles_reach_sunburst_without_coarse_hints(provider, horizontal, vertical):
    result = asyncio.run(main.generate_edit_workspace_image(payload('lighting', editWorkspaceLight={
        'coordinateSystem': 'spherical-degrees', 'layers': [{'horizontal': horizontal, 'vertical': vertical}]})))
    assert result['ok']
    prompt = provider[0][0][1]['data']['prompt']
    assert f'azimuth {horizontal} degrees' in prompt and f'elevation {vertical} degrees' in prompt


@pytest.mark.parametrize('settings', [
    {'coordinateSystem': []}, {'coordinateSystem': 'unknown'},
    *[{'coordinateSystem': 'spherical-degrees', 'layers': [layer]} for layer in [
        {'horizontal': -1}, {'horizontal': 361}, {'vertical': -91}, {'vertical': 91},
        {'horizontal': float('nan')}, {'brightness': float('inf')}, {'color': '#bad'}, {'brightness': 0},
    ]],
])
def test_invalid_light_settings_rejected_before_provider(provider, settings):
    result = asyncio.run(main.generate_edit_workspace_image(payload('lighting', editWorkspaceLight=settings)))
    assert not result['ok'] and not provider[0]


def test_lighting_legacy_controls_remain_supported():
    lighting = edit.lighting_parameters({'horizontal': -100, 'vertical': 100, 'brightness': None})
    assert lighting['layers'][0] == {'horizontal': 270, 'vertical': 90, 'brightness': 1, 'color': '#ffffff', 'enabled': True}
    assert 'azimuth 270 degrees (left), elevation 90 degrees' in edit.lighting_prompt(lighting)
