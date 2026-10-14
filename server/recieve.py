import paho.mqtt.subscribe as subscribe
import json

# メッセージが届いたら
def on_message(client, userdata, message):
    text = message.payload.decode("utf-8")
    data = json.loads(text) # 文字列を辞書に戻す
    print("届いたデータ：", text)
    print("気温:",data["temperature"],"℃")
    print("湿度:",data["humidity"],"%")


# 指定したトピックのメッセージを待つ
subscribe.callback(
    on_message,
    "project/weather/result",
    hostname="broker.hivemq.com"
)