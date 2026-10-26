"""소재지 해석과 안전한 지역 폴더 이름. 법원 관할을 주소로 추정하지 않는다."""
import re
from .models import REGIONS, AuctionError, response_data

FULL_NAMES=dict(zip(REGIONS,('서울특별시','부산광역시','대구광역시','인천광역시','광주광역시','대전광역시','울산광역시','세종특별자치시','경기도','충청북도','충청남도','전라남도','경상북도','경상남도','제주특별자치도','강원특별자치도','전북특별자치도')))
ALIASES={**{v:k for k,v in REGIONS.items()},**{v:k for k,v in FULL_NAMES.items()},'강원도':'51','전라북도':'52'}


def region_id(value):
    code=ALIASES.get(value,value)
    if code not in REGIONS: raise AuctionError('invalid_region')
    return code


def location(raw):
    def text(key):
        v=raw.get(key)
        return v.strip() if isinstance(v,str) and v.strip() else None
    region=text('daepyoSidoCd') or text('rprsAdongSdCd')
    if region not in REGIONS: region=ALIASES.get(text('hjguSido'))
    district=text('daepyoSiguCd') or text('rprsAdongSggCd')
    if district and region and re.fullmatch(r'\d{3}',district): district=region+district
    if not (district and region and re.fullmatch(r'\d{5}',district) and district.startswith(region)):
        district=None
    parts=[text(k) for k in ('hjguSido','hjguSigu','hjguDong','daepyoLotno')]
    address=text('bgPlaceRdAllAddr') or (' '.join(p for p in parts if p) if any(parts) else None)
    return {'region_code':region,'region_name':REGIONS.get(region),'district_code':district,
            'district_name':text('hjguSigu'),'address':address}


def map_districts(body, region):
    rows=response_data(body).get('adongSggLst')
    if not isinstance(rows,list): raise AuctionError('schema_changed')
    result=[]; excluded=[]
    for row in rows:
        if not isinstance(row,dict): raise AuctionError('schema_changed')
        code=row.get('code'); name=row.get('name')
        if code in ('','000',None): continue  # 전체 항목은 UI에서 별도 제공
        if not isinstance(code,str) or not re.fullmatch(r'\d{3}',code) or not isinstance(name,str) or not name.strip():
            raise AuctionError('schema_changed')
        if region+code=='11745' and name.strip()=='테스트구':
            excluded.append({'code':region+code,'reason':'source_test_entry'})
            continue
        result.append({'code':region+code,'name':name.strip()})
    return {'ok':True,'region':region,'region_name':REGIONS[region],'districts':result,'excluded':excluded,'source':'official_live_codes'}


def folder_part(value):
    # 외부 문자열은 경로가 될 수 없다. Windows와 POSIX 모두에서 한 구성요소만 만든다.
    value=re.sub(r'[^가-힣A-Za-z0-9 _-]','_',str(value or '지역미확인')).strip(' .')[:70]
    return value or '지역미확인'


def folder_parts(record):
    n=record['normalized']; loc=location(record.get('raw',{}))
    region=n.get('region_name') or loc['region_name'] or '지역미확인'
    district=n.get('district_name') or loc['district_name'] or '시군구미확인'
    code=n.get('district_code') or loc['district_code']
    return folder_part(region),folder_part((code+'_' if code else '')+district)
