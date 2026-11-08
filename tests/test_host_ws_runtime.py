"""Background failures are delivered on the owning ASGI event loop."""
import asyncio
import threading

from starlette.websockets import WebSocket

from host_services import auth_manager, ws


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


def _websocket_boundary(received_messages):
    """Build a WebSocket at the ASGI receive/send boundary, without a fake app."""
    async def receive():
        return await received_messages.get()

    sent_messages = []

    async def send(message):
        sent_messages.append(message)

    scope = {
        'type': 'websocket', 'asgi': {'version': '3.0', 'spec_version': '2.3'},
        'scheme': 'ws', 'path': '/ws', 'raw_path': b'/ws', 'query_string': b'',
        'headers': [], 'client': ('test-client', 1234), 'server': ('host', 80),
        'subprotocols': [], 'state': {},
    }
    return WebSocket(scope, receive, send), sent_messages


def test_disconnect_without_heartbeat_releases_connection():
    async def run():
        messages = asyncio.Queue()
        await messages.put({'type': 'websocket.connect'})
        ticket = auth_manager.create_ws_ticket(['error.event'])['ws_ticket']
        socket, sent = _websocket_boundary(messages)
        endpoint = asyncio.create_task(ws.ws_endpoint(socket, ticket=ticket))
        try:
            while not any(message['type'] == 'websocket.send' for message in sent):
                await asyncio.sleep(0)
            await messages.put({'type': 'websocket.disconnect', 'code': 1000})
            await asyncio.wait_for(endpoint, timeout=0.5)
            assert not ws._connections
        finally:
            if not endpoint.done():
                endpoint.cancel()
                await asyncio.gather(endpoint, return_exceptions=True)

    asyncio.run(run())


def test_host_shutdown_closes_active_websocket_tasks():
    async def run():
        messages = asyncio.Queue()
        await messages.put({'type': 'websocket.connect'})
        ticket = auth_manager.create_ws_ticket(['error.event'])['ws_ticket']
        socket, sent = _websocket_boundary(messages)
        endpoint = asyncio.create_task(ws.ws_endpoint(socket, ticket=ticket))
        try:
            while not any(message['type'] == 'websocket.send' for message in sent):
                await asyncio.sleep(0)
            await ws.close_event_loop()
            assert endpoint.done()
            assert not ws._connections
        finally:
            if not endpoint.done():
                endpoint.cancel()
                await asyncio.gather(endpoint, return_exceptions=True)

    asyncio.run(run())
