"""明示指定時だけ、公開HiveMQで全5役の通信を架空データにより確認する。

RUN_HIVEMQ_TEST=1 python -m pytest -q tests/test_hivemq_public.py
外部の地理/気象/花粉APIは呼ばず、秘密情報・実在する個人の条件を送らない。
"""
import os
import threading
import uuid

import pytest

from common import mqtt_settings as ms


@pytest.mark.skipif(os.getenv("RUN_HIVEMQ_TEST") != "1", reason="公開Broker試験は明示指定時のみ実施")
def test_five_roles_over_hivemq_websockets_tls(monkeypatch):
    import server
    import send_weather
    import send_pollen
    import send_recommend
    from mqtt_client import ask_server

    prefix = "project-exercises-test/" + uuid.uuid4().hex
    for name, value in {"BROKER": "broker.hivemq.com", "PORT": 8884,
                        "TRANSPORT": "websockets", "WS_PATH": "/mqtt", "TLS": True,
                        "USERNAME": "", "PASSWORD": "", "PREFIX": prefix}.items():
        monkeypatch.setattr(ms, name, value)
    for name, suffix in {
        "TOPIC_REQUEST": "/request", "TOPIC_WEATHER_REQUEST": "/weather/request",
        "TOPIC_POLLEN_REQUEST": "/pollen/request", "TOPIC_RECOMMEND_REQUEST": "/recommend/request",
        "TOPIC_WEATHER_RESULT": "/weather/result", "TOPIC_POLLEN_RESULT": "/pollen/result",
        "TOPIC_RECOMMEND_RESULT": "/recommend/result",
    }.items():
        monkeypatch.setattr(ms, name, prefix + suffix)
    monkeypatch.setattr(server, "find_location", lambda name: {"name": name, "latitude": 0.0, "longitude": 0.0})
    monkeypatch.setattr(server, "waiting", {})
    monkeypatch.setattr(send_weather, "get_weather", lambda lat, lon, day: {"weather_code": 0, "wind_speed_max": 1.0})
    monkeypatch.setattr(send_pollen, "get_pollen_info", lambda lat, lon, day: ({"upi": 3, "types": {"WEED": 3}}, True))
    clients = []
    try:
        for role, module, expected_subscriptions in [
            ("server", server, 4), ("weather", send_weather, 1),
            ("pollen", send_pollen, 1), ("recommend", send_recommend, 1),
        ]:
            ready = threading.Event()
            acknowledgements = []
            client = ms.create_client(role)
            clients.append(client)
            client.on_connect = module.on_connect
            client.on_message = module.on_message
            def on_subscribe(c, u, mid, codes, props, ready=ready, acks=acknowledgements,
                             expected=expected_subscriptions):
                acks.extend(codes)
                if len(acks) >= expected:
                    ready.set()
            client.on_subscribe = on_subscribe
            client.connect_timeout = 5
            client.connect(ms.BROKER, ms.PORT, 60)
            client.loop_start()
            assert ready.wait(15), role + " の購読が未完了"
            assert not any(code.is_failure for code in acknowledgements)
        result = ask_server("架空の通信テスト地域", "2026-10-30", [], timeout=30)
        assert result["status"] == "success"
        assert result["data"]["location"] == "架空の通信テスト地域"
        assert result["pollen_is_mock"] is True
        assert result["request_id"]
        assert result["data"]["date"] == "2026-10-30"
        assert "day" not in result["data"]
        assert server.waiting == {}
    finally:
        for client in clients:
            client.disconnect()
            client.loop_stop()
