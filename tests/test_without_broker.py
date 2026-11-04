"""Pahoを読み込めない条件で、画面から検索して推薦表示まで進める。"""
import os
from pathlib import Path
import subprocess
import sys


def test_ui_search_works_without_broker_library():
    root = Path(__file__).resolve().parents[1]
    probe = '''
import importlib.abc, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

class NoBroker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "paho" or fullname.startswith("paho."):
            raise AssertionError("Brokerライブラリを必要としないこと")
sys.meta_path.insert(0, NoBroker())

import requests
today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
class Response:
    def raise_for_status(self): pass
    def json(self): return self.data
def get(url, params, timeout):
    response = Response()
    if "address-search" in url:
        response.data = [{"properties": {"title": "千葉県習志野市"},
                          "geometry": {"coordinates": [140.0, 35.0]}}]
    elif "forecast" in url:
        response.data = {"daily": {"time": [today], "weather_code": [0],
            "wind_speed_10m_max": [1.0], "temperature_2m_mean": [20.0],
            "relative_humidity_2m_mean": [50]}}
    else:
        raise AssertionError("想定外の外部通信")
    return response
requests.get = get
from streamlit.testing.v1 import AppTest
app = AppTest.from_file(str(Path("UI/app.py").resolve())).run()
assert not app.exception
app.button[0].click().run()
assert not app.exception
result = app.session_state["result"]
assert result["status"] == "success"
assert result["data"]["location"] == "千葉県 習志野市"
assert result["data"]["date"] == today
assert result["pollen_is_mock"] is True
assert len(app.metric) == 3
assert any("ダミー" in warning.value for warning in app.warning)
print("DIRECT_UI_SEARCH_OK")
'''
    environment = os.environ.copy()
    environment["GOOGLE_POLLEN_API_KEY"] = ""
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run([sys.executable, "-c", probe], cwd=root, env=environment,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DIRECT_UI_SEARCH_OK" in result.stdout
