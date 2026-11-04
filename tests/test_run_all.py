"""run_all.pyの起動引数・終了処理と、本物のStreamlit起動を確認する。"""
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

import run_all

ROOT = Path(__file__).resolve().parents[1]


def load_launcher(monkeypatch, *, exit_code=0, interrupt=False):
    calls = []
    child = SimpleNamespace(terminated=False, waited=0)
    def wait(timeout=None):
        child.waited += 1
        if interrupt and child.waited == 1:
            raise KeyboardInterrupt
        return exit_code
    child.wait = wait
    child.poll = lambda: None
    child.terminate = lambda: setattr(child, "terminated", True)
    child.kill = lambda: None
    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return child
    monkeypatch.setattr(subprocess, "Popen", popen)
    return run_all, calls, child


@pytest.mark.parametrize("exit_code", [0, 7])
def test_launcher_starts_only_ui_and_returns_its_exit_code(monkeypatch, tmp_path, exit_code):
    launcher, calls, child = load_launcher(monkeypatch, exit_code=exit_code)
    monkeypatch.setattr(launcher, "ROOT", tmp_path, raising=False)
    assert launcher.main(["--server.headless", "true"]) == exit_code
    assert calls == [([sys.executable, "-m", "streamlit", "run", str(tmp_path / "UI/app.py"),
                       "--server.headless", "true"], {"cwd": tmp_path})]
    assert not child.terminated


def test_keyboard_interrupt_terminates_and_waits_for_ui(monkeypatch):
    launcher, calls, child = load_launcher(monkeypatch, interrupt=True)
    assert launcher.main([]) == 130
    assert child.terminated and child.waited == 2
    assert len(calls) == 1


@pytest.mark.skipif(sys.platform == "win32", reason="この終了試験はPOSIXのSIGINTを使用する")
def test_run_all_starts_real_streamlit_and_releases_port_on_interrupt(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}/_stcore/health"
    with (tmp_path / "streamlit.log").open("w+") as log:
        process = subprocess.Popen([
            sys.executable, str(ROOT / "run_all.py"), "--server.headless", "true",
            "--server.address", "127.0.0.1", "--server.port", str(port),
            "--browser.gatherUsageStats", "false",
        ], cwd=tmp_path, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 15
            while True:
                assert process.poll() is None, "run_all.pyが起動途中で終了しました"
                try:
                    response = requests.get(url, timeout=0.3)
                    if response.status_code == 200:
                        break
                except requests.RequestException:
                    pass
                assert time.monotonic() < deadline, "Streamlitの起動がタイムアウトしました"
                time.sleep(0.1)
            assert response.text == "ok"
            process.send_signal(signal.SIGINT)
            assert process.wait(timeout=10) == 130
            with pytest.raises(requests.ConnectionError):
                requests.get(url, timeout=0.5)
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
