import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from openpyxl import load_workbook
from court_auction_mcp import AuctionService
from court_auction_mcp.client import Client
from court_auction_mcp.cli import execute
from court_auction_mcp.export import restore_excel, restore_csv
from court_auction_mcp.server import call, serve, tools
from fixtures import item, search, detail, QUERY
from test_collection import FakeClock


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.clock=FakeClock()
        def handler(r):
            if r.method=='GET': return httpx.Response(200,text='<html>court</html>')
            if 'pgj15A' in str(r.url): return httpx.Response(200,json=detail())
            return httpx.Response(200,json=search([item()],1))
        self.service=AuctionService(self.root/'db.sqlite3',self.root/'exports',client_factory=lambda st,j:Client(st,j,transport=httpx.MockTransport(handler),clock=self.clock.time,sleep=self.clock.sleep))
    def tearDown(self): self.tmp.cleanup()

    def test_cli_python_mcp_search_equivalent(self):
        q=self.root/'query.json'; q.write_text(json.dumps(QUERY))
        a=self.service.call('search',{'query':QUERY})
        b=execute(['search','--query',str(q)],self.service)
        c=call(self.service,'auction_search',{'query':QUERY})
        for value in (a,b,c): value.pop('request_id')
        self.assertEqual(a,b); self.assertEqual(b,c)

    def test_cli_python_mcp_detail_equivalent(self):
        params={'court':'B000210','case':'2099타경123'}
        a=self.service.call('detail',params); b=execute(['detail','--court','B000210','--case','2099타경123'],self.service); c=call(self.service,'auction_detail',params)
        for value in (a,b,c): value.pop('request_id')
        self.assertEqual(a,b); self.assertEqual(b,c)

    def test_export_long_unicode_control_and_formula(self):
        self.service.collect('example',QUERY)
        record=next(self.service.store.records('example'))
        record['raw']['buldNm']='=HYPERLINK("x")'+('가상\x00😀'*20000)
        with self.service.store.connect() as db:
            from court_auction_mcp.models import canonical
            db.execute('UPDATE records SET data=? WHERE job_id=?',(canonical(record),'example'))
        result=self.service.export('example','long')
        directory=Path(result['directory'])
        restored=list(restore_excel(directory/'records.xlsx'))
        self.assertEqual(restored,[record])
        jsonl=[json.loads(line) for line in (directory/'records.jsonl').read_text().splitlines()]
        self.assertEqual(list(restore_csv(directory/'records.csv')),jsonl)
        self.assertEqual(jsonl,restored)
        wb=load_workbook(directory/'records.xlsx',read_only=True)
        for ws in wb:
            for row in ws:
                for cell in row: self.assertNotEqual(cell.data_type,'f')
        wb.close()
        self.assertEqual(self.service.call('export',{'job_id':'example','name':'long'})['reason'],'export_destination_exists')

    def test_export_partial_metadata(self):
        self.service.collect('example',QUERY)
        self.service.store.mark('example','call_limit','call_limit')
        result=self.service.export('example')
        manifest=json.loads((Path(result['directory'])/'manifest.json').read_text())
        self.assertTrue(result['partial']); self.assertTrue(manifest['collection']['partial'])
        self.assertEqual(manifest['collection']['status'],'call_limit')

    def test_invalid_arguments_no_network(self):
        for name,args in [('search',{'query':{}}),('detail',{'court':'unknown','case':'2099타경1'}),('export',{'job_id':'missing','name':'../../bad'}),('collect',{'job_id':'../bad','query':QUERY})]:
            self.assertFalse(self.service.call(name,args)['ok'])
        self.assertFalse(self.service.call('codes',['x'])['ok'])
        self.assertFalse(self.service.call('unknown')['ok'])
        self.assertFalse(self.service.call('codes',{'extra':1})['ok'])

    def test_stdio_errors_and_notifications(self):
        lines=['bad json',json.dumps({'jsonrpc':'2.0','id':0,'method':'tools/list'}),json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'test','version':'1'}}}),json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'}),json.dumps({'jsonrpc':'2.0','id':2,'method':'tools/list'}),json.dumps({'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'auction_coverage','arguments':{}}}),json.dumps({'jsonrpc':'2.0','id':4,'method':'tools/call','params':{'name':'missing'}}),json.dumps({'jsonrpc':'2.0','id':5,'method':'ping'})]
        out=io.StringIO(); serve(self.service,io.StringIO('\n'.join(lines)),out)
        result=[json.loads(x) for x in out.getvalue().splitlines()]
        self.assertEqual(len(result),7)
        self.assertEqual(result[0]['error']['code'],-32700)
        self.assertEqual(result[1]['error']['code'],-32002)
        self.assertEqual(len(result[3]['result']['tools']),7)
        self.assertFalse(result[4]['result']['isError'])
        self.assertEqual(result[5]['error']['code'],-32602)

    def test_stdio_subprocess_initialization_list_and_call(self):
        messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'test','version':'1'}}},{'jsonrpc':'2.0','method':'notifications/initialized'},{'jsonrpc':'2.0','id':2,'method':'tools/list'},{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'auction_codes','arguments':{}}}]
        proc=subprocess.run([sys.executable,'-m','court_auction_mcp','--db',str(self.root/'stdio.sqlite3'),'serve'],input='\n'.join(json.dumps(r) for r in messages)+'\n',text=True,capture_output=True,timeout=10)
        self.assertEqual(proc.returncode,0,proc.stderr)
        rows=[json.loads(line) for line in proc.stdout.splitlines()]
        self.assertEqual(len(rows),3); self.assertEqual(len(rows[1]['result']['tools']),7)
        self.assertEqual(len(rows[2]['result']['structuredContent']['courts']),60)
        self.assertFalse((self.root/'stdio.sqlite3').exists())

    def test_cli_module_and_entrypoint(self):
        script=Path(sys.executable).parent/('court-auction-mcp.exe' if os.name=='nt' else 'court-auction-mcp')
        a=subprocess.run([sys.executable,'-m','court_auction_mcp','coverage'],capture_output=True,text=True,check=True)
        b=subprocess.run([str(script),'coverage'],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(a.stdout),json.loads(b.stdout))

    def test_no_parameters_codes_coverage_do_not_create_db(self):
        self.assertTrue(self.service.codes()['ok']); self.assertTrue(self.service.coverage()['ok'])
        self.assertFalse((self.root/'db.sqlite3').exists())

    def test_export_traversal_and_invalid_names(self):
        self.service.collect('example',QUERY)
        for name in ('../bad','/tmp/bad','a/b','..','a\\b'):
            result=self.service.call('export',{'job_id':'example','name':name})
            self.assertEqual(result['reason'],'invalid_export_name')

    def test_tool_argument_error_is_error(self):
        init={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{}}}
        req=[init,{'jsonrpc':'2.0','method':'notifications/initialized'},{'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'auction_search','arguments':{'query':{}}}}]
        out=io.StringIO(); serve(self.service,io.StringIO('\n'.join(map(json.dumps,req))),out)
        result=json.loads(out.getvalue().splitlines()[-1])
        self.assertTrue(result['result']['isError'])
