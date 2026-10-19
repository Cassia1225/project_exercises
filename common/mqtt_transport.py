"""MQTTで取得を依頼し、気象・花粉の返信を受け取る。検索IDで返信を区別する。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
import threading
import time
from uuid import uuid4
import paho.mqtt.client as mqtt
from .protocol import (
    SCHEMA,
    TOPIC_ROOT,
    ProtocolError,
    validate_worker_request,
    matches_result,
    deadline,
    now_iso,
    remaining,
)


def decode(data):
    if len(data) > 131072:
        raise ValueError("packet too large")

    def invalid(_):
        raise ValueError("nonfinite JSON")

    return json.loads(data, parse_constant=invalid)


def client(role):
    mqtt_client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=role + "-" + uuid4().hex,
        clean_session=True,
        protocol=mqtt.MQTTv311,
    )
    mqtt_client.connect_timeout = 5
    return mqtt_client


class MqttCollector:
    """通信制御側。気象・花粉へ依頼し、両方の返信を集める。"""

    def __init__(self, host=None, port=None, wait_timeout=20, connect_timeout=5):
        self.host = host or os.getenv("MQTT_HOST", "127.0.0.1")
        self.port = port or int(os.getenv("MQTT_PORT", "1883"))
        self.wait_timeout = wait_timeout
        self.connect_timeout = connect_timeout

    def collect(self, location, date, is_mock, request_id=None, *, until=None):
        if until is None:
            until = time.monotonic() + self.connect_timeout + self.wait_timeout
        connect_until = min(until, time.monotonic() + self.connect_timeout)
        request_id = request_id or str(uuid4())
        request = {
            "schema_version": SCHEMA,
            "request_id": request_id,
            "controller_id": "demo-local",
            "location_id": location["location_id"],
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "date": date,
            "is_mock": is_mock,
            "expires_at": (
                datetime.now(timezone.utc)
                + timedelta(seconds=remaining(until, 60, "mqtt"))
            ).isoformat(),
        }
        validate_worker_request(request)
        replies = {}
        condition = threading.Condition()
        subscribed = threading.Event()
        mqtt_client = client("controller")
        mqtt_client.connect_timeout = remaining(
            connect_until, self.connect_timeout, "mqtt"
        )
        closing = threading.Event()
        topics = {}
        for source in ("weather", "pollen"):
            topic = f"{TOPIC_ROOT}/demo-local/{source}/result"
            topics[topic] = source

        def on_connect(conn, userdata, flags, reason, properties):
            if not reason.is_failure:
                subscriptions = []
                for topic in topics:
                    subscriptions.append((topic, 1))
                conn.subscribe(subscriptions)

        def on_subscribe(conn, userdata, mid, reasons, properties):
            if reasons and not any(reason.is_failure for reason in reasons):
                subscribed.set()

        def on_disconnect(*args):
            closing.set()
            with condition:
                condition.notify_all()

        def on_message(conn, userdata, message):
            source = topics.get(message.topic)
            if source is None or message.retain:
                return
            try:
                reply = decode(message.payload)
            except (ValueError, UnicodeError):
                return
            if not matches_result(reply, request, source):
                return
            with condition:
                if source not in replies:
                    replies[source] = reply
                    condition.notify_all()

        # paho-mqttが接続・購読・受信・切断を検知したときに呼ぶ関数。
        mqtt_client.on_connect = on_connect
        mqtt_client.on_subscribe = on_subscribe
        mqtt_client.on_message = on_message
        mqtt_client.on_disconnect = on_disconnect
        try:
            mqtt_client.connect(self.host, self.port, keepalive=30)
            mqtt_client.loop_start()
            if not subscribed.wait(
                remaining(connect_until, self.connect_timeout, "mqtt")
            ):
                raise ProtocolError(
                    "BROKER_UNAVAILABLE",
                    "MQTTの返信購読を開始できませんでした。",
                    "mqtt",
                )
            # 返信の受信準備ができてから、気象・花粉へ取得を依頼する。
            for source in ("weather", "pollen"):
                info = mqtt_client.publish(
                    f"{TOPIC_ROOT}/{source}/request",
                    json.dumps(request),
                    qos=1,
                    retain=False,
                )
                if info.rc != mqtt.MQTT_ERR_SUCCESS:
                    raise ProtocolError(
                        "BROKER_UNAVAILABLE",
                        "MQTTへ要求を送信できませんでした。",
                        "mqtt",
                    )
            wait_until = min(until, time.monotonic() + self.wait_timeout)
            with condition:
                while len(replies) < 2 and not closing.is_set():
                    seconds = wait_until - time.monotonic()
                    if seconds <= 0:
                        break
                    condition.wait(seconds)
            return replies
        except (OSError, TimeoutError):
            raise ProtocolError(
                "BROKER_UNAVAILABLE",
                "MQTT Brokerに接続できません。起動状態と宛先を確認してください。",
                "mqtt",
            ) from None
        finally:
            mqtt_client.disconnect()
            mqtt_client.loop_stop()


class Worker:
    """取得担当側。要求を待ち、provider関数で取得して結果を返信する。"""

    def __init__(self, source, provider, host=None, port=None, is_mock=False):
        if source not in ("weather", "pollen"):
            raise ValueError("unknown worker")
        self.source = source
        self.provider = provider
        self.is_mock = is_mock
        self.host = host or os.getenv("MQTT_HOST", "127.0.0.1")
        self.port = port or int(os.getenv("MQTT_PORT", "1883"))
        self.client = client(source)
        self.ready = threading.Event()
        self.stopped = threading.Event()
        self.lock = threading.Lock()
        self.seen = {}
        # 同時に受け付ける数と実行数を制限し、依頼が集中しても増え続けないようにする。
        self.slots = threading.BoundedSemaphore(8)
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix=source)

    def start(self, timeout=5):
        mqtt_client = self.client

        def on_connect(conn, userdata, flags, reason, properties):
            self.ready.clear()
            if not reason.is_failure:
                conn.subscribe(f"{TOPIC_ROOT}/{self.source}/request", qos=1)

        def on_subscribe(conn, userdata, mid, reasons, properties):
            if reasons and not any(reason.is_failure for reason in reasons):
                self.ready.set()

        def on_disconnect(*args):
            self.ready.clear()

        def on_message(conn, userdata, message):
            if message.retain or self.stopped.is_set():
                return
            try:
                request = decode(message.payload)
                validate_worker_request(request)
                if request["is_mock"] is not self.is_mock:
                    return
            except (ProtocolError, ValueError, TypeError):
                return
            key = (request["controller_id"], request["request_id"])
            now = time.monotonic()
            with self.lock:
                # 期限切れの記録を除き、同じ取得依頼を二重に処理しない。
                active_requests = {}
                for request_key, expires_at in self.seen.items():
                    if expires_at > now:
                        active_requests[request_key] = expires_at
                self.seen = active_requests
                if (
                    key in self.seen
                    or len(self.seen) >= 256
                    or not self.slots.acquire(blocking=False)
                ):
                    return
                self.seen[key] = now + 60
            self.pool.submit(self._handle, request)

        mqtt_client.on_connect = on_connect
        mqtt_client.on_subscribe = on_subscribe
        mqtt_client.on_disconnect = on_disconnect
        mqtt_client.on_message = on_message
        try:
            mqtt_client.connect(self.host, self.port, keepalive=30)
            mqtt_client.loop_start()
            if not self.ready.wait(timeout):
                raise RuntimeError("MQTT購読を開始できませんでした。")
        except Exception:
            self.stop()
            raise
        return self

    def _handle(self, request):
        try:
            if deadline(request["expires_at"]) <= datetime.now(timezone.utc):
                return
            # 要求と同じ検索ID・地域・日付を付けて返信する。
            reply = {
                "schema_version": request["schema_version"],
                "request_id": request["request_id"],
                "controller_id": request["controller_id"],
                "location_id": request["location_id"],
                "date": request["date"],
                "is_mock": request["is_mock"],
                "source": self.source,
                "errors": [],
                "warnings": [],
                "fetched_at": None,
            }
            try:
                data = dict(self.provider(request))
                warnings = data.pop("_warnings", [])
                reply["status"] = "success"
                reply["data"] = data
                reply["warnings"] = warnings
                reply["fetched_at"] = now_iso()
            except ProtocolError as exc:
                reply["status"] = "error"
                reply["data"] = None
                reply["errors"] = [exc.as_dict()]
            except Exception:
                reply.update(
                    status="error",
                    data=None,
                    errors=[
                        {
                            "source": self.source,
                            "code": "WORKER_ERROR",
                            "message": "取得処理を完了できませんでした。",
                        }
                    ],
                )
            if (
                deadline(request["expires_at"]) > datetime.now(timezone.utc)
                and not self.stopped.is_set()
            ):
                self.client.publish(
                    f"{TOPIC_ROOT}/{request['controller_id']}/{self.source}/result",
                    json.dumps(reply, ensure_ascii=False, allow_nan=False),
                    qos=1,
                    retain=False,
                )
        finally:
            self.slots.release()

    def run(self):
        self.start()
        print(f"READY {self.source}", flush=True)
        try:
            self.stopped.wait()
        finally:
            self.stop()

    def stop(self):
        self.stopped.set()
        self.client.disconnect()
        self.client.loop_stop()
        self.pool.shutdown(wait=False, cancel_futures=True)
