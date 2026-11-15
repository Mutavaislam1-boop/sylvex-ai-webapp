"""Targeted cold-start concurrency tests. Real API functions; fake DB, no network."""
import ast,concurrent.futures,functools,os,pathlib,threading,types,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=pathlib.Path(os.environ.get('SYLVEX_NOTIFICATION_SOURCE',str(ROOT/'main.py')))

class DeadlockDetected(Exception):pass
class SchemaFailure(Exception):pass
class CommitFailure(Exception):pass
class NotificationError(Exception):
    def __init__(self,code,status=400):self.code=code;self.status=status
class ReviewError(Exception):
    def __init__(self,code,status=400):self.code=code;self.status=status
class HTTPError(Exception):
    def __init__(self,status_code,detail):self.status_code=status_code;self.detail=detail

@functools.lru_cache(maxsize=None)
def actual_functions():
    tree=ast.parse(SOURCE.read_text());names={'ensure_notification_tables','_notifications_run','_reviews_run','_record_surface_sync'};nodes=[]
    for n in tree.body:
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))and n.name in names:nodes.append(n)
        elif isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='_NOTIFICATIONS_SCHEMA_LOCK'for t in n.targets):nodes.insert(0,n)
    assert names=={n.name for n in nodes if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    return compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),'exec')

class Cursor:
    def __init__(self,connection):self.connection=connection;self.closed=False
    def close(self):self.closed=True

class Connection:
    def __init__(self,harness):self.harness=harness;self.closed=False;self.commits=0;self.rollbacks=0;self.is_schema=False;self.c=Cursor(self)
    def cursor(self):return self.c
    def commit(self):
        if self.is_schema and self.harness.commit_failures:
            self.harness.commit_failures-=1;raise CommitFailure()
        if self.is_schema:
            self.harness.ready_during_schema_commit.append(self.harness.ns['NOTIFICATIONS_SCHEMA_READY'])
            self.harness.schema_commits+=1
        self.commits+=1
    def rollback(self):self.rollbacks+=1
    def close(self):self.closed=True

class Harness:
    def __init__(self,*,cold_hold=False,schema_failures=0,commit_failures=0):
        self.connections=[];self.guard=threading.Lock();self.active_schema=0;self.schema_calls=0;self.schema_commits=0;self.ready_during_schema_commit=[]
        self.first_schema=threading.Event();self.second_schema=threading.Event();self.release_schema=threading.Event();self.cold_hold=cold_hold;self.schema_failures=schema_failures;self.commit_failures=commit_failures;self.schema_steps=[];self.surface_records=[]
        self.ns={'DATABASE_URL':'test-only-no-connection','NOTIFICATIONS_SCHEMA_READY':False,'threading':threading,'HTTPException':HTTPError,'db_connect':self.connect,'notifications_service':types.SimpleNamespace(ensure_tables=self.ensure,NotificationError=NotificationError),'reviews_service':types.SimpleNamespace(ensure_tables=lambda c:self.schema_steps.append('reviews'),ReviewError=ReviewError),'platform_usage_service':types.SimpleNamespace(ensure_table=lambda c:self.schema_steps.append('usage'),record=lambda c,uid,surface:self.surface_records.append((uid,surface)))}
        exec(actual_functions(),self.ns)
        # Baseline has no mutex. This unused fallback only lets cleanup assertions share the harness.
        self.ns.setdefault('_NOTIFICATIONS_SCHEMA_LOCK',threading.Lock())
    def connect(self,url):
        assert url=='test-only-no-connection';c=Connection(self)
        with self.guard:self.connections.append(c)
        return c
    def ensure(self,cursor):
        cursor.connection.is_schema=True
        with self.guard:
            self.schema_calls+=1
            if self.active_schema:
                self.second_schema.set();raise DeadlockDetected()
            self.active_schema+=1
        self.first_schema.set()
        try:
            if self.cold_hold and not self.release_schema.wait(2):raise AssertionError('Test synchronization timeout')
            if self.schema_failures:self.schema_failures-=1;raise SchemaFailure()
            self.schema_steps.append('notifications')
        finally:
            with self.guard:self.active_schema-=1
    def ensure_now(self):return self.ns['ensure_notification_tables']()
    def notification(self,work):return self.ns['_notifications_run'](work)
    def review(self,work):return self.ns['_reviews_run'](work)
    def assert_clean(self,test):
        test.assertTrue(all(c.closed and c.c.closed for c in self.connections))
        mutex=self.ns['_NOTIFICATIONS_SCHEMA_LOCK'];test.assertTrue(mutex.acquire(blocking=False));mutex.release()

class NotificationSchemaTests(unittest.TestCase):
    def concurrent_cold_calls(self,count,surface_first=False):
        h=Harness(cold_hold=True);results=[];errors=[];second_started=threading.Event()
        def request(i):
            if i:second_started.set()
            try:
                if i==0 and surface_first:
                    h.ns['_record_surface_sync'](7,'web');results.append(i);return
                work=lambda c:i
                results.append(h.review(work)if i%2 else h.notification(work))
            except Exception as exc:errors.append(type(exc).__name__)
        with concurrent.futures.ThreadPoolExecutor(max_workers=count)as pool:
            futures=[pool.submit(request,0)]
            self.assertTrue(h.first_schema.wait(1))
            futures.extend(pool.submit(request,i)for i in range(1,count))
            self.assertTrue(second_started.wait(1))
            # Old code deterministically attempts competing DDL while the first transaction is held.
            # Fixed code waits at the mutex and therefore never signals second_schema.
            h.second_schema.wait(0.15);h.release_schema.set()
            for f in futures:f.result(timeout=2)
        self.assertEqual(errors,[]);self.assertEqual(sorted(results),list(range(count)))
        self.assertEqual(h.schema_calls,1);self.assertEqual(h.schema_commits,1);self.assertTrue(h.ns['NOTIFICATIONS_SCHEMA_READY']);h.assert_clean(self)
        if surface_first:self.assertEqual(h.surface_records,[(7,'web')])
    def test_notification_and_feedback_first_requests_succeed(self):self.concurrent_cold_calls(2)
    def test_twelve_concurrent_first_requests_initialize_once(self):self.concurrent_cold_calls(12)
    def test_surface_tracking_and_notifications_share_initialization(self):self.concurrent_cold_calls(3,surface_first=True)
    def test_warm_requests_do_not_repeat_schema(self):
        h=Harness();h.ensure_now()
        for i in range(4):self.assertEqual(h.notification(lambda c:i),i)
        self.assertEqual(h.schema_calls,1);self.assertEqual(h.schema_commits,1);h.assert_clean(self)
    def test_missing_database_keeps_existing_503(self):
        h=Harness();h.ns['DATABASE_URL']='';h.ensure_now()
        with self.assertRaises(HTTPError)as e:h.notification(lambda c:None)
        self.assertEqual(e.exception.status_code,503);self.assertEqual(h.connections,[]);self.assertFalse(h.ns['NOTIFICATIONS_SCHEMA_READY'])
    def test_schema_failure_releases_mutex_and_allows_retry(self):
        h=Harness(schema_failures=1)
        with self.assertRaises(SchemaFailure):h.ensure_now()
        self.assertFalse(h.ns['NOTIFICATIONS_SCHEMA_READY']);h.assert_clean(self)
        h.ensure_now();self.assertTrue(h.ns['NOTIFICATIONS_SCHEMA_READY']);self.assertEqual(h.schema_calls,2);h.assert_clean(self)
    def test_commit_failure_does_not_mark_ready(self):
        h=Harness(commit_failures=1)
        with self.assertRaises(CommitFailure):h.ensure_now()
        self.assertFalse(h.ns['NOTIFICATIONS_SCHEMA_READY']);h.assert_clean(self)
        h.ensure_now();self.assertEqual(h.ready_during_schema_commit,[False]);self.assertTrue(h.ns['NOTIFICATIONS_SCHEMA_READY']);h.assert_clean(self)
    def test_notification_error_keeps_http_mapping_and_rollback(self):
        h=Harness()
        def fail(c):raise NotificationError('test_denied',403)
        with self.assertRaises(HTTPError)as e:h.notification(fail)
        self.assertEqual((e.exception.status_code,e.exception.detail),(403,'test_denied'));self.assertEqual(h.connections[-1].rollbacks,1);h.assert_clean(self)
    def test_review_error_keeps_http_mapping_and_rollback(self):
        h=Harness()
        def fail(c):raise ReviewError('test_invalid',422)
        with self.assertRaises(HTTPError)as e:h.review(fail)
        self.assertEqual((e.exception.status_code,e.exception.detail),(422,'test_invalid'));self.assertEqual(h.connections[-1].rollbacks,1);h.assert_clean(self)
    def test_unexpected_work_failure_keeps_schema_ready(self):
        h=Harness()
        def fail(c):raise ValueError('synthetic work error')
        with self.assertRaises(ValueError):h.notification(fail)
        self.assertEqual(h.connections[-1].rollbacks,1);self.assertTrue(h.ns['NOTIFICATIONS_SCHEMA_READY']);self.assertEqual(h.review(lambda c:'ok'),'ok');self.assertEqual(h.schema_calls,1);h.assert_clean(self)
    def test_regular_work_runs_outside_initialization_mutex(self):
        h=Harness()
        def work(c):
            mutex=h.ns['_NOTIFICATIONS_SCHEMA_LOCK'];self.assertTrue(mutex.acquire(blocking=False));mutex.release();return 'ok'
        self.assertEqual(h.notification(work),'ok');self.assertEqual(h.ready_during_schema_commit,[False]);self.assertEqual(h.schema_steps,['notifications','reviews','usage']);h.assert_clean(self)

if __name__=='__main__':unittest.main()
