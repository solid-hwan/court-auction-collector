import unittest
from court_auction_mcp.models import query, search_body, map_search, AuctionError
from fixtures import QUERY, item, search

class RegionTests(unittest.TestCase):
    def test_region_request_uses_location_mode_and_three_digit_district(self):
        q=query({'region':'11','district':'11680','start':'2026-11-01','end':'2026-11-30'})
        f=search_body(q,1)['dma_srchGdsDtlSrchInfo']
        self.assertEqual(f['cortStDvs'],'2')
        self.assertEqual(f['rprsAdongSggCd'],'680')
        self.assertEqual(f['rprsAdongSdCd'],'11')

    def test_court_and_region_are_alternative_modes(self):
        with self.assertRaises(AuctionError): query({**QUERY,'region':'11'})

    def test_mismatched_filters_stop_instead_of_claiming_success(self):
        for q,row in [(QUERY,item(maeGiil='20200101')),({**QUERY,'appraisal_min':200000000},item()),({**QUERY,'minimum_max':100},item()),({**QUERY,'failures_min':1},item()),({'region':'11','district':'11680','start':QUERY['start'],'end':QUERY['end']},item(hjguSido='서울특별시',hjguSigu='관악구',rprsAdongSggCd='620',rprsAdongSdCd='11'))]:
            with self.subTest(query=q),self.assertRaises(AuctionError): map_search(search([row],1),query(q),1)

    def test_unknown_is_not_verified(self):
        r=map_search(search([item(maeGiil=None)],1),query(QUERY),1)
        self.assertEqual(r['records'][0]['filter_check']['unverified'],['sale_date'])
        self.assertFalse(r['filters_verified'])


    def test_official_test_district_is_explicitly_excluded(self):
        from court_auction_mcp.regions import map_districts
        body={'data':{'adongSggLst':[{'code':'680','name':'강남구'},{'code':'745','name':'테스트구'}]}}
        r=map_districts(body,'11')
        self.assertEqual(r['districts'],[{'code':'11680','name':'강남구'}])
        self.assertEqual(r['excluded'],[{'code':'11745','reason':'source_test_entry'}])
