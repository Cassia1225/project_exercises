
import json
import os
from datetime import date, time

from dotenv import load_dotenv
from supabase import create_client
import paho.mqtt.client as mqtt

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
    required = ["area", "date", "time"]

    for key in required:
        if not data.get(key):
            raise ValueError(f"{key} が入力されていません")

    # 日付と時刻の形式をチェックする
    date.fromisoformat(data["date"])
    time.fromisoformat(data["time"])

    return {
        "area": data["area"],
        "outing_date": data["date"],
        "outing_time": data["time"],
        "allergies": data.get("allergies", []),
        "status": "received",
    }


def save_to_supabase(request_data):
    """入力内容をSupabaseに保存する。"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "Supabaseの接続設定がありません。.envを確認してください"
        )

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    result = (
        supabase.table(TABLE_NAME)
        .insert(request_data)
        .execute()
    )

    return result.data


def send_mqtt(request_data):
    """設定されていれば、MQTTで入力内容を送信する。"""
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
            raise RuntimeError("MQTTメッセージを送信できませんでした")

        return True

    finally:
        client.loop_stop()
        client.disconnect()


def process_request(data):
    """入力を受け取り、保存して、通信する。"""
    try:
        request_data = validate_request(data)

        # まず入力内容をDBに保存
        saved_data = save_to_supabase(request_data)

        # MQTTの設定がある場合だけ送信
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
        "time": "14:00",
        "allergies": ["スギ"],
    }

    result = process_request(test_data)
    print(result)
