import paho.mqtt.publish as publish
import json
from get_weather_data import weather_data_output

whether_data = weather_data_output()

weather = json.dumps(whether_data)

# メッセージを1回送る
publish.single(
    "project/weather/result",
    payload=weather,
    hostname="broker.hivemq.com"
)

print("気象情報を送信しました")