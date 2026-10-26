"""가상 응답만 사용. 실제 경매 물건·개인정보 없음."""
from copy import deepcopy

QUERY={'court':'B000210','start':'2026-10-26','end':'2026-11-30','page_size':2}


def item(mae=1,mok=1,**overrides):
    return {'srnSaNo':'2099타경123','jiwonNm':'서울중앙지방법원','maemulSer':str(mae),'mokmulSer':str(mok),'gamevalAmt':'100,000,000','notifyMinmaePrice1':'80,000,000','minmaePrice':'90,000,000','yuchalCnt':'0','maeGiil':'20261030','lclsUtilCd':'20000','dspslUsgNm':'가상건물','bgPlaceRdAllAddr':'가상주소','intrpsNm':'DO_NOT_STORE_PERSON','token':'DO_NOT_STORE_TOKEN',**overrides}


def search(items=None,total='3'):
    return {'status':200,'token':'DO_NOT_STORE_ENVELOPE','data':{'dlt_srchResult':items if items is not None else [item(),item(mok=2)],'dma_pageInfo':{'totalCnt':total}}}


def detail():
    identity={'cortOfcCd':'B000210','csNo':'20990130000123'}
    return {'status':200,'token':'DO_NOT_STORE_ENVELOPE','data':{
        'dma_csBasInf':{**identity,'csNm':'가상 부동산경매','mvprpRletDvsCd':'00031R','jdgeAojAsstnNm':'DO_NOT_STORE_PERSON','jdbnTelno':'DO_NOT_STORE_PHONE'},
        'dlt_dspslGdsDspslObjctLst':[{**identity,'dspslGdsSeq':'1','dspslObjctSeq':'1','lclDspslGdsLstUsgCd':'10000','aeeEvlAmt':'120000000','fstPbancLwsDspslPrc':'90000000'}, {**identity,'dspslGdsSeq':'2','dspslObjctSeq':'2','lclDspslGdsLstUsgCd':'20000','aeeEvlAmt':'220000000','fstPbancLwsDspslPrc':'190000000'}],
        'dlt_rletCsDspslObjctLst':[{**identity,'dspslObjctSeq':'1'},{**identity,'dspslObjctSeq':'2'}],
        'dlt_rletCsGdsDtsDxdyInf':[{**identity,'dxdyYmd':'20261101'},{**identity,'dspslGdsSeq':'2','dxdyYmd':'20261102'}],
        'dlt_rletCsIntrpsLst':[{'intrpsNm':'DO_NOT_STORE_PERSON','auctnIntrpsDvsNm':'임차인'}]}}
