"""画面からのHTTP要求を受け、検索・現在地取得・対策取得へ振り分ける。"""

import os
from dotenv import load_dotenv
from common.protocol import SCHEMA, coordinates
from common.http_api import serve, not_found
from .controller import Controller


class ControllerApp:
    def __init__(self, controller):
        self.controller = controller

    def dispatch(self, method, path, query, body):
        if method == "GET" and path == "/health":
            mode = "live"
            if self.controller.is_mock:
                mode = "demo"
            return 200, {
                "status": "ok",
                "service": "controller",
                "schema_version": SCHEMA,
                "mode": mode,
            }
        if method == "GET" and path == "/api/v1/locations/options":
            # 名前検索の50件制限を使わず、選択用の一覧を自治体コード順に返す。
            catalog = self.controller.locations.catalog()
            candidates = []
            for code in sorted(catalog):
                candidates.append(catalog[code])
            return 200, {
                "schema_version": SCHEMA,
                "candidates": candidates,
                "errors": [],
            }
        if method == "GET" and path == "/api/v1/locations":
            return 200, {
                "schema_version": SCHEMA,
                "candidates": self.controller.locations.search(
                    query.get("query", [""])[0]
                ),
                "errors": [],
            }
        if method == "POST" and path == "/api/v1/locations/current":
            coordinates(body.get("latitude"), body.get("longitude"))
            return 200, {
                "schema_version": SCHEMA,
                "location": self.controller.locations.current(
                    body["latitude"], body["longitude"]
                ),
                "errors": [],
            }
        if method == "POST" and path == "/api/v1/recommendations":
            return self.controller.recommend(body)
        return not_found()


def main():
    load_dotenv()
    controller = Controller(
        recommend_url=os.getenv("RECOMMEND_URL", "http://127.0.0.1:8001"),
        is_mock=os.getenv("APP_MODE", "live") == "demo",
    )
    serve(
        ControllerApp(controller),
        os.getenv("CONTROLLER_HOST", "127.0.0.1"),
        int(os.getenv("CONTROLLER_PORT", "8000")),
        "controller",
    )


if __name__ == "__main__":
    main()
