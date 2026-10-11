"""Bound request bodies before FastAPI's multipart parser consumes them."""

from tempfile import SpooledTemporaryFile

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = -1
        if declared < 0:
            await JSONResponse(
                {"error": {"code": "INVALID_REQUEST", "message": "Invalid Content-Length."}},
                status_code=400,
            )(scope, receive, send)
            return
        if declared > self.max_bytes:
            await self.reject(scope, receive, send)
            return
        with SpooledTemporaryFile(max_size=1024 * 1024) as body:
            total = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                total += len(chunk)
                if total > self.max_bytes:
                    await self.reject(scope, receive, send)
                    return
                body.write(chunk)
                if not message.get("more_body", False):
                    break
            body.seek(0)

            async def replay() -> Message:
                data = body.read(64 * 1024)
                return {"type": "http.request", "body": data, "more_body": body.tell() < total}

            await self.app(scope, replay, send)

    @staticmethod
    async def reject(scope: Scope, receive: Receive, send: Send) -> None:
        await JSONResponse(
            {
                "error": {
                    "code": "UPLOAD_LIMIT",
                    "message": "Request body exceeds configured size limit.",
                }
            },
            status_code=413,
        )(scope, receive, send)
