"""CLI/Python/MCP가 공유하는 공개 처리 코드."""
from __future__ import annotations
import json
import re
import sqlite3
import uuid
from importlib.resources import files
from pathlib import Path
from .models import AuctionError, COURTS, REGIONS, USES, query as validate_query, court_id, case_id, display_case, positive, search_body, map_search, map_detail
from .store import Store
from .client import Client
from .export import export_records


def failure(reason):
    return {'ok':False,'reason':reason}


class AuctionService:
    def __init__(self, db=None, export_root=None, *, client_factory=Client):
        self.db = Path(db).expanduser() if db else Path.home()/'.court-auction-mcp'/'jobs.sqlite3'
        self.export_root=Path(export_root).expanduser() if export_root else Path.cwd()/'output'
        self.client_factory=client_factory
        self._store=None

    @property
    def store(self):
        if self._store is None:
            self._store=Store(self.db)
        return self._store

    def codes(self, region=None, max_calls=10):
        if region is not None:
            from .regions import region_id, map_districts
            region=region_id(region)
            return self._single('codes',{'region':region},max_calls,lambda c:map_districts(c.districts(region),region))
        return {'ok':True,'courts':[{'code':k,'name':v} for k,v in COURTS.items()], 'regions':REGIONS,'usage':USES,'court_snapshot':'2026-04-19','district_note':'codes(region=시도코드 또는 이름)으로 공식 시군구 목록 조회. 초기 연결 포함 요청 한도 적용.','usage_note':'usage=all은 토지+건물. usage_mid/usage_small은 공식 사이트에서 확인한 5자리 코드 입력; 하위 코드 목록 미제공.'}

    def coverage(self):
        live=json.loads(files(__package__).joinpath('live_verification.json').read_text('utf-8'))
        return {'ok':True,'version':'0.2.1','integration':'unofficial_internal_json','supported':['codes','search','detail_15A','collect','status','export_jsonl_csv_xlsx','resume','district_codes_live','region_folders','guide'], 'excluded':['15B','photos','documents','vehicles','onbid','rights_analysis','investment_advice','bidding'], 'minimum_interval_seconds':3,'default_max_calls':10,'live_verification':live}

    def _single(self, kind, q, max_calls, operation):
        positive(max_calls,'max_calls')
        job_id=kind+'-'+uuid.uuid4().hex
        self.store.create(job_id,q,max_calls,kind)
        client=self.client_factory(self.store,job_id)
        try:
            result=operation(client)
            self.store.mark(job_id,'complete')
            result.update(request_id=job_id,calls=self.store.status(job_id)['calls'])
            return result
        except AuctionError as error:
            self.store.mark(job_id,error.code,error.code)
            return {**failure(error.code),'request_id':job_id,'calls':self.store.status(job_id)['calls']}
        finally:
            client.close()

    def search(self, query, page=1, max_calls=10):
        q=validate_query(query)
        positive(page,'page')
        return self._single('search',{'query':q,'page':page},max_calls,lambda c:map_search(c.search(search_body(q,page)),q,page))

    def detail(self, court, case, max_calls=10):
        court=court_id(court)
        case=case_id(case)
        return self._single('detail',{'court':court,'case':case},max_calls,lambda c:map_detail(c.detail(court,display_case(case)),court,case))

    def collect(self, job_id, query=None, max_calls=None, max_pages=1):
        positive(max_pages,'max_pages',1000)
        q=validate_query(query) if query is not None else None
        self.store.create(job_id,q,max_calls)
        with self.store.job_lock(job_id):
            state=self.store.status(job_id)
            if state['status'] in ('complete','blocked','schema_changed','repeated_page','source_changed','detail_identity_mismatch','court_identity_mismatch') or state['status'].startswith('filter_mismatch_') or state['host_blocked']:
                return state
            if state['query'].get('region') and state['saved_count'] and any('filter_check' not in row for row in self.store.records(job_id)):
                self.store.mark(job_id,'legacy_region_job','legacy_region_job_requires_new_job')
                return self.store.status(job_id)
            q=state['query']
            client=self.client_factory(self.store,job_id)
            try:
                for _ in range(max_pages):
                    page=self.store.status(job_id)['next_page']
                    result=map_search(client.search(search_body(q,page)),q,page)
                    self.store.save_page(job_id,result)
                    if self.store.status(job_id)['status'] in ('complete','source_changed'):
                        break
                else:
                    self.store.mark(job_id,'partial','page_limit')
            except AuctionError as error:
                self.store.mark(job_id,error.code,error.code)
            finally:
                client.close()
            return self.store.status(job_id)

    def status(self, job_id):
        return self.store.status(job_id)

    def export(self, job_id, name=None):
        state=self.store.status(job_id)
        name=name or job_id+'-'+uuid.uuid4().hex[:8]
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,100}',name):
            raise AuctionError('invalid_export_name')
        return export_records(self.store.records(job_id),self.export_root/name,state,by_region=True)

    def call(self, name, arguments=None):
        methods={'codes':self.codes,'search':self.search,'detail':self.detail,'collect':self.collect,'status':self.status,'export':self.export,'coverage':self.coverage}
        if name not in methods:
            return failure('unknown_tool')
        if arguments is not None and not isinstance(arguments,dict):
            return failure('invalid_arguments')
        try:
            return methods[name](**(arguments or {}))
        except AuctionError as error:
            return failure(error.code)
        except (TypeError,ValueError,KeyError):
            return failure('invalid_arguments')
        except (OSError,RuntimeError,sqlite3.Error):
            return failure('local_execution_error')
