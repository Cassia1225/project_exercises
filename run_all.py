"""5つのプログラムを1つのコマンドでまとめて起動する。

使い方（リポジトリのルートで、仮想環境を有効にしてから）:
    python run_all.py

Ctrl+C を1回押すと、5つすべてが止まる。
各プログラムの表示は、先頭に [気象] などの名前を付けてこの画面にまとめて出す。
"""
import subprocess
import sys
import threading
import time

# (表示名, 実行するコマンド)
# sys.executable は「今このファイルを動かしているPython」。仮想環境のPythonがそのまま使われる
PROGRAMS = [
    ("通信制御", [sys.executable, "-u", "server/server.py"]),
    ("気象", [sys.executable, "-u", "weather/send_weather.py"]),
    ("花粉", [sys.executable, "-u", "pollen/send_pollen.py"]),
    ("推薦", [sys.executable, "-u", "recommend/send_recommend.py"]),
    ("UI", [sys.executable, "-m", "streamlit", "run", "UI/app.py"]),
]


def show_output(name, process):
    """1つのプログラムの出力を、名前を付けて1行ずつ表示する。"""
    for line in process.stdout:
        print(f"[{name}] {line}", end="")


def main():
    processes = []

    for name, command in PROGRAMS:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # エラーの表示も同じ画面に出す
            text=True,
        )
        processes.append((name, process))

        # 出力を読む係を、プログラムごとに裏で動かす
        reader = threading.Thread(target=show_output, args=(name, process), daemon=True)
        reader.start()

        # UIは、ほかの4つがブローカーにつながってから起動する
        if name == "推薦":
            time.sleep(2)

    print("5つのプログラムを起動しました。止めるときは Ctrl+C")

    try:
        # どれか1つでも止まったら知らせる
        while True:
            for name, process in processes:
                if process.poll() is not None:
                    print(f"[{name}] が終了しました（終了コード {process.returncode}）。全体を止めます")
                    raise KeyboardInterrupt
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n停止しています...")
    finally:
        for name, process in processes:
            if process.poll() is None:
                process.terminate()
        for name, process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        print("すべて停止しました")


if __name__ == "__main__":
    main()
