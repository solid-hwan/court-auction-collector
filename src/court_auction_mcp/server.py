"""MCP 2025-11-25 stdio tools. 표준 출력에 줄 단위 JSON-RPC만 쓴다."""
import json
import sys
from .models import QUERY_FIELDS

QUERY_PROPERTIES={k:{'type':['string','null']} for k in ('court','region','district','usage_mid','usage_small')}
QUERY_PROPERTIES.update({k:{'type':'string','description':'YYYY-MM-DD'} for k in ('start','end')})
QUERY_PROPERTIES['usage']={'type':'string','enum':['all','land','building'],'default':'all'}
QUERY_PROPERTIES['page_size']={'type':'integer','minimum':1,'maximum':100,'default':10}
for field in QUERY_FIELDS-set(QUERY_PROPERTIES):
    QUERY_PROPERTIES[field]={'type':['integer','null'],'minimum':0}
QUERY={'type':'object','properties':QUERY_PROPERTIES,'required':['start','end'],'anyOf':[{'required':['court'],'properties':{'court':{'type':'string','minLength':1}}},{'required':['region'],'properties':{'region':{'type':'string','minLength':1}}}],'additionalProperties':False}


def obj(properties=None, required=()):
    return {'type':'object','properties':properties or {},'required':list(required),'additionalProperties':False}


JOB={'type':'string','pattern':'^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$'}
LIMIT={'type':'integer','minimum':1,'description':'초기 연결·재시도 포함 누적 한도. 신규 기본 10.'}
SCHEMAS={
    'auction_codes':obj({'region':{'type':'string','description':'시도 코드/이름. 생략 시 오프라인 목록, 지정 시 공식 시군구 목록 조회.'},'max_calls':LIMIT}),
    'auction_search':obj({'query':QUERY,'page':{'type':'integer','minimum':1,'default':1},'max_calls':LIMIT},('query',)),
    'auction_detail':obj({'court':{'type':'string'},'case':{'type':'string'},'max_calls':LIMIT},('court','case')),
    'auction_collect':obj({'job_id':JOB,'query':QUERY,'max_calls':LIMIT,'max_pages':{'type':'integer','minimum':1,'maximum':1000,'default':1}},('job_id',)),
    'auction_job_status':obj({'job_id':JOB},('job_id',)),
    'auction_export':obj({'job_id':JOB,'name':{'type':'string','pattern':'^[A-Za-z0-9][A-Za-z0-9_-]{0,100}$'}},('job_id',)),
    'auction_coverage':obj(),
}
DESCRIPTIONS={'auction_codes':'법원·시도·토지/건물 대분류 코드. 하위 코드 목록 지원 범위 확인.', 'auction_search':'명시한 법원/지역·매각기일 범위에서 한 페이지 조회.', 'auction_detail':'법원·사건 식별을 검증한 15A 상세. 권리분석이나 투자추천이 아님.', 'auction_collect':'순차 수집·원자 체크포인트. 같은 job_id로 재개, 조건 변경 거부.', 'auction_job_status':'저장 건수·누적 요청·체크포인트·실패 요약.', 'auction_export':'새 로컬 폴더에 JSONL/CSV/Excel. 기존 출력은 덮어쓰지 않음.', 'auction_coverage':'지원 기능과 실제 검증 범위·한계 확인.'}
METHODS={'auction_'+k:k for k in ('codes','search','detail','collect','export','coverage')}
METHODS['auction_job_status']='status'


def tools():
    return [{'name':name,'description':DESCRIPTIONS[name],'inputSchema':schema,'annotations':{'readOnlyHint':name in ('auction_coverage','auction_job_status'),'destructiveHint':False,'openWorldHint':name in ('auction_codes','auction_search','auction_detail','auction_collect')}} for name,schema in SCHEMAS.items()]


def call(service, name, arguments):
    return service.call(METHODS.get(name,''),arguments)


def error(identifier,code,message):
    return {'jsonrpc':'2.0','id':identifier,'error':{'code':code,'message':message}}


def serve(service, stdin=None, stdout=None):
    stdin=stdin or sys.stdin; stdout=stdout or sys.stdout
    initialized=False; ready=False
    for line in stdin:
        try:
            request=json.loads(line)
        except ValueError:
            print(json.dumps(error(None,-32700,'Parse error')),file=stdout,flush=True)
            continue
        if not isinstance(request,dict) or request.get('jsonrpc')!='2.0' or not isinstance(request.get('method'),str):
            print(json.dumps(error(None,-32600,'Invalid request')),file=stdout,flush=True)
            continue
        method=request['method']; identifier=request.get('id'); params=request.get('params',{})
        if 'id' not in request:
            if method=='notifications/initialized' and initialized:
                ready=True
            continue
        if type(identifier) not in (str,int):
            output=error(None,-32600,'Invalid request id')
        elif not isinstance(params,dict):
            output=error(identifier,-32602,'Invalid params')
        elif method=='initialize':
            if not isinstance(params.get('protocolVersion'),str) or not isinstance(params.get('capabilities'),dict) or not isinstance(params.get('clientInfo'),dict):
                output=error(identifier,-32602,'Invalid initialization params')
            else:
                initialized=True; ready=False
                output={'jsonrpc':'2.0','id':identifier,'result':{'protocolVersion':'2025-11-25','capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'court-auction-mcp','version':'0.2.0'},'instructions':'비공식 연동. partial/reason과 coverage를 확인하세요. 차단 후 재요청·우회 금지.'}}
        elif method=='ping':
            output={'jsonrpc':'2.0','id':identifier,'result':{}}
        elif not ready:
            output=error(identifier,-32002,'Initialize and send notifications/initialized first')
        elif method=='tools/list':
            output={'jsonrpc':'2.0','id':identifier,'result':{'tools':tools()}}
        elif method=='tools/call':
            if not isinstance(params.get('name'),str) or params['name'] not in METHODS:
                output=error(identifier,-32602,'Unknown tool')
            else:
                data=call(service,params['name'],params.get('arguments',{}))
                encoded=json.dumps(data,ensure_ascii=False)
                if len(encoded.encode('utf-8'))>1024*1024:
                    data={'ok':False,'reason':'mcp_response_limit','message':'수집 후 export로 파일을 사용하거나 페이지 크기를 줄이세요.','request_id':data.get('request_id')}
                    encoded=json.dumps(data,ensure_ascii=False)
                output={'jsonrpc':'2.0','id':identifier,'result':{'content':[{'type':'text','text':encoded}],'structuredContent':data,'isError':data.get('ok') is False}}
        else:
            output=error(identifier,-32601,'Method not found')
        print(json.dumps(output,ensure_ascii=False),file=stdout,flush=True)
