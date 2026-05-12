"""
全局异常处理中间件

捕获所有未处理异常，返回统一 JSON 格式响应，
区分业务异常和系统异常，附加 request_id 便于追踪。
"""

import logging
import uuid
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

log = logging.getLogger(__name__)


class AppException(Exception):
    """
    业务异常基类

    用于主动抛出的业务逻辑错误，如参数校验失败、服务不可用等。
    异常会被全局中间件捕获并转换为统一 JSON 响应。
    """

    def __init__(self, code: int = 400, message: str = "业务异常") -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    全局异常处理中间件

    捕获请求处理过程中抛出的所有异常：
    - AppException（业务异常）：返回对应的业务错误码和消息
    - 其他 Exception（系统异常）：返回 500，记录完整堆栈
    所有响应均附带 request_id 字段，便于日志追踪。
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

        except AppException as exc:
            log.warning(
                "业务异常 [request_id=%s]: code=%d, message=%s",
                request_id,
                exc.code,
                exc.message,
            )
            return JSONResponse(
                status_code=exc.code,
                content={
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": request_id,
                },
                headers={"X-Request-ID": request_id},
            )

        except Exception as exc:
            log.exception(
                "系统异常 [request_id=%s]: %s",
                request_id,
                exc,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "code": 500,
                    "message": "服务内部错误，请稍后重试",
                    "request_id": request_id,
                },
                headers={"X-Request-ID": request_id},
            )
