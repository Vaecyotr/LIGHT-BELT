"""Authentication through the released REST and ticket entry points."""
import time

import jwt
import pytest
from fastapi.testclient import TestClient

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


@pytest.mark.parametrize('authorization', [None, 'Bearer invalid', 'Basic invalid'])
@pytest.mark.parametrize('path,body', [
    ('/brightness/set', {'brightness_scale': 0.17}),
    ('/session/ws-ticket', {'subscribe': ['heartbeat']}),
])
def test_anonymous_or_invalid_token_cannot_write_or_get_ticket(client, authorization, path, body):
    before = engine_adapter._state['brightness_scale']
    headers = {'X-Request-Id': 'auth-contract'}
    if authorization:
        headers['Authorization'] = authorization
    response = client.post('/api/v1' + path, json=body, headers=headers)
    assert response.status_code == 401
    assert response.json() == {
        'ok': False, 'request_id': 'auth-contract',
        'error': {'code': 'UNAUTHORIZED', 'message': 'Missing or invalid token'},
    }
    assert engine_adapter._state['brightness_scale'] == before


@pytest.mark.parametrize('claims,code', [
    ({'exp': int(time.time()) - 60}, 'TOKEN_EXPIRED'),
    ({'type': 'refresh'}, 'UNAUTHORIZED'),
    ({'scope': 'lights:write'}, 'UNAUTHORIZED'),
    ({'sub': ''}, 'UNAUTHORIZED'),
    ({'exp': []}, 'UNAUTHORIZED'),
    ({'exp': None}, 'UNAUTHORIZED'),
    ({'exp': float('inf')}, 'UNAUTHORIZED'),
])
def test_rejects_expired_wrong_type_or_malformed_claims(client, claims, code):
    response = client.get('/api/v1/state', headers={'Authorization': 'Bearer ' + token(**claims)})
    assert response.status_code == 401
    assert response.json()['error']['code'] == code


def test_missing_expiration_is_rejected(client):
    value = jwt.encode({'sub': 'client', 'scope': ['state:read'], 'type': 'access'}, auth_manager.JWT_SECRET, algorithm='HS256')
    response = client.get('/api/v1/state', headers={'Authorization': 'Bearer ' + value})
    assert response.status_code == 401


def test_read_scope_cannot_write_but_can_read_and_get_ticket(client):
    headers = {'Authorization': 'Bearer ' + token(scope=['state:read'])}
    assert client.get('/api/v1/state', headers=headers).status_code == 200
    denied = client.post('/api/v1/brightness/set', json={'brightness_scale': 0.17}, headers=headers)
    assert denied.status_code == 403
    assert denied.json()['error']['code'] == 'FORBIDDEN'
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
