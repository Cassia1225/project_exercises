"""Catches corrupt settings, repeated GPS events and automatic forecast calls."""
from pathlib import Path
import pytest


@pytest.mark.parametrize('raw',[None,'broken','[]','{"version":true,"allergy_state":"unknown","allergies":[]}',
    {'version':1,'allergy_state':'selected','allergies':['evil']},
    {'version':1,'allergy_state':'unknown','allergies':['sugi']}])
def test_invalid_saved_profile_restores_unknown(raw):
    from UI.state import restored_settings
    assert restored_settings(raw)=={'allergy_state':'unknown','allergies':[]}


def test_restore_and_delete_and_duplicate_event():
    from UI.state import consume_event
    state={}
    e={'id':'one','kind':'loaded','profile':{'version':1,'allergy_state':'selected','allergies':['hinoki']},'storage_ok':True}
    assert consume_event(state,e)['kind']=='loaded'
    assert state['allergies']==['hinoki'] and state['browser_ready']
    assert consume_event(state,e) is None
    consume_event(state,{'id':'two','kind':'deleted','storage_ok':True})
    assert state['allergies']==[]
    consume_event(state,{'id':'three','kind':'geo_error','message':'位置情報の利用が許可されませんでした。'})
    assert '位置情報' in state['browser_message']


class Response:
    status_code = 200

    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


def location_options():
    return {
        'candidates': [
            {'candidate_id': 'gsi:01233', 'name': '北海道伊達市', 'prefecture': '北海道', 'country_code': 'JP', 'municipality_code': '01233'},
            {'candidate_id': 'gsi:07213', 'name': '福島県伊達市', 'prefecture': '福島県', 'country_code': 'JP', 'municipality_code': '07213'},
            {'candidate_id': 'gsi:12204', 'name': '千葉県船橋市', 'prefecture': '千葉県', 'country_code': 'JP', 'municipality_code': '12204'},
            {'candidate_id': 'gsi:12216', 'name': '千葉県習志野市', 'prefecture': '千葉県', 'country_code': 'JP', 'municipality_code': '12216'},
            {'candidate_id': 'gsi:13101', 'name': '東京都千代田区', 'prefecture': '東京都', 'country_code': 'JP', 'municipality_code': '13101'},
        ],
        'errors': [],
    }


def get_options(url, **kwargs):
    assert url.endswith('/api/v1/locations/options')
    return Response(location_options())


def test_streamlit_initial_page_does_not_fetch_forecast(monkeypatch):
    from streamlit.testing.v1 import AppTest

    def forbidden(*args, **kwargs):
        raise AssertionError('no forecast before user action')

    monkeypatch.setattr('requests.get', get_options)
    monkeypatch.setattr('requests.post', forbidden)
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'UI/app.py'), default_timeout=10).run()
    assert not at.exception
    assert at.sidebar.header[0].value == '⚙️ ユーザー設定'
    assert len(at.sidebar.multiselect) == 1
    assert not at.sidebar.text_input
    assert at.multiselect[0].value == []
    assert at.selectbox(key='prefecture').options == ['北海道', '福島県', '千葉県', '東京都']
    assert at.selectbox(key='prefecture').value is None
    assert at.selectbox(key='municipality_candidate').disabled
    assert at.button(key='get_forecast').disabled
    assert [metric.label for metric in at.metric] == ['🌸 予想飛散量', '☀️ 天気予報', '💨 予想風速']
    assert all(metric.value == '未取得' for metric in at.metric)
    assert [checkbox.label for checkbox in at.checkbox if checkbox.key.startswith('countermeasure_')] == [
        '😷 花粉ガードマスクを着用した',
        '👓 メガネ・サングラスを着用した',
        '🧥 つるつるした素材の上着を選んだ',
        '🧹 帰宅時に花粉を払う準備（ブラシ等）',
    ]


def test_prefecture_filters_cities_and_clears_previous_choice(monkeypatch):
    from streamlit.testing.v1 import AppTest

    reads = []
    def get(url, **kwargs):
        reads.append(url)
        return get_options(url, **kwargs)

    monkeypatch.setattr('requests.get', get)
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'UI/app.py'))
    at.session_state['browser_ready'] = True
    at.run()
    at.selectbox(key='prefecture').select('千葉県').run()
    assert at.selectbox(key='municipality_candidate').options == ['船橋市', '習志野市']
    at.selectbox(key='municipality_candidate').select('gsi:12216').run()
    assert not at.button(key='get_forecast').disabled
    assert at.session_state['chosen_location']['candidate_id'] == 'gsi:12216'
    at.selectbox(key='prefecture').select('東京都').run()
    assert at.selectbox(key='municipality_candidate').options == ['千代田区']
    assert at.selectbox(key='municipality_candidate').value is None
    assert at.session_state['chosen_location'] is None
    assert at.button(key='get_forecast').disabled
    # 同名の市も、別の都道府県の候補を混ぜない。
    at.selectbox(key='prefecture').select('北海道').run()
    at.selectbox(key='municipality_candidate').select('gsi:01233').run()
    assert at.session_state['chosen_location']['name'] == '北海道伊達市'
    at.selectbox(key='prefecture').select('福島県').run()
    at.selectbox(key='municipality_candidate').select('gsi:07213').run()
    assert at.session_state['chosen_location']['name'] == '福島県伊達市'
    assert len(reads) == 1
    assert not at.exception


def test_streamlit_selection_and_partial_result(monkeypatch):
    from streamlit.testing.v1 import AppTest
    from recommend.service import assess
    from tests.test_assessment import payload

    posted = []
    def post(url, **kwargs):
        assert url.endswith('/api/v1/recommendations')
        posted.append(kwargs['json'])
        data = payload(['sugi', 'hinoki'])
        data['pollen']['plants'] = data['pollen']['plants'][:1]
        return Response(assess(data))

    monkeypatch.setattr('requests.get', get_options)
    monkeypatch.setattr('requests.post', post)
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'UI/app.py'), default_timeout=10)
    at.session_state['browser_ready'] = True
    at.run()
    at.selectbox(key='prefecture').select('東京都').run()
    at.selectbox(key='municipality_candidate').select('gsi:13101').run()
    at.multiselect(key='allergies').select('sugi').run()
    assert not posted
    at.button(key='get_forecast').click().run()
    assert not at.exception
    assert len(posted) == 1
    assert posted[0]['location_input'] == {'mode': 'search', 'candidate_id': 'gsi:13101'}
    assert posted[0]['allergies'] == ['sugi']
    assert any('暫定' in item.value for item in at.warning)
    assert any('デモ' in item.value for item in at.warning)
    assert len(at.dataframe) >= 1
    at.checkbox(key='countermeasure_0').check().run()
    at.selectbox(key='target_date').select(at.selectbox(key='target_date').options[1]).run()
    at.selectbox(key='prefecture').select('千葉県').run()
    assert len(posted) == 1
    area_card = next(block.value for block in at.markdown if '確認中の対象エリア・日程' in block.value)
    assert '東京都千代田区' in area_card and '今日 (' in area_card
    assert at.button(key='get_forecast').disabled
    advice_card = next(block.value for block in at.markdown if 'からだケアのアドバイス' in block.value)
    assert 'マスクを着用する' in advice_card


def test_current_location_sets_both_dropdowns(monkeypatch):
    from streamlit.testing.v1 import AppTest

    events = [{'id': 'gps-once', 'kind': 'geo', 'latitude': 35.681252, 'longitude': 139.767242, 'accuracy_m': 20}]
    def bridge(*args, **kwargs):
        return events.pop(0) if events else None
    def post(url, **kwargs):
        assert url.endswith('/api/v1/locations/current')
        assert kwargs['json'] == {'latitude': 35.681252, 'longitude': 139.767242}
        return Response({'location': dict(location_options()['candidates'][-1], latitude=35.69, longitude=139.75)})

    monkeypatch.setattr('UI.browser.browser_bridge', bridge)
    monkeypatch.setattr('requests.get', get_options)
    monkeypatch.setattr('requests.post', post)
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'UI/app.py'))
    at.session_state['browser_ready'] = True
    at.run()
    assert not at.exception
    assert at.selectbox(key='prefecture').value == '東京都'
    assert at.selectbox(key='municipality_candidate').value == 'gsi:13101'
    assert not at.button(key='get_forecast').disabled


def test_location_options_failure_can_retry_without_forecast(monkeypatch):
    from streamlit.testing.v1 import AppTest

    def unavailable(url, **kwargs):
        raise __import__('requests').ConnectionError('fixture')
    def forbidden(*args, **kwargs):
        raise AssertionError('must not fetch forecast')

    monkeypatch.setattr('requests.get', unavailable)
    monkeypatch.setattr('requests.post', forbidden)
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'UI/app.py'))
    at.session_state['browser_ready'] = True
    at.run()
    assert not at.exception
    assert at.selectbox(key='prefecture').disabled
    assert at.button(key='get_forecast').disabled
    monkeypatch.setattr('requests.get', get_options)
    at.button(key='reload_locations').click().run()
    assert at.selectbox(key='prefecture').options == ['北海道', '福島県', '千葉県', '東京都']
    assert not at.exception
