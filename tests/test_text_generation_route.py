"""Admission registers durable jobs without running providers in the HTTP request."""
import asyncio
from types import SimpleNamespace
import unittest

from test_generation_lifecycle import functions


class AdmissionTests(unittest.IsolatedAsyncioTestCase):
    def endpoint(self, create):
        class SecurityError(Exception):
            pass
        class ActiveJobError(Exception):
            pass
        return functions('main.py', {'public_prostudio_generate'},
            asyncio=asyncio, TEXT_ATTACHMENT_BYTES_KEY='_attachment_bytes',
            grid_references_service=SimpleNamespace(resolve_grid_catalog_references=lambda *args:0),
            WEBAPP_URL='https://synthetic', normalize_grid_video_request=lambda _:None,
            _core_account_owner=lambda request,payload:42, _json_list=lambda value:value or [],
            model_control=SimpleNamespace(norm=lambda value:value),_disabled_model_ids=lambda:[],
            get_user_state=lambda _: {'subscription_status':'active','balance':1000},
            text_media_attachment=lambda _:False,text_output_cap=lambda _:100,
            video_editor_request=lambda _:False,is_enhance_video_request=lambda _:False,
            calculate_generation_price=lambda _: {'credits':1,'pricing_available':True,'price_snapshot':{'final_credits':1}},
            is_internal_ui_model=lambda _:False,PROSTUDIO_WORKER_ENABLED=True,
            prostudio_debug=lambda *args,**kwargs:None,log_user_event=lambda *args:None,
            create_prostudio_generation_job=create,SecurityError=SecurityError,ActiveProstudioJobError=ActiveJobError,
            JSONResponse=lambda data,status_code:SimpleNamespace(data=data,status_code=status_code))

    async def test_text_is_registered_in_same_queue_before_http_response(self):
        created=[]
        endpoint=self.endpoint(lambda payload:created.append(payload) or 'durable-job')
        async def payload(): return {'mode':'text','model':'gpt-5.5','prompt':'hello','telegram_id':42,'client_request_id':'same-request'}
        response=await endpoint.public_prostudio_generate(SimpleNamespace(json=payload,state=SimpleNamespace()))
        self.assertEqual(response,{'ok':True,'job_id':'durable-job','generation_id':'durable-job','status':'queued'})
        self.assertEqual(created[0]['client_request_id'],'same-request')
        self.assertTrue(created[0]['skip_telegram'])
        self.assertEqual(created[0]['price_snapshot']['final_credits'],1)

    async def test_video_missing_required_prompt_is_rejected_before_reservation_or_dispatch(self):
        created=[]
        endpoint=self.endpoint(lambda payload:created.append(payload))
        async def payload(): return {'mode':'video','model':'kling','prompt':'','telegram_id':42,'video_options':{'input_video':'already-uploaded'}}
        response=await endpoint.public_prostudio_generate(SimpleNamespace(json=payload,state=SimpleNamespace()))
        self.assertEqual(response.status_code,400);self.assertEqual(response.data['error'],'prompt_required')
        self.assertFalse(created)


if __name__ == '__main__':
    unittest.main()
