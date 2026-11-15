"""Retired Kling effects: real functions, synthetic files, no DB/provider calls."""
import ast
import json
import os
import sys
import types
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pytest

ROOT = Path(os.environ.get('SYLVEX_TEST_SOURCE_ROOT', Path(__file__).resolve().parents[1]))
MAIN = (ROOT / 'main.py').read_text()
ROUTER = (ROOT / 'services/video_router.py').read_text()


@lru_cache(maxsize=2)
def tree(source):
    return ast.parse(source)


def function(source, name, namespace):
    node = next(n for n in tree(source).body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<target source>', 'exec'), namespace)
    return namespace[name]


@pytest.fixture
def target(tmp_path, monkeypatch):
    catalog = types.ModuleType('services.catalog_video')
    catalog.is_catalog_video_edit = lambda opts: False
    services = types.ModuleType('services')
    services.__path__ = []
    monkeypatch.setitem(sys.modules, 'services', services)
    monkeypatch.setitem(sys.modules, 'services.catalog_video', catalog)
    ns = {'Optional': Optional, 'json': json, 'WEBAPP_DIR': tmp_path,
          'VIDEO_MODEL_CONFIG': {'kling_effects': {'provider': 'kling'},
                                 'kling_o3_omni': {'provider': 'kling'},
                                 'runway_gen4_5': {'provider': 'runway'}},
          'model_capabilities_service': types.SimpleNamespace(
              video_character_object_visual_reference_supported=lambda _: {'character': True, 'object': True},
              video_frame_support=lambda _: {'start_frame': True, 'end_frame': True},
              video_reference_input_error=lambda *a, **k: None),
          'prostudio_error': lambda *a, **k: pytest.fail('Unexpected catalog error'),
          '_provider_error': lambda provider, model, error: {'ok': False, 'provider': provider, 'model': model, 'error': error}}
    # Baseline mode exercises the original validation/catalog/provider entry.
    # A missing new helper behaves as the old code (no availability check).
    try:
        node = next(n for n in tree(ROUTER).body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'KLING_OFFLINE_EFFECT_SCENES' for t in n.targets))
    except StopIteration:
        ns['KLING_OFFLINE_EFFECT_SCENES'] = frozenset()
        ns['kling_offline_effect_scene'] = lambda *a: ''
    else:
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<target source>', 'exec'), ns)
        function(ROUTER, 'kling_offline_effect_scene', ns)
    ns['_KLING_OFFLINE_EFFECT_SCENES'] = ns['KLING_OFFLINE_EFFECT_SCENES']
    for source, name in [(MAIN, 'validate_video_feature_request'),
                         (MAIN, 'prostudio_kling_effects_library'),
                         (ROUTER, '_call_kling')]:
        function(source, name, ns)
    return ns, tmp_path


@pytest.mark.parametrize('scene', ['hug', 'kiss'])
@pytest.mark.parametrize('shape', ['direct', 'template', 'motion_preset', 'options_alias'])
def test_stale_client_request_is_rejected_before_media_and_pricing(target, scene, shape):
    ns, _ = target
    opts = {'model': 'kling_effects'}
    if shape == 'template':
        opts['video_template'] = {'effect_scene': scene, 'catalog_type': 'kling_effect'}
    elif shape == 'motion_preset':
        opts['motion_preset'] = scene
    else:
        opts['effect_scene'] = scene
    payload = {'mode': 'video', 'video_options' if shape != 'options_alias' else 'options': opts}
    error = ns['validate_video_feature_request'](payload)
    assert error and error['ok'] is False
    assert error['code'] == 'kling_effect_unavailable'
    assert error['model'] == 'kling_effects'


@pytest.mark.parametrize('scene', ['hug', 'kiss'])
@pytest.mark.parametrize('model,flags', [
    ('kling_effects', {}), ('kling_o3_omni', {'video_effects': True}),
    ('kling_o3_omni', {'generation_mode': 'video_effects'})])
def test_direct_or_alternate_adapter_path_never_reaches_credentials_or_network(target, scene, model, flags):
    ns, _ = target
    def forbidden(*args, **kwargs):
        pytest.fail('Retired effect reached the old provider submission path')
    ns['_get_env'] = forbidden
    ns['_request_json'] = forbidden
    result = ns['_call_kling'](model, 'synthetic prompt', {'video_options': {**flags, 'effect_scene': scene}})
    assert result['ok'] is False and result['provider'] == 'kling'


def test_catalog_filters_retired_effects_and_preserves_other_entries(target):
    ns, root = target
    p = root / 'providers/kling/effects/effects.json'
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({'effects': [
        {'id': 'hug', 'cost_credits': 95}, {'id': 'kiss', 'cost_credits': 95},
        {'id': 'fuzzyfuzzy', 'name': 'Fuzzy Fuzzy', 'duration': 5, 'cost_credits': 95},
        {'id': 'heart_gesture', 'input_count': 2, 'cost_credits': 95}]}))
    entries = ns['prostudio_kling_effects_library']()
    assert [x['id'] for x in entries] == ['fuzzyfuzzy', 'heart_gesture']
    assert entries[0]['cost_credits'] == 95 and entries[0]['duration'] == 5
    assert entries[1]['input_count'] == 2


@pytest.mark.parametrize('model,opts', [
    ('kling_effects', {'effect_scene': 'fuzzyfuzzy'}),
    ('kling_effects', {'effect_scene': 'heart_gesture'}),
    ('kling_o3_omni', {'mode': 'image_to_video', 'start_image': 'https://example.test/fixture.png', 'effect_scene': 'hug'}),
    ('kling_o3_omni', {'mode': 'motion_control', 'reference_video': 'https://example.test/fixture.mp4'}),
    ('runway_gen4_5', {'mode': 'video_effects', 'effect_scene': 'hug'})])
def test_working_effects_omni_motion_and_other_providers_remain_admitted(target, model, opts):
    ns, _ = target
    payload = {'mode': 'video', 'video_options': {'model': model, **opts}}
    assert ns['kling_offline_effect_scene'](model, payload) == ''
    assert ns['validate_video_feature_request'](payload) is None


def test_unaffected_kling_submission_enters_original_path(target):
    ns, _ = target
    class OriginalPathReached(Exception):
        pass
    def marker(*args):
        raise OriginalPathReached
    ns['_get_env'] = marker
    with pytest.raises(OriginalPathReached):
        ns['_call_kling']('kling_effects', 'fixture', {'video_options': {'effect_scene': 'fuzzyfuzzy'}})


def test_retired_selection_does_not_mutate_the_request(target):
    ns, _ = target
    payload = {'mode': 'video', 'video_options': {'model': 'kling_effects', 'effect_scene': ' hug '}}
    before = json.dumps(payload)
    assert ns['validate_video_feature_request'](payload)['code'] == 'kling_effect_unavailable'
    assert json.dumps(payload) == before
