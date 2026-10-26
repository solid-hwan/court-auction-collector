"""네트워크 없이 가상 다물건 사건 수집→3형식 출력→Excel 복원."""
import argparse
import json
from pathlib import Path
import tempfile
import httpx
from court_auction_mcp import AuctionService
from court_auction_mcp.client import Client
from court_auction_mcp.export import restore_excel, restore_csv

p=argparse.ArgumentParser()
p.add_argument('--output',default=None,help='새 출력 폴더의 상위 경로; 생략 시 임시 디렉터리')
args=p.parse_args()
root=Path(args.output) if args.output else Path(tempfile.mkdtemp(prefix='court-auction-example-'))
fixture=json.loads(Path(__file__).with_name('synthetic.json').read_text(encoding='utf-8'))
clock=[1000.0]
def handler(request):
    if request.method=='GET': return httpx.Response(200,text='<html>synthetic</html>')
    return httpx.Response(200,json=fixture)
def sleep(seconds): clock[0]+=seconds
service=AuctionService(root/'example.sqlite3',root,client_factory=lambda st,j:Client(st,j,transport=httpx.MockTransport(handler),clock=lambda:clock[0],sleep=sleep))
query={'court':'B000210','start':'2026-10-26','end':'2026-11-30','page_size':10}
result=service.call('collect',{'job_id':'synthetic','query':query})
assert result['saved_count']==2 and not result['partial'],result
exported=service.call('export',{'job_id':'synthetic'})
assert exported['ok'],exported
directory=Path(exported['directory'])
records=list(service.store.records('synthetic'))
assert list(restore_excel(directory/'records.xlsx'))==records
assert list(restore_csv(directory/'records.csv'))==records
print(json.dumps({'synthetic':True,'network_requests':0,'saved_count':2,'export':exported},ensure_ascii=False))
