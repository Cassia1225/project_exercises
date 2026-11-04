"""RUN_EMQX_TEST=1でのみ、公開EMQXへ架空データの全5役試験を行う。"""
import os

import pytest

from test_hivemq_public import exercise_five_roles_over_websockets_tls


@pytest.mark.skipif(os.getenv("RUN_EMQX_TEST") != "1", reason="公開EMQX試験は明示指定時のみ実施")
def test_five_roles_over_emqx_websockets_tls(monkeypatch):
    exercise_five_roles_over_websockets_tls(monkeypatch, "broker.emqx.io", 8084)
