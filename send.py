
import uuid
import threading
import paho.mqtt.client as mqtt

BROKER = "broker.emqx.io"
PORT = 8084
TOPIC = "projectensyuu/team8/test-7c4a91"

connected = threading.Event()

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Broker接続成功！")
        connected.set()
    else:
        print("接続失敗:", reason_code)

client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id=f"sender-{uuid.uuid4().hex[:8]}",
    transport="websockets"
)

client.ws_set_options(path="/mqtt")
client.tls_set()

client.on_connect = on_connect

try:
    client.connect(BROKER, PORT, 60)
    client.loop_start()

    if not connected.wait(timeout=15):
        raise TimeoutError("Brokerへの接続が完了しませんでした")

    while True:
        message = input("送信するメッセージ（exitで終了）: ")

        if message == "exit":
            break

        info = client.publish(
            TOPIC,
            payload=message,
            qos=1,
            retain=False
        )

        info.wait_for_publish(timeout=10)

        if info.is_published():
            print("Brokerへの送信完了！")
        else:
            print("送信確認がタイムアウトしました")

finally:
    client.disconnect()
    client.loop_stop()
