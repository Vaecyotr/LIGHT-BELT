"""Direct REST access, token compatibility, and WebSocket ticket contracts."""
import time

import jwt
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from host_services import auth_manager, config, engine_adapter
from host_services.main import app


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def token(**changes):
    claims = {
        'sub': 'contract-client', 'scope': list(auth_manager.DEFAULT_SCOPE),
        'exp': int(time.time()) + 60, 'type': 'access',
    }
    claims.update(changes)
    return jwt.encode(claims, auth_manager.JWT_SECRET, algorithm='HS256')


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


@pytest.mark.parametrize('claims', [
    {'exp': int(time.time()) - 60},
    {'type': 'refresh'},
    {'scope': 'lights:write'},
    {'sub': ''},
    {'exp': []},
    {'exp': None},
    {'exp': float('inf')},
])
def test_rejects_expired_wrong_type_or_malformed_claims(claims):
    value = token(**claims)
    assert auth_manager.verify_access_token(value) is None


def test_missing_expiration_is_rejected():
    value = jwt.encode({'sub': 'client', 'scope': ['state:read'], 'type': 'access'}, auth_manager.JWT_SECRET, algorithm='HS256')
    assert auth_manager.verify_access_token(value) is None


@pytest.mark.parametrize('authorization', ['Bearer invalid', 'Basic invalid', 'Bearer ' + token(scope=['state:read'])])
def test_rest_passthrough_ignores_authorization_headers(client, monkeypatch, authorization):
    monkeypatch.setitem(engine_adapter._state, 'brightness_scale', 0.5)
    headers = {'Authorization': authorization}
    assert client.post('/api/v1/brightness/set', json={'brightness_scale': 0.17}, headers=headers).status_code == 200
    ticket = client.post('/api/v1/session/ws-ticket', json={'subscribe': ['heartbeat']}, headers=headers)
    assert ticket.status_code == 200


def test_refresh_preserves_granted_scopes_and_rotates_once(client):
    refresh = auth_manager.create_refresh_token('restricted', ['state:read'])
    response = client.post('/api/v1/auth/refresh', json={'refresh_token': refresh})
    assert response.status_code == 200
    assert response.json()['data']['scope'] == ['state:read']
    assert client.post('/api/v1/auth/refresh', json={'refresh_token': refresh}).status_code == 401


def test_new_refresh_token_reclaims_expired_tokens_and_preserves_live_scope(monkeypatch):
    now = [1000]
    monkeypatch.setattr(auth_manager, '_now', lambda: now[0])
    monkeypatch.setattr(auth_manager, '_refresh_tokens', {})
    expired = auth_manager.create_refresh_token('expired', ['state:read'])
    now[0] += 1
    live = auth_manager.create_refresh_token('live', ['state:read', 'playback:write'])
    live_expiry = now[0] + config.REFRESH_TOKEN_EXPIRE_SECONDS
    now[0] += config.REFRESH_TOKEN_EXPIRE_SECONDS - 1

    auth_manager.create_refresh_token('new', ['state:read'])

    assert len(auth_manager._refresh_tokens) == 2
    assert expired not in auth_manager._refresh_tokens
    assert auth_manager.consume_refresh_token(live) == {
        'client_id': 'live', 'scope': ['state:read', 'playback:write'],
        'expires_at': live_expiry,
    }


def test_new_ws_ticket_reclaims_expired_ticket_and_keeps_single_use(monkeypatch):
    now = [1000]
    monkeypatch.setattr(auth_manager, '_now', lambda: now[0])
    monkeypatch.setattr(auth_manager, '_ws_tickets', {})
    expired = auth_manager.create_ws_ticket(['error.event'])['ws_ticket']
    now[0] += 1
    live = auth_manager.create_ws_ticket(['heartbeat'])['ws_ticket']
    now[0] += config.WS_TICKET_EXPIRE_SECONDS - 1

    auth_manager.create_ws_ticket(['playback.progress'])

    assert len(auth_manager._ws_tickets) == 2
    assert expired not in auth_manager._ws_tickets
    consumed = auth_manager.consume_ws_ticket(live)
    assert consumed is not None
    assert consumed['subscribe'] == ['heartbeat']
    assert auth_manager.consume_ws_ticket(live) is None


def test_status_and_static_assets_remain_public(client):
    assert client.get('/api/v1/status').status_code == 200
    assert client.get('/').status_code == 200


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
def test_ticket_websocket_url_uses_the_authenticated_request_transport(client, scheme, ws_scheme):
    response = client.post(
        f'{scheme}://testserver:8443/api/v1/session/ws-ticket',
        json={'subscribe': ['heartbeat']},
        headers={'Authorization': 'Bearer ' + token(scope=['state:read'])},
    )
    assert response.status_code == 200
    assert response.json()['data']['ws_url'].startswith(f'{ws_scheme}://testserver:8443/ws?ticket=')


def test_real_mode_rejects_development_credentials(monkeypatch):
    monkeypatch.setattr(config, 'ENGINE_ADAPTER', 'real')
    monkeypatch.setattr(config, 'JWT_SECRET', 'light-belt-dev-secret-change-in-production')
    monkeypatch.setattr(config, 'PAIRING_CODE', '123456')
    with pytest.raises(RuntimeError, match='LIGHT_BELT_JWT_SECRET'):
        config.validate_security_configuration()


def test_real_mode_accepts_explicit_credentials(monkeypatch):
    monkeypatch.setattr(config, 'ENGINE_ADAPTER', 'real')
    monkeypatch.setattr(config, 'JWT_SECRET', 'test-only-' + 'x' * 32)
    monkeypatch.setattr(config, 'PAIRING_CODE', 'test-only-code')
    config.validate_security_configuration()
