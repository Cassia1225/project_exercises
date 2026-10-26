"""海外地域の座標解決から推薦結果までを、実MQTTと別プロセスで確認する。"""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from common import mqtt_settings as ms
from mqtt_client import ask_server
from test_mqtt_network import broker_factory


def test_overseas_coordinates_and_ambiguity_over_real_mqtt(broker_factory, tmp_path, monkeypatch):
    port, broker_log = broker_factory(False)
    prefix = 'audit/overseas-ui'
    for name, value in [('BROKER', '127.0.0.1'), ('PORT', port), ('PREFIX', prefix),
                        ('TOPIC_REQUEST', prefix + '/request'), ('USERNAME', ''), ('PASSWORD', '')]:
        monkeypatch.setattr(ms, name, value)

    # 座標検索・気象・花粉の外部サービスだけ固定応答。地域解決と全MQTT経路は実装を使う。
    (tmp_path / 'sitecustomize.py').write_text('''
import sys, types, requests
class Response:
    def raise_for_status(self): pass
    def json(self): return self.data

def get(url, params, timeout):
    response = Response()
    place = {'name': 'Paris', 'admin1': 'Île-de-France', 'country': 'France', 'latitude': 48.85, 'longitude': 2.35}
    if params['name'].startswith('Springfield'):
        response.data = {'results': [dict(place, name='Springfield', admin1='Illinois'), dict(place, name='Springfield', admin1='Missouri')]}
    else:
        response.data = {'results': [place]}
    return response
requests.get = get
weather = types.ModuleType('get_weather_data')
def get_weather(lat, lon, day):
    assert (lat, lon) == (48.85, 2.35)
    return {'weather_code': 0, 'wind_speed_max': 1.0}
weather.get_weather = get_weather
sys.modules['get_weather_data'] = weather
pollen = types.ModuleType('get_pollen_data')
def get_pollen_info(lat, lon, day):
    assert (lat, lon) == (48.85, 2.35)
    return {'upi': 4, 'types': {'TREE': 4}}, True
pollen.get_pollen_info = get_pollen_info
sys.modules['get_pollen_data'] = pollen
''', encoding='utf-8')
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.update({'MQTT_BROKER': '127.0.0.1', 'MQTT_PORT': str(port), 'MQTT_TOPIC_PREFIX': prefix,
                        'MQTT_USERNAME': '', 'MQTT_PASSWORD': '', 'PYTHONPATH': str(tmp_path),
                        'PYTHONDONTWRITEBYTECODE': '1'})
    processes, logs = [], []
    try:
        for index, program in enumerate(['server/server.py', 'weather/send_weather.py', 'pollen/send_pollen.py', 'recommend/send_recommend.py']):
            log = (tmp_path / f'worker-{index}.log').open('w')
            logs.append(log)
            processes.append(subprocess.Popen([sys.executable, '-u', program], cwd=root, env=environment, stdout=log, stderr=log))
        suffixes = ['/request', '/weather/request', '/pollen/request', '/recommend/request',
                    '/weather/result', '/pollen/result', '/recommend/result']
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            assert all(p.poll() is None for p in processes)
            text = broker_log.read_text()
            if all(prefix + suffix in text for suffix in suffixes):
                break
            time.sleep(0.05)
        else:
            pytest.fail('担当プログラムの購読が完了しませんでした')

        result = ask_server('Paris, France', '2026-10-26', ['オーク'], timeout=5)
        assert result['status'] == 'success'
        assert result['data']['location'] == 'Paris, Île-de-France, France'
        assert 'オーク' in result['data']['reason']
        assert result['pollen_is_mock'] is True
        error = ask_server('Springfield, USA', '2026-10-26', [], timeout=5)
        assert error['status'] == 'error'
        assert '複数' in error['errors'][0]['message']
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            process.wait(timeout=5)
        for log in logs:
            log.close()
