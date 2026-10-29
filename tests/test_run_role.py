"""担当別の起動を、短い確認用プログラムを実際に起動して調べる。"""
import json
import os
import sys

import pytest


PROBE = '''
import json, os, sys
from pathlib import Path
Path("started.json").write_text(json.dumps({
    "arguments": sys.argv[1:],
    "broker": os.getenv("MQTT_BROKER"),
    "port": os.getenv("MQTT_PORT"),
    "prefix": os.getenv("MQTT_TOPIC_PREFIX"),
    "username": os.getenv("MQTT_USERNAME"),
    "password": os.getenv("MQTT_PASSWORD"),
    "cwd": str(Path.cwd()),
}))
sys.exit(int(os.getenv("PROBE_EXIT_CODE", "0")))
'''


def test_selected_worker_uses_lan_settings_without_changing_local_file(tmp_path, monkeypatch):
    import run_role
    monkeypatch.setattr(run_role, "ROOT", tmp_path)
    (tmp_path / "weather").mkdir()
    (tmp_path / "weather/send_weather.py").write_text(PROBE)
    local_text = "MQTT_BROKER=localhost\nMQTT_PORT=1883\n"
    (tmp_path / ".env").write_text(local_text)
    (tmp_path / ".env.lan").write_text(
        "MQTT_BROKER=192.168.0.10\nMQTT_PORT=1884\n"
        "MQTT_TOPIC_PREFIX=group8/v1\nMQTT_USERNAME=group8\nMQTT_PASSWORD=test-only\n"
    )
    monkeypatch.setenv("MQTT_BROKER", "old-host")
    # 起動した場所に依存せず、設定も担当ファイルもプロジェクトから探す。
    monkeypatch.chdir(tmp_path.parent)
    assert run_role.main(["weather", "--env-file", ".env.lan"]) == 0
    result = json.loads((tmp_path / "started.json").read_text())
    assert result["broker"] == "192.168.0.10"
    assert result["port"] == "1884"
    assert result["prefix"] == "group8/v1"
    assert result["username"] == "group8"
    assert result["password"] == "test-only"
    assert result["cwd"] == str(tmp_path)
    assert (tmp_path / ".env").read_text() == local_text
    assert os.getenv("MQTT_BROKER") == "old-host"  # 親の設定は書き換えない。


def test_ui_starts_streamlit_with_ui_file(tmp_path, monkeypatch):
    import run_role
    monkeypatch.setattr(run_role, "ROOT", tmp_path)
    (tmp_path / "streamlit.py").write_text(PROBE)
    assert run_role.main(["ui"]) == 0
    result = json.loads((tmp_path / "started.json").read_text())
    assert result["arguments"] == ["run", "UI/app.py"]


def test_worker_exit_code_is_returned(tmp_path, monkeypatch):
    import run_role
    monkeypatch.setattr(run_role, "ROOT", tmp_path)
    (tmp_path / "server").mkdir()
    (tmp_path / "server/server.py").write_text(PROBE)
    monkeypatch.setenv("PROBE_EXIT_CODE", "7")
    assert run_role.main(["server"]) == 7


def test_missing_lan_file_stops_before_starting(tmp_path, monkeypatch):
    import run_role
    monkeypatch.setattr(run_role, "ROOT", tmp_path)
    with pytest.raises(SystemExit) as error:
        run_role.main(["weather", "--env-file", "missing.env"])
    assert error.value.code == 2
    assert not (tmp_path / "started.json").exists()


def test_unknown_role_is_rejected():
    import run_role
    with pytest.raises(SystemExit) as error:
        run_role.main(["weathre"])
    assert error.value.code == 2
