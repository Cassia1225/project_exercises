import requests, json, datetime, os
from dotenv import load_dotenv

load_dotenv()
URL = "https://weather.googleapis.com/v1/currentConditions:lookup"
KEY = os.getenv("GOOGLE_API_KEY")

params = {
    "key":KEY,
    "location.latitude":"",
    "location.longitude":""
}


def main():
    response = requests.get(URL,params=params)
    
    print(response.status_code)

if __name__ == "__main__":
    main()