"""実際のBrokerで通信を確認する。Mosquittoがない環境ではスキップする。

使うのは試験専用のポートと架空データ。外部APIと既存Brokerは使わない。
"""
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from common import mqtt_settings as ms


@pytest.fixture
def broker_factory(tmp_path):
    executable = shutil.which("mosquitto")
    password_tool = shutil.which("mosquitto_passwd")
    if executable is None or password_tool is None:
        pytest.skip("通信試験にはMosquittoとmosquitto_passwdが必要です")
    processes = []
    logs = []

    def start(authenticated):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        folder = tmp_path / str(port)
        folder.mkdir()
        config = f"listener {port} 127.0.0.1\npersistence false\n"
        if authenticated:
            passwords = folder / "passwords"
            subprocess.run(
                [password_tool, "-b", "-c", str(passwords), "group8", "test-only"],
                check=True, capture_output=True,
            )
            # 配布する設定例そのものを使い、試験用に接続先とパスだけを変える。
            template = Path(__file__).resolve().parent.parent / "mqtt/mosquitto-lan.conf.example"
            config = template.read_text()
            config = config.replace("listener 1884 0.0.0.0", f"listener {port} 127.0.0.1")
            config = config.replace("password_file mqtt/passwords", f"password_file {passwords}")
        else:
            config += "allow_anonymous true\n"
        config_file = folder / "broker.conf"
        config_file.write_text(config)
        log_file = folder / "broker.log"
        log = log_file.open("w")
        logs.append(log)
        process = subprocess.Popen(
            [executable, "-c", str(config_file), "-v"], stdout=log, stderr=log,
        )
        processes.append(process)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail("試験Brokerが起動できませんでした: " + log_file.read_text())
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    return port, log_file
            except OSError:
                time.sleep(0.05)
        pytest.fail("試験Brokerの起動がタイムアウトしました")

    yield start
    for process in processes:
        process.terminate()
        process.wait(timeout=5)
    for log in logs:
        log.close()


def connect_client(client, port):
    connected = threading.Event()
    result = []

    def on_connect(client, userdata, flags, reason_code, properties):
        result.append(reason_code)
        connected.set()

    client.on_connect = on_connect
    client.connect("127.0.0.1", port, 60)
    client.loop_start()
    assert connected.wait(5), "Brokerから接続結果が届きませんでした"
    return result[0]


def test_password_connection_can_exchange_json(broker_factory, monkeypatch):
    port, _ = broker_factory(True)
    monkeypatch.setattr(ms, "USERNAME", "group8", raising=False)
    monkeypatch.setattr(ms, "PASSWORD", "test-only", raising=False)
    receiver = ms.create_client("test-receiver")
    sender = ms.create_client("test-sender")
    received = queue.Queue()
    subscribed = threading.Event()
    receiver.on_message = lambda c, u, message: received.put(ms.read_json(message))
    receiver.on_subscribe = lambda c, u, mid, codes, props: subscribed.set()
    try:
        assert not connect_client(receiver, port).is_failure
        assert not connect_client(sender, port).is_failure
        receiver.subscribe("audit/network", qos=1)
        assert subscribed.wait(5)
        ms.send_json(sender, "audit/network", {"request_id": "net-001", "message": "気象の返信"})
        assert received.get(timeout=5) == {"request_id": "net-001", "message": "気象の返信"}
    finally:
        receiver.disconnect()
        sender.disconnect()
        receiver.loop_stop()
        sender.loop_stop()


def test_local_connection_still_works_without_password(broker_factory, monkeypatch):
    port, _ = broker_factory(False)
    monkeypatch.setattr(ms, "USERNAME", "", raising=False)
    monkeypatch.setattr(ms, "PASSWORD", "", raising=False)
    client = ms.create_client("test-local")
    try:
        assert not connect_client(client, port).is_failure
    finally:
        client.disconnect()
        client.loop_stop()


def test_wrong_password_is_rejected(broker_factory, monkeypatch):
    port, _ = broker_factory(True)
    monkeypatch.setattr(ms, "USERNAME", "group8", raising=False)
    monkeypatch.setattr(ms, "PASSWORD", "wrong-password", raising=False)
    client = ms.create_client("test-wrong-password")
    try:
        assert connect_client(client, port).is_failure
    finally:
        client.disconnect()
        client.loop_stop()


def test_separate_workers_return_results_for_two_users(broker_factory, tmp_path, monkeypatch):
    """4担当を別プロセスで動かし、UIの実MQTT関数から2件を同時に検索する。"""
    from concurrent.futures import ThreadPoolExecutor
    from mqtt_client import ask_server

    port, broker_log = broker_factory(True)
    prefix = "audit/separate-workers"
    monkeypatch.setattr(ms, "BROKER", "127.0.0.1")
    monkeypatch.setattr(ms, "PORT", port)
    monkeypatch.setattr(ms, "PREFIX", prefix)
    monkeypatch.setattr(ms, "TOPIC_REQUEST", prefix + "/request")
    monkeypatch.setattr(ms, "USERNAME", "group8")
    monkeypatch.setattr(ms, "PASSWORD", "test-only")

    # 外部サービスだけを架空の応答に置き換える。MQTT・集約・推薦は本物を使う。
    (tmp_path / "sitecustomize.py").write_text('''
import sys, types
locations = types.ModuleType("common.locations")
locations.find_location = lambda name: {"name": name, "latitude": 35.0, "longitude": 140.0}
sys.modules["common.locations"] = locations
weather = types.ModuleType("get_weather_data")
weather.get_weather = lambda lat, lon, date: {"weather_code": 0, "wind_speed_max": 1.0}
sys.modules["get_weather_data"] = weather
pollen = types.ModuleType("get_pollen_data")
pollen.get_pollen_info = lambda lat, lon, date: ({"upi": 4, "types": {"WEED": 4}}, True)
sys.modules["get_pollen_data"] = pollen
''')
    root = Path(__file__).resolve().parent.parent
    environment = os.environ.copy()
    environment.update({
        "MQTT_BROKER": "127.0.0.1", "MQTT_PORT": str(port),
        "MQTT_TOPIC_PREFIX": prefix, "MQTT_USERNAME": "group8", "MQTT_PASSWORD": "test-only",
        "PYTHONPATH": str(tmp_path), "PYTHONDONTWRITEBYTECODE": "1",
    })
    programs = ["server/server.py", "weather/send_weather.py", "pollen/send_pollen.py", "recommend/send_recommend.py"]
    processes = []
    logs = []
    try:
        for number, program in enumerate(programs):
            log = (tmp_path / f"worker-{number}.log").open("w")
            logs.append(log)
            processes.append(subprocess.Popen(
                [sys.executable, "-u", program], cwd=root, env=environment, stdout=log, stderr=log,
            ))
        # 全担当の購読がBrokerに届いてから依頼する。固定秒数の待機で判定しない。
        expected_topics = [prefix + suffix for suffix in [
            "/request", "/weather/request", "/pollen/request", "/recommend/request",
            "/weather/result", "/pollen/result", "/recommend/result",
        ]]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            assert all(p.poll() is None for p in processes), "担当プロセスが途中で終了しました"
            broker_text = broker_log.read_text()
            if all(topic in broker_text for topic in expected_topics):
                break
            time.sleep(0.05)
        else:
            pytest.fail("全担当の購読が完了しませんでした")

        with ThreadPoolExecutor(max_workers=2) as executor:
            a = executor.submit(ask_server, "テスト地域A", "2026-10-23", [], 5)
            b = executor.submit(ask_server, "テスト地域B", "2026-10-23", [], 5)
            first = a.result(timeout=10)
            second = b.result(timeout=10)
        assert first["status"] == second["status"] == "success"
        assert first["data"]["location"] == "テスト地域A"
        assert second["data"]["location"] == "テスト地域B"
        assert first["request_id"] != second["request_id"]
        assert first["pollen_is_mock"] is True
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            process.wait(timeout=5)
        for log in logs:
            log.close()
