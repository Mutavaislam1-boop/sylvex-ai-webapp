"""Targeted persistence regression: fake download/storage, real image verification, no network/DB."""
import ast,functools,io,mimetypes,os,pathlib,tempfile,types,unittest,uuid,urllib.parse
from PIL import Image
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=pathlib.Path(os.environ.get('SYLVEX_PERSIST_SOURCE',str(ROOT/'main.py')))
SAFE_IO=pathlib.Path(os.environ.get('SYLVEX_SAFE_IO_SOURCE',str(ROOT/'services/safe_io.py')))

@functools.lru_cache(maxsize=None)
def function(path,name):
    node=next(n for n in ast.parse(path.read_text()).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))and n.name==name)
    return ast.Module(body=[node],type_ignores=[])

class ValidationError(Exception):pass

def image(fmt):
    out=io.BytesIO();Image.new('RGB',(3,2),(10,20,30)).save(out,format=fmt);return out.getvalue()

class PersistenceTypeTests(unittest.TestCase):
    def exercise(self,content,headers,category='images',url='https://provider.example.invalid/output.jpeg',compatibility=False):
        calls=[];downloads=[];errors=[]
        validator={'Path':pathlib.Path,'mimetypes':mimetypes,'SecurityError':ValidationError}
        exec(compile(function(SAFE_IO,'validated_upload_path'),str(SAFE_IO),'exec'),validator)
        def download(source,target,timeout):
            downloads.append(source);pathlib.Path(target).write_bytes(content);return {'headers':headers,'url':source}
        def put_file(path,key,mime,remove_local=False):
            calls.append((key,mime,pathlib.Path(path).read_bytes(),'file'));return 'https://owned.example.invalid/output'
        def put_bytes(data,key,mime):
            calls.append((key,mime,data,'bytes'));return 'https://owned.example.invalid/output'
        default_get=object()
        def fake_get(source,timeout):
            downloads.append(source);return types.SimpleNamespace(headers=headers,url=source,content=content,raise_for_status=lambda:None)
        env={'pathlib':pathlib,'tempfile':tempfile,'mimetypes':mimetypes,'urllib':urllib,'uuid4':uuid.uuid4,'WEBAPP_DIR':pathlib.Path('/unused'),'_DEFAULT_SAFE_GET':default_get,'safe_get':fake_get if compatibility else default_get,'safe_download_to_file':download,'storage_key_from_url':lambda value:'generated/images/existing.jpeg'if value.startswith('https://owned.example.invalid/')else'','generated_key':lambda cat,name:'generated/'+cat+'/'+name,'storage_put_file':put_file,'storage_put_bytes':put_bytes,'r2_enabled':lambda:True,'prostudio_debug':lambda *args,**kwargs:None,'prostudio_error':lambda *args,**kwargs:errors.append(args[0]),'_sql_text':lambda value,limit:value[:limit],'validated_upload_path':validator['validated_upload_path'],'SecurityError':ValidationError}
        exec(compile(function(SOURCE,'_persist_remote_media_url'),str(SOURCE),'exec'),env)
        result=env['_persist_remote_media_url'](url,category,'fake-provider')
        return calls,downloads,errors,result

    def test_generic_jpeg_is_stored_as_actual_image(self):
        data=image('JPEG');calls,_,errors,_=self.exercise(data,{'content-type':'application/octet-stream'})
        self.assertFalse(errors);self.assertEqual(calls[0][1],'image/jpeg');self.assertEqual(calls[0][2],data)

    def test_missing_png_header_uses_verified_bytes(self):
        data=image('PNG');calls,_,errors,_=self.exercise(data,{},url='https://provider.example.invalid/output.png')
        self.assertFalse(errors);self.assertEqual(calls[0][1],'image/png');self.assertEqual(calls[0][2],data)

    def test_compatibility_bytes_branch_keeps_same_fix(self):
        data=image('JPEG');calls,_,errors,_=self.exercise(data,{'content-type':'application/octet-stream'},compatibility=True)
        self.assertFalse(errors);self.assertEqual(calls[0][1],'image/jpeg');self.assertEqual(calls[0][2],data);self.assertEqual(calls[0][3],'bytes')

    def test_declared_image_type_unchanged(self):
        calls,_,errors,_=self.exercise(image('JPEG'),{'content-type':'image/jpeg'})
        self.assertFalse(errors);self.assertEqual(calls[0][1],'image/jpeg')

    def test_video_mime_unchanged(self):
        calls,_,errors,_=self.exercise(b'fake-video',{'content-type':'application/octet-stream'},'videos','https://provider.example.invalid/output.mp4')
        self.assertFalse(errors);self.assertEqual(calls[0][1],'application/octet-stream')

    def test_audio_mime_unchanged(self):
        calls,_,errors,_=self.exercise(b'fake-audio',{'content-type':'audio/mpeg'},'audio','https://provider.example.invalid/output.mp3')
        self.assertFalse(errors);self.assertEqual(calls[0][1],'audio/mpeg')

    def test_invalid_generic_image_is_not_relabelled(self):
        # Exercise the decoder failure branch without loading unrelated native plugins.
        with patch('PIL.Image.open',side_effect=OSError('invalid image')):
            calls,_,errors,_=self.exercise(b'<html>not an image</html>',{'content-type':'application/octet-stream'})
        self.assertFalse(errors);self.assertEqual(calls[0][1],'application/octet-stream')

    def test_other_declared_mime_unchanged(self):
        calls,_,errors,_=self.exercise(image('JPEG'),{'content-type':'application/pdf'})
        self.assertFalse(errors);self.assertEqual(calls[0][1],'application/pdf')

    def test_existing_owned_media_is_not_rewritten(self):
        calls,downloads,errors,result=self.exercise(image('JPEG'),{'content-type':'application/octet-stream'},url='https://owned.example.invalid/existing.jpeg')
        self.assertEqual(calls,[]);self.assertEqual(downloads,[]);self.assertFalse(errors);self.assertEqual(result,'https://owned.example.invalid/existing.jpeg')

    def test_unknown_extension_unchanged(self):
        calls,_,errors,_=self.exercise(image('JPEG'),{'content-type':'application/octet-stream'},url='https://provider.example.invalid/output.bin')
        self.assertFalse(errors);self.assertEqual(calls[0][1],'application/octet-stream')

if __name__=='__main__':unittest.main()
