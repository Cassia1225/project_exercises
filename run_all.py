"""5つのプログラムを1つのコマンドでまとめて起動する。

使い方（リポジトリのルートで、仮想環境を有効にしてから）:
    python run_all.py

Ctrl+C を1回押すと、5つすべてが止まる。
"""
import subprocess
import sys
import time

# 起動するファイルの一覧（UIは最後）
PROGRAMS = [
    "server/server.py",
    "weather/send_weather.py",
    "pollen/send_pollen.py",
    "recommend/send_recommend.py",
]

# sys.executable は「今このファイルを動かしているPython」（仮想環境のPython）
# -u は、print の表示をためずにすぐ出す指定（ないとログが遅れて出る）
processes = []
for program in PROGRAMS:
    #起動したプログラムを操作するためのオブジェクトを保存。停止に使う。
    processes.append(subprocess.Popen([sys.executable, "-u", program]))

# 4つがブローカーにつながるのを2秒待ってから、UIを起動する
time.sleep(2)
processes.append(subprocess.Popen([sys.executable, "-m", "streamlit", "run", "UI/app.py"]))

print("5つのプログラムを起動しました。止めるときは Ctrl+C")

try:
    # Ctrl+C が押されるまで、ずっと待つ
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    # 5つすべてに「止まって」と合図し、止まるのを待つ
    for process in processes:
        process.terminate()#終了を要求する。
    for process in processes:
        process.wait()#それぞれの終了を待つ
    print("すべて停止しました")
