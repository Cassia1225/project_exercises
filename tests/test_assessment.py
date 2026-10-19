"""Catches wrong UPI grouping, missing-data substitution and crossed search replies."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest


def entry(code, upi, availability='available'):
    return dict(code=code, provider_code=code.upper(), name=code, upi=upi, availability=availability)


def payload(allergies=None):
    return {'schema_version':'1.2-draft','request_id':str(uuid4()),
            'location':{'location_id':'gsi:13101','name':'東京都千代田区'},
            'date':datetime.now(timezone(timedelta(hours=9))).date().isoformat(),
            'allergy_state':'selected' if allergies else 'unknown','allergies':allergies or [],
            'is_mock':True,'weather':{'weather_code':0,'wind_speed_max':2.0},
            'pollen':{'types':[entry('tree',4)], 'plants':[entry('sugi',2),entry('hinoki',0)]},
            'errors':[], 'warnings':[]}


@pytest.mark.parametrize('upi,want',[(0,'低'),(1,'低'),(2,'中'),(3,'中'),(4,'高'),(5,'非常に高い')])
def test_upi_boundaries(upi,want):
    from recommend.service import assess
    p=payload(['sugi']);p['pollen']['plants'][0]['upi']=upi
    r=assess(p)
    assert r['data']['level']==want
    assert r['status']=='success'
    assert set(r['data'])=={'location','date','level','pollen','weather','wind','items','reason'}


@pytest.mark.parametrize('bad',[True,False,None,-1,6,2.5,'4',float('nan'),10**309])
def test_invalid_upi_is_not_used(bad):
    from recommend.service import assess
    p=payload(['sugi']);p['pollen']['plants'][0]['upi']=bad
    r=assess(p)
    assert r['data']['level'] is None
    assert r['status']=='partial'
    assert r['details']['regional_reference']['level']=='高'


def test_selected_max_partial_and_all_missing():
    from recommend.service import assess
    p=payload(['sugi','hinoki']);p['pollen']['plants'][0]['upi']=3
    assert assess(p)['data']['level']=='中'
    p['pollen']['plants'][1]=entry('hinoki',None,'missing')
    r=assess(p)
    assert r['data']['level']=='中' and r['meta']['is_provisional']
    assert r['meta']['unavailable_allergies']==['hinoki']
    p['pollen']['plants']=[]
    r=assess(p)
    assert r['data']['level'] is None and r['meta']['personalization_status']=='unavailable'
    assert r['details']['regional_reference']['level']=='高'


def test_general_uses_types_never_substitutes_plant():
    from recommend.service import assess
    p=payload();assert assess(p)['data']['level']=='高'
    p['pollen']['types']=[]
    assert assess(p)['data']['level'] is None


def test_weather_does_not_change_level_or_pollen_provisional_status():
    from recommend.service import assess
    p=payload(['sugi']);a=assess(p)
    p['weather']['wind_speed_max']=20
    b=assess(p)
    assert a['data']['level']==b['data']['level']=='中'
    assert a['data']['items']!=b['data']['items']
    p['weather']=None;r=assess(p)
    assert r['status']=='partial' and r['data']['level']=='中'
    assert r['meta']['is_provisional'] is False
    p['pollen']=None;r=assess(p)
    assert r['status']=='error' and r['data'] is None


def test_weather_only_keeps_information_without_level():
    from recommend.service import assess
    p=payload();p['pollen']=None;r=assess(p)
    assert r['status']=='partial' and r['data']['level'] is None
    assert r['data']['weather']!='未取得'


def test_future_advisor_can_only_change_items():
    from recommend.service import assess
    p=payload(['sugi'])
    r=assess(p,advisor=lambda context:['マスクを持参する'])
    assert r['data']['level']=='中'
    assert r['data']['items']==['マスクを持参する']
    r=assess(p,advisor=lambda context:['処方薬を服用する'])
    assert r['data']['level']=='中' and r['meta']['recommendation_source']=='rule'


def test_query_validation_rejects_invalid_date_settings_and_location():
    from common.protocol import validate_query, ProtocolError
    p=payload();p['location_input']={'mode':'search','candidate_id':'gsi:13101'}
    assert validate_query(p)['allergy_state']=='unknown'
    for updates in [{'allergy_state':'selected','allergies':[]},{'allergies':['evil']},
                    {'date':'2020-01-01'},{'location_input':{'mode':'current','latitude':True,'longitude':139}},
                    {'schema_version':'1.0'}]:
        with pytest.raises(ProtocolError):validate_query(dict(p,**updates))


def test_correlated_reply_checks_every_field_and_expiry():
    from common.protocol import matches_result, validate_worker_request, ProtocolError
    req={'schema_version':'1.2-draft','request_id':str(uuid4()),'controller_id':'demo-local',
         'location_id':'gsi:13101','latitude':35.69,'longitude':139.75,
         'date':payload()['date'],'expires_at':(datetime.now(timezone.utc)+timedelta(seconds=20)).isoformat(),
         'is_mock':True}
    validate_worker_request(req)
    reply={k:req[k] for k in ['schema_version','request_id','controller_id','location_id','date','is_mock']}
    reply.update(source='pollen',status='success',data={},errors=[],warnings=[],fetched_at=datetime.now(timezone.utc).isoformat())
    assert matches_result(reply,req,'pollen')
    for field,value in [('request_id',str(uuid4())),('date','2000-01-01'),('location_id','gsi:12216'),
                         ('source','weather'),('schema_version','1.0'),('is_mock',False),('status','partial')]:
        assert not matches_result(dict(reply,**{field:value}),req,'pollen')
    expired=dict(req,expires_at='2020-01-01T00:00:00+00:00')
    assert not matches_result(reply,expired,'pollen')
    with pytest.raises(ProtocolError):validate_worker_request(dict(req,controller_id='../+'))


def test_informational_mock_and_advisor_warnings_do_not_claim_missing_data():
    from recommend.service import assess
    p=payload(['sugi']);p['warnings']=[{'source':'pollen','code':'MOCK_DATA','message':'架空値'}]
    assert assess(p)['status']=='success'
    p['warnings']=[]
    r=assess(p,advisor=lambda context:['処方薬を服用する'])
    assert r['status']=='success' and r['meta']['recommendation_source']=='rule'
    assert r['warnings'][0]['code']=='ADVISOR_FALLBACK'
