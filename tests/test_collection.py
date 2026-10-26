import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import httpx
from court_auction_mcp import AuctionService
from court_auction_mcp.client import Client
from court_auction_mcp.models import AuctionError, query, map_search
from court_auction_mcp.store import Store
from fixtures import QUERY, item, search


class FakeClock:
    def __init__(self): self.now=1000; self.sleeps=[]
    def time(self): return self.now
    def sleep(self,seconds): self.sleeps.append(seconds); self.now+=seconds


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name); self.requests=[]; self.times=[]; self.clock=FakeClock()
    def tearDown(self): self.tmp.cleanup()
    def service(self, handler):
        def wrapped(request):
            self.requests.append(request); self.times.append(self.clock.time())
            if request.method=='GET': return httpx.Response(200,text='<html>court</html>')
            return handler(request)
        def factory(store,job): return Client(store,job,transport=httpx.MockTransport(wrapped),clock=self.clock.time,sleep=self.clock.sleep)
        return AuctionService(self.path/'jobs.sqlite3',self.path/'exports',client_factory=factory)
    def handler(self,request):
        page=json.loads(request.content)['dma_pageInfo']['pageNo']
        return httpx.Response(200,json=search([item(),item(mok=2)] if page==1 else [item(mae=2)],'3'))

    def test_resume_cumulative_budget_and_checkpoint(self):
        s=self.service(self.handler)
        r=s.collect('a',QUERY,max_calls=3)
        self.assertEqual((r['saved_count'],r['next_page'],r['calls'],r['status']),(2,2,2,'partial'))
        s=self.service(self.handler)
        r=s.collect('a')
        self.assertEqual((r['saved_count'],r['next_page'],r['calls'],r['status']),(2,2,3,'call_limit'))
        r=s.collect('a',max_calls=5)
        self.assertEqual((r['saved_count'],r['next_page'],r['calls'],r['status']),(3,3,5,'complete'))
        self.assertTrue(all(b-a>=3 for a,b in zip(self.times,self.times[1:])))
        before=len(self.requests); s.collect('a'); self.assertEqual(len(self.requests),before)

    def test_same_job_changed_query_rejected(self):
        s=self.service(self.handler); s.collect('a',QUERY)
        r=s.call('collect',{'job_id':'a','query':{**QUERY,'end':'2026-12-01'}})
        self.assertEqual(r['reason'],'job_query_changed'); self.assertEqual(len(self.requests),2)

    def test_block_persisted_across_job_and_restart(self):
        s=self.service(lambda r:httpx.Response(403,text='secret'))
        r=s.collect('a',QUERY,max_pages=5)
        self.assertEqual(r['status'],'blocked'); self.assertEqual(len(self.requests),2)
        s=self.service(self.handler)
        s.collect('a',max_calls=100); s.collect('b',QUERY)
        self.assertEqual(len(self.requests),2)

    def test_block_on_initial_no_search(self):
        calls=[]
        def handler(r): calls.append(r); return httpx.Response(429)
        s=AuctionService(self.path/'initial.sqlite3',client_factory=lambda st,j:Client(st,j,transport=httpx.MockTransport(handler),clock=self.clock.time,sleep=self.clock.sleep))
        r=s.collect('a',QUERY,max_pages=10)
        self.assertEqual(r['calls'],1); self.assertEqual(r['status'],'blocked'); self.assertEqual(len(calls),1)

    def test_ipcheck_false_stops(self):
        s=self.service(lambda r:httpx.Response(200,json={'data':{'ipcheck':False}}))
        r=s.collect('a',QUERY,max_pages=10)
        self.assertEqual(r['status'],'blocked'); self.assertEqual(len(self.requests),2)

    def test_captcha_stops(self):
        s=self.service(lambda r:httpx.Response(200,text='<h1>CAPTCHA</h1>'))
        r=s.collect('a',QUERY); self.assertEqual(r['status'],'blocked'); self.assertEqual(len(self.requests),2)

    def test_only_one_retry_5xx(self):
        s=self.service(lambda r:httpx.Response(503))
        r=s.collect('a',QUERY)
        self.assertEqual((r['status'],r['calls']),('server_error',3))

    def test_retry_network_then_success(self):
        n=0
        def handler(r):
            nonlocal n
            n+=1
            if n==1: raise httpx.ConnectError('secret',request=r)
            return httpx.Response(200,json=search([],total='0'))
        r=self.service(handler).collect('a',QUERY)
        self.assertEqual((r['status'],r['calls']),('complete',3))

    def test_no_retry_other_http_or_schema_or_maintenance(self):
        for code,body,expected in [(400,'bad','http_400'),(200,'<html>unexpected</html>','schema_changed'),(200,'시스템 점검','maintenance')]:
            with self.subTest(code=code,body=body):
                self.requests=[]
                r=self.service(lambda r:httpx.Response(code,text=body)).collect('case'+expected,QUERY)
                self.assertEqual(r['status'],expected); self.assertEqual(len(self.requests),2)

    def test_total_change_is_partial(self):
        def handler(r):
            page=json.loads(r.content)['dma_pageInfo']['pageNo']
            return httpx.Response(200,json=search([item(),item(mok=2)] if page==1 else [item(mae=2)],'4' if page==1 else '3'))
        r=self.service(handler).collect('a',QUERY,max_pages=3)
        self.assertTrue(r['partial']); self.assertEqual(r['status'],'source_changed'); self.assertEqual(r['saved_count'],3)

    def test_repeated_page_stops_without_checkpoint_change(self):
        r=self.service(lambda r:httpx.Response(200,json=search())).collect('a',QUERY,max_pages=5)
        self.assertEqual((r['status'],r['next_page'],r['saved_count']),('repeated_page',2,2))
        self.assertEqual(len(self.requests),3)

    def test_overlap_dedup_preserves_distinct_objects(self):
        def handler(r):
            page=json.loads(r.content)['dma_pageInfo']['pageNo']
            rows=[item(),item(mok=2)] if page==1 else ([item(mok=2),item(mae=2)] if page==2 else [])
            return httpx.Response(200,json=search(rows,'3'))
        r=self.service(handler).collect('a',QUERY,max_pages=3)
        self.assertEqual(r['saved_count'],3); self.assertEqual(r['read_count'],4)

    def test_atomic_page_and_checkpoint(self):
        st=Store(self.path/'atomic.sqlite3'); q=query(QUERY); st.create('a',q)
        with st.connect() as db:
            db.executescript("CREATE TRIGGER abort_page BEFORE INSERT ON pages BEGIN SELECT RAISE(ABORT,'injected'); END;")
        with self.assertRaises(sqlite3.IntegrityError): st.save_page('a',map_search(search(),q,1))
        self.assertEqual(st.status('a')['saved_count'],0); self.assertEqual(st.status('a')['next_page'],1)

    def test_missing_total_remains_unknown(self):
        r=self.service(lambda r:httpx.Response(200,json=search([item()],None))).collect('a',QUERY)
        self.assertIsNone(r['total']); self.assertIsNotNone(r['total_reason'])

    def test_false_empty_with_positive_total_not_complete(self):
        r=self.service(lambda r:httpx.Response(200,json=search([],100))).collect('a',QUERY)
        self.assertEqual(r['status'],'source_changed'); self.assertEqual(r['reason'],'early_end_before_total')

    def test_limit_reservation_survives_crash(self):
        st=Store(self.path/'crash.sqlite3'); st.create('a',query(QUERY),1); st.reserve('a',1000)
        st=Store(self.path/'crash.sqlite3')
        with self.assertRaises(AuctionError): st.reserve('a',1003)
        self.assertEqual(st.status('a')['calls'],1)

    def test_same_job_lock(self):
        st=Store(self.path/'lock.sqlite3')
        with st.job_lock('a'):
            with self.assertRaises(AuctionError):
                with st.job_lock('a'): pass

    def test_secret_not_saved(self):
        s=self.service(self.handler); s.collect('a',QUERY)
        contents=(self.path/'jobs.sqlite3').read_bytes()
        self.assertNotIn(b'DO_NOT_STORE',contents)

    def test_tls_failure_is_not_retried(self):
        def handler(r): raise httpx.ConnectError('CERTIFICATE_VERIFY_FAILED',request=r)
        r=self.service(handler).collect('tls',QUERY)
        self.assertEqual(r['status'],'tls_error'); self.assertEqual(len(self.requests),2)

    def test_budget_includes_retry(self):
        r=self.service(lambda r:httpx.Response(503)).collect('limited',QUERY,max_calls=2)
        self.assertEqual((r['status'],r['calls']),('call_limit',2)); self.assertEqual(len(self.requests),2)

    def test_changed_total_null_not_zero(self):
        def handler(r):
            page=json.loads(r.content)['dma_pageInfo']['pageNo']
            return httpx.Response(200,json=search([item(),item(mok=2)] if page==1 else [],None if page==1 else '2'))
        r=self.service(handler).collect('changed-null',QUERY,max_pages=2)
        self.assertEqual(r['status'],'source_changed'); self.assertTrue(r['partial'])

    def test_redirect_not_followed(self):
        r=self.service(lambda r:httpx.Response(302,headers={'location':'https://example.com'})).collect('redirect',QUERY)
        self.assertEqual(r['status'],'http_302'); self.assertEqual(len(self.requests),2)
