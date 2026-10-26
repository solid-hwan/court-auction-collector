import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from court_auction_mcp import AuctionService
from court_auction_mcp.client import Client
from court_auction_mcp.cli import execute
from court_auction_mcp.guide import run
from court_auction_mcp.server import call,serve
from fixtures import item,search
from test_collection import FakeClock

class GuideTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); clock=FakeClock(); self.requests=[]
        def handler(r):
            self.requests.append(r)
            if r.method=='GET': return httpx.Response(200,text='<html>court</html>')
            if 'AdongSgg' in str(r.url): return httpx.Response(200,json={'data':{'adongSggLst':[{'code':'','name':'전체'},{'code':'680','name':'강남구'}]}})
            return httpx.Response(200,json=search([item(daepyoSidoCd='11',daepyoSiguCd='680',hjguSido='서울특별시',hjguSigu='강남구')],1))
        self.api=AuctionService(self.root/'db.sqlite3',self.root/'exports',client_factory=lambda s,j:Client(s,j,transport=httpx.MockTransport(handler),clock=clock.time,sleep=clock.sleep))
    def tearDown(self): self.tmp.cleanup()

    def test_districts_cli_python_mcp_same(self):
        results=[self.api.call('codes',{'region':'서울'}),execute(['codes','--region','11'],self.api),call(self.api,'auction_codes',{'region':'11'})]
        for r in results: r.pop('request_id')
        self.assertEqual(results[0],results[1]); self.assertEqual(results[1],results[2]); self.assertEqual(results[0]['districts'],[{'code':'11680','name':'강남구'}])

    def test_flags_equal_json_and_mutually_exclusive(self):
        q={'region':'11','district':'11680','start':'2026-10-26','end':'2026-11-30'}
        args=['search']
        for k,v in q.items(): args+=['--'+k,v]
        a=execute(args,self.api); b=self.api.call('search',{'query':q})
        a.pop('request_id'); b.pop('request_id'); self.assertEqual(a,b)
        before=len(self.requests)
        self.assertEqual(execute(args+['--query','any.json'],self.api)['reason'],'query_file_and_flags_are_exclusive')
        self.assertEqual(len(self.requests),before)

    def test_select_and_export_with_total_request_budget(self):
        inputs=iter(['1','1','2026-10-26','2026-11-30'])
        r=run(self.api,max_calls=4,input_fn=lambda _:next(inputs),output=io.StringIO())
        self.assertTrue(r['ok']); self.assertEqual(r['guide_calls'],4); self.assertEqual(len(self.requests),4)
        self.assertEqual(r['max_calls'],2); self.assertEqual(r['query']['district'],'11680')
        self.assertTrue((Path(r['export']['directory'])/'지역별'/'서울'/'11680_강남구'/'records.xlsx').exists())

    def test_selection_errors_cancel_and_bad_dates(self):
        for values,expected in [(['999','x','-1'],'invalid_selection'),(['1','0','bad','2026-11-30'],'invalid_start')]:
            values=iter(values)
            r=run(self.api,input_fn=lambda _:next(values),output=io.StringIO())
            self.assertEqual(r['reason'],expected)
        def cancel(_): raise EOFError
        self.assertEqual(run(self.api,input_fn=cancel,output=io.StringIO())['reason'],'cancelled')

    def test_filter_mismatch_collect_is_terminal_and_atomic(self):
        q={'region':'26','start':'2026-10-26','end':'2026-11-30'}
        r=self.api.collect('bad',q)
        self.assertEqual(r['status'],'filter_mismatch_region_code'); self.assertEqual(r['saved_count'],0); self.assertEqual(r['next_page'],1)
        before=len(self.requests); self.api.collect('bad'); self.assertEqual(len(self.requests),before)

    def test_legacy_regional_job_cannot_mix_old_results(self):
        from court_auction_mcp.models import canonical
        q={'region':'11','district':'11680','start':'2026-10-26','end':'2026-11-30'}
        self.api.collect('old',q)
        row=next(self.api.store.records('old')); row.pop('filter_check')
        with self.api.store.connect() as db:
            db.execute('UPDATE records SET data=? WHERE job_id=?',(canonical(row),'old'))
        self.api.store.mark('old','partial','page_limit')
        before=len(self.requests)
        r=self.api.collect('old')
        self.assertEqual(r['reason'],'legacy_region_job_requires_new_job')
        self.assertEqual(len(self.requests),before); self.assertEqual(r['saved_count'],1)
