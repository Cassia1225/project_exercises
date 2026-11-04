"""python run_all.pyで画面と、そこから呼ぶ取得・推薦処理を起動する。"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main(arguments=None):
    if arguments is None:
        arguments = sys.argv[1:]
    command = [sys.executable, "-m", "streamlit", "run", str(ROOT / "UI/app.py"), *arguments]
    process = subprocess.Popen(command, cwd=ROOT)
    print("花粉対策ナビを起動しました。止めるときは Ctrl+C", flush=True)
    try:
        return process.wait()
    except KeyboardInterrupt:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        print("花粉対策ナビを停止しました", flush=True)
        return 130


if __name__ == "__main__":
    sys.exit(main())
