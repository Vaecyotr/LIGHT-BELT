"""Background failures are delivered on the owning ASGI event loop."""
import asyncio
import threading

from host_services import ws


def test_background_error_is_dispatched_on_bound_loop_and_closed(monkeypatch):
    received = []

    async def run():
        loop = asyncio.get_running_loop()
        delivered = asyncio.Event()

        async def record(kind, data):
            received.append((kind, data, asyncio.get_running_loop()))
            delivered.set()

        monkeypatch.setattr(ws, 'broadcast', record)
        ws.bind_event_loop(loop)
        sender = threading.Thread(target=ws.publish_error, args=({'code': 'MEDIA_ERROR'},))
        sender.start()
        sender.join(timeout=1)
        assert not sender.is_alive()
        await asyncio.wait_for(delivered.wait(), timeout=1)
        assert received == [('error.event', {'code': 'MEDIA_ERROR'}, loop)]
        await ws.close_event_loop()
        ws.publish_error({'code': 'AFTER_SHUTDOWN'})
        await asyncio.sleep(0)
        assert len(received) == 1

    asyncio.run(run())
