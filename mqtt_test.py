
import uuid
import threading
import paho.mqtt.client as mqtt

BROKER = "broker.hivemq.com"
PORT = 8884
TOPIC = f"projectensyuu/test/{uuid.uuid4().hex}"

received = threading.Event()

def on_connect(client, userdata, flags, reason_code, properties):
    print("接続結果:", reason_code)

    if reason_code == 0:
        client.subscribe(TOPIC, qos=1)
    else:
        received.set()

def on_subscribe(client, userdata, mid, reason_code_list, properties):
    print("購読結果:", reason_code_list)
    client.publish(TOPIC, "MQTT通信テスト", qos=1)

def on_message(client, userdata, message):
    print("受信成功:", message.payload.decode("utf-8"))
    received.set()

client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id=f"test-{uuid.uuid4().hex[:8]}",
    transport="websockets"
)

client.ws_set_options(path="/mqtt")
client.tls_set()

client.on_connect = on_connect
client.on_subscribe = on_subscribe
client.on_message = on_message

try:
    client.connect(BROKER, PORT, 60)
    client.loop_start()

    if not received.wait(timeout=15):
        print("タイムアウト：送受信が完了しませんでした")
finally:
    client.disconnect()
    client.loop_stop()
