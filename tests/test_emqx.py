"""EMQX設定を実際のクライアント・子プロセス・手動試験へ反映する。"""
import json
import runpy
import ssl
from pathlib import Path
from types import SimpleNamespace

import paho.mqtt.client as mqtt
import pytest
from dotenv import dotenv_values

from test_mqtt_settings import load_settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("role", ["ui", "server", "weather", "pollen", "recommend"])
def test_emqx_example_creates_verified_websocket_client(role, load_settings, capsys):
    example = ROOT / ".env.emqx.example"
    assert example.is_file(), "配布するEMQX設定見本が必要です"
    settings = load_settings(**dotenv_values(example, interpolate=False))
    client = settings.create_client(role)
    assert (settings.BROKER, settings.PORT) == ("broker.emqx.io", 8084)
    assert client.transport == "websockets"
    assert client._websocket_path == "/mqtt"
    assert client._ssl_context.check_hostname
    assert client._ssl_context.verify_mode == ssl.CERT_REQUIRED
    assert client._username is None and client._password is None
    assert "公開Broker" in capsys.readouterr().out


@pytest.mark.parametrize("role", ["ui", "server", "weather", "pollen", "recommend"])
def test_selected_role_receives_emqx_instead_of_parent_lan_settings(role, tmp_path, monkeypatch):
    import run_role
    monkeypatch.setattr(run_role, "ROOT", tmp_path)
    example = ROOT / ".env.emqx.example"
    assert example.is_file()
    (tmp_path / ".env.emqx").write_bytes(example.read_bytes())
    monkeypatch.setenv("MQTT_BROKER", "old-lan-host")
    monkeypatch.setenv("MQTT_TRANSPORT", "tcp")
    monkeypatch.setenv("MQTT_TLS", "false")
    monkeypatch.setenv("MQTT_PASSWORD", "old-lan-password")
    monkeypatch.setenv("GOOGLE_POLLEN_API_KEY", "not-for-public-tests")
    probe = '''
import json, os
from pathlib import Path
keys = ["MQTT_BROKER", "MQTT_PORT", "MQTT_TRANSPORT", "MQTT_WS_PATH", "MQTT_TLS",
        "MQTT_USERNAME", "MQTT_PASSWORD", "GOOGLE_POLLEN_API_KEY"]
Path("started.json").write_text(json.dumps({key: os.getenv(key) for key in keys}))
'''
    if role == "ui":
        (tmp_path / "streamlit.py").write_text(probe)
    else:
        program = tmp_path / run_role.PROGRAMS[role]
        program.parent.mkdir()
        program.write_text(probe)
    assert run_role.main([role, "--env-file", ".env.emqx"]) == 0
    started = json.loads((tmp_path / "started.json").read_text())
    assert started == {
        "MQTT_BROKER": "broker.emqx.io", "MQTT_PORT": "8084", "MQTT_TRANSPORT": "websockets",
        "MQTT_WS_PATH": "/mqtt", "MQTT_TLS": "true", "MQTT_USERNAME": "",
        "MQTT_PASSWORD": "", "GOOGLE_POLLEN_API_KEY": "",
    }


@pytest.mark.parametrize("script", ["send.py", "recieve.py", "mqtt_test.py"])
def test_manual_script_connects_to_emqx_with_tls(script, monkeypatch):
    connections = []
    class Client:
        def __init__(self, *args, **kwargs):
            self.transport = kwargs["transport"]
            self.tls = False
            self.closed = False
            connections.append(self)

        def ws_set_options(self, path):
            self.path = path

        def tls_set(self):
            self.tls = True

        def connect(self, host, port, keepalive):
            self.address = host, port, keepalive

        def loop_start(self):
            self.on_connect(self, None, None, 0, None)

        loop_forever = loop_start

        def subscribe(self, topic, qos):
            if hasattr(self, "on_subscribe"):
                self.on_subscribe(self, None, 1, [qos], None)

        def publish(self, topic, payload, qos):
            self.on_message(self, None, SimpleNamespace(topic=topic, payload=payload.encode()))

        def disconnect(self):
            self.closed = True

        def loop_stop(self):
            pass

    monkeypatch.setattr(mqtt, "Client", Client)
    monkeypatch.setattr("builtins.input", lambda prompt: "exit")
    runpy.run_path(str(ROOT / script), run_name="__main__")
    client, = connections
    assert client.address == ("broker.emqx.io", 8084, 60)
    assert client.transport == "websockets" and client.path == "/mqtt" and client.tls
    assert client.closed
