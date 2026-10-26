"""표준 출력은 JSON 또는 MCP 메시지만 사용한다."""
import argparse
import json
from pathlib import Path
from .service import AuctionService
from .models import QUERY_FIELDS


def parser():
    p=argparse.ArgumentParser(prog='court-auction-mcp',description='법원경매 부동산 검색·수집·Excel 출력 (비공식 연동)')
    p.add_argument('--db',help='작업 SQLite 경로; 기본 ~/.court-auction-mcp/jobs.sqlite3')
    p.add_argument('--export-root',help='내보내기 루트; 기본 ./output')
    sub=p.add_subparsers(dest='command',required=True)
    codes=sub.add_parser('codes')
    codes.add_argument('--region',help='시도 코드 또는 이름; 지정하면 공식 시군구 목록 조회')
    codes.add_argument('--max-calls',type=int,default=10)
    guide=sub.add_parser('guide',help='지역과 기간을 선택해 수집·지역별 저장')
    guide.add_argument('--max-calls',type=int,default=10)
    guide.add_argument('--max-pages',type=int,default=1)
    for name in ('coverage','serve'):
        sub.add_parser(name)
    search=sub.add_parser('search')
    search.add_argument('--query',help='검색 조건 JSON 파일')
    search.add_argument('--page',type=int,default=1)
    search.add_argument('--max-calls',type=int,default=10)
    detail=sub.add_parser('detail')
    detail.add_argument('--court',required=True)
    detail.add_argument('--case',required=True)
    detail.add_argument('--max-calls',type=int,default=10)
    collect=sub.add_parser('collect')
    collect.add_argument('--job-id',required=True)
    collect.add_argument('--query',help='재개 시 생략 가능; 조건 변경은 거부')
    collect.add_argument('--max-calls',type=int,help='작업 시작부터 누적 한도. 신규 기본 10')
    collect.add_argument('--max-pages',type=int,default=1)
    status=sub.add_parser('status')
    status.add_argument('--job-id',required=True)
    export=sub.add_parser('export')
    export.add_argument('--job-id',required=True)
    export.add_argument('--name',help='출력 루트 아래 새 폴더명')
    for command in (search,collect):
        for field in sorted(QUERY_FIELDS):
            numeric=field.endswith(('_min','_max')) or field=='page_size'
            command.add_argument('--'+field.replace('_','-'),type=int if numeric else str,default=None)
    return p


def execute(argv=None, service=None):
    args=vars(parser().parse_args(argv))
    command=args.pop('command')
    db=args.pop('db'); export_root=args.pop('export_root')
    service=service or AuctionService(db,export_root)
    if command=='guide':
        from .guide import run
        return run(service,**args)
    if command=='serve':
        from .server import serve
        serve(service)
        return None
    if command in ('search','collect'):
        direct={k:args.pop(k) for k in QUERY_FIELDS if args.get(k) is not None}
        for k in QUERY_FIELDS: args.pop(k,None)
        if direct:
            if args.get('query'): return {'ok':False,'reason':'query_file_and_flags_are_exclusive'}
            args['query']=direct
    if isinstance(args.get('query'),str):
        try:
            args['query']=json.loads(Path(args['query']).read_text(encoding='utf-8'))
        except (OSError,ValueError):
            return {'ok':False,'reason':'invalid_query_file'}
    if command=='search' and not args.get('query'):
        return {'ok':False,'reason':'query_required'}
    return service.call(command,args)


def main(argv=None):
    result=execute(argv)
    if result is None:
        return 0
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    if not result.get('ok'):
        return 2
    if result.get('partial'):
        return 3
    return 0
