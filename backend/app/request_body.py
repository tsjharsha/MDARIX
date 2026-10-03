"""Read a request body with a hard size limit, without ever holding more than the limit in memory.

A declared Content-Length over the limit is refused at once; otherwise the body is streamed and reading stops as
soon as it passes the limit, so a chunked upload without a declared length cannot exhaust memory. (The reverse proxy
also caps request bodies; this is the application's own guard.)
"""

from __future__ import annotations

from fastapi import HTTPException, Request

WEBHOOK_LIMIT_BYTES = 1024 * 1024


async def read_limited(
    request: Request, limit: int, *, code: str = "FILE_TOO_LARGE", message: str | None = None
) -> bytes:
    too_large = HTTPException(
        413, detail={"code": code, "message": message or f"The upload is larger than {limit // (1024 * 1024)} MB."}
    )
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise too_large
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise too_large
        chunks.append(chunk)
    return b"".join(chunks)
