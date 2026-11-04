"""
依赖注入：统一鉴权拦截，相当于 Spring 的 HandlerInterceptor。
在需要鉴权的 router 上加 dependencies=[Depends(require_auth)] 即可。
"""

from fastapi import Request, HTTPException
from . import auth_manager


def require_auth(request: Request):
    token = auth_manager.extract_token(request)
    claims = auth_manager.verify_access_token(token) if token else None
    if claims is None:
        expired = bool(token and auth_manager.is_token_expired(token))
        raise HTTPException(401, detail={
            "code": "TOKEN_EXPIRED" if expired else "UNAUTHORIZED",
            "message": "Access token has expired" if expired else "Missing or invalid token",
        })

    scope = "state:read"
    if request.method != "GET" and request.url.path != "/api/v1/session/ws-ticket":
        resource = request.url.path.split("/")[3]
        scope = {
            "playback": "playback:write", "lights": "lights:write",
            "brightness": "lights:write", "effects": "effects:write",
            "audio": "audio:write", "scenes": "scenes:write",
        }[resource]
    if scope not in claims["scope"]:
        raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Insufficient token scope"})
    request.state.auth = claims
    return claims
