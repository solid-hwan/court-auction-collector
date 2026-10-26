import httpx
import unittest
import test_collection
from fixtures import QUERY,search,item

class ChallengeTests(unittest.TestCase):
    setUp = test_collection.CollectionTests.setUp
    tearDown = test_collection.CollectionTests.tearDown
    service = test_collection.CollectionTests.service
    def test_false_captcha_and_business_maintenance_are_normal(self):
        for flag in (False,'false','FALSE',0,None):
            body=search([item(buldNm='가상 유지보수 건물',dspslUsgNm='captcha 연구소')],1)
            body['captcha']=flag
            result=self.service(lambda r:httpx.Response(200,json=body)).collect('safe'+str(flag),QUERY)
            self.assertEqual(result['status'],'complete')
            self.assertFalse(result['host_blocked'])

    def test_true_json_challenge_stops(self):
        for n,body in enumerate(({'captcha':True},{'captchaRequired':'true'},{'data':{'ipcheck':False}},{'status':403,'message':'access denied'})):
            # 각 가상 상황에 독립 DB 사용. 실제 차단 우회와 무관.
            service=self.service(lambda r:httpx.Response(200,json=body))
            service.db=self.path/f'blocked{n}.sqlite3'
            self.assertEqual(service.collect('a',QUERY)['status'],'blocked')
