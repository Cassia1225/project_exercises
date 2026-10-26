"""自分の担当プログラムだけを起動する。

1台で全部動かす場合は、従来どおり python run_all.py を使う。
各自のPCで動かす場合の例:
    python run_role.py weather --env-file .env.lan
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

# このファイルが置かれている、プロジェクトのフォルダー。
ROOT = Path(__file__).resolve().parent
print(f"ROOT : {ROOT}")

# 左側が起動時に指定する担当名、右側がその担当のファイル。
PROGRAMS = {
    "server": "server/server.py",
    "weather": "weather/send_weather.py",
    "pollen": "pollen/send_pollen.py",
    "recommend": "recommend/send_recommend.py",
}


def main(arguments=None):
    # コマンドに書かれた担当名と、設定ファイル名を読み取る。
    parser = argparse.ArgumentParser(description="自分の担当だけを起動します")
    parser.add_argument(
        "role",
        choices=["ui", "server", "weather", "pollen", "recommend"],
        help="ui=画面、server=通信制御、weather=気象、pollen=花粉、recommend=推薦",
    )
    parser.add_argument("--env-file", help="複数PC用の設定ファイル（例: .env.lan）")
    args = parser.parse_args(arguments)

    # 指定がなければ従来の .env、指定があればそのファイルを使う。
    if args.env_file is None:
        env_file = ROOT / ".env"
    else:
        env_file = ROOT / args.env_file
        if not env_file.is_file():
            parser.error("設定ファイルが見つかりません: " + str(env_file))

    # 設定は子プログラムにだけ渡す。.envや、今のターミナルの設定は書き換えない。
    environment = os.environ.copy()
    if env_file.is_file():
        settings = dotenv_values(env_file, interpolate=False)
        for name, value in settings.items():
            if value is not None:
                environment[name] = value

    # UIだけはStreamlitで起動する。他の担当は通常のPythonで起動する。
    if args.role == "ui":
        command = [sys.executable, "-m", "streamlit", "run", "UI/app.py"]
    else:
        program = PROGRAMS[args.role]
        command = [sys.executable, "-u", program]

    print("起動する担当:", args.role, flush=True)
    print("接続先:", environment.get("MQTT_BROKER", "localhost"), flush=True)
    print("ポート:", environment.get("MQTT_PORT", "1883"), flush=True)
    print("止めるときは Ctrl+C を押してください", flush=True)

    try:
        # cwdを固定し、違うフォルダーから起動しても担当ファイルを見つけられるようにする。
        result = subprocess.run(command, cwd=ROOT, env=environment)
        return result.returncode
    except KeyboardInterrupt:
        print("担当プログラムを停止しました")
        return 130


if __name__ == "__main__":
    sys.exit(main())
