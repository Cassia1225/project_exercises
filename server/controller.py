"""入力確認→市区町村の確定→MQTTで気象・花粉取得→HTTPで推薦→画面へ返却。"""

from uuid import uuid4
import requests
import time
from common.protocol import (
    SCHEMA,
    ProtocolError,
    validate_query,
    error_response,
    now_iso,
    remaining,
)
from common.mqtt_transport import MqttCollector
from .locations import Locations


class Controller:
    def __init__(
        self,
        locations=None,
        collector=None,
        recommend_url="http://127.0.0.1:8001",
        is_mock=False,
        request_timeout=35,
    ):
        self.locations = locations or Locations()
        self.collector = collector or MqttCollector()
        self.recommend_url = recommend_url.rstrip("/")
        self.is_mock = is_mock
        self.request_timeout = request_timeout

    def recommend(self, query):
        request_id = str(uuid4())
        until = time.monotonic() + self.request_timeout
        try:
            validate_query(query)
            location_input = query["location_input"]
            # 手動検索は候補ID、現在地は緯度・経度から市区町村を決める。
            if location_input["mode"] == "search":
                location = self.locations.resolve(
                    location_input["candidate_id"], until=until
                )
            else:
                location = self.locations.current(
                    location_input["latitude"], location_input["longitude"], until=until
                )
            replies = self.collector.collect(
                location,
                query["date"],
                self.is_mock,
                request_id=request_id,
                until=until,
            )
        except ProtocolError as exc:
            if exc.code == "TIMEOUT":
                status = 504
            elif exc.source == "request":
                status = 400
            else:
                status = 502
            return status, error_response(request_id, [exc.as_dict()], self.is_mock)
        # 気象・花粉の返信を確認し、正常な値とエラーを分ける。
        errors = []
        warnings = []
        collected_data = {}
        fetched = []
        for source in ("weather", "pollen"):
            reply = replies.get(source)
            if reply is None:
                source_name = "花粉"
                if source == "weather":
                    source_name = "気象"
                collected_data[source] = None
                errors.append(
                    {
                        "source": source,
                        "code": "TIMEOUT",
                        "message": f"{source_name}担当から期限内に返信がありませんでした。",
                    }
                )
            elif reply["status"] == "error":
                collected_data[source] = None
                errors.extend(reply["errors"])
            elif reply["data"].get("provider_date") != query["date"]:
                collected_data[source] = None
                errors.append(
                    {
                        "source": source,
                        "code": "DATE_MISMATCH",
                        "message": "提供元の日付が対象日と一致しません。",
                    }
                )
            else:
                collected_data[source] = reply["data"]
                warnings.extend(reply["warnings"])
                if reply.get("fetched_at"):
                    fetched.append(reply["fetched_at"])
        if collected_data["weather"] is None and collected_data["pollen"] is None:
            status = 502
            for error in errors:
                if error["code"] == "TIMEOUT":
                    status = 504
                    break
            return status, error_response(request_id, errors, self.is_mock)

        if fetched:
            fetched_at = max(fetched)
        else:
            fetched_at = now_iso()
        # 取得結果に設定を加え、推薦担当へ渡す。
        payload = {
            "schema_version": SCHEMA,
            "request_id": request_id,
            "location": location,
            "date": query["date"],
            "allergy_state": query["allergy_state"],
            "allergies": query["allergies"],
            "is_mock": self.is_mock,
            "errors": errors,
            "warnings": warnings,
            "fetched_at": fetched_at,
            "weather": collected_data["weather"],
            "pollen": collected_data["pollen"],
        }
        try:
            response = requests.post(
                self.recommend_url + "/api/v1/evaluate",
                json=payload,
                timeout=remaining(until, 3, "recommend"),
            )
            response.raise_for_status()
            result = response.json()
            if (
                not isinstance(result, dict)
                or result.get("schema_version") != SCHEMA
                or result.get("request_id") != request_id
                or result.get("status") not in ("success", "partial", "error")
            ):
                raise ValueError
            if result["status"] != "error":
                if (
                    not isinstance(result.get("data"), dict)
                    or result["data"].get("date") != query["date"]
                    or result.get("details", {}).get("location", {}).get("location_id")
                    != location["location_id"]
                    or result.get("meta", {}).get("is_mock") is not self.is_mock
                ):
                    raise ValueError
            status = 200
            if result["status"] == "error":
                status = 502
            return status, result
        except ProtocolError as exc:
            return 504, error_response(request_id, [exc.as_dict()], self.is_mock)
        except requests.Timeout:
            return 504, error_response(
                request_id,
                [
                    {
                        "source": "recommend",
                        "code": "TIMEOUT",
                        "message": "推薦の待機期限を超えました。再検索してください。",
                    }
                ],
                self.is_mock,
            )
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            return 502, error_response(
                request_id,
                [
                    {
                        "source": "recommend",
                        "code": "RECOMMEND_UNAVAILABLE",
                        "message": "推薦担当に接続できないか、返信が不正です。起動状態を確認してください。",
                    }
                ],
                self.is_mock,
            )
