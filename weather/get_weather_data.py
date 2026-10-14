import requests, json, datetime, os
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
from supabase import create_client

load_dotenv()
URL = "https://api.open-meteo.com/v1/forecast"
latitude = 35.6812
longitude = 139.7671

#ダミーデータとして、東京駅周辺のロケーション
params = {
    "latitude":latitude,
    "longitude":longitude,
    "daily":(
            "temperature_2m_mean,"
             "wind_speed_10m_max,"
             "relative_humidity_2m_mean"
    ),
    "forecast_days": 1,
    "timezone":"Asia/Tokyo"
}


def weather_data_output():
    res = requests.get(URL,params=params)
    res.raise_for_status()
    data = res.json()
    daily = data['daily']
    
    current_obj = {
        "time":daily['time'][0],
        "temperature_mean":daily['temperature_2m_mean'][0],
        "humidity_mean":daily['relative_humidity_2m_mean'][0],
        "wind_speed_max":daily["wind_speed_10m_max"][0]
    }
    
    return current_obj
    
    
def check_output(current_obj,daily):
    print(daily)
    print("日時：",current_obj['time'])
    print("気温：",current_obj['temperature_mean'],"℃")
    print("湿度：",current_obj['humidity_mean'],"%")
    print("最大風速:",current_obj['wind_speed_max'])


if __name__ == "__main__":
    weather_data_output()