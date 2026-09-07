"""Optional PostgreSQL WASM adapter used only by transaction regression tests."""
import json
import os
from pathlib import Path
import subprocess

class Database:
 def __init__(self):
  self.process=subprocess.Popen([os.environ['SYLVEX_TEST_NODE'],str(Path(__file__).with_name('pglite_bridge.mjs'))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 def execute(self,sql,params=()):
  for index in range(sql.count('%s')):sql=sql.replace('%s',f'${index+1}',1)
  self.process.stdin.write(json.dumps({'sql':sql,'params':params})+'\n');self.process.stdin.flush()
  line=self.process.stdout.readline()
  if not line:raise RuntimeError('PostgreSQL WASM process stopped')
  result=json.loads(line)
  if 'error' in result:raise RuntimeError(result['error'])
  return result
 def connect(self):return Connection(self)
 def close(self):self.process.stdin.close();self.process.wait(timeout=10)

class Connection:
 def __init__(self,db):self.db=db;self.active=False
 def cursor(self):return Cursor(self)
 def __enter__(self):return self
 def __exit__(self,kind,*args):
  if kind:self.rollback()
  else:self.commit()
 def begin(self):
  if not self.active:self.db.execute('BEGIN');self.active=True
 def commit(self):
  if self.active:self.db.execute('COMMIT');self.active=False
 def rollback(self):
  if self.active:self.db.execute('ROLLBACK');self.active=False
 def close(self):self.rollback()

class Cursor:
 def __init__(self,conn):self.conn=conn;self.rows=[];self.rowcount=0
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def execute(self,sql,params=()):
  self.conn.begin();result=self.conn.db.execute(sql,params);self.rows=result['rows'];self.rowcount=result['count']
 def fetchone(self):return self.rows.pop(0) if self.rows else None
 def fetchall(self):result=self.rows;self.rows=[];return result
 def close(self):pass
