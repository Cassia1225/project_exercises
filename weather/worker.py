"""MQTTの気象取得担当を起動する。"""

import os
from dotenv import load_dotenv
from common.mqtt_transport import Worker
from common.providers import mock_data
from .get_weather_data import get_weather


def get_demo_data(request):
    """デモでは、APIの代わりに動作確認用の値を返す。"""
    return mock_data("weather", request)


def main():
    load_dotenv()
    demo = os.getenv("APP_MODE", "live") == "demo"

    # Workerには「依頼が来たときに呼ぶ取得関数」を渡す。
    if demo:
        provider = get_demo_data
    else:
        provider = get_weather
    worker = Worker("weather", provider, is_mock=demo)

    try:
        worker.run()
    except KeyboardInterrupt:
        worker.stop()


if __name__ == "__main__":
    main()
