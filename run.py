"""5担当のプログラムとMQTT Brokerを順に起動する。Ctrl+Cでまとめて停止する。"""

import argparse
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import requests
from dotenv import load_dotenv

#プロジェクトのフォルダーがどこにあるのかを調べて、ROOTに保存している。
# __file__ はrun.pyの場所
# resolve() 絶対パスに変換
#parent run.pyが入っているフォルダー
ROOT = Path(__file__).resolve().parent


def ensure_ports_free(ports):
    """起動前に、必要なポートが他のプログラムに使われていないか確認する。"""
    seen = set()
    for label, port in ports:
        if port in seen:
            raise RuntimeError(f"{label}：他の担当と同じポートを指定しています。")
        seen.add(port)
        if not 1 <= port <= 65535:
            raise RuntimeError(f"{label}：ポートは1〜65535です。")
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                raise RuntimeError(
                    f"{label}のポート {port} は使用中です。先に起動したアプリを終了するか、ポートを変更してください。"
                ) from None


def launch_plan(no_ui=False, external_broker=False, ui_port=None):
    """起動する順番と、各プログラムの実行方法を一覧にする。"""
    jobs = []
    for name, module in [
        ("broker", "common.broker"),
        ("weather", "weather.worker"),
        ("pollen", "pollen.worker"),
        ("recommend", "recommend.api"),
        ("controller", "server.api"),
    ]:
        if name == "broker" and external_broker:
            continue
        jobs.append((name, [sys.executable, "-u", "-m", module]))
    if not no_ui:
        jobs.append(
            (
                "ui",
                [
                    sys.executable,
                    "-m",
                    "streamlit",
                    "run",
                    str(ROOT / "UI/app.py"),
                    "--server.address=127.0.0.1",
                    f'--server.port={ui_port or os.getenv("UI_PORT","8501")}',
                    "--server.headless=true",
                    "--browser.gatherUsageStats=false",
                ],
            )
        )
    return jobs


class Supervisor:
    """起動した各プログラムを覚え、起動確認と終了をまとめて行う。"""

    def __init__(self, env=None):
        self.env = dict(env or os.environ)
        self.children = []
        self.ready = set()
        self.condition = threading.Condition()

    def start(self, name, command):
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
        )
        self.children.append((name, process))

        def reader():
            try:
                for line in process.stdout:
                    if line.startswith("READY " + name):
                        with self.condition:
                            self.ready.add(name)
                            self.condition.notify_all()
                    print(f"[{name}] {line.rstrip()}", flush=True)
            finally:
                process.stdout.close()

        threading.Thread(target=reader, daemon=True, name="logs-" + name).start()
        return process

    def check(self):
        for name, process in self.children:
            if process.poll() is not None:
                raise RuntimeError(
                    f"{name}が停止しました（終了コード {process.returncode}）。上の起動メッセージを確認してください。"
                )

    def wait_ready(self, name, process, timeout=10):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            self.check()
            if name in self.ready:
                return
            if name == "ui":
                try:
                    response = requests.get(
                        f'http://127.0.0.1:{self.env.get("UI_PORT","8501")}/_stcore/health',
                        timeout=0.3,
                    )
                    if response.status_code == 200:
                        return
                except requests.RequestException:
                    pass
            with self.condition:
                self.condition.wait(0.05)
        raise RuntimeError(f"{name}の起動を確認できませんでした。")

    def stop(self):
        for _, process in reversed(self.children):
            if process.poll() is None:
                process.terminate()
        for _, process in reversed(self.children):
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def main(argv=None):
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(
        description="花粉対策ナビをまとめて起動します。停止はCtrl+C。"
    )
    parser.add_argument(
        "--demo", action="store_true", help="APIキーなしの架空予報で動作確認"
    )
    parser.add_argument("--no-ui", action="store_true", help="画面を起動せず通信を確認")
    parser.add_argument(
        "--external-broker",
        action="store_true",
        help="MQTT_HOST/MQTT_PORTの既存Brokerを使用",
    )
    for name, default in [
        ("mqtt", 1883),
        ("controller", 8000),
        ("recommend", 8001),
        ("ui", 8501),
    ]:
        parser.add_argument(
            "--" + name + "-port",
            type=int,
            default=int(os.getenv(name.upper() + "_PORT", str(default))),
        )
    args = parser.parse_args(argv)
    # 各担当へ渡す起動設定。APIキーを画面やログへ表示しない。
    env = dict(os.environ)
    if args.demo:
        env["APP_MODE"] = "demo"
    else:
        env["APP_MODE"] = "live"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for name in ("mqtt", "controller", "recommend", "ui"):
        env[name.upper() + "_PORT"] = str(getattr(args, name + "_port"))
    env["CONTROLLER_URL"] = f"http://127.0.0.1:{args.controller_port}"
    env["RECOMMEND_URL"] = f"http://127.0.0.1:{args.recommend_port}"
    supervisor = Supervisor(env)
    try:
        for module in ("amqtt", "streamlit", "paho.mqtt", "requests"):
            if importlib.util.find_spec(module) is None:
                raise RuntimeError(
                    "必要なライブラリがありません。python -m pip install -r requirements.txt を実行してください。"
                )
        if not args.external_broker and env.get("MQTT_HOST", "127.0.0.1") not in (
            "127.0.0.1",
            "localhost",
        ):
            raise RuntimeError(
                "外部Brokerを使う場合は --external-broker を指定してください。"
            )
        ports = [("通信制御", args.controller_port), ("推薦", args.recommend_port)]
        if not args.external_broker:
            ports.append(("MQTT", args.mqtt_port))
        if not args.no_ui:
            ports.append(("画面", args.ui_port))
        ensure_ports_free(ports)
        if args.demo:
            print("デモモード（予報は架空値）", flush=True)
        else:
            print("実APIモード", flush=True)
        if not args.demo and not env.get("GOOGLE_POLLEN_API_KEY", "").strip():
            print(
                "花粉APIキー未設定：気象のみ表示します。花粉取得には.envの設定が必要です。",
                flush=True,
            )
        for name, command in launch_plan(
            args.no_ui, args.external_broker, args.ui_port
        ):
            process = supervisor.start(name, command)
            supervisor.wait_ready(name, process, timeout=15)
        if not args.no_ui:
            print(f"起動完了。画面：http://localhost:{args.ui_port}", flush=True)
        else:
            print("起動完了。HTTP/MQTTの動作を確認できます。", flush=True)
        print("停止するときは、この端末で Ctrl+C を押してください。", flush=True)
        while True:
            supervisor.check()
            time.sleep(0.25)
    except KeyboardInterrupt:
        return 0
    except (RuntimeError, OSError) as exc:
        print("起動できませんでした：" + str(exc), file=sys.stderr, flush=True)
        return 1
    finally:
        supervisor.stop()


if __name__ == "__main__":
    raise SystemExit(main())
