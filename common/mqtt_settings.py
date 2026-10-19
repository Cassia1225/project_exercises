"""5つのプログラムが共通で使う、MQTTの設定と小さな便利関数。

接続先（ブローカー）は .env の MQTT_BROKER で変えられる。
何も書かなければ、自分のPCで動かしている Mosquitto（localhost）につなぐ。

※ 将来、別々のPCで動かすときは、全員の .env に
   「Mosquitto を動かしているPCのIPアドレス」を書く（localhost は自分のPCのこと）。
"""
import json
import os
import uuid

import paho.mqtt.client as mqtt
from dotenv import load_dotenv

# .env ファイルがあれば、その内容を環境変数として読み込む
load_dotenv()

BROKER = os.getenv("MQTT_BROKER", "localhost")
PORT = int(os.getenv("MQTT_PORT", "1883"))

# トピック名の先頭。公開ブローカーで他の班と混ざらないよう、必要なら .env で変える
PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "project_exercises/v1")

# ---- トピック（MQTTの「宛先」）の一覧 ----
# UI → 通信制御
TOPIC_REQUEST = PREFIX + "/request"
# 通信制御 → 気象 / 花粉 / 推薦
TOPIC_WEATHER_REQUEST = PREFIX + "/weather/request"
TOPIC_POLLEN_REQUEST = PREFIX + "/pollen/request"
TOPIC_RECOMMEND_REQUEST = PREFIX + "/recommend/request"
# 気象 / 花粉 / 推薦 → 通信制御
TOPIC_WEATHER_RESULT = PREFIX + "/weather/result"
TOPIC_POLLEN_RESULT = PREFIX + "/pollen/result"
TOPIC_RECOMMEND_RESULT = PREFIX + "/recommend/result"


def result_topic_for(request_id):
    """通信制御 → UI の返信先。検索ごとに request_id で分ける。"""
    return PREFIX + "/result/" + request_id


def create_client(role):
    """MQTTクライアントを作る。role は "weather" などの役割名。

    クライアントIDが他と重ならないよう、役割名の後ろにランダムな文字列を付ける。
    """
    client_id = role + "-" + uuid.uuid4().hex[:8]
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
    )
    return client


def send_json(client, topic, data):
    """辞書(dict)をJSON文字列に変えて送信する。"""
    text = json.dumps(data, ensure_ascii=False)
    client.publish(topic, text, qos=1)


def read_json(message):
    """受信したメッセージを辞書(dict)に戻す。壊れたJSONや辞書でないものは None。"""
    try:
        text = message.payload.decode("utf-8")
        data = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        print("JSONとして読めないメッセージを無視しました")
        return None

    if not isinstance(data, dict):
        print("辞書の形ではないメッセージを無視しました")
        return None
    return data
