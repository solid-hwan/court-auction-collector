"""공개 계약: 필드 허용목록, 엄격한 값 해석, 출처별 식별자."""
from __future__ import annotations
import json
import math
import re
from datetime import date
from importlib.resources import files

SOURCE = json.loads(files(__package__).joinpath('source_codes.json').read_text('utf-8'))
COURTS = {r['code']: r['name'] for r in SOURCE['COURTS']}
REGIONS = {'11':'서울','26':'부산','27':'대구','28':'인천','29':'광주','30':'대전','31':'울산','36':'세종','41':'경기','43':'충북','44':'충남','46':'전남','47':'경북','48':'경남','50':'제주','51':'강원','52':'전북'}
USES = {'all':'', 'land':'10000', 'building':'20000'}

class AuctionError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)


def scalar(value):
    return value if type(value) in (str, int, bool) or (type(value) is float and math.isfinite(value)) else None


def pick(row, fields):
    return {k: scalar(row[k]) for k in fields if k in row}


def number(value):
    if type(value) is int and value >= 0:
        return value
    if type(value) is not str:
        return None
    s = value.strip()
    if not re.fullmatch(r'(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)', s):
        return None
    digits=s.replace(',', '')
    return int(digits) if len(digits)<=20 else None


def day(value):
    if type(value) is not str:
        return None
    s = value.strip()
    if re.fullmatch(r'[0-9]{8}', s):
        s = f'{s[:4]}-{s[4:6]}-{s[6:]}'
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', s):
        return None
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        return None


def case_id(value):
    if not isinstance(value, str):
        raise AuctionError('invalid_case_number')
    s = value.strip()
    m = re.fullmatch(r'([0-9]{4})타경([0-9]{1,6})', s)
    if m and int(m[2]) > 0:
        return f'{m[1]}0130{int(m[2]):06d}'
    if re.fullmatch(r'[0-9]{4}0130[0-9]{6}', s) and int(s[-6:]) > 0:
        return s
    raise AuctionError('invalid_case_number')


def display_case(value):
    s = case_id(value)
    return f'{s[:4]}타경{int(s[-6:])}'


def court_id(value):
    if value in COURTS:
        return value
    matches = [k for k, v in COURTS.items() if isinstance(value, str) and value and value in v]
    if len(matches) != 1:
        raise AuctionError('unknown_or_ambiguous_court')
    return matches[0]


def positive(value, name, maximum=None):
    if type(value) is not int or value < 1 or (maximum and value > maximum):
        raise AuctionError('invalid_' + name)
    return value


QUERY_FIELDS = {'court','region','district','start','end','usage','usage_mid','usage_small','appraisal_min','appraisal_max','minimum_min','minimum_max','failures_min','failures_max','page_size'}


def query(value):
    if not isinstance(value, dict) or set(value) - QUERY_FIELDS:
        raise AuctionError('invalid_query_fields')
    q = {'court':None,'region':None,'district':None,'usage':'all','usage_mid':None,'usage_small':None,'page_size':10, **value}
    if not q['court'] and not q['region']:
        raise AuctionError('court_or_region_required')
    if q['court']:
        q['court'] = court_id(q['court'])
    if q['region'] is not None and q['region'] not in REGIONS:
        raise AuctionError('invalid_region')
    if q['district'] is not None and (not q['region'] or not isinstance(q['district'], str) or not re.fullmatch(r'[0-9]{5}', q['district']) or not q['district'].startswith(q['region'])):
        raise AuctionError('invalid_district')
    if q['usage'] not in USES:
        raise AuctionError('invalid_usage')
    for k in ('usage_mid','usage_small'):
        if q[k] is not None and (q['usage']=='all' or not isinstance(q[k],str) or not re.fullmatch(r'[0-9]{5}', q[k])):
            raise AuctionError('invalid_' + k)
    if q['usage_small'] and not q['usage_mid']:
        raise AuctionError('usage_mid_required')
    for k in ('start','end'):
        if not day(q.get(k)):
            raise AuctionError('invalid_' + k)
        q[k] = day(q[k])
    if q['start'] > q['end']:
        raise AuctionError('invalid_date_range')
    positive(q['page_size'], 'page_size', 100)
    for prefix in ('appraisal','minimum','failures'):
        for suffix in ('min','max'):
            k = prefix + '_' + suffix
            q.setdefault(k, None)
            if q[k] is not None and (type(q[k]) is not int or q[k] < 0):
                raise AuctionError('invalid_' + k)
        lo, hi = q[prefix+'_min'], q[prefix+'_max']
        if lo is not None and hi is not None and lo > hi:
            raise AuctionError('invalid_' + prefix + '_range')
    return q


def search_body(q, page):
    fields = {**SOURCE['BASE_SRCH'], 'cortOfcCd':q['court'] or '', 'rprsAdongSdCd':q['region'] or '', 'rprsAdongSggCd':q['district'] or '', 'lclDspslGdsLstUsgCd':USES[q['usage']], 'mclDspslGdsLstUsgCd':q['usage_mid'] or '', 'sclDspslGdsLstUsgCd':q['usage_small'] or '', 'bidBgngYmd':q['start'].replace('-',''), 'bidEndYmd':q['end'].replace('-','')}
    for prefix, target in [('appraisal','aeeEvlAmt'),('minimum','lwsDspslPrc'),('failures','flbdNcnt')]:
        for suffix in ('min','max'):
            v = q[prefix+'_'+suffix]
            fields[target+suffix.title()] = '' if v is None else str(v)
    return {'dma_pageInfo':{'pageNo':page,'pageSize':q['page_size'],'bfPageNo':'','startRowNo':'','totalCnt':'','totalYn':'Y','groupTotalCount':''}, 'dma_srchGdsDtlSrchInfo':fields}


SEARCH_FIELDS = ('srnSaNo','jiwonCd','cortOfcCd','jiwonNm','maemulSer','mokmulSer','gamevalAmt','notifyMinmaePrice1','minmaePrice','yuchalCnt','maeGiil','maeHh1','lclsUtilCd','dspslUsgNm','bgPlaceRdAllAddr','hjguSido','hjguSigu','hjguDong','rdNm','buldNo','daepyoLotno','buldNm','buldList')


def parsed_fields(raw, mapping):
    normalized, reasons = {}, {}
    for name, (field, parser) in mapping.items():
        v = raw.get(field)
        normalized[name] = parser(v)
        if normalized[name] is None:
            reasons[name] = 'missing_source_value' if v is None or v == '' else 'invalid_source_value'
    return normalized, reasons


def map_item(row, requested_court=None):
    if not isinstance(row, dict):
        raise AuctionError('schema_changed')
    raw = pick(row, SEARCH_FIELDS)
    # 검색 결과 자체에 법원 식별이 있어야 한다. 요청 법원으로 다른 응답을 덮지 않는다.
    source_court = raw.get('cortOfcCd') or raw.get('jiwonCd') or raw.get('jiwonNm')
    if not source_court:
        raise AuctionError('missing_court_identity')
    court = court_id(source_court)
    if requested_court and court != requested_court:
        raise AuctionError('court_identity_mismatch')
    cs = case_id(raw.get('srnSaNo'))
    mae, mok = number(raw.get('maemulSer')), number(raw.get('mokmulSer'))
    if mae is None or mok is None:
        raise AuctionError('missing_item_identity')
    minimum = 'notifyMinmaePrice1' if raw.get('notifyMinmaePrice1') not in (None,'') else 'minmaePrice'
    normalized, reasons = parsed_fields(raw, {'appraisal_price':('gamevalAmt', number),'minimum_price':(minimum,number),'fail_count':('yuchalCnt',number),'sale_date':('maeGiil',day)})
    normalized.update(court_code=court, case_no=display_case(cs), case_id=cs, sale_item_no=mae, object_no=mok, minimum_price_source=minimum,
                      property_kind={'10000':'land','20000':'building'}.get(raw.get('lclsUtilCd')), usage=raw.get('dspslUsgNm'))
    if normalized['property_kind'] is None:
        reasons['property_kind'] = 'missing_or_unknown_classification'
    key = f'{court}|{cs}|{mae}|{mok}'
    return {'item_key':key, 'normalized':normalized, 'missing_reasons':reasons, 'raw':raw}


def response_data(body):
    if not isinstance(body, dict) or not isinstance(body.get('data'), dict):
        raise AuctionError('schema_changed')
    if body.get('status') not in (None, 0, '0', 200, '200'):
        raise AuctionError('source_error')
    return body['data']


def map_search(body, q, page):
    data = response_data(body)
    if not isinstance(data.get('dlt_srchResult'), list):
        raise AuctionError('schema_changed')
    rows = data['dlt_srchResult']
    if len(rows) > q['page_size']:
        raise AuctionError('unexpected_page_size')
    pageinfo = data.get('dma_pageInfo')
    if pageinfo is not None and not isinstance(pageinfo, dict):
        raise AuctionError('schema_changed')
    total_raw = (pageinfo or {}).get('totalCnt')
    total = number(total_raw)
    records = [map_item(row,q['court']) for row in rows]
    return {'ok':True,'status':'empty' if not rows else 'page','records':records,'page':page,'page_size':q['page_size'],'read_count':len(rows), 'source_total_count':total,'source_total_raw':scalar(total_raw),'source_total_reason':None if total is not None else ('missing_source_value' if total_raw in (None,'') else 'invalid_source_value'),'query':q,'snapshot_guarantee':False,'usage_filter_scope':'sale_item_with_associated_objects'}


BASIC_FIELDS = ('cortOfcCd','csNo','csNm','csRcptYmd','csCmdcYmd','csProgStatCd','csUltmtYmd','mvprpRletDvsCd')
PROPERTY_FIELDS = ('cortOfcCd','csNo','dspslGdsSeq','dspslObjctSeq','aeeEvlAmt','lclDspslGdsLstUsgCd','mclDspslGdsLstUsgCd','sclDspslGdsLstUsgCd','auctnGdsUsgCd','dspslDxdyYmd','fstPbancLwsDspslPrc','scndPbancLwsDspslPrc','thrdPbancLwsDspslPrc','fothPbancLwsDspslPrc','rdnmRefcAddr','rprsLtnoAddr','auctnLstNm','auctnLstDvsCd')
EVENT_FIELDS = ('cortOfcCd','csNo','dspslGdsSeq','dxdyYmd','dxdyHm','auctnDxdyKndCd','auctnDxdyRsltCd')


def check_identity(row, court, cs, required=False):
    if not isinstance(row,dict):
        raise AuctionError('schema_changed')
    if required and (not row.get('cortOfcCd') or not row.get('csNo')):
        raise AuctionError('missing_detail_identity')
    if row.get('cortOfcCd') and row['cortOfcCd'] != court:
        raise AuctionError('detail_identity_mismatch')
    if row.get('csNo') and case_id(row['csNo']) != cs:
        raise AuctionError('detail_identity_mismatch')


def map_detail(body, court, cs):
    cs = case_id(cs)
    data = response_data(body)
    basic = data.get('dma_csBasInf')
    check_identity(basic, court, cs, required=True)
    if basic.get('mvprpRletDvsCd') not in (None,'','00031R'):
        raise AuctionError('non_real_estate_response')
    result = {'ok':True,'court_code':court,'case_no':display_case(cs),'case_id':cs,'basic':pick(basic,BASIC_FIELDS),'sale_items':[],'objects':[],'events':[], 'source':'15A'}
    for source, target, fields in [('dlt_dspslGdsDspslObjctLst','sale_items',PROPERTY_FIELDS),('dlt_rletCsDspslObjctLst','objects',PROPERTY_FIELDS),('dlt_rletCsGdsDtsDxdyInf','events',EVENT_FIELDS)]:
        rows = data.get(source)
        if not isinstance(rows,list):
            raise AuctionError('schema_changed')
        for row in rows:
            check_identity(row,court,cs)
            raw = pick(row,fields)
            if target=='events':
                normalized, reasons = parsed_fields(raw,{'sale_item_no':('dspslGdsSeq',number),'sale_date':('dxdyYmd',day)})
                normalized['minimum_price'] = None
                reasons['minimum_price'] = 'no_verified_event_price_join'
            else:
                normalized, reasons = parsed_fields(raw,{'sale_item_no':('dspslGdsSeq',number),'object_no':('dspslObjctSeq',number),'appraisal_price':('aeeEvlAmt',number),'sale_date':('dspslDxdyYmd',day)})
                normalized['property_kind'] = {'10000':'land','20000':'building'}.get(raw.get('lclDspslGdsLstUsgCd'))
                if normalized['property_kind'] is None:
                    reasons['property_kind']='missing_or_unknown_classification'
                for prefix in ('fst','scnd','thrd','foth'):
                    field = prefix+'PbancLwsDspslPrc'
                    normalized[field] = number(raw.get(field))
                    if normalized[field] is None:
                        reasons[field] = 'missing_or_invalid_source_value'
            result[target].append({'raw':raw,'normalized':normalized,'missing_reasons':reasons})
    return result
