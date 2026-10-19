"""このPC内で動くMQTTの中継役。アプリ終了時に停止する。"""

import asyncio
import logging
import os
import signal
from amqtt.broker import Broker
from dotenv import load_dotenv


async def run_broker():
    stop = asyncio.Event()

    def request_stop(*args):
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, request_stop)
    broker = Broker(
        {
            "listeners": {
                "default": {
                    "type": "tcp",
                    "bind": f"127.0.0.1:{int(os.getenv('MQTT_PORT','1883'))}",
                    "max_connections": 64,
                }
            },
            "plugins": {
                "amqtt.plugins.authentication.AnonymousAuthPlugin": {
                    "allow_anonymous": True
                }
            },
        }
    )
    await broker.start()
    print("READY broker", flush=True)
    try:
        await stop.wait()
    finally:
        await broker.shutdown()


def main():
    load_dotenv()
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(run_broker())


if __name__ == "__main__":
    main()
