"""JSONでHTTP要求を受け、処理結果を返す。通信制御・推薦で共用する。"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
import json
from .protocol import ProtocolError, error_response


def make_server(app, host="127.0.0.1", port=8000):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(45)

        def log_message(self, *args):
            # 位置情報や設定を、HTTPのログへ残さない。
            pass

        def do_GET(self):
            self.handle_request()

        def do_POST(self):
            self.handle_request()

        def do_OPTIONS(self):
            self.send_json(
                405,
                error_response(
                    None,
                    [
                        {
                            "source": "http",
                            "code": "METHOD_NOT_ALLOWED",
                            "message": "許可されていない操作です。",
                        }
                    ],
                ),
            )

        def handle_request(self):
            parts = urlsplit(self.path)
            try:
                body = None
                if self.command == "POST":
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 131072:
                        raise ProtocolError(
                            "INVALID_BODY", "送信データが空か、大きすぎます。"
                        )
                    if self.headers.get_content_type() != "application/json":
                        raise ProtocolError(
                            "INVALID_BODY", "JSON形式で送信してください。"
                        )

                    def invalid(_):
                        raise ValueError("nonfinite JSON")

                    body = json.loads(self.rfile.read(length), parse_constant=invalid)
                    if not isinstance(body, dict):
                        raise ProtocolError(
                            "INVALID_BODY", "JSONオブジェクトを送信してください。"
                        )
                status, result = app.dispatch(
                    self.command, parts.path, parse_qs(parts.query), body
                )
            except ProtocolError as exc:
                # 400: 入力不正、502: 取得先の異常、504: 待機時間切れ。
                if exc.code == "TIMEOUT":
                    status = 504
                elif exc.source == "request":
                    status = 400
                else:
                    status = 502
                result = error_response(None, [exc.as_dict()])
            except (ValueError, UnicodeError, TimeoutError):
                status, result = 400, error_response(
                    None,
                    [
                        {
                            "source": "http",
                            "code": "INVALID_BODY",
                            "message": "送信データを読み取れませんでした。",
                        }
                    ],
                )
            except Exception:
                status, result = 500, error_response(
                    None,
                    [
                        {
                            "source": "http",
                            "code": "INTERNAL_ERROR",
                            "message": "処理中にエラーが発生しました。起動した端末を確認してください。",
                        }
                    ],
                )
            self.send_json(status, result)

        def send_json(self, status, result):
            data = json.dumps(result, ensure_ascii=False, allow_nan=False).encode(
                "utf-8"
            )
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def serve(app, host, port, name):
    server = make_server(app, host, port)
    print(f"READY {name} http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def not_found():
    return 404, error_response(
        None,
        [
            {
                "source": "http",
                "code": "NOT_FOUND",
                "message": "接続先が見つかりません。",
            }
        ],
    )
