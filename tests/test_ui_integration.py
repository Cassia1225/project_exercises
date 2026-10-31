"""旧UIの追加意図と現行MQTT仕様の結合を確認する。外部APIは固定応答。"""
from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from common import locations
import mqtt_client
from recommend import _allergy_matches
from get_weather_data import get_weather

APP = Path(__file__).resolve().parents[1] / 'UI' / 'app.py'


def test_overseas_location_uses_resolved_coordinates(monkeypatch):
    response = Mock()
    response.json.return_value = {'results': [
        {'name': 'Paris', 'admin1': 'Île-de-France', 'country': 'France',
         'latitude': 48.85, 'longitude': 2.35},
    ]}
    get = Mock(return_value=response)
    monkeypatch.setattr(locations.requests, 'get', get)
    result = locations.find_location('Paris, France')
    assert result['latitude'] == 48.85
    assert result['longitude'] == 2.35
    assert result['name'] == 'Paris, Île-de-France, France'
    assert get.call_args.kwargs['params']['name'] == 'Paris, France'
    assert get.call_args.kwargs['timeout'] == 5


def test_ambiguous_city_is_not_silently_selected(monkeypatch):
    response = Mock()
    response.json.return_value = {'results': [
        {'name': 'Springfield', 'admin1': 'Illinois', 'country': 'United States', 'latitude': 1, 'longitude': 2},
        {'name': 'Springfield', 'admin1': 'Missouri', 'country': 'United States', 'latitude': 3, 'longitude': 4},
    ]}
    monkeypatch.setattr(locations.requests, 'get', Mock(return_value=response))
    with pytest.raises(ValueError, match='複数'):
        locations.find_location('Springfield, USA')


def test_overseas_city_not_found(monkeypatch):
    response = Mock()
    response.json.return_value = {}
    monkeypatch.setattr(locations.requests, 'get', Mock(return_value=response))
    assert locations.find_location('NoSuchCity, France') is None


@pytest.mark.parametrize(('allergy', 'group'), [('ヨモギ', 'weed'), ('オーク', 'tree'), ('シラカバ', 'tree'), ('カモガヤ', 'grass')])
def test_new_labels_reach_existing_group_matching(allergy, group):
    assert _allergy_matches([allergy], {group}) == [allergy]


def test_forecast_uses_location_timezone(monkeypatch):
    response = Mock()
    response.json.return_value = {'daily': {'time': []}}
    get = Mock(return_value=response)
    monkeypatch.setattr('get_weather_data.requests.get', get)
    assert get_weather(48.85, 2.35, '2026-10-26') is None
    assert get.call_args.kwargs['params']['timezone'] == 'auto'


def reply(location, target_date, allergies):
    return {'status': 'success', 'data': {
        'location': location, 'date': target_date, 'level': '低', 'Pollen': '少ない',
        'weather': '晴れ', 'Wind': '1 m/s', 'items': ['マスク'], 'reason': '試験用の理由',
    }, 'errors': []}


def test_ui_sends_canonical_allergies_only_when_clicked_and_keeps_result(monkeypatch):
    ask = Mock(side_effect=reply)
    monkeypatch.setattr(mqtt_client, 'ask_server', ask)
    app = AppTest.from_file(str(APP)).run()
    assert not app.exception
    assert len(app.button) == 1
    assert not ask.called
    app.multiselect[0].set_value(['スギ', 'ヨモギ', 'オーク']).run()
    app.button[0].click().run()
    assert not app.exception
    assert ask.call_count == 1
    assert ask.call_args.args[2] == ['スギ', 'ヨモギ', 'オーク']
    heading = next(m.value for m in app.markdown if 'の花粉警戒度' in m.value)
    app.selectbox(key='forecast_date').select_index(1).run()
    app.multiselect[0].set_value(['ブタクサ']).run()
    assert ask.call_count == 1
    assert next(m.value for m in app.markdown if 'の花粉警戒度' in m.value) == heading
    assert any('スギ' in w.value and 'オーク' in w.value for w in app.info)
    app.checkbox[0].check().run()
    assert ask.call_count == 1


def test_ui_overseas_preset_and_empty_input(monkeypatch):
    ask = Mock(side_effect=reply)
    monkeypatch.setattr(mqtt_client, 'ask_server', ask)
    app = AppTest.from_file(str(APP)).run()
    app.radio[0].set_value('海外主要都市').run()
    app.selectbox(key='overseas_city').set_value('Paris, France').run()
    app.button[0].click().run()
    assert not app.exception
    assert ask.call_args.args[0] == 'Paris, France'
    app.selectbox(key='overseas_city').set_value('直接入力する').run()
    app.text_input[0].set_value('   ').run()
    app.button[0].click().run()
    assert ask.call_count == 1
    assert any('都市名' in e.value for e in app.error)


@pytest.mark.parametrize('status', ['error', 'partial'])
def test_ui_keeps_error_and_partial_handling(monkeypatch, status):
    result = reply('Paris, France', '2026-10-26', [])
    result['status'] = status
    result['pollen_is_mock'] = True
    result['errors'] = [{'source': 'server', 'message': '試験用エラー'}]
    if status == 'error':
        result['data'] = None
    monkeypatch.setattr(mqtt_client, 'ask_server', Mock(return_value=result))
    app = AppTest.from_file(str(APP)).run()
    app.button[0].click().run()
    assert not app.exception
    if status == 'error':
        assert any('試験用エラー' in e.value for e in app.error)
    else:
        assert any('一部' in w.value for w in app.warning)
        assert any('ダミー' in w.value for w in app.warning)


@pytest.mark.parametrize(('name', 'city', 'country'), [('New York, USA', 'New York', 'US'), ('London, UK', 'London', 'GB'), ('New York, New York, USA', 'New York, New York', 'US')])
def test_country_abbreviations_use_api_country_codes(monkeypatch, name, city, country):
    response = Mock()
    response.json.return_value = {'results': []}
    get = Mock(return_value=response)
    monkeypatch.setattr(locations.requests, 'get', get)
    locations.find_location(name)
    assert get.call_args.kwargs['params']['name'] == city
    assert get.call_args.kwargs['params']['countryCode'] == country


def test_ui_starts_without_system_timezone_database():
    # Windows等でIANAデータベースがない環境でも、日本時間の日付を作れること
    import zoneinfo
    zoneinfo.ZoneInfo.clear_cache()
    zoneinfo.reset_tzpath(())
    try:
        app = AppTest.from_file(str(APP)).run()
        assert not app.exception
    finally:
        zoneinfo.reset_tzpath()
        zoneinfo.ZoneInfo.clear_cache()


def test_ui_can_reload_an_old_session_without_crashing(monkeypatch):
    ask = Mock(side_effect=reply)
    monkeypatch.setattr(mqtt_client, 'ask_server', ask)
    app = AppTest.from_file(str(APP))
    app.session_state['result'] = reply('千葉県 習志野市', '2026-10-26', [])
    app.session_state['searched'] = '千葉県 習志野市 / 今日 (10/26)'
    app.run()
    assert not app.exception
    assert not ask.called
    assert any('対策を調べる' in item.value for item in app.info)
