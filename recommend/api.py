"""推薦担当のHTTP受付。届いたデータを確認して、対策の判定を呼び出す。"""

import os
from uuid import UUID
from dotenv import load_dotenv
from common.protocol import SCHEMA, ProtocolError, base, valid_date, settings
from common.http_api import serve, not_found
from .service import assess


class RecommendationApp:
    def dispatch(self, method, path, query, body):
        if method == "GET" and path == "/health":
            return 200, {
                "status": "ok",
                "service": "recommend",
                "schema_version": SCHEMA,
            }
        if method == "POST" and path == "/api/v1/evaluate":
            base(body)
            valid_date(body.get("date"))
            settings(body)
            try:
                UUID(body.get("request_id"))
            except (TypeError, ValueError, AttributeError):
                raise ProtocolError("INVALID_ID", "検索IDが不正です。") from None
            if not isinstance(body.get("location"), dict):
                raise ProtocolError(
                    "INVALID_LOCATION", "確定した市区町村がありません。"
                )
            for source in ("weather", "pollen"):
                data = body.get(source)
                if data is not None and (
                    not isinstance(data, dict)
                    or data.get("provider_date") != body["date"]
                ):
                    raise ProtocolError(
                        "INVALID_DATA", "対象日の正規化データを指定してください。"
                    )
            result = assess(body)
            status = 200
            if result["status"] == "error":
                status = 502
            return status, result
        return not_found()


def main():
    load_dotenv()
    serve(
        RecommendationApp(),
        os.getenv("RECOMMEND_HOST", "127.0.0.1"),
        int(os.getenv("RECOMMEND_PORT", "8001")),
        "recommend",
    )


if __name__ == "__main__":
    main()
