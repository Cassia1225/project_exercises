
import uuid
import paho.mqtt.client as mqtt

BROKER = "broker.emqx.io"
PORT = 8084
TOPIC = "projectensyuu/team8/test-7c4a91"

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Broker接続成功！")
        client.subscribe(TOPIC, qos=1)
    else:
        print("接続失敗:", reason_code)

def on_subscribe(client, userdata, mid, reason_codes, properties):
    print("購読結果:", reason_codes)
    print("メッセージを待機中...")

def on_message(client, userdata, message):
    text = message.payload.decode("utf-8")
    print(f"\n受信成功！: {text}")

client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id=f"receiver-{uuid.uuid4().hex[:8]}",
    transport="websockets"
)

client.ws_set_options(path="/mqtt")
client.tls_set()

client.on_connect = on_connect
client.on_subscribe = on_subscribe
client.on_message = on_message

try:
    client.connect(BROKER, PORT, 60)
    client.loop_forever()
except KeyboardInterrupt:
    print("\n受信を終了しました")
finally:
    client.disconnect()
