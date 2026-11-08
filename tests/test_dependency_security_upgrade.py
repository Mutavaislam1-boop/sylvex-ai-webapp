"""Offline compatibility of the security update with media and verified TLS."""
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import io,ipaddress,ssl,threading
import certifi,httpx,pytest,requests
from PIL import Image,ImageOps
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from services.safe_io import SecurityError,validated_upload_type,validated_upload_path


@pytest.mark.parametrize('fmt,mode,suffix,mime',[
 ('PNG','RGBA','.png','image/png'),('PNG','RGB','.png','image/png'),
 ('JPEG','RGB','.jpg','image/jpeg'),('JPEG','L','.jpeg','image/jpeg'),
 ('WEBP','RGBA','.webp','image/webp'),('WEBP','RGB','.webp','image/webp')])
def test_real_encoded_upload_round_trip(fmt,mode,suffix,mime,tmp_path):
 image=Image.new(mode,(32,24));data=io.BytesIO();image.save(data,format=fmt)
 raw=data.getvalue();path=tmp_path/('reference'+suffix);path.write_bytes(raw)
 assert validated_upload_type(raw,suffix)==mime
 assert validated_upload_path(path,suffix)==mime
 with Image.open(io.BytesIO(raw))as restored:
  restored.load();assert restored.size==(32,24)
  transformed=ImageOps.exif_transpose(restored).convert('RGB')
  transformed.thumbnail((16,16),Image.Resampling.LANCZOS)
  reference=io.BytesIO();transformed.save(reference,format='JPEG')
  assert validated_upload_type(reference.getvalue(),'.jpg')=='image/jpeg'


@pytest.mark.parametrize('raw',[b'<html>not an image</html>',b'II*\x00\x08\x00\x00\x00',b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'+b'\x00'*64])
def test_malformed_or_disguised_images_still_rejected(raw,tmp_path):
 path=tmp_path/'fake.png';path.write_bytes(raw)
 for invoke in [lambda:validated_upload_type(raw,'.png'),lambda:validated_upload_path(path,'.png')]:
  with pytest.raises(SecurityError):invoke()


@pytest.mark.parametrize('mode',['RGB','RGBA','L'])
def test_tiff_bytesio_save_load_is_stable(mode):
 # Exercise the changed TIFF writer without an exploit or large allocation.
 output=io.BytesIO();Image.new(mode,(64,48)).save(output,format='TIFF',compression='tiff_lzw')
 with Image.open(io.BytesIO(output.getvalue()))as restored:
  restored.load();assert restored.size==(64,48)and restored.mode==mode


def test_heif_plugin_abi_roundtrip_to_jpeg():
 import pillow_heif
 pillow_heif.register_heif_opener()
 out=io.BytesIO();Image.new('RGB',(64,64),color=(80,120,160)).save(out,format='HEIF',quality=90)
 with Image.open(io.BytesIO(out.getvalue()))as image:
  image.load();jpeg=io.BytesIO();image.convert('RGB').save(jpeg,format='JPEG')
 assert validated_upload_type(jpeg.getvalue(),'.jpg')=='image/jpeg'


def test_default_tls_bundle_removed_emsign_and_still_requires_verification():
 context=ssl.create_default_context(cafile=certifi.where())
 assert context.verify_mode==ssl.CERT_REQUIRED and context.check_hostname
 roots=context.get_ca_certs();assert len(roots)>50
 # 2026.10.19 restored unaffected roots; only the compromised G3 is barred.
 assert not any('emsign ecc root ca - g3'in repr(cert['subject']).lower()for cert in roots)
 assert requests.Session().verify is True


def test_encoded_image_reaches_real_r2_sdk_without_external_io(monkeypatch):
 from botocore.stub import Stubber
 import services.storage as storage
 for name,value in dict(R2_BUCKET='synthetic-bucket',R2_ENDPOINT='https://r2.invalid',
  R2_ACCESS_KEY_ID='synthetic-access',R2_SECRET_ACCESS_KEY='synthetic-secret',DATABASE_URL='',
  WEBAPP_URL='https://synthetic.invalid').items():monkeypatch.setattr(storage,name,value)
 storage.r2_client.cache_clear()
 try:
  client=storage.r2_client()
  assert client._endpoint.http_session._verify is not False
  out=io.BytesIO();Image.new('RGB',(16,16)).save(out,format='PNG');data=out.getvalue()
  expected=dict(Bucket='synthetic-bucket',Key='diagnostic.png',Body=data,ContentType='image/png',CacheControl='public, max-age=31536000, immutable')
  with Stubber(client)as stub:
   stub.add_response('put_object',{'ETag':'"synthetic"'},expected)
   assert storage.put_bytes(data,'diagnostic.png','image/png')
   stub.assert_no_pending_responses()
 finally:storage.r2_client.cache_clear()


@pytest.fixture
def tls_server(tmp_path):
 key=ec.generate_private_key(ec.SECP256R1());subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'SYLVEX synthetic TLS test')])
 now=datetime.now(timezone.utc)
 cert=(x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
  .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
  .add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True)
  .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False).sign(key,hashes.SHA256()))
 certfile=tmp_path/'synthetic-ca.pem';certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
 keyfile=tmp_path/'synthetic-key.pem';keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
 class Handler(BaseHTTPRequestHandler):
  def do_GET(self):self.send_response(200);self.end_headers();self.wfile.write(b'ok')
  def log_message(self,*args):pass
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
 context.load_cert_chain(certfile,keyfile);server.socket=context.wrap_socket(server.socket,server_side=True)
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:yield 'https://127.0.0.1:'+str(server.server_port),certfile
 finally:server.shutdown();server.server_close();thread.join(timeout=3)


@pytest.mark.parametrize('client',['requests','httpx'])
def test_https_rejects_untrusted_ca_and_accepts_explicit_trusted_ca(client,tls_server):
 url,ca=tls_server
 if client=='requests':
  with pytest.raises(requests.exceptions.SSLError):requests.get(url,timeout=3)
  assert requests.get(url,verify=str(ca),timeout=3).status_code==200
 else:
  with httpx.Client(trust_env=False,timeout=3)as session:
   with pytest.raises(httpx.ConnectError):session.get(url)
  with httpx.Client(verify=ssl.create_default_context(cafile=str(ca)),trust_env=False,timeout=3)as session:
   assert session.get(url).status_code==200
