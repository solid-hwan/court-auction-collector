"""허용된 원문만 내보내며 Excel의 셀 길이·수식 제한을 처리한다."""
import csv
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from openpyxl import Workbook, load_workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from .regions import location, folder_parts
from .models import COURTS
from .models import AuctionError, canonical


def text_row(sheet, values):
    cells=[]
    for value in values:
        cell=WriteOnlyCell(sheet, value=str(value))
        cell.data_type='s'
        cells.append(cell)
    sheet.append(cells)


OVERVIEW_KEYS=('region_name','district_name','address','court_code','case_no','sale_item_no','object_no','usage','property_kind','appraisal_price','minimum_price','sale_date','fail_count','filter_status')
OVERVIEW_HEADERS=['시도','시군구','주소','법원','사건','매물','목적물','용도','토지/건물','감정가','최저매각가','매각기일','유찰횟수','조건검증']


def overview_values(record):
    n={**location(record.get('raw',{})),**record['normalized']}
    n['court_code']=COURTS.get(n.get('court_code'),n.get('court_code'))
    n['property_kind']={'land':'토지','building':'건물'}.get(n.get('property_kind'),'')
    n['filter_status']=record.get('filter_check',{}).get('status','unverified')
    return [n.get(k) for k in OVERVIEW_KEYS]


def safe_text(value):
    return ILLEGAL_CHARACTERS_RE.sub('',str(value))[:30000]


def overview_row(sheet, values, header=False):
    cells=[]
    for value in values:
        cell=WriteOnlyCell(sheet)
        if type(value) is int and abs(value)<10**15:
            cell.value=value; cell.number_format='#,##0'
        else:
            cell.value='' if value is None else safe_text(value); cell.data_type='s'
        if header:
            cell.font=Font(bold=True,color='FFFFFF'); cell.fill=PatternFill('solid',fgColor='234E70')
        cells.append(cell)
    sheet.append(cells)


def csv_value(value):
    if value is None: return ''
    if isinstance(value,str):
        value=safe_text(value)
        if value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n')): return "'"+value
    return value


def export_records(records, destination, context, *, by_region=False):
    destination=Path(destination)
    if destination.exists():
        raise AuctionError('export_destination_exists')
    destination.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.auction-export-',dir=destination.parent))
    try:
        workbook=Workbook(write_only=True)
        overview=workbook.create_sheet('Overview')
        sheet=workbook.create_sheet('records')
        overflow=workbook.create_sheet('long_values')
        metadata=workbook.create_sheet('Collection')
        overview.freeze_panes='D2'
        for col,width in {'A':12,'B':20,'C':65,'D':24,'E':20,'F':10,'G':10,'H':22,'I':12,'J':20,'K':20,'L':16,'M':12,'N':16}.items():
            overview.column_dimensions[col].width=width
        overview_row(overview,OVERVIEW_HEADERS,header=True)
        text_row(sheet,['record_index','record_json'])
        text_row(overflow,['record_index','chunk_index','text'])
        count=0
        groups={}
        region_root=staging/'지역별'
        with (staging/'records.jsonl').open('w',encoding='utf-8') as jf, (staging/'records.csv').open('w',encoding='utf-8-sig',newline='') as cf, (staging/'overview.csv').open('w',encoding='utf-8-sig',newline='') as vf:
            visible=csv.writer(vf); visible.writerow(OVERVIEW_HEADERS)
            writer=csv.writer(cf)
            writer.writerow(['record_index','record_json'])
            for count, record in enumerate(records,1):
                value=canonical(record)
                jf.write(value+'\n')
                writer.writerow([count,value])
                shown=overview_values(record)
                overview_row(overview,shown)
                visible.writerow([csv_value(v) for v in shown])
                if by_region:
                    parts=folder_parts(record)
                    group=groups.setdefault(parts,{'count':0,'spool':staging/('group-'+str(len(groups))+'.jsonl')})
                    group['count']+=1
                    with group['spool'].open('a',encoding='utf-8') as stream: stream.write(value+'\n')
                if len(value)>30000:
                    for i,start in enumerate(range(0,len(value),30000)):
                        text_row(overflow,[count,i,value[start:start+30000]])
                    text_row(sheet,[count,f'[long_values:{count}]'])
                else:
                    text_row(sheet,[count,value])
        safe_context={k:context.get(k) for k in ('job_id','status','reason','partial','query','calls','max_calls','next_page','saved_count','read_count','total','total_reason','total_changed','snapshot_guarantee','unverified_count','filters_verified')}
        # 쿼리는 한정된 코드/숫자/날짜만 허용되어 셀 한도를 초과하지 않는다.
        for k,v in safe_context.items():
            text_row(metadata,[k,canonical(v)])
        overview.auto_filter.ref=f'A1:N{count+1}'
        workbook.save(staging/'records.xlsx')
        regional=[]
        if by_region:
            region_root.mkdir()
            for parts,group in sorted(groups.items()):
                dest=region_root.joinpath(*parts)
                with group['spool'].open(encoding='utf-8') as stream:
                    export_records((json.loads(line) for line in stream),dest,context)
                group['spool'].unlink()
                regional.append({'region':parts[0],'district':parts[1],'rows':group['count'],'path':dest.relative_to(staging).as_posix()})
            with (region_root/'지역목록.csv').open('w',encoding='utf-8-sig',newline='') as stream:
                writer=csv.writer(stream); writer.writerow(['시도','시군구','저장건수','폴더'])
                writer.writerows([[r['region'],r['district'],r['rows'],r['path']] for r in regional])
            (region_root/'README.md').write_text('# 지역별 결과\n\n지역목록.csv에서 원하는 시도·시군구의 폴더를 열어 records.xlsx 또는 overview.csv를 보세요. 저장된 물건만 분류하며 전국 전체 통계가 아닙니다. 지역미확인은 주소 정보가 없는 자료입니다. 전체 작업의 수집 상태는 상위 manifest.json을 확인하세요.\n',encoding='utf-8')
        manifest={'rows':count,'collection':safe_context,'canonical':'records.jsonl','csv':'record_json is a JSON object; parse with json.loads','excel':'restore_excel(path) joins ordered long_values chunks','sha256':{name:hashlib.sha256((staging/name).read_bytes()).hexdigest() for name in ('records.jsonl','records.csv','records.xlsx','overview.csv')}}
        manifest['regions']=regional
        if by_region:
            for file in sorted(region_root.rglob('*')):
                if file.is_file(): manifest['sha256'][file.relative_to(staging).as_posix()]=hashlib.sha256(file.read_bytes()).hexdigest()
        (staging/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        # 디렉터리 교체는 기존 파일 덮어쓰기를 허용하지 않는다.
        if destination.exists():
            raise AuctionError('export_destination_exists')
        os.rename(staging,destination)
        return {'ok':True,'directory':str(destination.resolve()),'rows':count,'partial':safe_context['partial'],'files':['records.jsonl','records.csv','records.xlsx','overview.csv','manifest.json'],'regional_folder':'지역별' if by_region else None,'region_groups':len(regional)}
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def restore_excel(path):
    workbook=load_workbook(path,read_only=True,data_only=False)
    try:
        chunks={}
        for index,order,text in workbook['long_values'].iter_rows(min_row=2,values_only=True):
            chunks.setdefault(index,[]).append((int(order),text))
        for index,value in workbook['records'].iter_rows(min_row=2,values_only=True):
            if value==f'[long_values:{index}]':
                value=''.join(t for _,t in sorted(chunks[index]))
            yield json.loads(value)
    finally:
        workbook.close()


def restore_csv(path):
    """Python csv 기본 128KiB 제한보다 긴 원문도 복원한다."""
    previous=csv.field_size_limit()
    try:
        csv.field_size_limit(256*1024*1024)
        with Path(path).open(encoding='utf-8-sig',newline='') as stream:
            for row in csv.DictReader(stream):
                yield json.loads(row['record_json'])
    finally:
        csv.field_size_limit(previous)
