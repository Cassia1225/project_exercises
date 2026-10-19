"""Real local MQTT: catches subscription races, mixed searches and late replies."""
import json
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
import paho.mqtt.client as mqtt


@pytest.fixture(scope='module')
def broker():
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    code='''import asyncio
from amqtt.broker import Broker
async def main():
 b=Broker({'listeners':{'default':{'type':'tcp','bind':'127.0.0.1:PORT'}},'plugins':{'amqtt.plugins.authentication.AnonymousAuthPlugin':{'allow_anonymous':True}}})
 await b.start()
 try: await asyncio.Event().wait()
 finally: await b.shutdown()
asyncio.run(main())'''.replace('PORT',str(port))
    proc=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        end=time.monotonic()+8
        while True:
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:
                if proc.poll() is not None or time.monotonic()>end:raise RuntimeError('test broker failed')
                time.sleep(.05)
        yield port
    finally:
        proc.terminate()
        try:proc.wait(timeout=3)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=3)


def location():return {'location_id':'gsi:13101','latitude':35.69,'longitude':139.75}
def today():return datetime.now(timezone(timedelta(hours=9))).date().isoformat()


def test_real_request_reply_parallel_and_no_personal_data(broker):
    from common.mqtt_transport import MqttCollector, Worker
    seen=[]
    def provider(r):
        seen.append(r)
        assert 'allergies' not in r and 'allergy_state' not in r
        return {'provider_date':r['date'],'echo':r['request_id']}
    workers=[Worker(s,provider,port=broker,is_mock=True) for s in ('weather','pollen')]
    for w in workers:w.start()
    try:
        def collect(_):
            return MqttCollector(port=broker,wait_timeout=2).collect(location(),today(),True)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(collect,range(2)))
        for replies in results:
            assert set(replies)=={'weather','pollen'}
            ids={r['data']['echo'] for r in replies.values()}
            assert len(ids)==1
        assert results[0]['pollen']['request_id']!=results[1]['pollen']['request_id']
        assert len(seen)==4
    finally:
        for w in workers:w.stop()


def test_worker_stopped_returns_available_source_before_deadline(broker):
    from common.mqtt_transport import MqttCollector, Worker
    w=Worker('weather',lambda r:{'provider_date':r['date'],'weather_code':0},port=broker,is_mock=True)
    w.start()
    try:
        start=time.monotonic()
        r=MqttCollector(port=broker,wait_timeout=.4).collect(location(),today(),True)
        assert set(r)=={'weather'} and time.monotonic()-start<2
    finally:w.stop()


def test_worker_deduplicates_and_ignores_retained_or_expired_requests(broker):
    from common.mqtt_transport import Worker
    seen=[]
    w=Worker('pollen',lambda r:seen.append(r) or {'provider_date':r['date']},port=broker,is_mock=True)
    w.start()
    c=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='test-'+uuid4().hex)
    c.connect('127.0.0.1',broker);c.loop_start()
    r={'schema_version':'1.2-draft','request_id':str(uuid4()),'controller_id':'test',
       'location_id':'gsi:13101','latitude':35.69,'longitude':139.75,'date':today(),
       'expires_at':(datetime.now(timezone.utc)+timedelta(seconds=3)).isoformat(),'is_mock':True}
    try:
        for _ in range(2):c.publish('project_exercises/v1/pollen/request',json.dumps(r),qos=1).wait_for_publish(timeout=1)
        c.publish('project_exercises/v1/pollen/request',json.dumps(dict(r,request_id=str(uuid4()),expires_at='2000-01-01T00:00:00Z')),qos=1)
        end=time.monotonic()+2
        while not seen and time.monotonic()<end:time.sleep(.02)
        time.sleep(.1)
        assert len(seen)==1
    finally:c.disconnect();c.loop_stop();w.stop()


def test_collector_rejects_wrong_id_day_mode_source_and_keeps_first_reply(broker):
    from common.mqtt_transport import MqttCollector
    c=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='test-'+uuid4().hex)
    ready=__import__('threading').Event()
    c.on_connect=lambda client,*args:client.subscribe('project_exercises/v1/+/request',qos=1)
    c.on_subscribe=lambda *args:ready.set()
    def on_message(client,_,message):
        r=json.loads(message.payload);source=message.topic.split('/')[-2]
        reply={k:r[k] for k in ('schema_version','request_id','controller_id','location_id','date','is_mock')}
        reply.update(source=source,status='success',data={'marker':'first'},errors=[],warnings=[],fetched_at=datetime.now(timezone.utc).isoformat())
        topic=f"project_exercises/v1/{r['controller_id']}/{source}/result"
        for k,v in [('request_id',str(uuid4())),('date','2000-01-01'),('is_mock',False),('source','other')]:
            client.publish(topic,json.dumps(dict(reply,**{k:v})),qos=1)
        client.publish(topic,json.dumps(reply),qos=1)
        client.publish(topic,json.dumps(dict(reply,data={'marker':'duplicate'})),qos=1)
    c.on_message=on_message;c.connect('127.0.0.1',broker);c.loop_start()
    try:
        assert ready.wait(2)
        r=MqttCollector(port=broker,wait_timeout=2).collect(location(),today(),True)
        assert set(r)=={'weather','pollen'}
        assert all(x['data']['marker']=='first' for x in r.values())
    finally:c.disconnect();c.loop_stop()
