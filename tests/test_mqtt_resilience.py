"""回線を使わず、重複・欠落・誤った応答・購読拒否を再現する。"""
import json
import socket
from types import SimpleNamespace

import pytest

from common import mqtt_settings as ms
import mqtt_client
import server


class RecordingClient:
    def __init__(self):
        self.sent = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.sent.append((topic, json.loads(payload)))


@pytest.fixture
def flow(monkeypatch):
    monkeypatch.setattr(server, "waiting", {})
    monkeypatch.setattr(server, "completed", {})
    monkeypatch.setattr(server, "find_location", lambda name: {
        "name": name, "latitude": 0.0, "longitude": 0.0,
    })
    client = RecordingClient()
    request = {"request_id": "audit-r1", "location": "架空地域", "date": "2026-11-02", "allergies": []}
    weather = {"request_id": "audit-r1", "source": "weather", "status": "success", "data": {"weather_code": 0}}
    pollen = {"request_id": "audit-r1", "source": "pollen", "status": "success", "data": {"upi": 3}, "is_mock": True}
    return client, request, weather, pollen


def test_duplicate_worker_result_requests_recommendation_only_once(flow):
    client, request, weather, pollen = flow
    server.on_ui_request(client, request)
    for reply in (weather, pollen, weather, pollen):
        server.on_worker_result(client, reply)
    assert sum(topic == ms.TOPIC_RECOMMEND_REQUEST for topic, _ in client.sent) == 1


def test_duplicate_ui_request_does_not_erase_received_weather(flow):
    client, request, weather, pollen = flow
    server.on_ui_request(client, request)
    server.on_worker_result(client, weather)
    server.on_ui_request(client, request.copy())
    server.on_worker_result(client, pollen)
    assert sum(topic == ms.TOPIC_WEATHER_REQUEST for topic, _ in client.sent) == 1
    assert sum(topic == ms.TOPIC_RECOMMEND_REQUEST for topic, _ in client.sent) == 1


def test_completed_request_is_not_restarted_by_late_duplicate(flow):
    client, request, weather, pollen = flow
    server.on_ui_request(client, request)
    server.on_worker_result(client, weather)
    server.on_worker_result(client, pollen)
    reply = {"request_id": request["request_id"], "status": "success", "data": {}, "errors": []}
    server.on_recommend_result(client, reply)
    before = len(client.sent)
    server.on_ui_request(client, request)
    server.on_recommend_result(client, reply)
    assert len(client.sent) == before
    assert server.waiting == {}


def test_missing_worker_is_expired_without_new_messages(flow):
    client, request, weather, _ = flow
    server.on_ui_request(client, request)
    server.on_worker_result(client, weather)
    server.expire_waiting(client, now=float("inf"))
    assert server.waiting == {}
    topic, reply = client.sent[-1]
    assert topic == ms.result_topic_for("audit-r1")
    assert reply["status"] == "error"
    assert reply["errors"][0]["code"] == "REQUEST_TIMEOUT"


def test_premature_recommendation_does_not_remove_active_request(flow):
    client, request, _, _ = flow
    server.on_ui_request(client, request)
    server.on_recommend_result(client, {"request_id": "audit-r1", "status": "success", "data": {}, "errors": []})
    assert "audit-r1" in server.waiting
    assert len(client.sent) == 2


def test_result_source_must_match_its_topic(flow):
    client, request, weather, _ = flow
    server.on_ui_request(client, request)
    message = SimpleNamespace(topic=ms.TOPIC_POLLEN_RESULT, payload=json.dumps(weather).encode())
    server.on_message(client, None, message)
    assert server.waiting["audit-r1"]["weather"] is None


@pytest.mark.parametrize("request_id", ["", "bad/#", [], 123])
def test_invalid_request_id_never_creates_work(flow, request_id):
    client, request, _, _ = flow
    request["request_id"] = request_id
    message = SimpleNamespace(topic=ms.TOPIC_REQUEST, payload=json.dumps(request).encode())
    server.on_message(client, None, message)
    assert server.waiting == {}
    assert client.sent == []


class UIClient(RecordingClient):
    """MQTT接続だけを置換し、UI本体の待機・JSON・相関処理を実行する。"""
    def __init__(self, connack=0, suback=1, replies=None):
        super().__init__()
        self.connack, self.suback, self.replies = connack, suback, replies
        self.topic = None
        self.closed = False

    def connect(self, host, port, keepalive):
        pass

    def loop_start(self):
        self.on_connect(self, None, None, self.connack, None)

    def subscribe(self, topic, qos):
        self.topic = topic
        self.on_subscribe(self, None, 1, [self.suback], None)
        return 0, 1

    def publish(self, topic, payload, qos=0, retain=False):
        super().publish(topic, payload, qos, retain)
        request_id = json.loads(payload)["request_id"]
        replies = self.replies(request_id) if self.replies else []
        for data in replies:
            self.on_message(self, None, SimpleNamespace(topic=self.topic, payload=json.dumps(data).encode()))

    def disconnect(self):
        self.closed = True

    def loop_stop(self):
        pass


def test_ui_discards_response_with_different_request_id(monkeypatch):
    client = UIClient(replies=lambda rid: [
        {"request_id": "other", "status": "success", "data": {"location": "別検索"}},
        {"request_id": rid, "status": "success", "data": {"location": "今回"}},
    ])
    monkeypatch.setattr(ms, "create_client", lambda role: client)
    result = mqtt_client.ask_server("架空地域", "2026-11-02", [], timeout=0.01)
    assert result["data"]["location"] == "今回"
    assert client.closed


@pytest.mark.parametrize("connack,suback", [(0, 128), (5, 1)])
def test_ui_does_not_publish_after_connection_or_subscription_rejection(monkeypatch, connack, suback):
    client = UIClient(connack=connack, suback=suback)
    monkeypatch.setattr(ms, "create_client", lambda role: client)
    result = mqtt_client.ask_server("架空地域", "2026-11-02", [], timeout=0.01)
    assert result["status"] == "error"
    assert client.sent == []
    assert client.closed


@pytest.mark.parametrize("error", [socket.gaierror(8, "test DNS failure"), TimeoutError("test TCP timeout")])
def test_ui_reports_connection_errors_without_starting_message_loop(monkeypatch, error):
    client = UIClient()
    def connect(*args):
        raise error
    client.connect = connect
    monkeypatch.setattr(ms, "create_client", lambda role: client)
    result = mqtt_client.ask_server("架空地域", "2026-11-02", [], timeout=0.01)
    assert result["status"] == "error"
    assert str(error) in result["errors"][0]["message"]
    assert client.sent == []


@pytest.mark.parametrize("module_name", ["server", "send_weather", "send_pollen", "send_recommend"])
def test_workers_do_not_subscribe_when_connection_is_rejected(module_name):
    subscriptions = []
    client = SimpleNamespace(subscribe=lambda topic, qos: subscriptions.append(topic))
    __import__(module_name).on_connect(client, None, None, 5, None)
    assert subscriptions == []
