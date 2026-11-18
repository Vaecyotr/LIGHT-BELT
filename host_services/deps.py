"""共用 REST 依赖。接口兼容 0831 的直通行为。"""

from fastapi import Request


def require_auth(request: Request):
    pass
