
import uuid
import paho.mqtt.client as mqtt

BROKER = "broker.hivemq.com"
PORT = 8884
TOPIC = "projectensyuu/team8/test"

def on_connect(client, userdata, flags, reason_code, properties):
    print("接続結果:", reason_code)

client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id=f"sender-{uuid.uuid4().hex[:8]}",
    transport="websockets"
)

client.ws_set_options(path="/mqtt")
client.tls_set()

client.on_connect = on_connect

client.connect(BROKER, PORT, 60)
client.loop_start()

try:
    while True:
        message = input("送信する文字を入力（exitで終了）: ")

        if message == "exit":
            break

        info = client.publish(
            TOPIC,
            payload=message,
            qos=1,
            retain=False
        )

        info.wait_for_publish(timeout=10)
        print("送信処理結果:", info.rc)

finally:
    client.disconnect()
    client.loop_stop()
