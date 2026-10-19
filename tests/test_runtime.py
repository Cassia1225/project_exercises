"""Catches occupied ports, wrong process order and leaked child processes."""
import os
import socket
import sys
import pytest


def test_occupied_port_fails_before_children_start():
    from run import ensure_ports_free
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));s.listen()
        with pytest.raises(RuntimeError,match='使用中'):ensure_ports_free([('通信制御',s.getsockname()[1])])


def test_launch_plan_has_independent_programs_and_propagates_mode():
    from run import launch_plan
    jobs=launch_plan(no_ui=False,external_broker=False)
    assert [x[0] for x in jobs]==['broker','weather','pollen','recommend','controller','ui']
    assert jobs[1][1][-1]=='weather.worker' and jobs[2][1][-1]=='pollen.worker'
    assert 'streamlit' in jobs[-1][1]
    assert [x[0] for x in launch_plan(no_ui=True,external_broker=True)]==['weather','pollen','recommend','controller']


def test_child_failure_and_stop_terminate_owned_processes():
    from run import Supervisor
    sup=Supervisor()
    try:
        p=sup.start('fixture',[sys.executable,'-u','-c','import time; print("READY fixture",flush=True); time.sleep(60)'])
        sup.wait_ready('fixture',p,timeout=2)
        assert p.poll() is None
        p.terminate();p.wait(timeout=2)
        with pytest.raises(RuntimeError):sup.check()
    finally:sup.stop()
    assert all(p.poll() is not None for _,p in sup.children)


def test_full_demo_subprocess_http_mqtt_and_ctrl_c(tmp_path):
    """No external requests: location is canonicalized using our controlled HTTP fixture."""
    from run import Supervisor
    from server.controller import Controller
    from common.mqtt_transport import MqttCollector
    from tests.test_http import Geo
    from tests.test_transport import today
    with socket.socket() as s:s.bind(('127.0.0.1',0));mqtt_port=s.getsockname()[1]
    with socket.socket() as s:s.bind(('127.0.0.1',0));recommend_port=s.getsockname()[1]
    env=dict(os.environ,APP_MODE='demo',MQTT_HOST='127.0.0.1',MQTT_PORT=str(mqtt_port),
             RECOMMEND_PORT=str(recommend_port),PYTHONDONTWRITEBYTECODE='1')
    sup=Supervisor(env=env)
    try:
        for name,module in [('broker','common.broker'),('weather','weather.worker'),('pollen','pollen.worker'),('recommend','recommend.api')]:
            p=sup.start(name,[sys.executable,'-u','-m',module]);sup.wait_ready(name,p,timeout=8)
        # Real independent workers and recommender; municipality lookup controlled.
        c=Controller(locations=Geo(),collector=MqttCollector(port=mqtt_port,wait_timeout=2),
                     recommend_url=f'http://127.0.0.1:{recommend_port}',is_mock=True)
        query={'schema_version':'1.2-draft','location_input':{'mode':'search','candidate_id':'gsi:13101'},
               'date':today(),'allergy_state':'selected','allergies':['sugi','hinoki']}
        status,result=c.recommend(query)
        assert status==200 and result['data']['level']=='高'
        assert result['meta']['assessed_allergies']==['sugi','hinoki'] and result['meta']['is_mock']
        sup.check()
    finally:sup.stop()
    assert all(p.poll() is not None for _,p in sup.children)
