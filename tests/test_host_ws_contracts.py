"""Anonymous REST and one-use WebSocket ticket contracts."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from host_services import ws, config, engine_adapter
from host_services.main import app


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def test_anonymous_rest_reads_writes_and_ws_ticket_are_available(client, monkeypatch):
    assert client.get('/api/v1/shows').status_code == 200
    assert client.get('/api/v1/state').status_code == 200

    monkeypatch.setitem(engine_adapter._state, 'brightness_scale', 0.5)
    write = client.post('/api/v1/brightness/set', json={'brightness_scale': 0.17})
    assert write.status_code == 200
    assert client.get('/api/v1/brightness').json()['data']['brightness_scale'] == 0.17

    ticket = client.post('/api/v1/session/ws-ticket', json={'subscribe': ['heartbeat']})
    assert ticket.status_code == 200
    assert ticket.json()['data']['ws_ticket']


@pytest.mark.parametrize('authorization', ['Bearer invalid', 'Basic invalid', 'Bearer legacy-opaque-token'])
def test_rest_passthrough_ignores_authorization_headers(client, monkeypatch, authorization):
    monkeypatch.setitem(engine_adapter._state, 'brightness_scale', 0.5)
    headers = {'Authorization': authorization}
    assert client.post('/api/v1/brightness/set', json={'brightness_scale': 0.17}, headers=headers).status_code == 200
    ticket = client.post('/api/v1/session/ws-ticket', json={'subscribe': ['heartbeat']}, headers=headers)
    assert ticket.status_code == 200


def test_new_ws_ticket_reclaims_expired_ticket_and_keeps_single_use(monkeypatch):
    now = [1000]
    monkeypatch.setattr(ws, '_now', lambda: now[0])
    monkeypatch.setattr(ws, '_ws_tickets', {})
    expired = ws.create_ws_ticket(['error.event'], 'testserver', secure=False)['ws_ticket']
    now[0] += 1
    live = ws.create_ws_ticket(['heartbeat'], 'testserver', secure=False)['ws_ticket']
    now[0] += config.WS_TICKET_EXPIRE_SECONDS - 1

    ws.create_ws_ticket(['playback.progress'], 'testserver', secure=False)

    assert len(ws._ws_tickets) == 2
    assert expired not in ws._ws_tickets
    consumed = ws.consume_ws_ticket(live)
    assert consumed is not None
    assert consumed['subscribe'] == ['heartbeat']
    assert ws.consume_ws_ticket(live) is None


def test_anonymous_ticket_allows_one_websocket_handshake(client):
    response = client.post('/api/v1/session/ws-ticket', json={'subscribe': ['heartbeat']})
    assert response.status_code == 200
    ticket = response.json()['data']['ws_ticket']
    with client.websocket_connect('/ws?ticket=' + ticket) as socket:
        assert socket.receive_json()['type'] == 'session.connected'
    with pytest.raises(WebSocketDisconnect) as reused:
        with client.websocket_connect('/ws?ticket=' + ticket):
            pytest.fail('Reused ticket opened a second connection')
    assert reused.value.code == 4401


@pytest.mark.parametrize('url', ['/ws', '/ws?ticket=invalid'])
def test_websocket_still_rejects_missing_or_invalid_ticket(client, url):
    with pytest.raises(WebSocketDisconnect) as rejected:
        with client.websocket_connect(url):
            pytest.fail('Invalid ticket opened a WebSocket connection')
    assert rejected.value.code == 4401


@pytest.mark.parametrize('scheme,ws_scheme', [('http', 'ws'), ('https', 'wss')])
def test_ticket_websocket_url_uses_the_request_transport(client, scheme, ws_scheme):
    response = client.post(
        f'{scheme}://testserver:8443/api/v1/session/ws-ticket',
        json={'subscribe': ['heartbeat']},
        headers={'Authorization': 'Bearer legacy-opaque-token'},
    )
    assert response.status_code == 200
    assert response.json()['data']['ws_url'].startswith(f'{ws_scheme}://testserver:8443/ws?ticket=')
