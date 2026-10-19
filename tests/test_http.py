"""HTTP tests exercise our validation, aggregation and error envelopes."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from threading import Thread
import requests


@contextmanager
def serving(app):
    from common.http_api import make_server
    server=make_server(app,host='127.0.0.1',port=0)
    t=Thread(target=server.serve_forever,daemon=True);t.start()
    try:yield f'http://127.0.0.1:{server.server_port}'
    finally:server.shutdown();server.server_close();t.join(timeout=2)


def query():
    return {'schema_version':'1.2-draft','location_input':{'mode':'search','candidate_id':'gsi:13101'},
            'date':datetime.now(timezone(timedelta(hours=9))).date().isoformat(),
            'allergy_state':'unknown','allergies':[]}


class Geo:
    def search(self,q):return [{'candidate_id':'gsi:13101','name':'東京都千代田区'}]
    def resolve(self,c,*,until=None):return {'location_id':c,'name':'東京都千代田区','latitude':35.69,'longitude':139.75}
    def current(self,lat,lon,*,until=None):return self.resolve('gsi:13101')


class Collector:
    def collect(self,location,date,is_mock,request_id=None,*,until=None):
        r={s:{'schema_version':'1.2-draft','request_id':request_id,'location_id':location['location_id'],
              'date':date,'status':'success','source':s,'data':{},'errors':[],'warnings':[],
              'is_mock':is_mock,'fetched_at':datetime.now(timezone.utc).isoformat()}
           for s in ('weather','pollen')}
        r['weather']['data']={'weather_code':0,'wind_speed_max':2,'provider_date':date}
        r['pollen']['data']={'types':[{'code':'tree','name':'樹木','availability':'available','upi':4}],
                            'plants':[],'provider_date':date}
        return r


def test_http_aggregation_calls_independent_recommender():
    from server.controller import Controller
    from recommend.api import RecommendationApp
    from server.api import ControllerApp
    with serving(RecommendationApp()) as recommendation:
        ctl=Controller(locations=Geo(),collector=Collector(),recommend_url=recommendation,is_mock=True)
        with serving(ControllerApp(ctl)) as url:
            assert requests.get(url+'/health',timeout=2).json()['mode']=='demo'
            candidates=requests.get(url+'/api/v1/locations',params={'query':'千代田区'},timeout=2).json()
            assert candidates['candidates'][0]['name']=='東京都千代田区'
            result=requests.post(url+'/api/v1/recommendations',json=query(),timeout=2)
            assert result.status_code==200
            data=result.json()
            assert data['data']['level']=='高' and data['meta']['is_mock']
            assert data['details']['location']['location_id']=='gsi:13101'


def test_invalid_http_json_schema_and_method_have_structured_errors():
    from server.controller import Controller
    from server.api import ControllerApp
    with serving(ControllerApp(Controller(locations=Geo(),collector=Collector()))) as url:
        for body in [None,[],{},dict(query(),date='2020-01-01')]:
            r=requests.post(url+'/api/v1/recommendations',json=body,timeout=2)
            assert r.status_code==400 and r.json()['status']=='error'
        r=requests.post(url+'/api/v1/recommendations',data='{"bad":NaN}',headers={'Content-Type':'application/json'},timeout=2)
        assert r.status_code==400
        assert requests.get(url+'/unknown',timeout=2).status_code==404


def test_recommender_stopped_is_reported_and_both_workers_missing_skip_it():
    from server.controller import Controller
    from server.api import ControllerApp
    with serving(ControllerApp(Controller(locations=Geo(),collector=Collector(),recommend_url='http://127.0.0.1:1'))) as url:
        r=requests.post(url+'/api/v1/recommendations',json=query(),timeout=4)
        assert r.status_code==502 and r.json()['errors'][0]['source']=='recommend'
    class Empty:
        def collect(self,*a,**k):return {}
    c=Controller(locations=Geo(),collector=Empty(),recommend_url='http://127.0.0.1:1')
    status,r=c.recommend(query())
    assert status==504 and {x['source'] for x in r['errors']}=={'weather','pollen'}


def test_controller_passes_one_deadline_through_every_stage():
    from server.controller import Controller
    from common.protocol import ProtocolError
    import time
    seen=[]
    class TimedGeo(Geo):
        def resolve(self,c,*,until=None):
            assert until is not None;seen.append(until)
            return super().resolve(c)
    class TimedCollector:
        def collect(self,*args,until=None,**kwargs):
            assert until==seen[0]
            while time.monotonic()<until:time.sleep(.001)
            raise ProtocolError('TIMEOUT','期限超過','mqtt')
    start=time.monotonic()
    c=Controller(locations=TimedGeo(),collector=TimedCollector(),request_timeout=.02)
    status,result=c.recommend(query())
    assert status==504 and result['errors'][0]['code']=='TIMEOUT'
    assert time.monotonic()-start<.1


def test_location_outage_uses_upstream_status_and_recommend_timeout_is_504():
    from server.controller import Controller
    from server.api import ControllerApp
    from common.providers import ProviderError
    import time
    class Unavailable(Geo):
        def search(self,q):raise ProviderError('LOCATION_SERVICE_ERROR','一覧を取得できません。','location')
    with serving(ControllerApp(Controller(locations=Unavailable(),collector=Collector()))) as url:
        r=requests.get(url+'/api/v1/locations',params={'query':'千代田区'},timeout=2)
        assert r.status_code==502 and r.json()['errors'][0]['source']=='location'
    class SlowRecommendation:
        def dispatch(self,*args):time.sleep(.15);return 200,{}
    with serving(SlowRecommendation()) as url:
        c=Controller(locations=Geo(),collector=Collector(),recommend_url=url,request_timeout=.02)
        status,r=c.recommend(query())
        assert status==504 and r['errors'][0]['source']=='recommend'



def test_location_options_returns_all_cities_without_search_limit():
    from server.controller import Controller
    from server.api import ControllerApp

    class CatalogGeo(Geo):
        def catalog(self):
            result = {}
            for index in range(60):
                code = f'13{index:03d}'
                result[code] = {
                    'candidate_id': 'gsi:' + code,
                    'name': '東京都市区町村' + str(index),
                    'prefecture': '東京都',
                    'country_code': 'JP',
                    'municipality_code': code,
                }
            return result

    with serving(ControllerApp(Controller(locations=CatalogGeo(), collector=Collector()))) as url:
        response = requests.get(url + '/api/v1/locations/options', timeout=2)
        assert response.status_code == 200
        data = response.json()
        assert len(data['candidates']) == 60
        assert data['candidates'][-1]['candidate_id'] == 'gsi:13059'
        assert data['candidates'][0]['prefecture'] == '東京都'
