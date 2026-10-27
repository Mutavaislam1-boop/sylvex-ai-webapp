"""Client draft codec -> existing API media signer -> client restoration.

No HTTP, database or provider calls. The S3 SDK only builds a presigned URL
with explicit dummy credentials, matching direct production delivery.
"""
import json
import subprocess
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]


def decode_in_client(value):
    script="""
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('webapp/js/cabinet.js','utf8');
const a=source.indexOf('  const composerDraftInitialStates'),b=source.indexOf('  async function saveVisualItemToBackend(',a);
const context=vm.createContext({imageState:{},videoState:{},musicState:{},voiceState:{},textState:{},input:JSON.parse(fs.readFileSync(0,'utf8'))});
vm.runInContext(source.slice(a,b),context);
process.stdout.write(JSON.stringify(vm.runInContext('decodeComposerDraft(input)',context)));
"""
    result=subprocess.run(['node','-e',script],cwd=ROOT,input=json.dumps(value),text=True,capture_output=True,check=True)
    return json.loads(result.stdout)


@pytest.mark.parametrize('direct',[False,True])
def test_existing_signer_refreshes_every_draft_reference_and_its_source_map(monkeypatch,direct):
    from services import media_access,storage
    monkeypatch.setenv('BOT_TOKEN','dummy-contract-signing-key')
    monkeypatch.setenv('WEBAPP_URL','https://webapp.test')
    monkeypatch.setenv('R2_ENDPOINT','https://account.r2.cloudflarestorage.com')
    monkeypatch.setenv('R2_BUCKET','dummy-media')
    if direct:
        import boto3
        from botocore.config import Config
        client=boto3.client('s3',endpoint_url='https://account.r2.cloudflarestorage.com',region_name='auto',
                            aws_access_key_id='dummy-access',aws_secret_access_key='dummy-secret',config=Config(signature_version='s3v4'))
        monkeypatch.setattr(storage,'presigned_get_url',lambda key,expires_in:client.generate_presigned_url('get_object',Params={'Bucket':'dummy-media','Key':key},ExpiresIn=expires_in))
    else:
        monkeypatch.setattr(storage,'presigned_get_url',lambda *a,**kw:'')
    old=[f'https://webapp.test/api/public/storage/generated/references/{name}.png?media_exp=1&media_sig=expired' for name in ['one','two','three','four']]
    state={
        'modelId':'seedream_5_0_lite',
        'uploadedImageUrls':[{'__sylvex_draft_media_v1':True,'url':url} for url in old],
        'referenceSourceByUrl':{'__sylvex_draft_sources_v1':True,'items':[{'url':url,'source':'history'} for url in old]},
    }
    signed=media_access.sign_response_media({'attachment':{'composer_draft':{'version':1,'mode':'image','state':state}}})
    restored=decode_in_client(signed['attachment']['composer_draft']['state'])
    assert len(restored['uploadedImageUrls'])==4
    assert all(media_access.valid_media_url(url) for url in restored['uploadedImageUrls'])
    assert all(restored['referenceSourceByUrl'][url]=='history' for url in restored['uploadedImageUrls'])
    assert all(url not in old for url in restored['uploadedImageUrls'])
    media_access.validate_input_media({'image_options':restored})
    if direct:
        assert all('X-Amz-Signature=' in url and '#media_exp=' in url for url in restored['uploadedImageUrls'])
