"""페이지/체크포인트 원자 저장, 요청 예약과 차단 상태의 영속성."""
from __future__ import annotations
import hashlib
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from .models import AuctionError, canonical, positive


class Store:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, query TEXT NOT NULL, kind TEXT NOT NULL,
                    max_calls INTEGER NOT NULL, calls INTEGER NOT NULL DEFAULT 0,
                    next_page INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'pending',
                    reason TEXT, read_count INTEGER NOT NULL DEFAULT 0,
                    total INTEGER, total_reason TEXT, total_changed INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS records (
                    job_id TEXT NOT NULL, key TEXT NOT NULL, data TEXT NOT NULL,
                    PRIMARY KEY (job_id,key));
                CREATE TABLE IF NOT EXISTS pages (
                    job_id TEXT NOT NULL, page INTEGER NOT NULL, fingerprint TEXT NOT NULL,
                    total INTEGER, PRIMARY KEY(job_id,page));
                CREATE TABLE IF NOT EXISTS control (
                    id INTEGER PRIMARY KEY CHECK(id=1), blocked TEXT, last_request REAL NOT NULL DEFAULT 0);
                INSERT OR IGNORE INTO control(id) VALUES(1);
                CREATE TABLE IF NOT EXISTS failures (
                    job_id TEXT NOT NULL, page INTEGER NOT NULL, reason TEXT NOT NULL, at REAL NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=65)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, job_id, q, max_calls=None, kind='collect'):
        if not isinstance(job_id,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',job_id):
            raise AuctionError('invalid_job_id')
        if max_calls is not None:
            positive(max_calls, 'max_calls')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            if old:
                if (q is not None and old['query'] != canonical(q)) or old['kind'] != kind:
                    raise AuctionError('job_query_changed')
                if max_calls is not None:
                    if max_calls < old['calls']:
                        raise AuctionError('limit_below_used_calls')
                    db.execute('UPDATE jobs SET max_calls=? WHERE id=?',(max_calls,job_id))
            else:
                if q is None:
                    raise AuctionError('query_required_for_new_job')
                db.execute('INSERT INTO jobs(id,query,kind,max_calls) VALUES(?,?,?,?)',(job_id,canonical(q),kind,max_calls or 10))
        return self.status(job_id)

    def status(self, job_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            if row is None:
                raise AuctionError('job_not_found')
            out = dict(row)
            out['query'] = json.loads(out['query'])
            out['saved_count'] = db.execute('SELECT COUNT(*) FROM records WHERE job_id=?',(job_id,)).fetchone()[0]
            out['unverified_count'] = db.execute("SELECT COUNT(*) FROM records WHERE job_id=? AND COALESCE(json_extract(data,'$.filter_check.status'),'unverified')!='verified'",(job_id,)).fetchone()[0]
            out['filters_verified'] = out['saved_count']>0 and out['unverified_count']==0
            out['failures'] = [dict(r) for r in db.execute('SELECT page,reason,at FROM failures WHERE job_id=? ORDER BY at DESC LIMIT 20',(job_id,))]
            out['host_blocked'] = db.execute('SELECT blocked FROM control WHERE id=1').fetchone()[0]
        out.update(ok=True,job_id=out.pop('id'),partial=out['status']!='complete',snapshot_guarantee=False)
        return out

    @contextmanager
    def request_lock(self):
        # 별도 SQLite 잠금은 프로세스가 죽으면 해제된다. 요청 예약 DB는 즉시 커밋한다.
        lock = sqlite3.connect(str(self.path)+'.request-lock',timeout=65)
        try:
            lock.execute('BEGIN IMMEDIATE')
            yield
        finally:
            lock.rollback()
            lock.close()

    @contextmanager
    def job_lock(self, job_id):
        # 같은 작업의 동시 수집만 거부. 네트워크 순서는 request_lock이 직렬화한다.
        suffix = hashlib.sha256(job_id.encode()).hexdigest()[:16]
        lock = sqlite3.connect(str(self.path)+'.job-'+suffix,timeout=0)
        try:
            try:
                lock.execute('BEGIN IMMEDIATE')
            except sqlite3.OperationalError:
                raise AuctionError('job_busy') from None
            yield
        finally:
            lock.rollback()
            lock.close()

    def control(self):
        with self.connect() as db:
            return dict(db.execute('SELECT * FROM control WHERE id=1').fetchone())

    def reserve(self, job_id, now):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT blocked FROM control WHERE id=1').fetchone()[0]:
                raise AuctionError('blocked')
            row = db.execute('SELECT calls,max_calls FROM jobs WHERE id=?',(job_id,)).fetchone()
            if not row or row['calls'] >= row['max_calls']:
                raise AuctionError('call_limit')
            db.execute('UPDATE jobs SET calls=calls+1 WHERE id=?',(job_id,))
            db.execute('UPDATE control SET last_request=? WHERE id=1',(now,))

    def block(self, reason):
        with self.connect() as db:
            db.execute('UPDATE control SET blocked=? WHERE id=1',(reason,))

    def mark(self, job_id, status, reason=None):
        with self.connect() as db:
            db.execute('UPDATE jobs SET status=?,reason=? WHERE id=?',(status,reason,job_id))
            if reason and status not in ('partial','complete'):
                page = db.execute('SELECT next_page FROM jobs WHERE id=?',(job_id,)).fetchone()[0]
                db.execute('INSERT INTO failures VALUES(?,?,?,?)',(job_id,page,reason,time.time()))

    def save_page(self, job_id, result):
        records = result['records']
        # 순서만 바꿔 돌려준 페이지도 반복으로 감지한다.
        fingerprint = hashlib.sha256(canonical(sorted(r['item_key'] for r in records)).encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            job = db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            if result['page'] != job['next_page']:
                raise AuctionError('checkpoint_conflict')
            if records and db.execute('SELECT 1 FROM pages WHERE job_id=? AND fingerprint=?',(job_id,fingerprint)).fetchone():
                raise AuctionError('repeated_page')
            prior_pages = db.execute('SELECT COUNT(*) FROM pages WHERE job_id=?',(job_id,)).fetchone()[0]
            changed = bool(job['total_changed']) or bool(prior_pages and job['total'] != result['source_total_count'])
            for row in records:
                db.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(job_id,key) DO UPDATE SET data=excluded.data',(job_id,row['item_key'],canonical(row)))
            db.execute('INSERT INTO pages VALUES(?,?,?,?)',(job_id,result['page'],fingerprint,result['source_total_count']))
            # totalCnt는 변할 수 있으므로 짧은/빈 페이지를 실제 종료 근거로 사용한다.
            end = result['read_count'] < result['page_size']
            inconsistent = end and result['source_total_count'] is not None and result['source_total_count'] > job['read_count'] + result['read_count']
            status = 'source_changed' if end and (changed or inconsistent) else ('complete' if end else 'running')
            reason = 'early_end_before_total' if inconsistent else ('source_total_changed' if changed else None)
            db.execute('UPDATE jobs SET next_page=?,status=?,reason=?,read_count=read_count+?,total=?,total_reason=?,total_changed=? WHERE id=?',
                       (result['page']+1,status,reason,result['read_count'],result['source_total_count'],result['source_total_reason'],int(changed),job_id))

    def records(self, job_id):
        with self.connect() as db:
            for row in db.execute('SELECT data FROM records WHERE job_id=? ORDER BY key',(job_id,)):
                yield json.loads(row[0])
