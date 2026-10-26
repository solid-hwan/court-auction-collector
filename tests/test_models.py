import json
import unittest
from court_auction_mcp.models import *
from fixtures import item, search, detail, QUERY

class ModelTests(unittest.TestCase):
    def test_amount_strict(self):
        for v in (True,False,-1,1.5,'1.5','-10','1,00','1억원','100원','1e3','  ',{},'01'):
            with self.subTest(value=v): self.assertIsNone(number(v))
        for v,e in [('1,000',1000),('0',0),(0,0),(100,100),(' 200 ',200)]: self.assertEqual(number(v),e)

    def test_calendar_strict(self):
        for v in ('20260229','20261301','2026-2-01','2026-02-30','20260100','garbage',20260101): self.assertIsNone(day(v))
        self.assertEqual(day('20240229'),'2024-02-29')

    def test_case_roundtrip(self):
        self.assertEqual(case_id('2099타경123'),'20990130000123')
        self.assertEqual(display_case('20990130000123'),'2099타경123')
        for v in ('2099하단123','2099타경1234567','2099타경0','abcd0130000123',None):
            with self.assertRaises(AuctionError): case_id(v)

    def test_multiplot_and_crosscourt(self):
        a=map_item(item()); b=map_item(item(mok=2)); c=map_item(item(jiwonNm='서울동부지방법원'))
        self.assertEqual(len({a['item_key'],b['item_key'],c['item_key']}),3)

    def test_missing_and_invalid_not_zero(self):
        r=map_item(item(gamevalAmt=None,yuchalCnt='',notifyMinmaePrice1='12.5',maeGiil='20260230'))
        for k in ('appraisal_price','fail_count','minimum_price','sale_date'):
            self.assertIsNone(r['normalized'][k]); self.assertIn(k,r['missing_reasons'])
        self.assertEqual(r['raw']['notifyMinmaePrice1'],'12.5')
        self.assertEqual(map_item(item(gamevalAmt=1.5))['raw']['gamevalAmt'],1.5)

    def test_zero_preserved(self):
        r=map_item(item(gamevalAmt='0',notifyMinmaePrice1='0'))
        self.assertEqual(r['normalized']['minimum_price'],0)
        self.assertEqual(r['normalized']['fail_count'],0)

    def test_fallback_price_explicit(self):
        r=map_item(item(notifyMinmaePrice1=''))
        self.assertEqual(r['normalized']['minimum_price'],90000000)
        self.assertEqual(r['normalized']['minimum_price_source'],'minmaePrice')

    def test_search_identity(self):
        for row in (item(jiwonNm=''),item(maemulSer=None),item(mokmulSer=None)):
            with self.assertRaises(AuctionError): map_item(row)
        with self.assertRaises(AuctionError): map_item(item(),'B000211')

    def test_search_schema_and_total(self):
        q=query(QUERY)
        r=map_search(search(total='unknown'),q,1)
        self.assertIsNone(r['source_total_count']); self.assertEqual(r['source_total_reason'],'invalid_source_value')
        for bad in ({},{'data':{}},{'status':500,'data':{'dlt_srchResult':[]}}):
            with self.assertRaises(AuctionError): map_search(bad,q,1)
        self.assertEqual(map_search(search([],total='0'),q,1)['status'],'empty')

    def test_all_includes_land_and_building(self):
        q=query(QUERY)
        self.assertEqual(search_body(q,1)['dma_srchGdsDtlSrchInfo']['lclDspslGdsLstUsgCd'],'')
        self.assertEqual(map_item(item(lclsUtilCd='10000'))['normalized']['property_kind'],'land')
        self.assertEqual(map_item(item(lclsUtilCd='20000'))['normalized']['property_kind'],'building')

    def test_query_validation(self):
        bad=[{}, {**QUERY,'start':'20260230'}, {**QUERY,'end':'2020-01-01'}, {**QUERY,'court':'서울'}, {**QUERY,'page_size':True}, {**QUERY,'page_size':101}, {**QUERY,'arbitrary':'x'}, {**QUERY,'minimum_min':100,'minimum_max':10}, {**QUERY,'failures_min':-1}, {**QUERY,'district':'11110'}, {**QUERY,'usage':'car'}]
        for q in bad:
            with self.subTest(q=q),self.assertRaises(AuctionError): query(q)

    def test_filter_request_mapping(self):
        q=query({**QUERY,'court':None,'region':'11','district':'11110','usage':'land','appraisal_min':1,'appraisal_max':10,'minimum_min':0,'minimum_max':5,'failures_min':1,'failures_max':3})
        body=search_body(q,2)
        f=body['dma_srchGdsDtlSrchInfo']
        self.assertEqual(f['rprsAdongSggCd'],'11110'); self.assertEqual(f['lclDspslGdsLstUsgCd'],'10000')
        self.assertEqual(f['aeeEvlAmtMax'],'10'); self.assertEqual(f['lwsDspslPrcMin'],'0'); self.assertEqual(f['flbdNcntMax'],'3')
        self.assertEqual(body['dma_pageInfo']['pageNo'],2)

    def test_detail_identity_and_no_unproven_join(self):
        r=map_detail(detail(),'B000210','2099타경123')
        self.assertEqual(len(r['sale_items']),2)
        for event in r['events']: self.assertIsNone(event['normalized']['minimum_price'])
        self.assertIsNone(r['events'][0]['normalized']['sale_item_no'])
        for field,value in [('csNo','20990130000124'),('cortOfcCd','B000211')]:
            d=detail(); d['data']['dma_csBasInf'][field]=value
            with self.assertRaises(AuctionError): map_detail(d,'B000210','2099타경123')
        d=detail(); d['data']['dlt_rletCsGdsDtsDxdyInf'][0]['csNo']='2099타경999'
        with self.assertRaises(AuctionError): map_detail(d,'B000210','2099타경123')

    def test_private_fields_removed(self):
        r=map_detail(detail(),'B000210','2099타경123')
        self.assertNotIn('DO_NOT_STORE',json.dumps(r))
        self.assertNotIn('DO_NOT_STORE',json.dumps(map_item(item())))
        self.assertNotIn('token',json.dumps(map_item(item())))

    def test_building_filter_keeps_associated_land(self):
        q=query({**QUERY,'usage':'building'})
        r=map_search(search([item(lclsUtilCd='10000',dspslUsgNm='단독주택'),item(mok=2,lclsUtilCd='20000',dspslUsgNm='단독주택')]),q,1)
        self.assertEqual(len(r['records']),2)
        self.assertEqual(r['records'][0]['normalized']['property_kind'],'land')
        self.assertEqual(r['usage_filter_scope'],'sale_item_with_associated_objects')
