"""国土地理院のデータを使い、市区町村名・現在地から代表地点を決める。

市区町村の一覧と代表地点だけをメモリーへ一時保存する。
現在地の座標は、市区町村を特定した後に保存しない。
"""

from concurrent.futures import Future, TimeoutError as FutureTimeout
import re
import threading
import time
import requests
from common.protocol import ProtocolError, coordinates, remaining
from common.providers import fetch_json, ProviderError


def compact(s):
    return re.sub(r"\s+", "", s)


class Locations:
    def __init__(self, session=requests):
        self.session = session
        self._catalog = {}
        self._loaded_at = 0
        self._points = {}
        self._lock = threading.RLock()
        self._flight = None
        self._flight_finished = 0

    def catalog(self, *, until=None):
        if until is None:
            until = time.monotonic() + 5
        remaining(until, 5, "location")
        with self._lock:
            if self._catalog and time.monotonic() - self._loaded_at < 3600:
                return self._catalog
            # 同時検索でも一覧を何度も取得せず、1回の取得結果・失敗を共有する。
            # 失敗後の1秒間も結果を共有し、接続失敗の繰り返しを防ぐ。
            if self._flight is None or (
                self._flight.done() and time.monotonic() - self._flight_finished >= 1
            ):
                self._flight = Future()
                owner = True
            else:
                owner = False
            flight = self._flight
        if not owner:
            try:
                return flight.result(timeout=remaining(until, 5, "location"))
            except FutureTimeout:
                raise ProtocolError(
                    "TIMEOUT",
                    "市区町村一覧の待機期限を超えました。再検索してください。",
                    "location",
                ) from None
        try:
            r = self.session.get(
                "https://maps.gsi.go.jp/js/muni.js",
                timeout=remaining(until, 5, "location"),
            )
            r.raise_for_status()
            r.encoding = "utf-8"
            remaining(until, 5, "location")
            rows = re.findall(
                r'GSI.MUNI_ARRAY\["(\d+)"\]\s*=\s*\x27([^\x27]+)\x27', r.text
            )
            result = {}
            for code, value in rows:
                parts = value.split(",")
                if len(parts) != 4:
                    continue
                pref = compact(parts[1])
                municipal = compact(parts[3])
                code = code.zfill(5)
                result[code] = {
                    "candidate_id": "gsi:" + code,
                    "name": pref + municipal,
                    "prefecture": pref,
                    "country_code": "JP",
                    "municipality_code": code,
                }
            if not result:
                raise ProviderError(
                    "LOCATION_SERVICE_ERROR",
                    "市区町村一覧の形式が変わっています。",
                    "location",
                )
            with self._lock:
                self._catalog = result
                self._loaded_at = time.monotonic()
            with self._lock:
                self._flight_finished = time.monotonic()
            flight.set_result(result)
            return result
        except Exception as exc:
            if isinstance(exc, ProtocolError):
                error = exc
            elif time.monotonic() >= until:
                error = ProtocolError(
                    "TIMEOUT", "市区町村一覧の待機期限を超えました。", "location"
                )
            else:
                error = ProviderError(
                    "LOCATION_SERVICE_ERROR",
                    "市区町村の一覧を取得できませんでした。",
                    "location",
                )
            with self._lock:
                self._flight_finished = time.monotonic()
            flight.set_exception(error)
            raise error from None

    def search(self, query, *, until=None):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 60:
            raise ProtocolError(
                "INVALID_QUERY", "市区町村名を1〜60文字で入力してください。"
            )
        q = compact(query)
        rows = []
        for municipality in self.catalog(until=until).values():
            if q in municipality["name"]:
                rows.append(dict(municipality))

        def sort_key(municipality):
            # 完全一致を先にし、続いて名前の短い順・名前順に並べる。
            different_name = q != municipality["name"]
            name_length = len(municipality["name"])
            return (different_name, name_length, municipality["name"])

        return sorted(rows, key=sort_key)[:50]

    def resolve(self, candidate_id, *, until=None):
        if until is None:
            until = time.monotonic() + 10
        remaining(until, 5, "location")
        if not isinstance(candidate_id, str) or not re.fullmatch(
            r"gsi:\d{5}", candidate_id
        ):
            raise ProtocolError("INVALID_LOCATION", "市区町村の候補IDが不正です。")
        code = candidate_id[4:]
        item = self.catalog(until=until).get(code)
        if not item:
            raise ProtocolError("INVALID_LOCATION", "市区町村の候補が見つかりません。")
        with self._lock:
            if code in self._points:
                return dict(self._points[code])
        raw = fetch_json(
            "https://msearch.gsi.go.jp/address-search/AddressSearch",
            session=self.session,
            params={"q": item["name"]},
            timeout=remaining(until, 5, "location"),
            source="location",
        )
        remaining(until, 5, "location")
        entries = []
        if isinstance(raw, list):
            entries = raw
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            props = entry.get("properties") or {}
            geometry = entry.get("geometry") or {}
            if (
                compact(str(props.get("title", ""))) != item["name"]
                or geometry.get("type") != "Point"
            ):
                continue
            pos = geometry.get("coordinates")
            if not isinstance(pos, list) or len(pos) != 2:
                continue
            lon = pos[0]
            lat = pos[1]
            coordinates(lat, lon)
            result = dict(
                item,
                location_id=candidate_id,
                latitude=lat,
                longitude=lon,
                coordinate_basis="municipality_representative",
                source="国土地理院",
            )
            with self._lock:
                self._points[code] = result
            return dict(result)
        raise ProviderError(
            "LOCATION_UNAVAILABLE",
            "この市区町村の代表地点を取得できませんでした。別の候補をお試しください。",
            "location",
        )

    def current(self, lat, lon, *, until=None):
        if until is None:
            until = time.monotonic() + 15
        coordinates(lat, lon)
        raw = fetch_json(
            "https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress",
            session=self.session,
            params={
                "lat": lat,
                "lon": lon,
            },
            timeout=remaining(until, 5, "location"),
            source="location",
        )
        remaining(until, 5, "location")
        result = None
        if isinstance(raw, dict):
            result = raw.get("results")
        code = None
        if isinstance(result, dict):
            code = result.get("muniCd")
        if not isinstance(code, str) or not re.fullmatch(r"\d{4,5}", code):
            raise ProtocolError(
                "LOCATION_UNRESOLVED",
                "国内の市区町村を特定できません。市区町村名から検索してください。",
            )
        return self.resolve("gsi:" + code.zfill(5), until=until)
