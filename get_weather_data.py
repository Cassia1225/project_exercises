import requests, json, datetime, os
from dotenv import load_dotenv
import paho.mqtt.client as mqtt

client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2
)

load_dotenv()
URL = "https://api.open-meteo.com/v1/forecast"

#ダミーデータとして、東京駅周辺のロケーション
params = {
    "latitude":35.6812,
    "longitude":139.7671,
    "current": "temperature_2m,wind_speed_10m"
}


def main():
    res = requests.get(URL,params=params)
    
    print(res.status_code)
    
    data = res.json()
    print(data)

if __name__ == "__main__":
    main()