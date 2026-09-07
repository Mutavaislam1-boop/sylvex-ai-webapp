"""Bind a provider-confirmed subscription to the authenticated application user."""
import hashlib
import hmac
import re
from services.security import signing_key,SecurityError

def make_binding(uid,plan):
 if not re.fullmatch(r'P-[A-Za-z0-9]+',plan):raise SecurityError('invalid_paypal_plan',400)
 payload=f'{int(uid)}:{plan}'
 sig=hmac.new(signing_key(),('paypal-owner:'+payload).encode(),hashlib.sha256).hexdigest()
 return payload+':'+sig

def read_binding(value,plan):
 try:
  uid,stored,sig=value.split(':')
  if stored!=plan or int(uid)<=0 or not hmac.compare_digest(make_binding(int(uid),plan),value):raise ValueError()
  return int(uid)
 except (ValueError,TypeError,AttributeError):raise SecurityError('paypal_owner_mismatch',403)
