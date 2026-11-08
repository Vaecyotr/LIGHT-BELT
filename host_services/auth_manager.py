"""
轻量认证模块：JWT 签发 / 校验 / 刷新，ws-ticket 管理。
相当于 Spring Security 的一个极简版。
"""

import time
import uuid
import jwt
from fastapi import Request
from .config import (
    JWT_SECRET, JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_SECONDS,
    REFRESH_TOKEN_EXPIRE_SECONDS,
    WS_TICKET_EXPIRE_SECONDS,
)

# ── 内存存储（生产可换 Redis） ──
_refresh_tokens: dict[str, dict] = {}          # refresh_token -> {client_id, scope, ...}
_ws_tickets: dict[str, dict] = {}              # ticket -> {session_id, subscribe, expires_at}

DEFAULT_SCOPE = ["state:read", "playback:write", "lights:write",
                 "effects:write", "audio:write", "scenes:write"]


def _now() -> int:
    return int(time.time())


def _prune_expired_entries(entries: dict[str, dict], now: int) -> None:
    for key, info in list(entries.items()):
        if now >= info["expires_at"]:
            del entries[key]


# ────────── Access Token ──────────

def create_access_token(client_id: str, scope: list[str]) -> tuple[str, int]:
    """返回 (token, expires_in)"""
    exp = _now() + ACCESS_TOKEN_EXPIRE_SECONDS
    payload = {"sub": client_id, "scope": scope, "exp": exp, "type": "access"}
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, ACCESS_TOKEN_EXPIRE_SECONDS


def verify_access_token(token: str) -> dict | None:
    """校验成功返回 payload，失败返回 None"""
    try:
        claims = jwt.decode(
            token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "scope", "exp", "type"]},
        )
        if claims["type"] != "access" or not isinstance(claims["sub"], str) or not claims["sub"]:
            return None
        if not isinstance(claims["scope"], list) or not all(isinstance(s, str) for s in claims["scope"]):
            return None
        return claims
    except jwt.ExpiredSignatureError:
        return None
    except (jwt.InvalidTokenError, TypeError, OverflowError):
        return None


def is_token_expired(token: str) -> bool:
    """区分 '过期' 和 '无效'"""
    try:
        jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return False
    except jwt.ExpiredSignatureError:
        return True
    except (jwt.InvalidTokenError, TypeError, OverflowError):
        return False


# ────────── Refresh Token ──────────

def create_refresh_token(client_id: str, scope: list[str]) -> str:
    now = _now()
    _prune_expired_entries(_refresh_tokens, now)
    token = f"rt_{uuid.uuid4().hex[:16]}"
    _refresh_tokens[token] = {
        "client_id": client_id,
        "scope": scope,
        "expires_at": now + REFRESH_TOKEN_EXPIRE_SECONDS,
    }
    return token


def consume_refresh_token(token: str) -> dict | None:
    """一次性消费，返回 {client_id, scope} 或 None"""
    info = _refresh_tokens.pop(token, None)
    if info is None:
        return None
    if _now() >= info["expires_at"]:
        return None
    return info


# ────────── Token Pair 便捷方法 ──────────

def issue_token_pair(client_id: str, scope: list[str] | None = None) -> dict:
    scope = list(DEFAULT_SCOPE if scope is None else scope)
    access, expires_in = create_access_token(client_id, scope)
    refresh = create_refresh_token(client_id, scope)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "scope": scope,
    }


# ────────── WS Ticket ──────────

def create_ws_ticket(subscribe: list[str], host: str = "0.0.0.0:8443", *, secure: bool = False) -> dict:
    now = _now()
    _prune_expired_entries(_ws_tickets, now)
    ticket = f"wst_{uuid.uuid4().hex[:16]}"
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    _ws_tickets[ticket] = {
        "session_id": session_id,
        "subscribe": subscribe,
        "expires_at": now + WS_TICKET_EXPIRE_SECONDS,
    }
    scheme = "wss" if secure else "ws"
    return {
        "ws_ticket": ticket,
        "session_id": session_id,
        "expires_in": WS_TICKET_EXPIRE_SECONDS,
        "ws_url": f"{scheme}://{host}/ws?ticket={ticket}",
    }


def consume_ws_ticket(ticket: str) -> dict | None:
    info = _ws_tickets.pop(ticket, None)
    if info is None:
        return None
    if _now() >= info["expires_at"]:
        return None
    return info


# ────────── 从 Request 提取并校验 token ──────────

def get_request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id", f"req-{uuid.uuid4().hex[:8]}")


def extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None
