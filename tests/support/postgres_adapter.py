"""Disposable schema for the existing retained local PostgreSQL test server."""
import os
from uuid import uuid4
import psycopg2


class Database:
    def __init__(self):
        self.url=os.environ['SYLVEX_TEST_DATABASE_URL']
        if '@sx001c3-postgres:' not in self.url or '/policy_erasure_test_' not in self.url:
            raise ValueError('Only the explicitly isolated local test database is allowed')
        self.schema='account_test_'+uuid4().hex
        with psycopg2.connect(self.url) as conn:
            with conn.cursor() as cur:cur.execute('CREATE SCHEMA '+self.schema)

    def connect(self,*args,**kwargs):
        return psycopg2.connect(self.url,options='-c search_path='+self.schema)

    def close(self):
        with psycopg2.connect(self.url) as conn:
            with conn.cursor() as cur:cur.execute('DROP SCHEMA '+self.schema+' CASCADE')
