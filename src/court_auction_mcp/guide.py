"""지역·기간을 선택해 수집하고 지역별 파일로 저장하는 대화형 실행."""
import sys
import uuid
from .models import AuctionError, query, positive


def run(service, max_calls=10, max_pages=1, *, input_fn=None, output=None):
    output=output or sys.stderr
    def say(text): print(text,file=output,flush=True)
    if input_fn is None:
        def input_fn(prompt):
            print(prompt,end='',file=output,flush=True)
            return input()
    def choose(rows,label,all_option=False):
        if all_option: say('0: 전체')
        for i,row in enumerate(rows,1): say(f"{i}: {row['name']} ({row['code']})")
        for _ in range(3):
            value=input_fn(label+' 번호: ').strip()
            if all_option and value=='0': return None
            if value.isdigit() and 1<=int(value)<=len(rows): return rows[int(value)-1]['code']
            say('표시된 번호를 입력하세요.')
        raise AuctionError('invalid_selection')
    try:
        positive(max_calls,'max_calls'); positive(max_pages,'max_pages',1000)
        if max_calls<4: raise AuctionError('guide_requires_at_least_four_calls')
        say('시도 → 시군구 → 매각기일 → 지역별 Excel 저장. 기본 한도는 코드 조회·초기 연결을 포함해 10회입니다.')
        codes=service.call('codes')
        if not codes['ok']: return codes
        region=choose([{'code':k,'name':v} for k,v in codes['regions'].items()],'시도')
        districts=service.call('codes',{'region':region,'max_calls':max_calls-2})
        if not districts['ok']: return districts
        district=choose(districts['districts'],'시군구',True)
        q={'region':region,'district':district,'start':input_fn('매각 시작일 (YYYY-MM-DD): ').strip(),'end':input_fn('매각 종료일 (YYYY-MM-DD): ').strip()}
        query(q)  # 수집 작업 생성 전에 입력 검증
        job='region-'+region+'-'+uuid.uuid4().hex[:10]
        say(f'작업 ID: {job}. 다음 실행에서 collect --job-id {job} 로 재개할 수 있습니다.')
        result=service.call('collect',{'job_id':job,'query':q,'max_calls':max_calls-districts['calls'],'max_pages':max_pages})
        if not result['ok']: return result
        say(f"저장 {result['saved_count']}건 / 상태 {result['status']} / 사유 {result.get('reason')}")
        if not result['saved_count']:
            return {**result,'guide_calls':districts['calls']+result['calls'],'code_request_id':districts['request_id']}
        exported=service.call('export',{'job_id':job})
        if not exported['ok']: return exported
        say('파일 저장: '+exported['directory'])
        return {**result,'export':exported,'guide_calls':districts['calls']+result['calls'],'code_request_id':districts['request_id']}
    except (EOFError,KeyboardInterrupt):
        return {'ok':False,'reason':'cancelled'}
    except AuctionError as error:
        return {'ok':False,'reason':error.code}
