"""Catches wrong municipality, wrong forecast day/unit and plant/group conflation."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest


def req():
    return {'schema_version':'1.2-draft','request_id':str(uuid4()),'controller_id':'demo-local',
            'location_id':'gsi:13101','latitude':35.69,'longitude':139.75,
            'date':datetime.now(timezone(timedelta(hours=9))).date().isoformat(),
            'expires_at':(datetime.now(timezone.utc)+timedelta(seconds=20)).isoformat(),'is_mock':False}


class Reply:
    def __init__(self,data=None,text=''):self.data,self.text,self.encoding=data,text,'utf-8'
    def raise_for_status(self):pass
    def json(self):return self.data


class Session:
    def __init__(self,reply):self.reply=reply;self.calls=[]
    def get(self,url,**kwargs):self.calls.append((url,kwargs));return self.reply


def test_weather_uses_exact_date_ms_timezone_and_timeout():
    from weather.get_weather_data import get_weather
    r=req();s=Session(Reply({'daily':{'time':['2000-01-01',r['date']],
        'weather_code':[61,0],'wind_speed_10m_max':[99,3.5],
        'temperature_2m_mean':[0,20],'relative_humidity_2m_mean':[1,65]},
        'daily_units':{'wind_speed_10m_max':'m/s'},'timezone':'Asia/Tokyo'}))
    d=get_weather(r,session=s)
    assert d['provider_date']==r['date'] and d['wind_speed_max']==3.5
    assert d['weather_code']==0 and d['units']['wind_speed_max']=='m/s'
    assert s.calls[0][1]['params']['wind_speed_unit']=='ms'
    assert s.calls[0][1]['params']['timezone']=='Asia/Tokyo'
    assert 0<s.calls[0][1]['timeout']<=8


@pytest.mark.parametrize('daily',[
    {'time':['2000-01-01'],'weather_code':[0],'wind_speed_10m_max':[2]},
    {'time':[]}, {'time':[req()['date']],'weather_code':[None],'wind_speed_10m_max':[None]}])
def test_weather_rejects_wrong_day_or_no_core_data(daily):
    from weather.get_weather_data import get_weather
    from common.providers import ProviderError
    with pytest.raises(ProviderError):get_weather(req(),session=Session(Reply({'daily':daily})))


def test_pollen_reads_dailyinfo_and_preserves_group_and_species(monkeypatch):
    from pollen.get_pollen_data import get_pollen
    monkeypatch.setenv('GOOGLE_POLLEN_API_KEY','secret-test-only')
    r=req();y,m,d=map(int,r['date'].split('-'))
    s=Session(Reply({'regionCode':'JP','dailyInfo':[{'date':{'year':y,'month':m,'day':d},
        'pollenTypeInfo':[{'code':'TREE','displayName':'樹木','indexInfo':{'code':'UPI','value':5}},
                          {'code':'GRASS','displayName':'イネ科','indexInfo':{'code':'UPI','value':0}}],
        'plantInfo':[{'code':'JAPANESE_CEDAR','displayName':'スギ','indexInfo':{'code':'UPI','value':2}},
                     {'code':'JAPANESE_CYPRESS','displayName':'ヒノキ','indexInfo':{'code':'UPI','value':True}},
                     {'code':'BIRCH','displayName':'シラカバ'}]}]}))
    data=get_pollen(r,session=s)
    assert data['types'][0]['code']=='tree' and data['types'][0]['upi']==5
    assert data['types'][1]['upi']==0
    assert data['plants'][0]['code']=='sugi' and data['plants'][0]['upi']==2
    assert data['plants'][1]['upi'] is None and data['plants'][1]['availability']!='available'
    assert data['provider_timezone']=='UTC'
    assert s.calls[0][1]['params']['days']==5
    assert s.calls[0][1]['headers']['X-Goog-Api-Key']=='secret-test-only'
    assert 'secret-test-only' not in s.calls[0][0]


def test_missing_key_and_upstream_error_do_not_leak_credentials(monkeypatch):
    from pollen.get_pollen_data import get_pollen
    from common.providers import ProviderError
    monkeypatch.delenv('GOOGLE_POLLEN_API_KEY',raising=False)
    with pytest.raises(ProviderError) as e:get_pollen(req())
    assert e.value.code=='MISSING_API_KEY'
    monkeypatch.setenv('GOOGLE_POLLEN_API_KEY','secret-test-only')
    class Broken:
        def get(self,*a,**k):
            import requests
            raise requests.HTTPError('request?key=secret-test-only')
    with pytest.raises(ProviderError) as e:get_pollen(req(),session=Broken())
    assert 'secret-test-only' not in str(e.value)


def test_malformed_json_and_pollen_wrong_day_are_errors(monkeypatch):
    from pollen.get_pollen_data import get_pollen
    from common.providers import ProviderError
    monkeypatch.setenv('GOOGLE_POLLEN_API_KEY','secret-test-only')
    for data in [None,[],{'dailyInfo':[]},{'dailyInfo':[{'date':{'year':2000,'month':1,'day':1}}]}]:
        with pytest.raises(ProviderError):get_pollen(req(),session=Session(Reply(data)))


MUNI='''GSI.MUNI_ARRAY["13101"] = '13,東京都,13101,千代田区';
GSI.MUNI_ARRAY["12216"] = '12,千葉県,12216,習志野市';
GSI.MUNI_ARRAY["01233"] = '1,北海道,1233,伊達市';
GSI.MUNI_ARRAY["07213"] = '7,福島県,7213,伊達市';
GSI.MUNI_ARRAY["1101"] = '1,北海道,1101,札幌市　中央区';'''


class GeoSession:
    def get(self,url,**kwargs):
        if url.endswith('muni.js'):return Reply(text=MUNI)
        if 'reverse-geocoder' in url:return Reply({'results':{'muniCd':'13101','lv01Nm':'丸の内一丁目'}})
        assert kwargs['params']['q']=='東京都千代田区'
        return Reply([{'properties':{'title':'東京都千代田区'},
                       'geometry':{'type':'Point','coordinates':[139.753616,35.69389]}}])


def test_municipality_search_disambiguates_and_current_resolves_representative():
    from server.locations import Locations
    geo=Locations(session=GeoSession())
    c=geo.search('伊達市')
    assert {x['name'] for x in c}=={'北海道伊達市','福島県伊達市'}
    assert geo.search('札幌市中央区')[0]['candidate_id']=='gsi:01101'
    assert geo.search('unknown')==[]
    loc=geo.current(35.681252,139.767242)
    assert loc['name']=='東京都千代田区' and loc['municipality_code']=='13101'
    assert loc['latitude']==35.69389 and loc['longitude']==139.753616
    assert loc['latitude']!=35.681252


def test_location_rejects_foreign_and_forged_candidates():
    from server.locations import Locations
    from common.protocol import ProtocolError
    geo=Locations(session=GeoSession())
    for lat,lon in [(40,-74),(True,139),(float('nan'),139)]:
        with pytest.raises(ProtocolError):geo.current(lat,lon)
    with pytest.raises(ProtocolError):geo.resolve('gsi:99999')
    class Ocean(GeoSession):
        def get(self,url,**kwargs):
            if 'reverse-geocoder' in url:return Reply({})
            return super().get(url,**kwargs)
    with pytest.raises(ProtocolError):Locations(session=Ocean()).current(35,140)


def test_concurrent_catalog_failure_is_shared_and_waiters_have_deadline():
    from server.locations import Locations
    from common.protocol import ProtocolError
    from concurrent.futures import ThreadPoolExecutor
    import threading,time,requests
    entered=threading.Event();release=threading.Event();calls=[]
    class Failing:
        def get(self,url,**kwargs):
            calls.append(url);entered.set();release.wait(1)
            raise requests.Timeout('fixture only')
    geo=Locations(session=Failing())
    def lookup():
        start=time.monotonic()
        with pytest.raises(ProtocolError):geo.search('伊達市')
        return time.monotonic()-start
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(lookup) for _ in range(8)]
        assert entered.wait(1)
        # Wait until all request threads have had a chance to join this one fetch.
        time.sleep(.05);release.set()
        elapsed=[f.result(timeout=2) for f in futures]
    assert len(calls)==1
    assert max(elapsed)<.5
    class Slow:
        def get(self,url,**kwargs):
            time.sleep(.05);raise requests.Timeout('fixture')
    geo=Locations(session=Slow())
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(geo.search,'伊達市')
        time.sleep(.01);start=time.monotonic()
        with pytest.raises(ProtocolError) as exc:geo.search('伊達市',until=time.monotonic()+.01)
        assert exc.value.code=='TIMEOUT' and time.monotonic()-start<.04
        with pytest.raises(ProtocolError):first.result(timeout=1)


def test_original_weather_function_keeps_date_and_weather_fields():
    from weather.get_weather_data import weather_data_output
    request = req()
    session = Session(Reply({
        'daily': {
            'time': [request['date']],
            'weather_code': [0],
            'wind_speed_10m_max': [3.5],
            'temperature_2m_mean': [20],
            'relative_humidity_2m_mean': [65],
        },
        'daily_units': {'wind_speed_10m_max': 'm/s'},
        'timezone': 'Asia/Tokyo',
    }))
    result = weather_data_output(
        request['latitude'], request['longitude'], request['date'], session=session
    )
    assert result['time'] == request['date']
    assert result['temperature_mean'] == 20
    assert result['humidity_mean'] == 65
    assert result['wind_speed_max'] == 3.5
    assert result['weather_code'] == 0


def test_original_pollen_functions_fetch_format_and_return_same_information(monkeypatch):
    from pollen.get_pollen_data import get_pollen_data, format_pollen_data, get_pollen_info
    monkeypatch.setenv('GOOGLE_POLLEN_API_KEY', 'secret-test-only')
    request = req()
    year, month, day = map(int, request['date'].split('-'))
    raw = {
        'regionCode': 'JP',
        'dailyInfo': [{
            'date': {'year': year, 'month': month, 'day': day},
            'pollenTypeInfo': [{
                'code': 'GRASS', 'displayName': 'イネ科',
                'indexInfo': {'code': 'UPI', 'value': 0},
            }],
            'plantInfo': [],
        }],
    }
    session = Session(Reply(raw))
    fetched = get_pollen_data(request['latitude'], request['longitude'], session=session)
    formatted = format_pollen_data(fetched, request['date'])
    result = get_pollen_info(
        request['latitude'], request['longitude'], request['date'], session=session
    )
    for output in (formatted, result):
        assert output['provider_date'] == request['date']
        assert output['types'][0]['code'] == 'grass'
        assert output['types'][0]['upi'] == 0
        assert output['plants'][0]['upi'] is None


def test_weather_keeps_weather_when_wind_units_are_null():
    from weather.get_weather_data import get_weather
    request = req()
    session = Session(Reply({
        'daily': {
            'time': [request['date']],
            'weather_code': [0],
            'wind_speed_10m_max': [3.5],
            'temperature_2m_mean': [20],
            'relative_humidity_2m_mean': [65],
        },
        'daily_units': None,
        'timezone': 'Asia/Tokyo',
    }))
    result = get_weather(request, session=session)
    assert result['weather_code'] == 0
    assert result['wind_speed_max'] is None
    assert result['_warnings'][0]['message'] == '未取得：風速'
