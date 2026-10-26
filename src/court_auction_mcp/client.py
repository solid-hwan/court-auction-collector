"""비공식 법원 JSON 전송. 차단을 우회하거나 응답 원문을 로그에 쓰지 않는다."""
from __future__ import annotations
import re
import json
import time
import httpx
from .models import AuctionError

BASE = 'https://www.courtauction.go.kr'
INIT = BASE+'/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml'
SEARCH = BASE+'/pgj/pgjsearch/searchControllerMain.on'
DETAIL = BASE+'/pgj/pgj15A/selectAuctnCsSrchRslt.on'


def blocked_json(value):
    if isinstance(value, dict):
        for k,v in value.items():
            if k.lower() == 'ipcheck' and (v is False or str(v).lower()=='false'):
                return True
            if k.lower() in ('captcha','captcharequired') and v not in (False,None,'',0) and str(v).lower() != 'false':
                return True
            if blocked_json(v):
                return True
    elif isinstance(value,list):
        return any(blocked_json(v) for v in value)
    return False


class Client:
    def __init__(self, store, job_id, *, transport=None, clock=time.time, sleep=time.sleep):
        self.store, self.job_id = store, job_id
        self.clock, self.sleep = clock, sleep
        self.http = httpx.Client(transport=transport, timeout=25, follow_redirects=False,
            headers={'User-Agent':'court-auction-mcp/0.2.1 (+https://github.com/solid-hwan/court-auction-collector)', 'Accept-Language':'ko-KR'})
        self.ready = False
        self.stopped = False

    def close(self):
        self.http.close()

    def request(self, method, url, *, body=None, submission=None, initial=False):
        if self.stopped:
            raise AuctionError('client_stopped')
        for attempt in range(2):
            try:
                with self.store.request_lock():
                    control = self.store.control()
                    if control['blocked']:
                        raise AuctionError('blocked')
                    delay = max(0, control['last_request']+3-self.clock())
                    if delay:
                        self.sleep(delay)
                    self.store.reserve(self.job_id,self.clock())
                    headers = {'Accept':'text/html' if initial else 'application/json', 'Referer':INIT,'Origin':BASE}
                    if submission:
                        headers.update({'SubmissionId':submission,'SC-Userid':'SYSTEM','Content-Type':'application/json;charset=UTF-8'})
                    with self.http.stream(method,url,json=body,headers=headers) as response:
                        if response.status_code in (401,403,429):
                            self.store.block('http_'+str(response.status_code))
                            raise AuctionError('blocked')
                        content = bytearray()
                        for part in response.iter_bytes():
                            content.extend(part)
                            if len(content)>10*1024*1024:
                                raise AuctionError('response_too_large')
                        text = bytes(content).decode('utf-8',errors='replace')
                        # JSON 업무 필드의 단어는 차단 화면이 아니다. 구조화된 제어값부터 판정한다.
                        try:
                            data=json.loads(text)
                            is_json=True
                        except (ValueError,UnicodeError):
                            data=None; is_json=False
                        envelope = ''
                        if isinstance(data,dict):
                            envelope=' '.join(str(data.get(k,'')) for k in ('message','error','errorMessage'))
                        signals = envelope if is_json else text
                        if blocked_json(data) or (isinstance(data,dict) and data.get('status') in (401,403,429,'401','403','429')) or re.search(r'captcha|자동입력\s*방지|접근.{0,12}차단|access denied|ipcheck[\s"\x27:=]+false',signals,re.I):
                            self.store.block('access_challenge')
                            raise AuctionError('blocked')
                        if any(k in signals for k in ('시스템 작업 안내','서비스 일시 중단','시스템 점검','유지보수')):
                            raise AuctionError('maintenance')
                        if response.status_code>=500:
                            if attempt==0:
                                continue
                            raise AuctionError('server_error')
                        if response.status_code!=200:
                            raise AuctionError('http_'+str(response.status_code))
                        if initial:
                            return None
                        if not is_json:
                            raise AuctionError('schema_changed')
                        return data
            except (httpx.TimeoutException,httpx.NetworkError) as error:
                # 인증서 검증 오류는 일시적 네트워크 장애가 아니다.
                if 'CERTIFICATE_VERIFY_FAILED' in str(error):
                    self.stopped=True
                    raise AuctionError('tls_error') from None
                if attempt==0:
                    continue
                self.stopped=True
                raise AuctionError('network_error') from None
            except AuctionError:
                self.stopped=True
                raise
            except httpx.HTTPError:
                self.stopped=True
                raise AuctionError('transport_error') from None
        raise AuctionError('network_error')

    def initialize(self):
        if not self.ready:
            self.request('GET',INIT,initial=True)
            self.ready=True

    def search(self, body):
        self.initialize()
        return self.request('POST',SEARCH,body=body,submission='mf_wfm_mainFrame_sbm_selectGdsDtlSrch')

    def detail(self, court, case):
        self.initialize()
        return self.request('POST',DETAIL,body={'dma_srchCsDtlInf':{'cortOfcCd':court,'csNo':case}},submission='mf_wfm_mainFrame_sbm_selectCsDtlInf')


    def districts(self, region):
        self.initialize()
        return self.request('POST',BASE+'/pgj/pgj002/selectAdongSggLst.on',body={'pbancMidYn':'N','srchDvsCd':'B','pbancDvsCd':'B','adongSdCd':region})
