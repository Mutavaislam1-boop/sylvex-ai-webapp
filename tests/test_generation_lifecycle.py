"""Focused lifecycle checks with synthetic providers; no DB or paid requests."""
import __future__
import ast
import asyncio
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def functions(path, names, **namespace):
    tree = ast.parse((ROOT / path).read_text())
    selected = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    for node in selected:
        node.decorator_list = []
    exec(compile(ast.Module(body=selected, type_ignores=[]), path, 'exec', flags=__future__.annotations.compiler_flag), namespace)
    return SimpleNamespace(**namespace)


class JobLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_job_survives_former_runtime_limit(self):
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def provider(job_id, payload):
            entered.set()
            await release.wait()
            calls.append(job_id)

        api = functions('main.py', {'run_prostudio_generation'}, process_prostudio_generation=provider)
        task = asyncio.create_task(api.run_prostudio_generation('same-job', {}))
        await entered.wait()
        await asyncio.sleep(.025)
        self.assertFalse(task.done())
        release.set()
        await asyncio.wait_for(task, 1)
        self.assertEqual(calls, ['same-job'])

    async def test_expired_legacy_wait_and_network_failures_do_not_discard_result(self):
        outcomes = iter([None] * 6 + [{'ok': True, 'status': 'completed', 'video_url': 'synthetic'}])
        saved = {'provider': 'kling', 'task_id': 'provider-original', 'background_wait': {'deadline': 0, 'poll_failures': 99}}
        failures, completed, updates, refs = [], [], [], []

        async def poll(ref):
            refs.append(ref['task_id'])
            return next(outcomes)

        async def off_loop(factory):
            return await factory()

        async def fail(*args):
            failures.append(args)

        def complete(*args):
            completed.append(args)
            return {'completed': True}

        api = functions('main.py', {'collect_provider_background_waits'},
            asyncio=asyncio, time=SimpleNamespace(time=lambda: 10**12),
            claim_background_wait_job=lambda: {'job_id': 'original', 'result': saved, 'payload': {}, 'telegram_id': 1, 'mode': 'video'},
            run_provider_coroutine_off_loop=off_loop, poll_video_generation=poll,
            prostudio_error=lambda *a, **k: None, _fail_background_wait=fail,
            generation_has_completed_result=lambda result, mode: bool(result.get('video_url')),
            complete_background_provider_job=complete,
            update_background_wait=lambda *a, **kw: updates.append(kw),
            classify_provider_failure=lambda result: SimpleNamespace(transient=False),
            PROSTUDIO_LATE_RESULT_POLL_SECONDS=60)
        self.assertEqual(await api.collect_provider_background_waits(limit=7), 1)
        self.assertFalse(failures)
        self.assertEqual(len(completed), 1)
        self.assertEqual(refs, ['provider-original'] * 7)
        self.assertEqual(len(updates), 6)

    async def test_legacy_late_result_survives_old_expiry_and_repeated_read_failures(self):
        updates, delivered = [], []
        outcomes = iter([None] * 6 + [{'ok':True,'status':'completed','video_url':'saved'}])
        async def poll(ref):
            self.assertEqual(ref['task_id'],'original-provider-task')
            return next(outcomes)
        async def off_loop(factory): return await factory()
        async def deliver(job_id): delivered.append(job_id)
        api = functions('main.py', {'collect_late_provider_results'}, asyncio=asyncio,
            time=SimpleNamespace(time=lambda:10**12),
            claim_late_result_jobs=lambda _: [{'job_id':'original','watch':{'provider_ref':{'task_id':'original-provider-task'},'expires_at':0,'poll_failures':99}}],
            poll_video_generation=poll,run_provider_coroutine_off_loop=off_loop,
            generation_has_completed_result=lambda result, mode: bool(result.get('video_url')),
            deliver_late_provider_result=lambda *args:True,deliver_pending_prostudio_job=deliver,
            generation_storage=SimpleNamespace(media_plan=lambda *args:[]),build_completed_job_result=lambda *args:{},
            update_late_result_watch=lambda *args, **kwargs:updates.append(kwargs),
            classify_provider_failure=lambda _:SimpleNamespace(transient=False),PROSTUDIO_LATE_RESULT_POLL_SECONDS=60,
            prostudio_error=lambda *args, **kwargs:None)
        self.assertEqual(await api.collect_late_provider_results(limit=7),1)
        self.assertEqual(delivered,['original']);self.assertEqual(len(updates),6)
        self.assertTrue(all(not update['done'] for update in updates))

    async def test_explicit_provider_failure_is_terminal(self):
        failures = []

        async def poll(ref):
            return {'ok': False, 'status': 'failed', 'error': 'confirmed provider failure'}

        async def off_loop(factory):
            return await factory()

        async def fail(*args):
            failures.append(args)

        api = functions('main.py', {'collect_provider_background_waits'}, asyncio=asyncio,
            claim_background_wait_job=lambda: {'job_id':'j','result':{'task_id':'p'},'payload':{},'telegram_id':1,'mode':'video'},
            run_provider_coroutine_off_loop=off_loop, poll_video_generation=poll,
            _fail_background_wait=fail,
            classify_provider_failure=lambda _: SimpleNamespace(transient=False))
        self.assertEqual(await api.collect_provider_background_waits(limit=1), 1)
        self.assertEqual(len(failures), 1)

    async def test_failed_delivery_keeps_retry_and_successful_delivery_acknowledges(self):
        for successful in (False, True):
            acknowledged = []

            async def deliver(*args):
                return successful

            api = functions('main.py', {'deliver_pending_prostudio_job'}, asyncio=asyncio,
                claim_pending_prostudio_delivery=lambda _: {'payload':{},'result':{},'telegram_id':1,'mode':'image'},
                deliver_completed_prostudio_job=deliver,
                finish_prostudio_delivery=lambda *args: acknowledged.append(args),
                prostudio_error=lambda *a, **k: None)
            self.assertEqual(await api.deliver_pending_prostudio_job('original'), successful)
            self.assertEqual(acknowledged[0][0], 'original')
            self.assertEqual(acknowledged[0][2], successful)


class PayloadTests(unittest.TestCase):
    def test_omni_sound_matches_toggle_for_text_image_and_reference_video(self):
        api = functions('services/video_router.py', {'_kling_omni_settings'},
            _kling_model_family=lambda model: model,
            _kling_resolution=lambda value, allowed: value or '720p',
            _kling_duration=lambda value, allowed: value or 5,
            _kling_aspect_ratio=lambda value: value or '16:9')
        self.assertEqual(api._kling_omni_settings('kling-3.0-omni', {'sound':True})['audio'], 'native')
        self.assertEqual(api._kling_omni_settings('kling-3.0-omni', {'sound':False})['audio'], 'off')
        self.assertEqual(api._kling_omni_settings('kling-3.0-omni', {'sound':True}, has_video=True, base_video=True)['audio'], 'original')
        self.assertEqual(api._kling_omni_settings('kling-o1', {'sound':False})['audio'], 'off')

    def test_duplicate_scope_changes_with_model_and_tool(self):
        api = functions('main.py', {'generation_request_scope'})
        base = {'mode':'image','model':'one','image_options':{'tool':'edit'}}
        self.assertEqual(api.generation_request_scope(base), api.generation_request_scope(dict(base)))
        self.assertNotEqual(api.generation_request_scope(base), api.generation_request_scope(dict(base, model='two')))
        self.assertNotEqual(api.generation_request_scope(base), api.generation_request_scope(dict(base, image_options={'tool':'remove_object'})))

    def test_189_base_plus_reference_has_one_canonical_190_total(self):
        names = {'_as_list','_sources','_stable_asset_key','_unique_values','_selected_assets','_option','sylvex_additions','finalise_price'}
        api = functions('services/price_engine.py', names, Decimal=Decimal, ROUND_CEILING=ROUND_CEILING,
            is_free_resize=lambda _:False, STYLE_CREDITS=Decimal(1), CHARACTER_CREDITS=Decimal(1),
            OBJECT_CREDITS=Decimal(1), REFERENCE_CREDITS=Decimal(1), PRICE_VERSION='test')
        price = api.finalise_price(189, {'mode':'video','video_options':{'reference_images':['same'],'referenceImageUrls':['same']}})
        self.assertEqual(price['final_credits'],190)
        self.assertEqual(price['additions_credits'],1)

    def test_full_settled_price_is_preserved_in_result_and_metadata(self):
        api = functions('main.py', {'build_completed_job_result'}, generation_result_urls=lambda result, mode: result.get('videos') or [])
        result = api.build_completed_job_result({'ok':True,'videos':['synthetic'],'cost_credits':190,'generation_cost':'190 ⚡','metadata':{'cost_credits':189}}, 'video')
        self.assertEqual(result['cost_credits'], 190)
        self.assertEqual(result['metadata']['cost_credits'], 190)
        self.assertEqual(result['metadata']['generation_cost'], '190 ⚡')
        self.assertTrue(result['delivery_pending'])


class StatusReadTests(unittest.TestCase):
    def test_read_retries_transient_http_and_network_errors_without_resubmission(self):
        responses = iter([TimeoutError(), SimpleNamespace(status_code=503), SimpleNamespace(status_code=429), SimpleNamespace(status_code=200)])
        calls, sleeps = [], []
        def read():
            calls.append(1)
            result = next(responses)
            if isinstance(result, Exception): raise result
            return result
        api = functions('services/provider_polling.py', {'transient_status','transient_error','read_status'},
            requests=SimpleNamespace(Timeout=TimeoutError,ConnectionError=ConnectionError),
            httpx=SimpleNamespace(TransportError=OSError),time=SimpleNamespace(sleep=sleeps.append))
        self.assertEqual(api.read_status(read).status_code,200)
        self.assertEqual(len(calls),4)
        self.assertEqual(sleeps,[5,5,5])

    def test_r2_cors_is_verified_without_bucket_administration(self):
        import threading
        headers={'Access-Control-Allow-Origin':'https://sylvex.ai','Access-Control-Allow-Methods':'GET, HEAD, PUT'}
        api = functions('services/storage.py', {'ensure_direct_upload_cors'},
            _direct_upload_cors_ready=False,_direct_upload_cors_lock=threading.Lock(),
            direct_upload_enabled=lambda:True,_direct_upload_origins=lambda:['https://sylvex.ai'],
            R2_ENDPOINT='https://storage.invalid',R2_BUCKET='bucket',
            r2_client=lambda: self.fail('Object credentials must not administer CORS'))
        with patch('requests.options', return_value=SimpleNamespace(status_code=204,headers=headers)) as options:
            self.assertTrue(api.ensure_direct_upload_cors())
            self.assertEqual(options.call_args.kwargs['headers']['Access-Control-Request-Method'],'PUT')


if __name__ == '__main__':
    unittest.main()
