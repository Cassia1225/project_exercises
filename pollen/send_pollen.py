import paho.mqtt.publish as publish
import json
from get_pollen_data import get_pollen_info

pollen_data = get_pollen_info()

pollen = json.dumps(pollen_data)

# メッセージを1回送る
publish.single(
    "project/pollen/result",
    payload=pollen,
    hostname="broker.hivemq.com"
)

print("花粉情報を送信しました")