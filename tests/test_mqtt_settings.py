"""共通MQTT設定が接続方式と既存の通信契約に反映されることを確認する。"""
import importlib.util
import json
import ssl
from types import SimpleNamespace

import pytest

from common import mqtt_settings as ms


@pytest.fixture
def load_settings(monkeypatch):
    # 個人の.envやターミナル設定をテストに混ぜない。
    monkeypatch.setattr("dotenv.load_dotenv", lambda: None)
    for name in ("MQTT_BROKER", "MQTT_PORT", "MQTT_TRANSPORT", "MQTT_WS_PATH",
                 "MQTT_TLS", "MQTT_USERNAME", "MQTT_PASSWORD", "MQTT_TOPIC_PREFIX"):
        monkeypatch.delenv(name, raising=False)

    def load(**settings):
        for name, value in settings.items():
            monkeypatch.setenv(name, value)
        spec = importlib.util.spec_from_file_location("isolated_mqtt_settings", ms.__file__)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return load


def test_default_client_keeps_local_tcp_without_tls(load_settings):
    settings = load_settings()
    client = settings.create_client("weather")
    assert (settings.BROKER, settings.PORT) == ("localhost", 1883)
    assert client.transport == "tcp"
    assert client._ssl_context is None
    assert settings.TOPIC_REQUEST == "project_exercises/v1/request"


@pytest.mark.parametrize("role", ["server", "weather", "pollen", "recommend", "ui"])
def test_hivemq_uses_websockets_and_verified_tls_for_every_role(load_settings, role):
    settings = load_settings(MQTT_BROKER="broker.hivemq.com", MQTT_PORT="8884",
                             MQTT_TRANSPORT="websockets", MQTT_WS_PATH="/mqtt", MQTT_TLS="true")
    client = settings.create_client(role)
    assert (settings.BROKER, settings.PORT) == ("broker.hivemq.com", 8884)
    assert client.transport == "websockets"
    assert client._websocket_path == "/mqtt"
    assert client._ssl_context.verify_mode == ssl.CERT_REQUIRED
    assert client._ssl_context.check_hostname is True
    assert client._username is None
    assert client._password is None
    assert client._client_id.decode().startswith(role + "-")
    assert client._client_id != settings.create_client(role)._client_id


def test_custom_websocket_path_is_applied(load_settings):
    settings = load_settings(MQTT_TRANSPORT="websockets", MQTT_WS_PATH="/custom/mqtt", MQTT_TLS="false")
    client = settings.create_client("ui")
    assert client.transport == "websockets"
    assert client._websocket_path == "/custom/mqtt"
    assert client._ssl_context is None


def test_lan_can_explicitly_disable_websockets_and_tls(load_settings):
    settings = load_settings(MQTT_BROKER="192.168.0.10", MQTT_PORT="1884", MQTT_TRANSPORT="tcp",
                             MQTT_TLS="false", MQTT_USERNAME="group8", MQTT_PASSWORD="test-only")
    client = settings.create_client("server")
    assert client.transport == "tcp"
    assert client._ssl_context is None
    assert client._username == b"group8"
    assert client._password == b"test-only"


@pytest.mark.parametrize("settings", [
    {"MQTT_TRANSPORT": "websocket"},
    {"MQTT_TLS": "typo"},
    {"MQTT_TRANSPORT": "websockets", "MQTT_WS_PATH": "mqtt"},
    {"MQTT_PORT": "0"},
    {"MQTT_PORT": "65536"},
])
def test_invalid_connection_settings_fail_before_connect(load_settings, settings):
    with pytest.raises(ValueError, match="MQTT_"):
        load_settings(**settings).create_client("ui")


def test_send_json_preserves_payload_qos_and_no_retention(load_settings, monkeypatch):
    settings = load_settings(MQTT_USERNAME="group8", MQTT_PASSWORD="test-only",
                             GOOGLE_POLLEN_API_KEY="fake-api-key-not-for-publish")
    client = settings.create_client("weather")
    sent = []
    monkeypatch.setattr(client, "publish", lambda topic, payload, qos=0, retain=False:
                        sent.append((topic, payload, qos, retain)))
    payload = {"request_id": "test-001", "source": "weather", "status": "success",
               "data": {"weather_code": 0, "wind_speed_max": 1.0}}
    settings.send_json(client, "project_exercises/v1/weather/result", payload)
    topic, text, qos, retain = sent[0]
    assert topic == "project_exercises/v1/weather/result"
    assert json.loads(text) == payload
    assert (qos, retain) == (1, False)
    assert "test-only" not in text
    assert "fake-api-key-not-for-publish" not in text
    assert settings.result_topic_for("test-001") == "project_exercises/v1/result/test-001"


@pytest.mark.parametrize("module_name, topics", [
    ("server", [ms.TOPIC_REQUEST, ms.TOPIC_WEATHER_RESULT, ms.TOPIC_POLLEN_RESULT, ms.TOPIC_RECOMMEND_RESULT]),
    ("send_weather", [ms.TOPIC_WEATHER_REQUEST]),
    ("send_pollen", [ms.TOPIC_POLLEN_REQUEST]),
    ("send_recommend", [ms.TOPIC_RECOMMEND_REQUEST]),
])
def test_workers_resubscribe_with_qos_one_on_each_connect(module_name, topics):
    module = __import__(module_name)
    subscriptions = []
    client = SimpleNamespace(subscribe=lambda topic, qos: subscriptions.append((topic, qos)))
    module.on_connect(client, None, None, 0, None)
    module.on_connect(client, None, None, 0, None)
    assert subscriptions == [(topic, 1) for topic in topics] * 2


@pytest.mark.parametrize("role", ["server", "weather", "pollen", "recommend", "ui"])
def test_run_role_passes_hivemq_settings_to_child(role, tmp_path, monkeypatch):
    import run_role
    monkeypatch.setattr(run_role, "ROOT", tmp_path)
    (tmp_path / ".env.hivemq").write_text(
        "MQTT_BROKER=broker.hivemq.com\nMQTT_PORT=8884\nMQTT_TRANSPORT=websockets\n"
        "MQTT_WS_PATH=/mqtt\nMQTT_TLS=true\nMQTT_USERNAME=\nMQTT_PASSWORD=\n"
        "MQTT_TOPIC_PREFIX=group8/synthetic-test/v1\nGOOGLE_POLLEN_API_KEY=\n"
    )
    # 親にLAN用設定が残っていても、明示したHiveMQ設定で上書きされる。
    monkeypatch.setenv("MQTT_TRANSPORT", "tcp")
    monkeypatch.setenv("MQTT_TLS", "false")
    monkeypatch.setenv("MQTT_PASSWORD", "test-only")
    probe = '''
import json, os
from pathlib import Path
keys = ["MQTT_BROKER", "MQTT_PORT", "MQTT_TRANSPORT", "MQTT_WS_PATH", "MQTT_TLS",
        "MQTT_USERNAME", "MQTT_PASSWORD", "MQTT_TOPIC_PREFIX", "GOOGLE_POLLEN_API_KEY"]
Path("settings.json").write_text(json.dumps({key: os.getenv(key) for key in keys}))
'''
    if role == "ui":
        (tmp_path / "streamlit.py").write_text(probe)
    else:
        program = tmp_path / run_role.PROGRAMS[role]
        program.parent.mkdir()
        program.write_text(probe)
    assert run_role.main([role, "--env-file", ".env.hivemq"]) == 0
    result = json.loads((tmp_path / "settings.json").read_text())
    assert result == {
        "MQTT_BROKER": "broker.hivemq.com", "MQTT_PORT": "8884", "MQTT_TRANSPORT": "websockets",
        "MQTT_WS_PATH": "/mqtt", "MQTT_TLS": "true", "MQTT_USERNAME": "", "MQTT_PASSWORD": "",
        "MQTT_TOPIC_PREFIX": "group8/synthetic-test/v1", "GOOGLE_POLLEN_API_KEY": "",
    }
    assert __import__("os").getenv("MQTT_PASSWORD") == "test-only"


@pytest.mark.parametrize("subscribed", [True, False])
def test_ui_keeps_subscription_and_result_timeouts(subscribed, monkeypatch):
    import mqtt_client
    waits, subscriptions, published, stopped = [], [], [], []
    event = SimpleNamespace(set=lambda: None, wait=lambda timeout: waits.append(timeout) or subscribed)
    monkeypatch.setattr(mqtt_client.threading, "Event", lambda: event)
    result_queue = SimpleNamespace(put=lambda data: None)

    def get(timeout):
        waits.append(timeout)
        raise mqtt_client.queue.Empty

    result_queue.get = get
    monkeypatch.setattr(mqtt_client.queue, "Queue", lambda: result_queue)
    client = SimpleNamespace()
    client.connect = lambda host, port, keepalive: stopped.append((host, port, keepalive))
    client.subscribe = lambda topic, qos: subscriptions.append((topic, qos))
    client.publish = lambda topic, text, qos: published.append((topic, json.loads(text), qos))
    # UIもon_connectごとに自分の返信先を再購読する。
    def start():
        client.on_connect(client, None, None, 0, None)
        client.on_connect(client, None, None, 0, None)
    client.loop_start = start
    client.loop_stop = lambda: stopped.append("loop_stop")
    client.disconnect = lambda: stopped.append("disconnect")
    monkeypatch.setattr(ms, "create_client", lambda role: client)
    result = mqtt_client.ask_server("架空のテスト地域", "2026-10-30", [])
    assert result["status"] == "error"
    assert waits == ([10, 30] if subscribed else [10])
    assert stopped == [(ms.BROKER, ms.PORT, 60), "loop_stop", "disconnect"]
    assert len(subscriptions) == 2 and subscriptions[0] == subscriptions[1]
    assert subscriptions[0][1] == 1
    if subscribed:
        topic, payload, qos = published[0]
        assert (topic, qos) == (ms.TOPIC_REQUEST, 1)
        assert set(payload) == {"request_id", "location", "date", "allergies"}
        assert subscriptions[0][0] == ms.result_topic_for(payload["request_id"])
    else:
        assert published == []
