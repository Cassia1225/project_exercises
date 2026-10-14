
import json
import os
from datetime import date

from dotenv import load_dotenv
from supabase import create_client
import paho.mqtt.client as mqtt

# .envから設定を読み込む
load_dotenv()

# Supabaseの接続設定
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TABLE_NAME = "outing_requests"

# MQTTの接続設定
MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = "pollen/request"


def validate_request(data):
    """画面から受け取った入力内容を確認する。"""

    # 地域と日付が入力されているか確認
    if not data.get("area"):
        raise ValueError("地域が入力されていません")

    if not data.get("date"):
        raise ValueError("日付が入力されていません")

    # 日付の形式をチェックする
    date.fromisoformat(data["date"])

    # アレルギー情報をDBのtext型に合わせる
    allergies = data.get("allergies", [])

    if isinstance(allergies, list):
        allergies = ", ".join(allergies)

    # DBに保存するデータを作成
    return {
    "area": data["area"],
    "outing_date": data["date"],
    "allergies": allergies,
    "status": "received",
    }


def save_to_supabase(request_data):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabaseの接続設定がありません。.envを確認してください")

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("Supabaseクライアントを作成しました")

    # 今回はAPIに送るデータを確認
    print("DBに送るデータ:", request_data)

    print("使用テーブル:", TABLE_NAME)
    print("送信データのarea:", repr(request_data.get("area")))
    print("送信データのouting_date:", repr(request_data.get("outing_date")))
    result = supabase.table(TABLE_NAME).insert(request_data).execute()
    return result.data


def send_mqtt(request_data):
    """設定されていれば、MQTTで入力内容を送信する。"""

    # MQTTブローカーが未設定なら送信をスキップ
    if not MQTT_BROKER:
        print("MQTT未設定のため、送信をスキップしました")
        return False

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()

        info = client.publish(
            MQTT_TOPIC,
            json.dumps(request_data, ensure_ascii=False),
            qos=1,
        )

        info.wait_for_publish(timeout=5)

        if not info.is_published():
            raise RuntimeError(
                "MQTTメッセージを送信できませんでした"
            )

        return True

    finally:
        client.loop_stop()
        client.disconnect()


def process_request(data):
    """入力を受け取り、DBに保存して、MQTTで送信する。"""

    try:
        # 入力内容を確認
        request_data = validate_request(data)
        print("送信するデータ:", request_data)

        # まずDBに保存
        saved_data = save_to_supabase(request_data)

        # DB保存後、MQTTで送信
        try:
            mqtt_sent = send_mqtt(request_data)
        except Exception as error:
            print("MQTT送信エラー:", error)
            mqtt_sent = False

        return {
            "success": True,
            "message": "入力を受け取りました",
            "saved_data": saved_data,
            "mqtt_sent": mqtt_sent,
        }

    except Exception as error:
        print("処理エラー:", error)

        return {
            "success": False,
            "message": str(error),
        }


if __name__ == "__main__":
    # 動作確認用のサンプルデータ
    test_data = {
        "area": "習志野市",
        "date": "2026-10-11",
        "allergies": ["スギ"],
    }

    result = process_request(test_data)
    print(result)